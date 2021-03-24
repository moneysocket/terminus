#!/usr/bin/env python3
# Copyright (c) 2021 Moneysocket Developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php

import os
import json
import logging
import uuid
import time

from moneysocket.beacon.beacon import MoneysocketBeacon
from moneysocket.beacon.shared_seed import SharedSeed

from moneysocket.utl.bolt11 import Bolt11
from moneysocket.wad.wad import Wad


EMPTY_DB = {'account_name':  "",
            'account_uuid':  "",
            'wad':           None,
            'cap':           None,
            'pending':       {},
            'shared_seeds':  [],
            'beacons':       [],
            'receipts':      []}

class AccountDb(object):
    PERSIST_DIR = None

    def __init__(self, account_name):
        self.account_name = account_name
        AccountDb._make_dirs_exist(AccountDb.PERSIST_DIR)

        self.filename = os.path.join(AccountDb.PERSIST_DIR,
                                     "%s.json" % account_name)
        self.make_exist(self.filename)
        logging.info("using account db: %s" % self.filename)
        self.db = self.read_json(self.filename)
        self.db['wad'] = Wad.from_dict(self.db['wad'])
        self.db['cap'] = Wad.from_dict(self.db['cap'])
        for session in self.db['receipts']:
            for entry in session:
                if 'wad' in entry:
                    entry['wad'] = Wad.from_dict(entry['wad'])
        self.session_index = {}

    ###########################################################################

    @staticmethod
    def _make_dirs_exist(dir_path):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    @staticmethod
    def iter_account_dbs():
        if not os.path.exists(AccountDb.PERSIST_DIR):
            return
        for f in os.listdir(AccountDb.PERSIST_DIR):
            path = os.path.join(AccountDb.PERSIST_DIR, f)
            if path.endswith(".json"):
                account_name = f[:-5]
                yield AccountDb(account_name)

    ###########################################################################


    def make_exist(self, filename):
        if os.path.exists(filename):
            return
        logging.info("initializing new persitence db: %s" % self.filename)
        dir_path = os.path.dirname(filename)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        record = EMPTY_DB.copy()
        record['account_name'] = self.account_name
        record['account_uuid'] = str(uuid.uuid4())
        self.write_json(filename, record)

    def write_file(self, path, content):
        f = open(path, 'w')
        f.write(content)
        f.close()

    def write_json(self, path, info, quick=True):
        content = (json.dumps(info) if quick else
                   json.dumps(info, indent=1, sort_keys=True))
        self.write_file(path, content)

    def read_json(self, path):
        f = open(path, 'r')
        c = f.read()
        info = json.loads(c)
        f.close()
        return info

    def persist(self):
        self.write_json(self.filename, self.db)

    def depersist(self):
        os.remove(self.filename)

    ###########################################################################

    def add_beacon(self, beacon):
        beacon_str = beacon.to_bech32_str()
        self.db['beacons'].append(beacon_str)
        self.persist()

    def remove_beacon(self, beacon):
        beacon_str = beacon.to_bech32_str()
        self.db['beacons'].remove(beacon_str)
        self.persist()

    def add_shared_seed(self, shared_seed):
        shared_seed_str = str(shared_seed)
        self.db['shared_seeds'].append(shared_seed_str)
        self.persist()

    def remove_shared_seed(self, shared_seed):
        shared_seed_str = str(shared_seed)
        self.db['shared_seeds'].remove(shared_seed_str)
        self.persist()

    def add_pending(self, payment_hash, bolt11):
        self.db['pending'][payment_hash] = bolt11
        self.persist()

    def remove_pending(self, payment_hash):
        _ = self.db['pending'].pop(payment_hash, None)
        self.persist()

    ###########################################################################

    def get_name(self):
        return self.db['account_name']

    def get_account_uuid(self):
        return self.db['account_uuid']

    def iter_shared_seeds(self):
        for ss in self.db['shared_seeds']:
            yield SharedSeed.from_hex_string(ss)

    def get_shared_seeds(self):
        return list(self.iter_shared_seeds())

    def iter_beacons(self):
        for b in self.db['beacons']:
            yield MoneysocketBeacon.from_bech32_str(b)[0]

    def get_beacons(self):
        return list(self.iter_beacons())

    def iter_pending(self):
        for payment_hash, bolt11 in self.db['pending'].items():
            yield payment_hash, bolt11

    def get_pending(self):
        return list(self.iter_pending())

    ###########################################################################

    def set_wad(self, wad):
        self.db['wad'] = wad
        self.persist()

    def get_wad(self):
        return self.db['wad']

    def subtract_wad(self, wad):
        assert not wad['asset_stable'], "terminus is bitcoin only"
        current_wad = self.get_wad()
        new_wad = Wad.bitcoin(current_wad['msats'] - wad['msats'])
        self.set_wad(new_wad)

    def add_wad(self, wad):
        assert not wad['asset_stable'], "terminus is bitcoin only"
        current_wad = self.get_wad()
        new_wad = Wad.bitcoin(current_wad['msats'] + wad['msats'])
        self.set_wad(new_wad)

    ###########################################################################

    def set_cap(self, cap):
        self.db['cap'] = cap
        self.persist()

    def get_cap(self):
        return self.db['cap']

    ###########################################################################

    def get_receipts(self):
        return self.db['receipts']

    def new_receipt_session(self, shared_seed):
        session = []
        self.db['receipts'].insert(0, session)
        self.session_index[shared_seed] = session

    def add_receipt_entry(self, shared_seed, entry):
        if not shared_seed in self.session_index:
            logging.info("not keeping receipt: %s %s" % (shared_seed, entry))
            return
        session = self.session_index[shared_seed]
        session.insert(0, entry)
        # TODO - this is gonna be slow for big receipt logs
        # can fix by implementing append-to-end log
        self.persist()

    def end_receipt_session(self, shared_seed):
        assert shared_seed in self.session_index, "unknown shared seed?"
        del self.session_index[shared_seed]

    ###########################################################################

    def prune_expired_pending(self):
        for pending, bolt11 in list(self.iter_pending()):
            info = Bolt11.to_dict(bolt11)
            expire_timestamp = info['created_at'] + info['expiry']
            #print("%s expire: %f" % (expire_timestamp,
            #                          expire_timestamp - time.time()))
            if time.time() > expire_timestamp:
                del self.db['pending'][pending]

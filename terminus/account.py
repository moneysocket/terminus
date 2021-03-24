# Copyright (c) 2021 Moneysocket Developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php

import logging

from moneysocket.beacon.beacon import MoneysocketBeacon
from moneysocket.utl.bolt11 import Bolt11
from moneysocket.wad.wad import Wad

from terminus.account_db import AccountDb
from terminus.receipts import SocketSessionReceipt

class Account(object):
    def __init__(self, name, db=None):
        self.connection_attempts = {}
        self.db = db if db else AccountDb(name)

    @staticmethod
    def iter_persisted_accounts():
        for account_db in AccountDb.iter_account_dbs():
            yield Account(account_db.get_name(), db=account_db)

    def depersist(self):
        self.db.depersist()

    ##########################################################################

    def iter_summary_lines(self, locations):
        yield "\t%s: wad: %s " % (self.db.get_name(), self.db.get_wad())
        for beacon in self.db.get_beacons():
            beacon_str = beacon.to_bech32_str()
            yield "\t\toutgoing beacon: %s" % beacon_str
            ca = (self.connection_attempts[beacon_str] if beacon_str in
                  self.connection_attempts else "(none)")
            yield "\t\t\tconnection attempt: %s" % str(ca)
        for shared_seed in self.db.get_shared_seeds():
            beacon = MoneysocketBeacon(shared_seed)
            for location in locations:
                beacon.add_location(location)
            yield "\t\tincoming shared seed: %s" % str(shared_seed)
            yield "\t\t\tincoming beacon: %s" % beacon.to_bech32_str()

    def summary_string(self, locations):
        return "\n".join(self.iter_summary_lines(locations))

    def get_attributes(self, locations):
        outgoing_beacons = []
        for beacon in self.db.get_beacons():
            beacon_str = beacon.to_bech32_str()
            outgoing_beacons.append(beacon_str)
        incoming_beacons = []
        for shared_seed in self.db.get_shared_seeds():
            beacon = MoneysocketBeacon(shared_seed)
            for location in locations:
                beacon.add_location(location)
            beacon_str = beacon.to_bech32_str()
            incoming_beacons.append(beacon_str)
        connection_attempts = {b: str(ca) for b, ca in
                               self.connection_attempts.items()}
        info = {'name':                self.db.get_name(),
                'wad':                 self.db.get_wad(),
                'cap':                 self.db.get_cap(),
                'outgoing_beacons':    outgoing_beacons,
                'incoming_beacons':    incoming_beacons,
                'connection_attempts': connection_attempts}
        return info


    ##########################################################################

    def add_connection_attempt(self, beacon, connection_attempt):
        beacon_str = beacon.to_bech32_str()
        self.connection_attempts[beacon_str] = connection_attempt

    ##########################################################################

    def add_beacon(self, beacon):
        self.db.add_beacon(beacon)

    def remove_beacon(self, beacon):
        self.db.remove_beacon(beacon)
        _ = self.connection_attempts.pop(beacon.to_bech32_str(), None)

    def add_shared_seed(self, shared_seed):
        self.db.add_shared_seed(shared_seed)

    def remove_shared_seed(self, shared_seed):
        self.db.remove_shared_seed(shared_seed)

    def add_pending(self, payment_hash, bolt11):
        self.db.add_pending(payment_hash, bolt11)

    def remove_pending(self, payment_hash):
        self.db.remove_pending(payment_hash)

    def prune_expired_pending(self):
        self.db.prune_expired_pending()

    ##########################################################################

    def set_wad(self, wad):
        self.db.set_wad(wad)

    def set_cap(self, wad):
        self.db.set_cap(wad)

    def get_wad(self):
        return self.db.get_wad()

    def get_cap(self):
        return self.db.get_cap()

    def add_wad(self, wad):
        self.db.add_wad(wad)

    def subtract_wad(self, wad):
        self.db.subtract_wad(wad)

    ##########################################################################

    def get_name(self):
        return self.db.get_name()

    def get_pending(self):
        return self.db.get_pending()

    def get_shared_seeds(self):
        return self.db.get_shared_seeds()

    def get_beacons(self):
        return self.db.get_beacons()


    def get_all_shared_seeds(self):
        # the shared seeds for both listening and outgoing
        return (self.get_shared_seeds() +
                [b.get_shared_seed() for b in self.get_beacons()])


    def get_disconnected_beacons(self):
        dbs = []
        for beacon in self.get_beacons():
            beacon_str = beacon.to_bech32_str()
            if beacon_str not in self.connection_attempts:
                continue
            state = self.connection_attempts[beacon_str].get_state()
            if state != "disconnected":
                continue
            dbs.append(beacon)
        return dbs


    def get_provider_info(self):
        return {'ready':         True,
                'payer':         True,
                'payee':         True,
                'wad':           self.db.get_wad(),
                'account_uuid':  self.db.get_account_uuid()}

    ##########################################################################

    def get_receipts(self):
        return self.db.get_receipts()

    def new_session(self, shared_seed):
        self.db.new_receipt_session(shared_seed)
        entry = SocketSessionReceipt.session_start_entry()
        self.db.add_receipt_entry(shared_seed, entry)

    def session_invoice_requested(self, shared_seed, msats):
        wad = Wad.bitcoin(msats)
        entry = SocketSessionReceipt.invoice_request_entry(wad)
        self.db.add_receipt_entry(shared_seed, entry)

    def session_pay_requested(self, shared_seed, bolt11):
        msats = Bolt11.get_msats(bolt11)
        wad = Wad.bitcoin(msats)
        entry = SocketSessionReceipt.pay_request_entry(bolt11, wad)
        self.db.add_receipt_entry(shared_seed, entry)

    def session_preimage_notified(self, shared_seed, preimage, increment,
                                  msats):
        wad = Wad.bitcoin(msats)
        entry = SocketSessionReceipt.preimage_notified_entry(preimage,
                                                             increment, wad)
        self.db.add_receipt_entry(shared_seed, entry)


    def session_invoice_notified(self, shared_seed, bolt11):
        entry = SocketSessionReceipt.invoice_notified_entry(bolt11)
        self.db.add_receipt_entry(shared_seed, entry)

    def session_error_notified(self, shared_seed, error):
        entry = SocketSessionReceipt.err_notified_entry(error)
        self.db.add_receipt_entry(shared_seed, entry)

    def end_session(self, shared_seed):
        entry = SocketSessionReceipt.session_end_entry()
        self.db.add_receipt_entry(shared_seed, entry)
        self.db.end_receipt_session(shared_seed)

# Copyright (c) 2020 Jarret Dyrbye
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php

import uuid
import logging
import argparse
from configparser import ConfigParser

from txjsonrpc.web import jsonrpc
from twisted.web import server
from twisted.internet import reactor
from twisted.internet.task import LoopingCall

from moneysocket.utl.bolt11 import Bolt11

from moneysocket.beacon.beacon import MoneysocketBeacon
from moneysocket.beacon.shared_seed import SharedSeed
from moneysocket.stack.bidirectional_provider import (
    BidirectionalProviderStack)
from moneysocket.wad.wad import Wad

from terminus.rpc import TerminusRpc
from terminus.account import Account
from terminus.account_db import AccountDb
from terminus.directory import TerminusDirectory


MAX_BEACONS = 3


class TerminusApp(object):
    def __init__(self, config, lightning):
        self.config = config
        self.lightning = lightning
        self.lightning.register_paid_recv_cb(self.node_received_payment_cb)

        AccountDb.PERSIST_DIR = self.config['App']['AccountPersistDir']

        self.directory = TerminusDirectory()
        self.provider_stack = self.setup_provider_stack()

        TerminusRpc.APP = self

        self.connect_loop = None
        self.prune_loop = None

        self.local_seeds_connecting = set()
        self.local_seeds_connected = set()
        self.local_seeds_disconnected = set()
        self.local_seeds = set()

    ###########################################################################

    def setup_provider_stack(self):
        s = BidirectionalProviderStack(self.config)
        s.onannounce = self.on_announce
        s.onrevoke = self.on_revoke
        s.onstackevent = self.on_stack_event
        s.handleproviderinforequest = self.handle_provider_info_request
        s.handleinvoicerequest = self.handle_invoice_request
        s.handlepayrequest = self.handle_pay_request
        return s

    ###########################################################################

    def on_announce(self, transact_nexus):
        print("ON ANNOUNCE")
        ss = transact_nexus.get_shared_seed()
        if self.is_local_seed(ss):
            self.set_local_seed_connected(ss)

        account = self.directory.lookup_by_seed(ss)
        assert account is not None, "shared seed not from known account?"
        print("announce seed: %s" % ss)
        account.new_session(ss)

    def on_revoke(self, transact_nexus):
        ss = transact_nexus.get_shared_seed()
        if self.is_local_seed(ss):
            self.set_local_seed_disconnected(ss)

        account = self.directory.lookup_by_seed(ss)
        assert account is not None, "shared seed not from known account?"
        account.end_session(ss)

    def on_stack_event(self, layer_name, nexus, status):
        #print("layer: %s   status: %s" % (layer_name, status))
        pass

    ###########################################################################

    def set_local_seed_connecting(self, shared_seed):
        self.local_seeds.add(shared_seed)
        self.local_seeds_connecting.add(shared_seed)

    def set_local_seed_connected(self, shared_seed):
        self.local_seeds_disconnected.discard(shared_seed)
        self.local_seeds_connecting.discard(shared_seed)
        self.local_seeds_connected.add(shared_seed)

    def set_local_seed_disconnected(self, shared_seed):
        self.local_seeds_connecting.discard(shared_seed)
        self.local_seeds_connected.discard(shared_seed)
        self.local_seeds_disconnected.add(shared_seed)

    def clear_local_seed(self, shared_seed):
        self.local_seeds.discard(shared_seed)
        self.local_seeds_disconnected.discard(shared_seed)

    def is_local_seed(self, shared_seed):
        return shared_seed in self.local_seeds

    def is_local_seed_disconnected(self, shared_seed):
        return (self.is_local_seed(shared_seed) and
                shared_seed in self.local_seeds_disconnected)

    ###########################################################################

    def provider_error(self, shared_seeds, error_msg, request_reference_uuid):
        print("provider error: %s" % error_msg)
        self.provider_stack.notify_error(shared_seeds, error_msg,
                request_reference_uuid=request_reference_uuid)

    def handle_provider_info_request(self, shared_seed):
        account = self.directory.lookup_by_seed(shared_seed)
        assert account is not None, "shared seed not from known account?"
        return account.get_provider_info()


    def handle_pay_request(self, nexus, bolt11, request_uuid):
        shared_seed = nexus.get_shared_seed()
        account = self.directory.lookup_by_seed(shared_seed)
        assert account is not None, "shared seed not from known account?"

        shared_seeds = account.get_all_shared_seeds()

        msats = Bolt11.get_msats(bolt11)
        if (msats is None):
            err = "bolt11 does not specify amount",
            account.session_error_notified(shared_seed, err)
            self.provider_error(shared_seeds, err, request_uuid)
            return

        wad = account.get_wad()
        if msats > wad['msats']:
            # TODO - estimate routing fees?
            err = "insufficent account balance"
            account.session_error_notified(shared_seed, err)
            self.provider_error(shared_seeds, err, request_uuid)
            return

        account.session_pay_requested(shared_seed, bolt11)

        preimage, paid_msats, err = self.lightning.pay_invoice(bolt11,
                                                               request_uuid)
        if err:
            account.session_error_notified(shared_seed, err)
            self.provider_error(shared_seeds, err, request_uuid)
            return

        paid_wad = Wad.bitcoin(paid_msats)

        if (paid_msats > wad['msats']):
            # routing fees could have exceeded balance... need to figure
            # out the best way to deal with this
            paid_msats = wad['msats']
        account.subtract_wad(paid_wad)

        # TODO new pay preimage message to propagate fees
        self.provider_stack.notify_preimage(shared_seeds, preimage,
                                            request_uuid)
        for ss in shared_seeds:
            account.session_preimage_notified(ss, preimage, False,
                                              paid_msats)

    def handle_invoice_request(self, nexus, msats, request_uuid):
        shared_seed = nexus.get_shared_seed()
        account = self.directory.lookup_by_seed(shared_seed)
        assert account is not None, "shared seed not from known account?"
        shared_seeds = account.get_all_shared_seeds()
        account.session_invoice_requested(shared_seed, msats)


        wad = account.get_wad()
        cap = account.get_cap()
        if cap['msats'] != 0 and (msats + wad['msats'] > cap['msats']):
            # TODO 0 track pending incoming?
            err = "account cap exceeded"
            account.session_error_notified(shared_seed, err)
            self.provider_error(shared_seeds, err, request_uuid)
            return

        bolt11, err = self.lightning.get_invoice(msats)
        if err:
            account.session_error_notified(shared_seed, err)
            self.provider_error(shared_seeds, err, request_uuid)
            return

        payment_hash = Bolt11.get_payment_hash(bolt11)
        account.add_pending(payment_hash, bolt11)
        for ss in shared_seeds:
            account.session_invoice_notified(shared_seed, bolt11)
        self.directory.reindex_account(account)
        self.provider_stack.notify_invoice(shared_seeds, bolt11, request_uuid)


    ###########################################################################

    def node_received_payment_cb(self, preimage, msats):
        received_wad = Wad.bitcoin(msats)
        logging.info("node received payment: %s %s" % (preimage, received_wad))

        payment_hash = Bolt11.preimage_to_payment_hash(preimage)
        # find accounts with this payment_hash
        accounts = self.directory.lookup_by_payment_hash(payment_hash)

        if len(accounts) > 1:
            logging.error("can't deal with more than one account with "
                          "a preimage collision yet")
            # TODO deal with this somehow - feed preimage back into lightning
            # node to claim any pending htlcs?
            return

        if len(accounts) == 0:
            logging.error("incoming payment not known")
            return

        account = list(accounts)[0]
        shared_seeds = account.get_all_shared_seeds()
        account.remove_pending(payment_hash)
        account.add_wad(received_wad)
        self.provider_stack.notify_preimage(shared_seeds, preimage, None)
        for ss in shared_seeds:
            account.session_preimage_notified(ss, preimage, True, msats)

    ##########################################################################

    def _getinfo_dict(self):
        locations = self.provider_stack.get_listen_locations()
        accounts = self.directory.get_account_list()
        info = {'accounts': [a.get_attributes(locations) for a in accounts]}
        return info

    def getinfo(self, args):
        return self._getinfo_dict()

    ##########################################################################

    def getaccountinfo(self, args):
        account_set = set(args.accounts)
        if len(account_set) == 0:
            return {'success': True, 'accounts': []}
        all_accounts = self._getinfo_dict()['accounts']
        accounts = [a for a in all_accounts if a['name'] in account_set]
        return {'success': True, 'accounts': accounts}

    ##########################################################################

    def getaccountreceipts(self, args):
        name = args.account
        account = self.directory.lookup_by_name(name)
        if not account:
            return {'success': False, 'error': "*** unknown account: %s" % name}
        receipts = account.get_receipts()
        return {'success':  True,
                'name':     name,
                'receipts': receipts}

    ##########################################################################

    def gen_account_name(self, name):
        i = 0
        def account_name(n):
            return "%s-%d" % (name, n)
        while self.directory.lookup_by_name(account_name(i)) is not None:
            i += 1
        return account_name(i)


    def create(self, args):
        wad, err = Wad.bitcoin_from_msat_string(args.msatoshis)
        if err:
            return {'success': False, "error": "*** " + err}

        if args.cap == "none":
            cap = Wad.bitcoin(0)
        else:
            cap, err = Wad.bitcoin_from_msat_string(args.cap)
            if err:
                return {'success': False, "error": "*** " + err}
        name = self.gen_account_name(args.account_name)
        account = Account(name)
        account.set_wad(wad)
        account.set_cap(cap)
        self.directory.add_account(account)
        return {'success': True, 'name': name, "wad": wad, 'cap': cap}

    ##########################################################################

    def rm(self, args):
        name = args.account
        account = self.directory.lookup_by_name(name)
        if not account:
            return {'success': False,
                    'error': "*** unknown account: %s" % name}

        if len(account.get_all_shared_seeds()) > 0:
            return {'success': False,
                    'error': "*** still has connections: %s" % name}

        self.directory.remove_account(account)
        account.depersist()
        return {'success': True, "name": name}

    ##########################################################################

    def connect(self, args):
        name = args.account
        account = self.directory.lookup_by_name(name)
        if not account:
            return {'success': False,
                    'error': "*** unknown account: %s" % name}

        beacon_str = args.beacon
        beacon, err = MoneysocketBeacon.from_bech32_str(beacon_str)
        if err:
            return {'success': False,
                    'error': "*** could not decode beacon: %s" % err}
        location = beacon.locations[0]
        if location.to_dict()['type'] != "WebSocket":
            return {'success': False,
                    'error': "*** can't connect to beacon location"}
        if len(account.get_beacons()) == MAX_BEACONS:
            return {'success': False,
                    'error': "*** max %s beacons per account" % MAX_BEACONS}

        shared_seed = beacon.shared_seed
        connection_attempt = self.provider_stack.connect(location, shared_seed)
        account.add_connection_attempt(beacon, connection_attempt)
        account.add_beacon(beacon)
        self.directory.reindex_account(account)
        return {'success': True, "name": name, "location": str(location)}


    ##########################################################################

    def listen(self, args):
        name = args.account
        account = self.directory.lookup_by_name(name)
        if not account:
            return {'success': False,
                    'error': "*** unknown account: %s" % name}

        shared_seed_str = args.shared_seed
        if shared_seed_str:
            shared_seed = SharedSeed.from_hex_str(shared_seed_str)
            if not shared_seed:
                return {'success': False,
                        'error': ("*** could not understand shared seed: %s" %
                                  args.shared_seed)}
            beacon = MoneysocketBeacon(shared_seed)
        else:
            # generate a shared_seed
            beacon = MoneysocketBeacon()
            shared_seed = beacon.shared_seed

        # generate new beacon
        # location is the provider_stack's incoming websocket
        beacon.locations = self.provider_stack.get_listen_locations()
        account.add_shared_seed(shared_seed)
        # register shared seed with local listener
        self.provider_stack.local_connect(shared_seed)
        self.set_local_seed_connecting(shared_seed)
        self.directory.reindex_account(account)
        return {'success': True, "name": name,
                "beacon": beacon.to_bech32_str()}

    ##########################################################################

    def clear(self, args):
        name = args.account
        account = self.directory.lookup_by_name(name)
        if not account:
            return {'success': False,
                    'error': "*** unknown account: %s" % name}

        # TODO - cli for more precice removal of connection?

        # outgoing websocket layer -> find all that have this shared seed
        # initiate close to disconnect
        for beacon in account.get_beacons():
            shared_seed = beacon.get_shared_seed()
            self.provider_stack.disconnect(shared_seed)
            account.remove_beacon(beacon)

        # deregister from local layer
        for shared_seed in account.get_shared_seeds():
            self.provider_stack.local_disconnect(shared_seed)
            self.clear_local_seed(shared_seed)
            account.remove_shared_seed(shared_seed)
        self.directory.reindex_account(account)
        return {'success': True, "name": name}

    ##########################################################################

    def load_persisted(self):
        for account in Account.iter_persisted_accounts():
            self.directory.add_account(account)
            for beacon in account.get_beacons():
                location = beacon.locations[0]
                assert location.to_dict()['type'] == "WebSocket"
                shared_seed = beacon.shared_seed
                connection_attempt = self.provider_stack.connect(location,
                                                                 shared_seed)
                account.add_connection_attempt(beacon, connection_attempt)
            for shared_seed in account.get_shared_seeds():
                self.provider_stack.local_connect(shared_seed)
                self.set_local_seed_connecting(shared_seed)

    ##########################################################################

    def retry_connections(self):
        for account in self.directory.iter_accounts():
            disconnected_beacons = account.get_disconnected_beacons()
            for beacon in disconnected_beacons:
                #logging.error("disconnected: %s" % beacon.to_bech32_str())
                location = beacon.locations[0]
                assert location.to_dict()['type'] == "WebSocket"
                shared_seed = beacon.shared_seed
                connection_attempt = self.provider_stack.connect(location,
                                                                 shared_seed)
                account.add_connection_attempt(beacon, connection_attempt)
        for shared_seed in self.local_seeds:
            if self.is_local_seed_disconnected(shared_seed):
                self.provider_stack.local_connect(shared_seed)
                self.set_local_seed_connecting(shared_seed)

    def prune_expired_pending(self):
        for account in self.directory.iter_accounts():
            account.prune_expired_pending()

    ##########################################################################

    def run_app(self):
        rpc_interface = self.config['Rpc']['BindHost']
        rpc_port = int(self.config['Rpc']['BindPort'])
        logging.info("listening on %s:%d" % (rpc_interface, rpc_port))
        reactor.listenTCP(rpc_port, server.Site(TerminusRpc()),
                          interface=rpc_interface)

        self.load_persisted()

        self.provider_stack.listen()

        self.connect_loop = LoopingCall(self.retry_connections)
        self.connect_loop.start(5, now=False)

        self.prune_loop = LoopingCall(self.prune_expired_pending)
        self.prune_loop.start(3, now=False)

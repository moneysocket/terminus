# Copyright (c) 2021 Jarret Dyrbye
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php

import time
import uuid

from moneysocket.wad.wad import Wad


class SocketSessionReceipt():
    @staticmethod
    def new_session(shared_seeed):
        u = uuid.uuid4()
        time = time.time()
        session = {'type':         'socket_session',
                   'receipt_uuid': u,
                   'time':         time,
                   'shared_seed':  shared_seed,
                   'entries':      []}
        return session

    @staticmethod
    def session_start_entry():
        entry = {'type':        'session_start',
                 'time':        time.time(),
                }
        return entry

    @staticmethod
    def invoice_request_entry(wad):
        entry = {'type':         'invoice_request',
                 'time':         time.time(),
                 'wad':          wad}
        return entry

    @staticmethod
    def pay_request_entry(bolt11, wad):
        entry = {'type':         'pay_request',
                 'time':         time.time(),
                 'wad':          wad,
                 'bolt11':       bolt11}
        return entry

    @staticmethod
    def preimage_notified_entry(preimage, increment, wad):
        entry = {'type':                   'preimage_notified',
                 'time':                   time.time(),
                 'preimage':               preimage,
                 'increment':              increment,
                 'wad':                    wad}
        return entry

    @staticmethod
    def invoice_notified_entry(bolt11):
        entry = {'type':                   'invoice_notified',
                 'time':                   time.time(),
                 'bolt11':                 bolt11}
        return entry

    @staticmethod
    def err_notified_entry(err):
        entry = {'type':  'error_notified',
                 'time':  time.time(),
                 'error': err}
        return entry

    @staticmethod
    def session_end_entry():
        entry = {'type': 'session_end',
                 'time':  time.time()}
        return entry


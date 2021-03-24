# Copyright (c) 2020 Moneysocket Developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php

import json
from txjsonrpc.web import jsonrpc
from terminus.cmd_parse import TerminusCmdParse

class TerminusRpc(jsonrpc.JSONRPC):
    APP = None

    def exec_cmd(self, name, *args):
        parser = TerminusCmdParse.get_parser(app=self.APP)
        #print("args: %s" % args)
        #print("name: %s" % name)
        toparse = [name]
        for a in args:
            #print("arg: %s " % str(a))
            if isinstance(a, str):
                #print("1")
                toparse.extend(a)
            elif isinstance(a, list):
                #print("2")
                toparse += a
            elif isinstance(a, tuple):
                #print("3")
                for t in a:
                    #print("4")
                    if isinstance(t, list):
                        toparse += t
                    else:
                        toparse += [t]
        #toparse.extend(list(args))
        #print("toparse: %s" % toparse)
        parsed = parser.parse_args(toparse)
        # TODO - handle failed parse natively
        #print("parsed: %s" % parsed)
        info = parsed.cmd_func(parsed)
        return json.dumps(info, indent=1, sort_keys=True)

    def jsonrpc_getinfo(self, *args):
        return self.exec_cmd('getinfo', args)

    def jsonrpc_getaccountinfo(self, *args):
        return self.exec_cmd('getaccountinfo', args)

    def jsonrpc_getaccountreceipts(self, *args):
        return self.exec_cmd('getaccountreceipts', args)

    def jsonrpc_create(self, *args):
        return self.exec_cmd('create', args)

    def jsonrpc_rm(self, *args):
        return self.exec_cmd('rm', args)

    def jsonrpc_connect(self, *args):
        return self.exec_cmd('connect', args)

    def jsonrpc_listen(self, *args):
        return self.exec_cmd('listen', args)

    def jsonrpc_clear(self, *args):
        return self.exec_cmd('clear', args)

# Copyright (c) 2020 Jarret Dyrbye
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
            if isinstance(a, str):
                toparse.extend(a)
            if isinstance(a, list):
                toparse += a
            if isinstance(a, tuple):
                for t in a:
                    toparse += t
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
        print(args)
        return self.exec_cmd('getaccountinfo', args)

    def jsonrpc_create(self, argv):
        return self.exec_cmd('create', argv)

    def jsonrpc_rm(self, argv):
        return self.exec_cmd('rm', argv)

    def jsonrpc_connect(self, argv):
        return self.exec_cmd('connect', argv)

    def jsonrpc_listen(self, argv):
        return self.exec_cmd('listen', argv)

    def jsonrpc_clear(self, argv):
        return self.exec_cmd('clear', argv)

Moneysocket Terminus
--------------------------

The Terminus is an application that provides an interface to the Lightning Network proper. It serves WebSocket connections that are Moneysocket protocol providers connected to accounts tracked by the application.

To receive satoshis, bolt11s are obtained from the node and when they are paid, the preimage value is notified via the relevant Moneysocket connetions.

To send satooshis, a bolt11 that is passed in via the Moneysocket connection is passed on to the node to execute the payment, subject to the account having sufficient balance.

The provider connections can be either incoming websocket connections or outgoing connections to a [relay](https://github.com/moneysocket/js-moneysocket) to rendezvous with a Consumer or directly to a Consumer that is capable of listening on its own.

Disclaimer!
-----

Moneysocket is still new, under development and is Reckless with your money. Use this stuff at your own risk.

Node Support
--------------------------

This Terminus application can run with either LND or C-Lightning. For C-Lightning, it runs as a [plugin](https://github.com/ElementsProject/lightning/blob/master/doc/PLUGINS.md) using [pyln-client](https://github.com/ElementsProject/lightning/tree/master/contrib/pyln-client). For LND, it runs as a standalone process using [lnd-grpc](https://pypi.org/project/lnd-grpc/) to connect to LND.

Once they are running, the code logic difference between these two setups is minimal. If desired, adapting to other LN node implementations is not viewed as particularly difficult.

Dependencies
------------------------------------------------------------------------

This depends on [py-moneysocket](https://github.com/moneysocket/py-moneysocket)

`$ pip3 install https://github.com/moneysocket/py-moneysocket`

to install the library and libraries dependencies into your environment.

Additionally, this application has a few dependencies documented in [requirements.txt](requirements.txt). These can be installed to your environment via:

`$ pip3 install -r requirements.txt`


Installing For C-Lightning
------------------------------------------------------------------------

The `terminus-plugin` executable along with the `terminus/` directory of source files must be placed in the plugin directory of a C-Lightning instance.

The script [install-terminus-plugin](install-terminus-plugin) will copy it from the checked-out repository to the plugin directory specified (or to a default ~/.lightning/plugins/ directory). E.g

`$ git clone https://github.com/moneysocket/terminus`
`$ cd terminus`
`$ install-terminus-plugin --plugin-dir /path/to/.lightning/plugins`


When C-Lightning is restarted it will execute this plugin, however it will need to be able to find the configuration file. By default it will look in the `.lightning/` directory under the folder corresponding to the network. The default configuration file is `moneysocket-terminus.conf`, but it can be specified differently by setting the `moneysocket_terminus_config` value of the C-Lightning configuration.

There is an example configuration provided [here](config/terminus-cl.conf) which can be copied to the default location and filename like so:

`$ cp config/terminus-cl.conf ~/.lightning/bitcoin/moneysocket-terminus.conf`

Reloading C-Lightning Plugin
------------------------------------------------------------------------

During development, it is useful to replace and restart the plugin without having to stop the running C-Lightning instance. This requires a few verbose commands to the C-Lightning RPC interface so to make it convenient, [a script to automate those steps](reload-terminus-plugin) is provided here:

`$ ./reload-terminus-plugin`

This script similarly defaults to `~/.lightning/plugins` as the plugin directory, but a different directory can be specified with the `--plugin-dir` flag.

This will stop the plugin, replace what is in the plugin directory with what is in the repository file structure and then start the plugin.


Installing For LND
------------------------------------------------------------------------

The `terminus-lnd` executable will start the Terminus application as a standalone program. For configuration it will look to `~/.lnd/moneysocket-terminus.conf` by default, but a different location can be specified with the `--config` flag.

To copy the example config to the default location:

`$ cp config/terminus-lnd.conf ~/.lnd/moneysocket-terminus.conf`

The configuration file must match the details for enabling access to the GRPC interface of your LND node.

Once the configuration is set, simply running the executable will start the Terminus:

`$ ./terminus-lnd`


CLI Interface
------------------------------------------------------------------------

The `terminus-cli` executable can be called in a similar way to `bitcoin-cli`, `lightning-cli` and/or `lncli` executables which you are likely already familiar with.

The executable connects to the Terminus process via a JSON-RPC interface. By default, it will look in the default locations for configuration details for making the connection. Using the `--config` flag can manually specify a different config.

To get a listing of available commands, the `help` command will print the usage:

`$ ./terminus-cli help`

To get a summary of the current state, the `getinfo` command will produce a summary:

`$ ./terminus-cli getinfo`



Setting up and using an account
------------------------------------------------------------------------

To create a new account with a balance of a value of satoshis, use the `create` command with a msatoshi integer value or a satoshi value with `sat` or `sats` as a postfix on the integer:

```
$ ./terminus-cli create 10000sat
created account: account-0  wad: ₿ 10000.000 sat
$ ./terminus-cli getinfo
ACCOUNTS:
        account-0: wad: ₿ 10000.000 sat
$ ./terminus-cli create 1234567
created account: account-1  wad: ₿ 1234.567 sat
$ ./terminus-cli getinfo
ACCOUNTS:
        account-0: wad: ₿ 10000.000 sat
        account-1: wad: ₿ 1234.567sat
```

The account can either listen for incoming Moneysocket connections, or can make an outgoing connection to a relay or a server that can recieve that connection.

To listen at bind and port settings specified in the config with a randomly-generated `shared_seed` value, use the `listen` command:

```
$ ./terminus-cli listen account-0
listening: account-0 to moneysocket1lcqqzqdm8nlqqqgph5g8dhtkmzmq7upekrqvdv3kcfechlsqqyquzg87qqqsr0cpq8lqqqgpcvfsqzf3xgmjuvpwxqhrzqgpqqpq8lftry7vdcps
$ ./terminus-cli getinfo
ACCOUNTS:
        account-0: wad: ₿ 10000.000 sat
                incoming shared seed: 76dd76d8b60f7039b0c0c6b236c2738b
                        incoming beacon: moneysocket1lcqqzqdm8nlqqqgph5g8dhtkmzmq7upekrqvdv3kcfechlsqqyquzg87qqqsr0cpq8lqqqgpcvfsqzf3xgmjuvpwxqhrzqgpqqpq8lftry7vdcps
        account-1: wad: ₿ 1234.567 sat
```

To connect ougoing to a particular beacon, use the `connect` command:

```
$ ./terminus-cli connect account-1 moneysocket1lcqqzqdm8hlqqqgph5g9r6k32wp6cvzcf4xzqjvma2vtalsqqyquzg07qqqsr0cpq8lqqqgpcv2qqynjv4kxz7fwwdhkx6m9wshx6mmwv4ustwjl28
connected: account-1 to wss://relay.socket.money:443
$ ./terminus-cli getinfo
ACCOUNTS:
        account-0: wad: ₿ 10000.000 sat
                incoming shared seed: 76dd76d8b60f7039b0c0c6b236c2738b
                        incoming beacon: moneysocket1lcqqzqdm8nlqqqgph5g8dhtkmzmq7upekrqvdv3kcfechlsqqyquzg87qqqsr0cpq8lqqqgpcvfsqzf3xgmjuvpwxqhrzqgpqqpq8lftry7vdcps
        account-1: wad: ₿ 1234.567 sat
                outgoing beacon: moneysocket1lcqqzqdm8hlqqqgph5g9r6k32wp6cvzcf4xzqjvma2vtalsqqyquzg07qqqsr0cpq8lqqqgpcv2qqynjv4kxz7fwwdhkx6m9wshx6mmwv4ustwjl28
                        connection attempt: <connected to relay.socket.money:443>
```

To clear listening or outgoing connections settings from an account the `clear` command can be used.

`$ ./terminus-cli clear <account>`

If an account is cleared - meaning it doesn't have any connections set up it can be removed via the `rm` command:

`$ ./terminus-cli rm <account>`

Project Links
------------------------------------------------------------------------

- [Homepage](https://socket.money).
- [Twitter](https://twitter.com/moneysocket)
- [Telegram](https://t.me/moneysocket)
- [Donate](https://socket.money/#donate)

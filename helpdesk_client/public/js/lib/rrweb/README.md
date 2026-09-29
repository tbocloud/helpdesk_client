# rrweb (vendored)

Browser (UMD) builds of [rrweb](https://github.com/rrweb-io/rrweb) used by
`public/js/session_replay.js`. They are vendored so customer servers do not
need `yarn install`, and they are loaded lazily with a script tag only when
Session Replay is enabled in HDS Support Settings — they are not part of the
esbuild bundle.

| File | npm package | Version | Global |
| --- | --- | --- | --- |
| `record.min.js` | `@rrweb/record` (`umd/record.min.js`) | 2.1.6 | `rrwebRecord` |
| `rrweb-plugin-console-record.min.js` | `@rrweb/rrweb-plugin-console-record` (`umd/rrweb-plugin-console-record.min.js`) | 2.1.6 | `rrwebPluginConsoleRecord` |
| `rrweb-plugin-network-record.min.js` | `@rrweb/rrweb-plugin-network-record` (`umd/rrweb-plugin-network-record.min.js`) | 2.1.6 | `rrwebPluginNetworkRecord` |

The files are byte-identical to the npm tarballs
(`https://registry.npmjs.org/@rrweb/<name>/-/<name>-2.1.6.tgz`). To upgrade,
download the new tarballs, copy the same `umd/*.min.js` files over these and
update the version above.

Licensed under the MIT License — see `LICENSE`.

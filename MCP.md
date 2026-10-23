# Cartouche MCP

The build agent calls this. The CLI is still there. This process does not start CLOSER or CodeRadar, and it does not rewrite a release.

One local stdio process. No port. stdout is the protocol, so the server does not print the watch there.

From the `CARTOUCHE` folder:

```sh
python3 -m cartouche.mcp
```

or `sh cartouche-mcp.sh` from that same folder. Both need Python 3.10 or newer. There is no extra package.

A client entry is the script, or `python3` with args `-m cartouche.mcp` and the `CARTOUCHE` folder on `PYTHONPATH`. No arguments. The target is not in the entry. `ct_watch` names it.

## Tools

| Tool | Call |
|---|---|
| `ct_watch` | `spec`, `contract`, `target`. Binds one build. |
| `ct_look` | no arguments. One scan of that build. |
| `ct_stop` | no arguments. Reports what is still open, then drops the bind. The process stays up. |
| `ct_hold` | `spec`, `contract`, `target`. The same comparison, once, with no watch. |

`spec` is the request JSON. `contract` is the release JSON from `cartouche release`. `target` is one Python file or a directory of them. Absolute paths. A relative path is resolved from the directory the server was started in.

`ct_watch` refuses a missing spec, a missing release, a release that is not signed off, and a spec whose hash is no longer the release. A different target while one is bound answers `ct_stop first`.

`ct_look` returns `issues`. Each row has `file`, `function`, `lines`, `fault`, and `directive`. A directory is one scan: a function counts in whichever file defines it. A file that does not parse has fault `SYNTAX`, and the rest of the tree is still scored. If the target is not written yet, `waiting` is true and `issues` is empty. That is not a miss.

`ct_stop` returns `stopped`, `sealed`, and the same `issues`. `sealed` false means the build does not match the lock. The release file is not written.

Until `ct_watch`, `ct_look` answers `no target — call ct_watch with the spec, the release, and the build path`.

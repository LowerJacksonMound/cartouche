# Cartouche MCP

The build agent calls this. The CLI is still there. This process does not start CLOSER or CodeRadar, and it does not rewrite a release.

One local stdio process. No port. The page (`cartouche page`) is a separate command; the server never opens one. stdout is the protocol, so the server does not print the watch there.

From the `CARTOUCHE` folder:

```sh
python3 -m cartouche.mcp
```

or `sh cartouche-mcp.sh` from that same folder. Both need Python 3.9 or newer. There is no extra package.

A client entry is the script, or `python3` with args `-m cartouche.mcp` and the `CARTOUCHE` folder on `PYTHONPATH`. No arguments. The target is not in the entry. `ct_watch` names it.

## Tools

| Tool | Call |
|---|---|
| `ct_watch` | `spec`, `contract`, `target`. Binds one build. |
| `ct_look` | no arguments. One scan of that build. |
| `ct_stop` | no arguments. Reports what is still open, then drops the bind. The process stays up. |
| `ct_hold` | `spec`, `contract`, `target`. The same comparison, once, with no watch. |
| `ct_chart` | `chart`, `out`. Checks a chart the agent drafted from the person's plain request; saves it to `out` only if it passes, else lists the problems. |
| `ct_wanted` | `spec`. Every line a path reaches: function, edge case or not, sign-off status, candidates so far, and its drop folder `incoming/<function>/`. Reserves each line's shelf slot and offers any clip already dropped. |
| `ct_search` | `searches` (one per line: `source`, `query`, optional `spoken`, `limit`), optional `creative_commons`. Runs them in parallel. `spoken` reads each YouTube hit's subtitles and names the seconds where those words are said. Downloads no video. |
| `ct_offer` | `spec`, `clips` (each: `phrase`, `source`, `url`, `start`, `seconds` up to 20, `why`). Cuts every candidate in parallel into `candidates/` beside the spec and records its source and licence. |
| `ct_withdraw` | `spec`, `withdraw` (each: `phrase`, `id`). Takes back offered candidates that do not fit. Refused for a signed-off line. |
| `ct_render` | `spec`, optional `phrases` (lines as `ct_wanted` gives them; default every line with no candidate), optional `voice`. Renders a stand-in, the line spoken by macOS `say` over a title card, into the line's incoming folder and offers it at once. For a line no footage says, or whose found clips are poor. macOS only. |

Rendered clips skip search: write them into a line's `incoming/<function>/` folder (sidecar `<clip>.json`: why, licence, title, author). The page offers them on its next poll.

The gather tools are the only AI step. No tool can choose, sign off, or release a clip: the person does that on
`cartouche page --request <spec>`, which runs Cartouche's own `view`, `approve` and `release`. After sign-off no AI
takes part: the lock, the scan and the watch are plain code. Sources are `youtube` (Creative Commons only unless
`creative_commons` is false), `archive` (Internet Archive), `pexels` (needs `PEXELS_API_KEY`), and `file`. YouTube
needs `yt-dlp` and `ffmpeg`. Set `CARTOUCHE_YTDLP_COOKIES` to `browser:chrome` or a cookies.txt path to send your
YouTube login, which avoids most rate limits; it is off by default.

`spec` is the request JSON. `contract` is the release JSON from `cartouche release`. `target` is one Python file or a directory of them. Absolute paths. A relative path is resolved from the directory the server was started in.

`ct_watch` refuses a missing spec, a missing release, a release that is not signed off, and a spec whose hash is no longer the release. A different target while one is bound answers `ct_stop first`.

`ct_look` returns `issues`. Each row has `file`, `function`, `lines`, `fault`, and `directive`. A directory is one scan: a function counts in whichever file defines it. A file that does not parse has fault `SYNTAX`, and the rest of the tree is still scored. If the target is not written yet, `waiting` is true and `issues` is empty. That is not a miss.

`ct_stop` returns `stopped`, `sealed`, and the same `issues`. `sealed` false means the build does not match the lock. The release file is not written.

Until `ct_watch`, `ct_look` answers `no target — call ct_watch with the spec, the release, and the build path`.

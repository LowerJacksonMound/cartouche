# Cartouche

Cartouche holds the intent of a build as one hash, the master cartouche, and tells you whether an agent's
Python tree still matches it. The intent is built line by line: a developer views and signs off each line
of the request's decision chart, each sign-off writes one signal lock, and the hash of those locks is the
lock the build is judged against. Cartouche reports what does not match. It does not fix, rewrite, or
re-lock.

## How it works

1. Bring a request: a decision chart where every box is a line of an interaction and every arrow is a
   decision (`spec.json`). Cartouche ships no chart.
2. `fetch` walks the chart and lists every box a path can reach. An unreached box is not fetched.
3. `fill` puts one entry on the dictionary shelf per distinct line, marks it `pending`, and reserves a clip
   path. An edge case gets its own clip even when the words are the same.
4. `view` records the bytes of a clip the developer looked at. A missing or empty file is not a viewing.
5. `approve` signs the clip off and writes the line's signal lock
   (`sha256("{token_id}::{phrase}::{primitive_fxn}")[:16]`). If the bytes changed since the viewing the
   sign-off is refused.
6. `release` reads the shelf. Every path has to be covered. An open path exits 2 and the contract names
   the lines that block. A covered shelf exits 0 and writes `build_input.json`, whose `cartouche_sha256` is
   the master cartouche: the hash of the signed locks. It is locked before any agent writes and does not
   move for the whole build.
7. The build agent calls `ct_watch`, then `ct_look` after each write, then `ct_stop` when it is done. Each
   issue names the file, the function, the lines, and the fault: one of the five defect words, `template`,
   `locked`, `hazy`, `missing`, `skew` (`SYNTAX` for a file that does not parse), with the scanner's codes
   in `detail`. You hand the issue to the build agent. Cartouche does not send it.
8. `ct_stop` answers `sealed: true` only when the tree is the locked intent: residual `0.00` and every
   required edge present. Anything else is `sealed: false` with the open issues, and the release is not
   rewritten.
9. A later request on the same interaction reuses an approved line by its normalized phrase: `fill`
   returns it as `reused` and writes no second entry. That is the dictionary.

## The four MCP tools

One local stdio process, `cartouche-mcp.sh`. No port. No extra package. Python 3.10 or newer.

| Tool | One line | Refuses |
|---|---|---|
| `ct_watch(spec, contract, target)` | Binds one build: the request, the release, and one Python file or a directory. Writes neither file. | a missing spec, a missing release, a release that is not signed off (`the request is not signed off`), a spec whose hash is no longer the release, and a second target while one is bound (`ct_stop first`). |
| `ct_look()` | One scan of the bound build. Returns `issues`; each row has `file`, `function`, `lines`, `fault` (one of `template`, `locked`, `hazy`, `missing`, `skew`), `detail`, `directive`. A directory is one scan. A file that does not parse is `SYNTAX` and the rest is still scored. A target not written yet is `waiting: true`, not an issue. | any call before `ct_watch` (`no target — call ct_watch with the spec, the release, and the build path`). |
| `ct_stop()` | Ends the watch, returns `stopped`, `sealed`, and the open `issues`, and drops the bind. The release is not written. The process stays up. | nothing; with nothing bound it says nothing is being watched. |
| `ct_hold(spec, contract, target)` | The same comparison, once, with no bind. | the same as `ct_watch`. |

The CLI has the same comparison as `cartouche hold`, and `cartouche start` / `cartouche stop` for a
watch driven from a terminal. The build agent uses the MCP tools.

## What it does not do

- It does not fix code. An issue goes back to the build agent; Cartouche reports it and keeps watching.
- It does not rewrite the lock, the release, the shelf, or the spec to match the code.
- It does not approve a line, invent a clip, or render a montage.
- It does not start, stop, or talk to CLOSER or CodeRadar. They are the running environment the lock
  sits in; see INTENT.md.
- It does not judge code that is not Python. Python targets only.
- It is built and tested on macOS first.

## Status

Release candidate, 2026-10-23. Self-test: `cartouche selftest`, or the plants under `plants/run_all.sh`.
The unit tests are `python3 -m unittest discover -s cartouche/tests` from this folder (99 tests on 2026-10-23).

## Install

`QUICKSTART.md` walks the fixture spec end to end. `install_cartouche_mcp.sh` registers the MCP server
with Claude Code at user scope; `--print` shows the command without running it.

## Law docs

- `INTENT.md`: what is locked, what the lock is for, release, start and stop, hold, sequence, macro,
  request, phrase, signs, image.
- `MCP.md`: the stdio server, the four tools, their arguments and refusals.
- `BROLL.md`: the dictionary shelf: seek, fill, check-off, reuse.

## License

PolyForm Noncommercial 1.0.0: read, run and modify freely for noncommercial purposes; commercial use needs a license from the author. See LICENSE.

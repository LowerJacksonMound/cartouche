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
   issue names the file, the function, the lines, and the fault: one of the four defect words, `template`,
   `locked`, `missing`, `skew` (`SYNTAX` for a file that does not parse), with the scanner's codes
   in `detail`. You hand the issue to the build agent. Cartouche does not send it.
8. `ct_stop` answers `sealed: true` only when the tree is the locked intent: residual `0.00` and every
   required edge present. Anything else is `sealed: false` with the open issues, and the release is not
   rewritten.
9. A later request on the same interaction reuses an approved line by its normalized phrase: `fill`
   returns it as `reused` and writes no second entry. That is the dictionary.

## The four MCP tools

One local stdio process, `cartouche-mcp.sh`. No port. No extra package. Python 3.9 or newer: the `python3` macOS ships (3.9.6) is enough, nothing to install. The gather step also needs
`ffmpeg` (cutting clips) and, for YouTube, `yt-dlp`: `brew install ffmpeg yt-dlp`. The lock, the scan and the watch need neither.

| Tool | One line | Refuses |
|---|---|---|
| `ct_watch(spec, contract, target)` | Binds one build: the request, the release, and one Python file or a directory. Writes neither file. | a missing spec, a missing release, a release that is not signed off (`the request is not signed off`), a spec whose hash is no longer the release, and a second target while one is bound (`ct_stop first`). |
| `ct_look()` | One scan of the bound build. Returns `issues`; each row has `file`, `function`, `lines`, `fault` (one of `template`, `locked`, `missing`, `skew`), `detail`, `directive`. A directory is one scan. A file that does not parse is `SYNTAX` and the rest is still scored. A target not written yet is `waiting: true`, not an issue. | any call before `ct_watch` (`no target — call ct_watch with the spec, the release, and the build path`). |
| `ct_stop()` | Ends the watch, returns `stopped`, `sealed`, and the open `issues`, and drops the bind. The release is not written. The process stays up. | nothing; with nothing bound it says nothing is being watched. |
| `ct_hold(spec, contract, target)` | The same comparison, once, with no bind. | the same as `ct_watch`. |

The CLI has the same comparison as `cartouche hold`, and `cartouche start` / `cartouche stop` for a
watch driven from a terminal. The build agent uses the MCP tools.

## Gather and sign off

The chart holds only the app's own lines, the ones you sign off. What the other party might say is not yours to
sign: each of their possible lines rides on a branch as `heard`, leading to the reaction you sign. The lock covers
those lines too, so changing what the other party is expected to say after release breaks the lock. A chart without
`heard` hashes exactly as before. On the page, each of your lines shows what they might say next, and the path player
plays whole conversations: your line, their line, your reaction. Voiced lines of theirs go in `heard/` beside the spec.

You give the agent a plain app request. The agent, in Claude Code, drafts the chart (every line of the interaction,
the function each stands for, every decision and edge case) and Cartouche checks it (`ct_chart`). For each line the
agent searches for footage (`ct_search`; with `spoken` it reads YouTube subtitles to find where the line is said) and
offers a few candidate clips (`ct_offer`). Cartouche cuts and stores them with their source and licence.

Then you open the page:

    cartouche page --request requests/appointment/spec.json

Each line shows its candidates. A clip's sign-off button stays off until you have watched it through. Signing off
copies that clip into the line's slot and runs Cartouche's own `view` and `approve` on those bytes. When every path is
signed, you release, and the page becomes the watch: the cartouche fills sign by sign while the build is written.

Clips can also be rendered instead of searched. Every line has a drop folder, `incoming/<function>/`, beside the
spec (each holds a LINE.txt naming its line). Drop rendered clips there, your own, a subagent's scenes, or a video
generator's output, with an optional `<clip>.json` giving why, licence, title and author. The page offers each one as
a candidate on its next poll, so search can be skipped for those lines.

The agent cannot choose, sign off or release. After your sign-off there is no AI anywhere: the lock, the scan and the
watch are plain code. Check each candidate's licence on the page before you publish footage that uses it.

## The signs

The signs are real Egyptian hieroglyphs, by Gardiner number (Q3 the stool, D21 the mouth, G5 the falcon, and
so on). That is on purpose. A sign from a dead script has no modern meaning, so nobody reading the cartouche
can bring their own idea of what a function should do back into the build. The outlines come from Noto Sans
Egyptian Hieroglyphs (SIL Open Font License; see THIRD_PARTY.md).

## The live page

`cartouche page` shows the cartouche filling in while the build is written. Each function's sign is drawn
at that function's fidelity from the same scan `ct_look` runs: a ghost outline until it is written, then
filled when it seals. Its fault word stands beside it. A seal lights when every sign in its ring is sealed,
and the ring closes in green. It stays up for the whole build.

    cartouche page --session session.json          # follow a `cartouche start` watch
    cartouche page spec.json build_input.json build/agent.py   # look at the build, for an MCP watch

It serves `http://127.0.0.1:8790/` (`--port` to change it) and binds localhost only. It writes nothing:
not the build, not the request, not the release. The MCP server still opens no port; the page is its own
command.

## What it does not do

- It does not fix code. An issue goes back to the build agent; Cartouche reports it and keeps watching.
- It does not rewrite the lock, the release, the shelf, or the spec to match the code.
- It does not approve a line, invent a clip, or render a montage. The live page only shows; it has no
  buttons and writes nothing.
- It does not start, stop, or talk to CLOSER or CodeRadar. They are the running environment the lock
  sits in; see INTENT.md.
- It does not judge code that is not Python. Python targets only.
- It is built and tested on macOS first.

## Status

Release candidate, 2026-10-23. Self-test: `cartouche selftest`, or the plants under `plants/run_all.sh`.
The unit tests are `python3 -m unittest discover -s cartouche/tests` from this folder (133 tests on 2026-11-02).

## Install

`QUICKSTART.md` walks the fixture spec end to end. `install_cartouche_mcp.sh` registers the MCP server
with Claude Code at user scope; `--print` shows the command without running it.

## Law docs

- `INTENT.md`: what is locked, what the lock is for, release, start and stop, hold, sequence, macro,
  request, phrase, signs, image.
- `MCP.md`: the stdio server, the nine tools (four for the watch, five for gather), their arguments and refusals.
- `BROLL.md`: the dictionary shelf: seek, fill, check-off, reuse.

## License

PolyForm Noncommercial 1.0.0: read, run and modify freely for noncommercial purposes; commercial use needs a license from the author. See LICENSE.

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
   issue names the file, the function, the lines, and the fault: one of the three defect words,
   `locked`, `missing`, `skew` (`SYNTAX` for a file that does not parse), with the scanner's codes
   in `detail`. A hollow or fake-shaped body and wrong parameters are CLOSER's to refuse; Cartouche reports missing, skew and locked. You hand the issue to the build agent. Cartouche does not send it.
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
| `ct_look()` | One scan of the bound build. Returns `issues`; each row has `file`, `function`, `lines`, `fault` (one of `locked`, `missing`, `skew`), `detail`, `directive`. A directory is one scan. A file that does not parse is `SYNTAX` and the rest is still scored. A target not written yet is `waiting: true`, not an issue. | any call before `ct_watch` (`no target — call ct_watch with the spec, the release, and the build path`). |
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
There is no unit test suite (Ian, 2026-11-11): the check is `python3 -m cartouche.selftest`, which runs the source end to end and the plants.

Multi-file edges are the newest part of the scanner (2026-11-03) and the likeliest first bug report ("my app with
`import as` or `getattr` does not seal"). Three rules decide them; each commit message states the rule:

- [b6a4bbe](https://github.com/LowerJacksonMound/cartouche/commit/b6a4bbe): a sequence or loop owner must be defined
  in the caller's own file; a test that sequences both ends does not satisfy the edge.
- [1874ec5](https://github.com/LowerJacksonMound/cartouche/commit/1874ec5): a module-level alias (`from m import f as g`,
  or `g = m.f`) names the function; a call through it is the edge.
- [d79c9aa](https://github.com/LowerJacksonMound/cartouche/commit/d79c9aa): `getattr(module_or_self, "literal")(...)`
  resolves to that function and is the edge; a computed name is not followed and reports `skew`.

A report should carry the `summary` line, the lock sha, and the `ct_look` rows (see Reporting a problem).

## Install

Nothing to install beyond Python 3.9. Clone or copy this folder, then either

    pip install -e .                      # gives you the `cartouche` command used in this README

or, with no install at all, run every `cartouche ...` line here as `python3 -m cartouche ...` with
`PYTHONPATH` set to this folder (that is how `QUICKSTART.md` runs it):

    export PYTHONPATH=/absolute/path/to/MCP-CARTOUCHE
    python3 -m cartouche page --request /absolute/path/to/spec.json

To drive it from Claude Code, register the MCP server once, at user scope:

    bash install_cartouche_mcp.sh         # --print shows the `claude mcp add-json` line without running it

A Claude Code session starts that server once and does not reload it. After any edit to this folder, run
`/mcp` in the session and reconnect `cartouche` (or start a new session) before trusting a verdict.
The same holds after `git pull`: the session's server is still the old code until you reconnect.

The page: `python3 -m cartouche page --request SPEC` prints `page=http://127.0.0.1:8790/` and serves it until you
stop it; `--port N` moves it. Every `ct_watch`, `ct_look`, `ct_hold` and `ct_stop` answer carries a one-sentence
`summary` ("Sealed: every locked line and edge is in build.", "Not sealed: 2 issues: ...") beside the rows.

Replacing a release: if the chart is saved again after release (another `ct_chart` on the same spec), the page
sets the old lock aside as `build_input.<sha8>.json`, keeps every signature, and goes back to the release step;
press release once more and the new lock is written. `ct_watch` on the old lock refuses with `locked`.

`QUICKSTART.md` walks the fixture spec end to end.

## Law docs

- `INTENT.md`: what is locked, what the lock is for, release, start and stop, hold, sequence, macro,
  request, phrase, signs, image.
- `MCP.md`: the stdio server, the ten tools (four for the watch, six for gather), their arguments and refusals.
- `BROLL.md`: the dictionary shelf: seek, fill, check-off, reuse.

## Reporting a problem

Open an issue on this repository. A precise report carries the `summary` line, the lock sha, and the `ct_look` rows
(file, function, lines, fault, detail). A security problem goes through SECURITY.md, not an issue.
Issues are welcome; this project does not take outside code.
Issues are read; there is no schedule for replies or fixes. Verified 2026-11-05 on a fresh clone on an Apple Silicon Mac under Python 3.9 (macOS's own), 3.13 and 3.14; other Macs are untested.

## License

PolyForm Noncommercial 1.0.0: read, run and modify freely for noncommercial purposes; commercial use needs a license
from the author (LowerJacksonMound@proton.me). See LICENSE.

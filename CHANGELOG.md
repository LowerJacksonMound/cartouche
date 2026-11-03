# Changelog

All notable changes to Cartouche are recorded here. The format follows Keep a Changelog; versions follow 0.x semantics, where a minor bump may break.

## [Unreleased]

### Changed
- `ct_search` (YouTube) over-fetches three ids per hit wanted, drops any title written in another script before
  fetching anything, reads subtitles for the rest, and returns the hits best spoken moment first. The unsubtitled
  trail behind them in YouTube's order, each marked. Measured on one query: 30 listed, 1 dropped by title, the ten
  returned led by the five that carry English subtitles; before, four of ten. A search takes about three times as
  long. The gather instructions no longer ask the agent to check the title's language.

## [0.2.0] - 2026-10-23

### Added
- Gather, the one AI step: MCP tools `ct_chart` (check and save a chart drafted from a plain request), `ct_wanted`
  (the lines to fill), `ct_search` (YouTube, Internet Archive, Pexels; parallel; `spoken` finds where a line is said
  in YouTube subtitles, read in one yt-dlp batch), `ct_offer` (cut candidates in parallel into `candidates/`, with
  source and licence). The MCP instructions hold the gather prompt: at most two search rounds.
- `cartouche page --request SPEC`: one page for the whole run. Watch each candidate through, sign one off per line
  (Cartouche's own `view` + `approve` on those bytes), release (`release`), then watch the build. No tool can sign off.
- Drop folders: `incoming/<function>/` per line. Rendered clips dropped there (the person's, a subagent's, a
  video generator's) are offered on the page's next poll, each once, with an optional sidecar for licence and why.
- The sign-off page follows the decision tree: lines in walk order (main path first, each alternative beside the
  line it replaces, each reply under the line it answers), and a path player plays every root-to-end path.
- `heard` on a branch: the other party's line that leads to our reaction. Only our lines are signed; theirs are
  gathered, voiced (`heard/`), shown and played, and covered by the lock (only in charts that use it; every other
  lock is unchanged). Once a chart uses `heard`, every fork must name it.
- `ct_withdraw`: the agent takes back candidates that do not fit (never on a signed-off line).
- Twenty more real Gardiner signs (A1 … Y5), used only when a chart has more than nine functions; charts of nine or
  fewer keep exactly the signs and lock they had.
- YouTube cuts prefer plain HTTPS H.264 streams (HLS streams could not be cut by section).
- `CARTOUCHE_YTDLP_COOKIES` (off by default) sends a YouTube login to yt-dlp.
- `cartouche page`: the live cartouche on 127.0.0.1. Each function's sign is drawn at that function's
  fidelity from the same scan as `ct_look`, a seal lights when its ring is sealed, and the fault word stands
  beside each sign. It follows a `cartouche start` session (`--session`) or looks at a build directly
  (spec, release, target) for an MCP watch. It writes nothing. The MCP server still opens no port.
- `cartouche start --interval SECONDS` (default 1).
- The session file gains `state`, `signs` (one row per function: sign, signed line, fidelity, fault, lines),
  `signs_sealed`, `signs_total`, and `svg`.
- `cartouche selftest` runs `start` and `page` as a user would and checks the page fills sign by sign.

### Changed
- Sealed or not (owner ruling 2026-10-24): `hazy` is retired. Four defect words: template, locked, missing, skew.
  A constant return or a swallowing bare except is `template`; locked parameters that are gone are `missing`; a
  short body is let through as a note (`SHORT_BODY`), never a fault. Signs draw sealed or not, no partial blur.
  The plant `counterfeit/hazy` is now `counterfeit/constant_return`. No lock moves.
- The seventeen signs are now real Egyptian hieroglyphs, drawn from the glyph outlines of Noto Sans
  Egyptian Hieroglyphs under their Gardiner numbers (see THIRD_PARTY.md). A sign from a dead script carries
  no modern meaning, so a reader cannot bring their own idea of a function back into the build. An unwritten
  or missing sign draws as its outline; a written one fills. Ids and names are unchanged.

### Unchanged
- No rule, hash, lock or MCP tool changed. The lock hashes each sign's id and name, not its drawing. The fixture release still hashes to `cd093843aefe1778…`.

## [0.1.0] - 2026-10-23

### Added
- Intent lock: fetch, fill, view, approve, release, lock, resolve, and the master cartouche hash.
- MCP server (stdio) with four tools: `ct_watch`, `ct_look`, `ct_stop`, `ct_hold`.
- Scan faults as the five defect words of INTENT.md (`template`, `locked`, `hazy`, `missing`, `skew`) plus `SYNTAX`, with the scanner's codes under `detail`.
- `cartouche selftest`: unit tests, end-to-end fetch-to-seal pass, every MCP tool over real stdio, plants, and a no-stray-files proof.
- `plants/`: honest cases that must seal and counterfeit cases that must be refused, with `run_all.sh`.
- README, QUICKSTART, `install_cartouche_mcp.sh`, RELEASE_CHECKLIST with two dated passes.

### Known limits
- Python targets only. macOS first. Runs on Python 3.9 or newer; selftest PASS on 3.9.6 (Apple), 3.10, 3.13, 3.14.
- Reports; does not fix.

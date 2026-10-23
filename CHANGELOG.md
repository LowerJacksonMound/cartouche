# Changelog

All notable changes to Cartouche are recorded here. The format follows Keep a Changelog; versions follow 0.x semantics, where a minor bump may break.

## [0.1.0] - 2026-10-23

### Added
- Intent lock: fetch, fill, view, approve, release, lock, resolve, and the master cartouche hash.
- MCP server (stdio) with four tools: `ct_watch`, `ct_look`, `ct_stop`, `ct_hold`.
- Scan faults as the five defect words of INTENT.md (`template`, `locked`, `hazy`, `missing`, `skew`) plus `SYNTAX`, with the scanner's codes under `detail`.
- `cartouche selftest`: unit tests, end-to-end fetch-to-seal pass, every MCP tool over real stdio, plants, and a no-stray-files proof.
- `plants/`: honest cases that must seal and counterfeit cases that must be refused, with `run_all.sh`.
- README, QUICKSTART, `install_cartouche_mcp.sh`, RELEASE_CHECKLIST with two dated passes.

### Known limits
- Python targets only. macOS first.
- Reports; does not fix.

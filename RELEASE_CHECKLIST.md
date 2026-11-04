# RELEASE CHECKLIST

Cartouche's release bar, in the same shape as CLOSER_THE_APP/RELEASE_CHECKLIST.md. A release is the tree
that passes every line below on the day, recorded as a dated pass. Nothing about a rule, a hash, a lock,
a CLI subcommand or an MCP tool changes in a release pass; a pass proves and packages what runs.

## Quiet run (2026-11-03)

- [x] Quiet run: three new apps of different kinds, fresh session, both gates, zero code changes to this tree. "Release" means first that the app works and runs as expected (Closer accepts, the app is run by hand), and second the signed form (Cartouche sealed). Names and dates here; ledger in ~/ct-live/QUIET_RUN.md.
      2026-11-03 passed: counter, connect4, wordfreq through both gates with zero edits to either tree (count 3, Cartouche d950b28,
      Closer 657c2c3); count 4 the same day cold-ran the release fixes, four of four (24655f3 / 2a5196a); connect4 re-ticketed
      and accepted under the owner rule (b6a4bbe). The ledger is kept privately by the owner.

## Any change

- [ ] `python3 -m cartouche selftest` prints `cartouche: selftest PASS` and exits 0. It runs the unit tests,
      the fetch → fill → view → approve → release pass on the fixture spec, every MCP tool over the real stdio
      server as a client would, the plants, and proves no file outside its temp dir was added or changed.
- [ ] `plants/run_all.sh` prints `plants: N PASS / 0 FAIL`. Every honest plant seals; every counterfeit plant is
      refused or reported. A changed scan rule has a plant that fails without the change and passes with it.
- [ ] `python3 -m unittest discover -s cartouche/tests -p "test_*.py"` is `OK`.
- [ ] The lock does not move: the fixture release hashes to `cd093843aefe1778…` before and after the pass.
- [ ] Law docs (INTENT.md, MCP.md, BROLL.md) match the code, or the mismatch is listed under "Known gaps"
      below with a date. Law docs are not rewritten to fit the code.
- [ ] README.md and QUICKSTART.md commands run as pasted; `install_cartouche_mcp.sh --print` prints the
      registration line for this tree's absolute path.
- [ ] `cartouche-mcp.sh` is executable and `python3 -m cartouche.mcp` answers `tools/list` with exactly
      `ct_watch ct_look ct_stop ct_hold ct_chart ct_wanted ct_search ct_offer ct_withdraw ct_render` (0.1.0 had the first four; 0.2.0 the next five).

## Scan or lock change

- [ ] The change was a proposal first, with a plant that splits.
- [ ] Signer yes.
- [ ] INTENT.md updated in the same pass; a new fault word went into MCP.md's `fault` list.

## Ruling 2026-10-24: sealed or not

Owner's ruling: a sign is sealed or it is not; hazy is retired. A constant return or a swallowing bare except is
`template`; locked parameters that are gone are `missing`; a short body alone is let through (recorded as a note,
never a fault). The law text in INTENT.md was amended by the owner's ruling, not to fit the code. The plant
`counterfeit/hazy` is now `counterfeit/constant_return`, expecting `template`. The lock does not move.

- [x] 2026-10-24 pass under the ruling: `plants/run_all.sh` 9 PASS / 0 FAIL; unit tests 133 OK; `cartouche selftest`
      PASS on Python 3.9 and 3.14; fixture lock `cd093843aefe1778` unmoved. A live build of a 15-function agent behind
      Closer ended sealed 15 of 15 and accepted (film take 4); the same code was 14 of 15 hazy before the ruling.

## Pass 2026-10-23 (release candidate; self-test, plants, front door and install added; no rule, hash, lock, CLI or tool changed)

- [x] `cartouche selftest`: `cartouche: selftest PASS`, exit 0. 21 checks ok, including sealed agent `sealed=true issues=0`,
      hazy `DEGENERATE_CONSTANT_RETURN`, shifted-edge `TOPOLOGY_BREAK`, esprit `MISSING_FUNCTION` + `HOLLOW_STUB`, split tree
      with an unparsed file `SYNTAX`, unsigned release refused, drifted spec refused, missing release refused, release bytes
      untouched, tree unchanged. Run twice (author agent, then the signer's own run); identical.
- [x] `plants/run_all.sh`: `plants: 9 PASS / 0 FAIL` (honest: sealed, orchestrated, split_tree; counterfeit: hazy, skew,
      missing, template, locked, unsigned). Negative control: a misfiled plant gives `9 PASS / 2 FAIL`, exit 1; a sabotaged
      honest plant makes selftest print `FAIL honest/sealed` and `cartouche: selftest FAIL`.
- [x] Unit tests: `Ran 91 tests` / `OK`, Python 3.13.
- [x] Lock unmoved: `cd093843aefe1778` before and after.
- [x] README.md, QUICKSTART.md, install_cartouche_mcp.sh added. Every QUICKSTART command run in a fresh dir under 3.13 and
      3.14; outputs pasted are real. `--print` verified; real registration not run (the signer registers).
- [x] `cartouche-mcp.sh` made executable (`chmod +x`, content untouched) so the registration shape in MCP.md works.
- [x] Whole-tree hash identical before and after the pass's runs.
- [x] `MCP-CARTOUCHE/` is the canonical tree. `Desktop/CARTOUCHE/` is an older copy with film drafts; not released.

### Known gaps, law docs vs code (recorded 2026-10-23): CLOSED the same day, code followed docs

Owner's ruling: the five defect words are necessary; each, applied to a cartouche symbol, says how the function
it represents is incorrect. So the code moved to the docs on all eight; the law docs were not edited (md5 unchanged).

1. Every issue row's `fault` is exactly one of `template`, `locked`, `hazy`, `missing`, `skew` (or `SYNTAX` for a file
   that does not parse). The scanner's codes stay on the row as `detail`. Vocabulary and mapping live in
   `project_symbol.py`, the same constants the sign image uses. A unit test asserts the set is closed.
2. One `fault` per row; several codes may sit in `detail`.
3. `cartouche fetch spec.json` works without `-o` (writes `<stem>.fetch.json` beside the spec).
4. An open release exits 2 and prints `block: <line>` per blocking line.
5. An unreleased release prints no `cartouche_sha256` on stdout.
6. A line approved under this request is `approved`; `reused` only when it pre-existed under another request
   (additive entry field `domain_id`).
7. `fetch` finds clips at `library/<interaction>/<digest>.mp4` as well as the declared path; `--base` / `--node`
   documented in CLI help.
8. Every MCP answer carries the resolved `target`.

An unreleased contract is a refusal, not a scan, and keeps `fault: UNRELEASED`; `locked` is reserved for a request
edited after release.

## Pass 2026-10-23, second (code follows docs on the eight gaps; no rule, hash, lock or tool changed)

- [x] Unit tests: `Ran 99 tests` / `OK` (8 new, incl. the closed fault-set test).
- [x] `cartouche selftest`: `cartouche: selftest PASS`, exit 0 (3 checks added: fetch without -o, fetch finds shelf clips,
      open-release stdout).
- [x] `plants/run_all.sh`: `plants: 9 PASS / 0 FAIL`; every counterfeit plant now expects a five-word fault with the
      scanner code under `details`.
- [x] Lock unmoved: `cd093843aefe1778ba3e8a43c951fb3fc2531ca7ff8632898c3d278acaf0c6f5` before and after.
- [x] `tools/list` over stdio: exactly `ct_watch ct_look ct_stop ct_hold`.
- [x] INTENT.md / MCP.md / BROLL.md md5 unchanged.
- [x] README.md / QUICKSTART.md re-run; pasted outputs are real.
- [x] Signer's own run of all three commands: identical results.
- [x] Registered with Claude Code (`install_cartouche_mcp.sh`), user scope.

## Pass 2026-10-23, third (rung 0 of the release ladder: version control, license, packaging, fresh-Mac rehearsal)

- [x] `git init`; first commit of 81 files. Excluded by `.gitignore`: `__pycache__`, `*.zip` (CARTOUCHE.zip), `.DS_Store`, `.env`, `*.fetch.json`, `/library/`, `/scratch/`.
- [x] Secret scan before the first commit: no keys, tokens or passwords. Personal absolute paths removed from QUICKSTART (now `$CT`).
- [x] `LICENSE`: PolyForm Noncommercial 1.0.0, canonical SPDX text, licensor block. README carries the license paragraph.
- [x] `pyproject.toml` (`cartouche-mcp` 0.1.0, scripts `cartouche` and `cartouche-mcp`, no dependencies) and `CHANGELOG.md` 0.1.0.
- [x] Python floor set to 3.9 from measurement: `cartouche selftest` PASS on Apple 3.9.6, 3.10, 3.13, 3.14. Wrapper refuses below 3.9 with a message; install script and docs say 3.9.
- [x] Fresh-Mac rehearsal: clone of the committed tree, `env -i`, PATH limited to Apple's `/usr/bin:/bin`, empty HOME, no brew/uv. `python3` = 3.9.6. `selftest PASS`, `plants 9 PASS / 0 FAIL`, `install --print` prints the registration line, wrapper answers `tools/list` over stdio with the four tools. Nothing had to be installed.
- [ ] Still to do for rung 0: the same rehearsal in a real second macOS user account, by a person following README only (rung 2 tester does this).

## Pass 2026-10-23, rung 1

- [x] Private repo https://github.com/LowerJacksonMound/cartouche, branch `main`, tag `v0.1.0`, prerelease published with install, verify and known-limits notes. A clone of the tag passes `selftest` on Apple python3.

## Pass 2026-10-23, rung 3 (prepared)

- [x] Full-history scan clean (secrets, personal paths). Author email: 6 commits carry the GitHub no-reply address, the rest the owner's GitHub email; the owner ruled 2026-11-04 that it stays. Repository READY for public: the flip itself is the owner's action (`gh repo edit --visibility public --accept-visibility-change-consequences`), recorded below when done. Rung 2 (invited testers) skipped by decision: the prerelease label and issue tracker take its place.

## Pass 2026-11-04, rung 1 and rung 3 (docs only; no rule, hash, lock, CLI or tool changed)

- [x] Tag `v0.2.0` re-pointed for the last time while private, to the head that carries README "Reporting a problem",
      SECURITY.md (contact LowerJacksonMound@proton.me) and the CHANGELOG fold. Draft prerelease "Cartouche 0.2.0" on GitHub.
- [x] Clean-clone rehearsal, 2026-11-04: clone into a scratch folder, HOME empty, QUICKSTART steps 1-6, hold and the live
      page followed as pasted; every output line identical, lock `cd093843aefe1778…`; `selftest` PASS; plants 9 PASS / 0 FAIL.
- [x] Repo settings: wiki, discussions, projects off; issues on. Private vulnerability reporting is offered by GitHub only
      on a public repo: first action after the flip.
- [ ] The friend's Mac run is post-flip; a finding is 0.2.1, no tag moves.

"""One command that proves the build. Nothing here changes a rule, a hash, or a tool.

`cartouche selftest` runs the unit tests, then walks the fixture request through the real
CLI (fetch, fill, view, approve, release) and the real stdio MCP server (ct_watch, ct_look,
ct_stop, ct_hold) as a client would, over JSON-RPC, in one temp dir. It then runs every plant
under `plants/`. One line per check. The last line is `cartouche: selftest PASS` with exit 0,
or the first failure is named and the exit is 1.

`python3 -m cartouche.selftest --plants plants` runs only the plant folder. `plants/run_all.sh`
calls that. A plant is a folder with Python files and an `expect.json`; `honest/` plants must
seal, `counterfeit/` plants must be refused or reported with the faults they name: one of the
five words (template, locked, hazy, missing, skew) per row, with the scanner's codes in `detail`.

Everything written lands under one temp dir, which is removed at the end. The unit tests are
run with TMPDIR inside it so their own scratch dirs land there too.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "cartouche" / "tests" / "fixture"
PLANTS = ROOT / "plants"
INTERACTION = "phone_conversation"

Say = Callable[[str, str], None]


class Failure(Exception):
    """The first check that did not hold. Its text is the whole report."""


def _env(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TMPDIR"] = str(tmp)
    return env


def cli(args: list[str], tmp: Path) -> subprocess.CompletedProcess[str]:
    """Run `python -m cartouche ...` from inside the temp dir, as a user would."""

    return subprocess.run(
        [sys.executable, "-m", "cartouche", *args],
        cwd=tmp,
        env=_env(tmp),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _need(proc: subprocess.CompletedProcess[str], code: int, what: str) -> str:
    out = (proc.stdout or "").strip()
    if proc.returncode != code:
        err = (proc.stderr or "").strip().splitlines()
        tail = err[-1] if err else out.splitlines()[-1] if out else "no output"
        raise Failure(f"{what}: exit {proc.returncode}, expected {code}: {tail}")
    return out


# ---- the release ----------------------------------------------------------------


def build_release(tmp: Path, say: Say) -> dict[str, Path]:
    """fetch -> fill -> view -> approve every line -> release. Returns the paths a client needs.

    `spec` and `contract` are the signed pair. `unsigned` is a release of an empty shelf.
    `drifted` is the same spec with one phrase changed, so it no longer hashes to `contract`.
    """

    work = tmp / "request"
    work.mkdir(parents=True, exist_ok=True)
    spec = work / "spec.json"
    shutil.copyfile(FIXTURE / "domain_spec.json", spec)
    shelf = work / "clip_dictionary.json"
    contract = work / "build_input.json"

    out = _need(cli(["fetch", str(spec)], tmp), 0, "fetch")
    if "sought=5" not in out or "missing=5" not in out or "unreached=0" not in out:
        raise Failure(f"fetch: unexpected counts: {out}")
    if not (work / "spec.fetch.json").is_file():
        raise Failure("fetch: no -o given, but spec.fetch.json was not written beside the spec")
    say("fetch", f"{out} -> spec.fetch.json")

    out = _need(cli(["fill", str(spec), "-o", str(shelf)], tmp), 0, "fill")
    if "pending=5" not in out or "approved=0" not in out or "paths=0/2" not in out:
        raise Failure(f"fill: unexpected counts: {out}")
    say("fill", out)

    entries = json.loads(shelf.read_text(encoding="utf-8"))["interactions"][INTERACTION]
    if len(entries) != 5:
        raise Failure(f"fill: {len(entries)} entries on the shelf, expected 5")

    # The clips are the bytes a reviewer sees. Each is written once, before the viewing.
    for entry in entries.values():
        clip = work / entry["clip_path"]
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(f"clip:{entry['phrase_key']}\n".encode("utf-8"))

    # Once the clips are on the shelf, fetch finds them where the app stores them.
    out = _need(cli(["fetch", str(spec), "-o", str(work / "fetch.json")], tmp), 0, "fetch with clips")
    if "found=5" not in out or "missing=0" not in out:
        raise Failure(f"fetch with clips: unexpected counts: {out}")
    say("fetch with clips", out)

    # An unseen line cannot be approved: the shelf must stay as it is.
    first = next(iter(entries.values()))
    before = shelf.read_text(encoding="utf-8")
    args = ["--interaction", INTERACTION, "--phrase", first["phrase"], "--base", str(work)]
    out = _need(cli(["approve", str(shelf), *args], tmp), 2, "approve before view")
    if "reason=unseen" not in out or shelf.read_text(encoding="utf-8") != before:
        raise Failure(f"approve before view: {out}")
    say("approve unseen", f"refused: {out}")

    approved = 0
    for entry in entries.values():
        args = ["--interaction", INTERACTION, "--phrase", entry["phrase"], "--base", str(work)]
        if entry.get("node_id"):
            args += ["--node", entry["node_id"]]
        out = _need(cli(["view", str(shelf), *args], tmp), 0, f"view {entry['phrase_key']!r}")
        if out != "seen=true":
            raise Failure(f"view {entry['phrase_key']!r}: {out}")
        out = _need(cli(["approve", str(shelf), *args], tmp), 0, f"approve {entry['phrase_key']!r}")
        if not out.startswith("approved "):
            raise Failure(f"approve {entry['phrase_key']!r}: {out}")
        approved += 1
    say("view+approve", f"{approved} lines signed off")

    signed = json.loads(shelf.read_text(encoding="utf-8"))["interactions"][INTERACTION]
    locks = [entry.get("signal_lock") for entry in signed.values()]
    if any(not lock for lock in locks) or any(e["status"] != "approved" for e in signed.values()):
        raise Failure("approve: a signed line has no signal lock")

    out = _need(cli(["release", str(spec), str(shelf), "-o", str(contract)], tmp), 0, "release")
    lines = out.splitlines()
    if lines[0] != "released=true paths=2/2 files=true":
        raise Failure(f"release: {lines[0]}")
    body = json.loads(contract.read_text(encoding="utf-8"))
    if body.get("released") is not True or body.get("cartouche_sha256") != lines[-1]:
        raise Failure("release: the contract on disk is not the one printed")
    if len(body.get("clips") or []) != 5 or body.get("rendered") is not False:
        raise Failure("release: the contract does not hold exactly the five signed clips")
    if any(clip.get("status") != "approved" for clip in body["clips"]):
        raise Failure("release: a line signed off for this request is not status approved")
    say("release", f"{lines[0]} sha={lines[-1][:16]} clips=approved")

    # An open shelf: the same command exits 2 and names every line that blocks.
    unsigned = work / "unsigned.json"
    out = _need(
        cli(["release", str(spec), str(work / "empty_shelf.json"), "-o", str(unsigned)], tmp),
        2,
        "release of an open shelf",
    )
    open_body = json.loads(unsigned.read_text(encoding="utf-8"))
    if open_body.get("released") is not False or len(open_body.get("blocks") or []) != 5:
        raise Failure(f"release of an open shelf: {out}")
    if open_body.get("cartouche_sha256") != body["cartouche_sha256"]:
        raise Failure("release of an open shelf: the lock moved")
    open_lines = out.splitlines()
    if open_lines[1:] != [f"block: {line}" for line in open_body["blocks"]]:
        raise Failure(f"release of an open shelf: the blocking lines are not on stdout: {out}")
    if body["cartouche_sha256"] in out:
        raise Failure("release of an open shelf: the lock was printed for an unreleased contract")
    say("release open", f"{open_lines[0]} blocks={len(open_body['blocks'])} (named on stdout, no lock printed)")

    # The same request with one phrase changed is a different intent.
    drifted_spec = json.loads(spec.read_text(encoding="utf-8"))
    drifted_spec["b_roll_atoms"]["tok_human"]["phrase"] = "Yeah, this is Michael."
    drifted = work / "drifted_spec.json"
    drifted.write_text(json.dumps(drifted_spec, indent=2) + "\n", encoding="utf-8")

    return {"spec": spec, "contract": contract, "unsigned": unsigned, "drifted": drifted, "work": work}


# ---- the server -----------------------------------------------------------------


class Server:
    """The real stdio server as a subprocess. Newline-delimited JSON-RPC, like a client."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.proc: subprocess.Popen[str] | None = None
        self.next_id = 0

    def __enter__(self) -> "Server":
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cartouche.mcp"],
            cwd=ROOT,
            env=_env(self.tmp),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        started = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        info = started.get("result", {}).get("serverInfo", {})
        if info.get("name") != "cartouche":
            raise Failure(f"initialize: {started}")
        self.notify("notifications/initialized")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait(timeout=5)

    def notify(self, method: str) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.proc is not None and self.proc.stdin is not None and self.proc.stdout is not None
        self.next_id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            body["params"] = params
        self.proc.stdin.write(json.dumps(body) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise Failure(f"{method}: the server closed stdout")
        reply = json.loads(line)
        if reply.get("id") != self.next_id:
            raise Failure(f"{method}: reply id {reply.get('id')!r} is not {self.next_id}")
        return reply

    def tools(self) -> list[str]:
        return [tool["name"] for tool in self.rpc("tools/list")["result"]["tools"]]

    def call(self, name: str, **arguments: str) -> dict[str, Any]:
        reply = self.rpc("tools/call", {"name": name, "arguments": arguments})
        result = reply.get("result")
        if result is None:
            raise Failure(f"{name}: {reply.get('error')}")
        payload = result.get("structuredContent")
        text = json.loads(result["content"][0]["text"])
        if payload != text:
            raise Failure(f"{name}: structuredContent and text disagree")
        if bool(result.get("isError")) != (payload.get("error") is not None):
            raise Failure(f"{name}: isError does not match the payload")
        return payload


def _faults(answer: dict[str, Any]) -> list[str]:
    return [str(row.get("fault")) for row in answer.get("issues") or []]


def _functions(answer: dict[str, Any]) -> list[str]:
    return [str(row.get("function")) for row in answer.get("issues") or []]


def _details(answer: dict[str, Any]) -> list[str]:
    return [str(row.get("detail")) for row in answer.get("issues") or []]


def _named(answer: dict[str, Any], function: str, fault: str, detail: str = "") -> dict[str, Any]:
    """The row for one function: its fault is the one word, and the scanner's code is in detail."""

    for row in answer.get("issues") or []:
        if row.get("function") == function and row.get("fault") == fault and detail in str(row.get("detail")):
            return row
    raise Failure(
        f"no issue names {function} with fault={fault} detail~{detail!r}: "
        f"faults={_faults(answer)} details={_details(answer)} functions={_functions(answer)}"
    )


# ---- selftest ---------------------------------------------------------------------


def _unit_tests(tmp: Path, say: Say) -> None:
    unit_tmp = tmp / "unit"
    unit_tmp.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "cartouche/tests", "-p", "test_*.py"],
        cwd=ROOT,
        env=_env(unit_tmp),
        capture_output=True,
        text=True,
        timeout=600,
    )
    text = proc.stderr + proc.stdout
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    if proc.returncode != 0 or not ran or not re.search(r"^OK$", text, re.M):
        tail = "\n".join(text.strip().splitlines()[-15:])
        raise Failure(f"unit tests: exit {proc.returncode}\n{tail}")
    say("unit tests", f"{ran.group(1)} tests, OK")


def _snapshot() -> dict[str, str]:
    seen: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if any(part == "__pycache__" or part.startswith(".") for part in rel.parts):
            continue
        if path.is_file():
            seen[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return seen


def _server_checks(paths: dict[str, Path], tmp: Path, say: Say) -> None:
    build = tmp / "build"
    build.mkdir()
    agents = {
        "sealed": "agent_sealed.py",
        "hazy": "agent_hazy_verify.py",
        "shifted": "agent_shifted_edge.py",
        "esprit": "agent_esprit.py",
    }
    for name, source in agents.items():
        shutil.copyfile(FIXTURE / source, build / f"{name}.py")
    spec, contract = str(paths["spec"]), str(paths["contract"])
    contract_before = paths["contract"].read_text(encoding="utf-8")
    lock = json.loads(contract_before)["cartouche_sha256"]

    with Server(tmp) as server:
        names = server.tools()
        if names != ["ct_watch", "ct_look", "ct_stop", "ct_hold"]:
            raise Failure(f"tools/list: {names}")
        say("mcp tools/list", " ".join(names))

        unbound = server.call("ct_look")
        if "no target" not in str(unbound.get("error")):
            raise Failure(f"ct_look before ct_watch: {unbound}")
        say("ct_look unbound", unbound["error"])

        # (a) the sealed agent
        watched = server.call("ct_watch", spec=spec, contract=contract, target=str(build / "sealed.py"))
        if watched.get("error") or watched.get("sealed") is not True or watched.get("issues"):
            raise Failure(f"ct_watch sealed: {watched}")
        if watched.get("cartouche_sha256") != lock:
            raise Failure("ct_watch sealed: the scan lock is not the release lock")
        looked = server.call("ct_look")
        if looked.get("sealed") is not True or looked.get("issues") or looked.get("open") != 0:
            raise Failure(f"ct_look sealed: {looked}")
        stopped = server.call("ct_stop")
        if stopped.get("stopped") is not True or stopped.get("sealed") is not True or stopped.get("bound"):
            raise Failure(f"ct_stop sealed: {stopped}")
        say("sealed agent", f"ct_watch/ct_look/ct_stop sealed=true issues=0 lock={lock[:16]}")

        # a different target while one is bound answers ct_stop first
        server.call("ct_watch", spec=spec, contract=contract, target=str(build / "sealed.py"))
        other = server.call("ct_watch", spec=spec, contract=contract, target=str(build / "hazy.py"))
        if "ct_stop first" not in str(other.get("error")):
            raise Failure(f"second ct_watch: {other}")
        server.call("ct_stop")
        say("second target", other["error"])

        # nothing written yet is waiting, not an issue
        waiting = server.call("ct_watch", spec=spec, contract=contract, target=str(build / "later.py"))
        if waiting.get("waiting") is not True or waiting.get("issues") or waiting.get("error"):
            raise Failure(f"ct_watch unwritten: {waiting}")
        if waiting.get("target") != str((build / "later.py").resolve()) or looked.get("target") != str((build / "sealed.py").resolve()):
            raise Failure(f"target is not named the same waiting and scanned: {waiting.get('target')!r} / {looked.get('target')!r}")
        server.call("ct_stop")
        say("unwritten target", "waiting=true issues=0 target named")

        # (b) the hazy agent: verify_human returns True
        hazy = server.call("ct_watch", spec=spec, contract=contract, target=str(build / "hazy.py"))
        if hazy.get("sealed") is not False:
            raise Failure(f"ct_watch hazy: {hazy}")
        row = _named(server.call("ct_look"), "fxnB_verify_human", "hazy", "DEGENERATE_CONSTANT_RETURN")
        if not row.get("lines") or not row.get("directive") or not str(row.get("file", "")).endswith("hazy.py"):
            raise Failure(f"ct_look hazy: row is incomplete: {row}")
        stopped = server.call("ct_stop")
        if stopped.get("sealed") is not False or stopped.get("open", 0) < 1:
            raise Failure(f"ct_stop hazy: {stopped}")
        say("hazy agent", f"sealed=false fxnB_verify_human fault={row['fault']} detail={row['detail']} lines={row['lines']}")

        # (b) the shifted-edge agent: verify_human no longer reaches transmit_request
        shifted = server.call("ct_watch", spec=spec, contract=contract, target=str(build / "shifted.py"))
        if shifted.get("sealed") is not False:
            raise Failure(f"ct_watch shifted: {shifted}")
        row = _named(server.call("ct_look"), "fxnB_verify_human", "skew", "TOPOLOGY_BREAK")
        stopped = server.call("ct_stop")
        if stopped.get("sealed") is not False:
            raise Failure(f"ct_stop shifted: {stopped}")
        say("shifted-edge agent", f"sealed=false fxnB_verify_human fault={row['fault']} detail={row['detail']} lines={row['lines']}")

        # (b) the esprit agent: voicemail missing, confirm a hollow stub
        esprit = server.call("ct_hold", spec=spec, contract=contract, target=str(build / "esprit.py"))
        if esprit.get("sealed") is not False:
            raise Failure(f"ct_hold esprit: {esprit}")
        _named(esprit, "fxnD_voicemail_fallback", "missing", "MISSING_FUNCTION")
        _named(esprit, "fxnE_confirm_slot", "template", "HOLLOW_STUB")
        say("esprit agent", "ct_hold sealed=false missing fxnD_voicemail_fallback, template fxnE_confirm_slot")

        # a tree is one scan, and a file that does not parse does not end it
        tree = tmp / "tree"
        tree.mkdir()
        sealed_src = (FIXTURE / "agent_sealed.py").read_text(encoding="utf-8")
        head, tail = sealed_src.split("def fxnC_transmit_request", 1)
        (tree / "front.py").write_text(head, encoding="utf-8")
        (tree / "back.py").write_text("def fxnC_transmit_request" + tail, encoding="utf-8")
        whole = server.call("ct_hold", spec=spec, contract=contract, target=str(tree))
        if whole.get("sealed") is not True:
            raise Failure(f"ct_hold split tree: {whole}")
        (tree / "mid.py").write_text("def still_writing(:\n", encoding="utf-8")
        broken = server.call("ct_hold", spec=spec, contract=contract, target=str(tree))
        if broken.get("sealed") is not False or "SYNTAX" not in _faults(broken) or "missing" in _faults(broken):
            raise Failure(f"ct_hold broken tree: faults={_faults(broken)}")
        if broken.get("target") != str(tree.resolve()):
            raise Failure(f"ct_hold broken tree: target {broken.get('target')!r} is not {str(tree)!r}")
        say("tree scan", "split tree sealed=true; with an unparsed file sealed=false fault=SYNTAX, rest still scored")

        # (c) an unsigned release is refused
        refused = server.call("ct_watch", spec=spec, contract=str(paths["unsigned"]), target=str(build / "sealed.py"))
        if "not signed off" not in str(refused.get("error")):
            raise Failure(f"ct_watch unsigned: {refused}")
        still = server.call("ct_look")
        if "no target" not in str(still.get("error")):
            raise Failure(f"ct_look after a refused watch: {still}")
        say("unsigned release", f"ct_watch refused: {refused['error']}")

        # a spec that no longer hashes to the release is refused
        moved = server.call("ct_watch", spec=str(paths["drifted"]), contract=contract, target=str(build / "sealed.py"))
        if "no longer matches the lock" not in str(moved.get("error")):
            raise Failure(f"ct_watch drifted spec: {moved}")
        say("drifted spec", f"ct_watch refused: {moved['error']}")

        # a missing release is refused
        gone = server.call("ct_watch", spec=spec, contract=str(tmp / "nowhere.json"), target=str(build / "sealed.py"))
        if "no such release" not in str(gone.get("error")):
            raise Failure(f"ct_watch missing release: {gone}")
        say("missing release", f"ct_watch refused: {gone['error']}")

        if server.proc is None or server.proc.poll() is not None:
            raise Failure("the server process did not stay up")

    if paths["contract"].read_text(encoding="utf-8") != contract_before:
        raise Failure("the release was rewritten")
    say("release untouched", "the contract bytes are the ones released")


def selftest() -> int:
    def say(name: str, detail: str) -> None:
        print(f"ok   {name}: {detail}")
        sys.stdout.flush()

    before = _snapshot()
    tmp = Path(tempfile.mkdtemp(prefix="cartouche-selftest-"))
    try:
        _unit_tests(tmp, say)
        paths = build_release(tmp, say)
        _server_checks(paths, tmp, say)
        if PLANTS.is_dir():
            passed, failed = run_plants(PLANTS, tmp / "plants", quiet=True)
            if failed or not passed:
                raise Failure(f"plants: {passed} PASS / {failed} FAIL (run plants/run_all.sh)")
            say("plants", f"{passed} PASS / {failed} FAIL")
        after = _snapshot()
        changed = sorted(set(before) ^ set(after) | {k for k in before if k in after and before[k] != after[k]})
        if changed:
            raise Failure("files changed outside the temp dir: " + ", ".join(changed))
        say("tree", "no file outside the temp dir was added or changed")
    except Failure as exc:
        print(f"FAIL {exc}")
        print("cartouche: selftest FAIL")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("cartouche: selftest PASS")
    return 0


# ---- plants -----------------------------------------------------------------------


def _plant_dirs(plants: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for kind in ("honest", "counterfeit"):
        base = plants / kind
        if not base.is_dir():
            continue
        for case in sorted(base.iterdir()):
            if case.is_dir() and (case / "expect.json").is_file():
                found.append((kind, case))
    return found


def _judge(kind: str, expect: dict[str, Any], answer: dict[str, Any]) -> str | None:
    """None when the plant behaves as its folder says. Otherwise, why not."""

    if answer.get("error"):
        return f"ct_hold answered an error: {answer['error']}"
    faults = _faults(answer)
    functions = _functions(answer)
    if kind == "honest":
        if answer.get("sealed") is not True:
            return f"not sealed: faults={faults} functions={functions}"
        if answer.get("issues"):
            return f"sealed but issues were reported: {faults}"
        return None
    if answer.get("sealed") is not False:
        return "sealed: the counterfeit was not reported"
    if not answer.get("issues"):
        return "not sealed but no issue was named"
    for fault in expect.get("faults") or []:
        if fault not in faults:
            return f"fault {fault} not named: faults={faults}"
    details = _details(answer)
    for detail in expect.get("details") or []:
        if not any(detail in item for item in details):
            return f"detail {detail} not named: details={details}"
    for function in expect.get("functions") or []:
        if function not in functions:
            return f"function {function} not named: functions={functions}"
    if expect.get("reason") and answer.get("reason") != expect["reason"]:
        return f"reason {answer.get('reason')!r}, expected {expect['reason']!r}"
    return None


def run_plants(plants: Path, tmp: Path, quiet: bool = False) -> tuple[int, int]:
    """Every plant through ct_hold on the real server. Returns (passed, failed)."""

    tmp.mkdir(parents=True, exist_ok=True)
    cases = _plant_dirs(plants)
    if not cases:
        print(f"no plants under {plants}")
        return 0, 0
    paths = build_release(tmp, lambda _n, _d: None)
    contract_before = paths["contract"].read_text(encoding="utf-8")
    passed = failed = 0
    with Server(tmp) as server:
        for kind, case in cases:
            label = f"{kind}/{case.name}"
            expect = json.loads((case / "expect.json").read_text(encoding="utf-8"))
            stage = tmp / "stage" / kind / case.name
            stage.mkdir(parents=True)
            sources = sorted(p for p in case.iterdir() if p.suffix == ".py" and p.is_file())
            for source in sources:
                shutil.copyfile(source, stage / source.name)
            target = expect.get("target")
            if target is None:
                target_path = stage / sources[0].name if len(sources) == 1 else stage
            else:
                target_path = (stage / target).resolve()
            spec = paths["drifted"] if expect.get("spec") == "drifted" else paths["spec"]
            contract = paths["unsigned"] if expect.get("contract") == "unsigned" else paths["contract"]
            answer = server.call("ct_hold", spec=str(spec), contract=str(contract), target=str(target_path))
            why = _judge(kind, expect, answer)
            if why is None and paths["contract"].read_text(encoding="utf-8") != contract_before:
                why = "the release was rewritten"
            if why is None:
                passed += 1
                if not quiet:
                    print(f"PASS {label}")
            else:
                failed += 1
                print(f"FAIL {label}: {why}")
    if not quiet:
        print(f"plants: {passed} PASS / {failed} FAIL")
    return passed, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cartouche-selftest")
    parser.add_argument("--plants", type=Path, help="run only the plants in this folder")
    args = parser.parse_args(argv)
    if args.plants is None:
        return selftest()
    tmp = Path(tempfile.mkdtemp(prefix="cartouche-plants-"))
    try:
        passed, failed = run_plants(args.plants.resolve(), tmp)
    except Failure as exc:
        print(f"FAIL {exc}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed and not failed else 1


if __name__ == "__main__":
    sys.exit(main())

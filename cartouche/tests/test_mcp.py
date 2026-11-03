"""The MCP door. A miss names the file, the function, and the fault. The release is not rewritten."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.build_release import release
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary
from cartouche.domain import INTERACTION, domain_spec, fixture_path
from cartouche.mcp_tools import Watch, issues_of
from cartouche.project_symbol import DEFECTS, FAULT_WORDS, LOCKED, MISSING, SKEW, SYNTAX, TEMPLATE
from cartouche.tests.signoff import see_shelf


def _covered() -> dict:
    dictionary = empty_dictionary()
    _dictionary, report = LibraryFiller().fill(domain_spec(), dictionary)
    base = Path(tempfile.mkdtemp())
    see_shelf(dictionary, base)
    for clip in report["clips"]:
        approve(dictionary, INTERACTION, clip["phrase"], base)
    return release(domain_spec(), dictionary)


def _paths(root: Path, contract: dict | None = None) -> tuple[Path, Path]:
    spec = root / "spec.json"
    spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
    contract_path = root / "release.json"
    contract_path.write_text(json.dumps(contract if contract is not None else _covered()), encoding="utf-8")
    return spec, contract_path


class McpToolTests(unittest.TestCase):
    def test_a_constant_return_names_the_fault_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, contract = _paths(Path(tmp))
            before = contract.read_text(encoding="utf-8")
            answer = Watch().hold(str(spec), str(contract), str(fixture_path("hazy")))
            self.assertFalse(answer["sealed"])
            self.assertGreater(answer["open"], 0)
            named = [row for row in answer["issues"] if row["function"] == "fxnB_verify_human"]
            self.assertTrue(named)
            self.assertEqual(named[0]["fault"], TEMPLATE)
            self.assertIn("DEGENERATE_CONSTANT_RETURN", named[0]["detail"])
            self.assertNotIn("LOW_AST_DENSITY", named[0]["detail"])  # a short body is let through, never a fault
            self.assertIn(fixture_path("hazy").name, named[0]["file"])
            self.assertEqual(answer["target"], str(fixture_path("hazy")))
            self.assertTrue(named[0]["directive"])
            self.assertEqual(contract.read_text(encoding="utf-8"), before)

    def test_nothing_written_is_waiting_not_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec, contract = _paths(root)
            watch = Watch()
            bound = watch.watch(str(spec), str(contract), str(root / "missing.py"))
            self.assertTrue(bound["bound"])
            self.assertTrue(bound["waiting"])
            self.assertEqual(bound["issues"], [])
            self.assertNotIn("error", bound)
            self.assertEqual(bound["target"], str((root / "missing.py").resolve()))
            (root / "missing.py").write_text(fixture_path("sealed").read_text(encoding="utf-8"), encoding="utf-8")
            looked = watch.look()
            self.assertTrue(looked["sealed"])
            self.assertEqual(looked["target"], str((root / "missing.py").resolve()))
            self.assertEqual(watch.stop()["target"], str((root / "missing.py").resolve()))

    def test_a_tree_is_one_scan_and_a_broken_file_does_not_end_it(self) -> None:
        sealed = fixture_path("sealed").read_text(encoding="utf-8")
        head, tail = sealed.split("def fxnC_transmit_request", 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec, contract = _paths(root)
            build = root / "build"
            build.mkdir()
            (build / "front.py").write_text(head, encoding="utf-8")
            (build / "back.py").write_text("def fxnC_transmit_request" + tail, encoding="utf-8")
            (build / "mid.py").write_text("def still_writing(:\n", encoding="utf-8")
            answer = Watch().hold(str(spec), str(contract), str(build))
            self.assertFalse(answer["sealed"])
            faults = [row["fault"] for row in answer["issues"]]
            self.assertIn(SYNTAX, faults)
            self.assertNotIn(MISSING, faults)
            syntax = next(row for row in answer["issues"] if row["fault"] == SYNTAX)
            self.assertEqual(Path(syntax["file"]).name, "mid.py")
            self.assertEqual(answer["target"], str(build.resolve()))

    def test_a_split_tree_seals(self) -> None:
        sealed = fixture_path("sealed").read_text(encoding="utf-8")
        head, tail = sealed.split("def fxnC_transmit_request", 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec, contract = _paths(root)
            build = root / "build"
            build.mkdir()
            (build / "front.py").write_text(head, encoding="utf-8")
            (build / "back.py").write_text("def fxnC_transmit_request" + tail, encoding="utf-8")
            answer = Watch().hold(str(spec), str(contract), str(build))
            self.assertTrue(answer["sealed"], answer["issues"])
            self.assertEqual(answer["issues"], [])

    def test_stop_reports_an_open_miss_and_drops_the_bind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec, contract = _paths(root)
            before = contract.read_text(encoding="utf-8")
            watch = Watch()
            watch.watch(str(spec), str(contract), str(fixture_path("esprit")))
            stopped = watch.stop()
            self.assertTrue(stopped["stopped"])
            self.assertFalse(stopped["sealed"])
            self.assertGreater(stopped["open"], 0)
            self.assertTrue(any(row["function"] for row in stopped["issues"]))
            self.assertEqual(contract.read_text(encoding="utf-8"), before)
            again = watch.look()
            self.assertIn("error", again)

    def test_an_unsigned_release_is_not_watched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, contract = _paths(Path(tmp), release(domain_spec(), empty_dictionary()))
            watch = Watch()
            answer = watch.watch(str(spec), str(contract), str(fixture_path("sealed")))
            self.assertIn("error", answer)
            self.assertFalse(watch.bound())

    def test_issue_rows_carry_the_warrant_function(self) -> None:
        report = {
            "waiting": False,
            "closer_warrants": [
                {
                    "warrant_type": "CARTOUCHE_MALFORMED_GLYPH",
                    "target_file": "agent.py",
                    "line_range": [4, 6],
                    "malformed_primitive": "fxnB_verify_human",
                    "cartouche_region": "the mouth",
                    "faults": ["DEGENERATE_CONSTANT_RETURN"],
                    "surgeon_directive": "fix the return",
                }
            ],
        }
        rows = issues_of(report)
        self.assertEqual(rows[0]["function"], "fxnB_verify_human")
        self.assertEqual(rows[0]["fault"], TEMPLATE)
        self.assertEqual(rows[0]["detail"], "DEGENERATE_CONSTANT_RETURN")
        self.assertNotEqual(rows[0]["fault"], "the mouth")

    def test_a_drifted_request_is_locked_and_an_open_shelf_is_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec, contract = _paths(root)
            drifted = json.loads(spec.read_text(encoding="utf-8"))
            drifted["b_roll_atoms"]["tok_human"]["phrase"] = "Yeah, this is Michael."
            moved = root / "drifted.json"
            moved.write_text(json.dumps(drifted), encoding="utf-8")
            answer = Watch().hold(str(moved), str(contract), str(fixture_path("sealed")))
            self.assertEqual(answer["reason"], "intent")
            self.assertFalse(answer["scanned"])
            self.assertEqual([row["fault"] for row in answer["issues"]], [LOCKED])
            self.assertEqual(answer["issues"][0]["detail"], "INTENT")
            self.assertEqual(answer["target"], str(fixture_path("sealed")))
            _spec, unsigned = _paths(root, release(domain_spec(), empty_dictionary()))
            refused = Watch().hold(str(spec), str(unsigned), str(fixture_path("sealed")))
            self.assertEqual(refused["reason"], "unreleased")
            self.assertFalse(refused["scanned"])
            self.assertEqual([row["fault"] for row in refused["issues"]], ["UNRELEASED"])

    def test_every_fault_a_scan_can_emit_is_one_of_the_five_words_or_syntax(self) -> None:
        """INTENT.md names five defects. Every scanned row carries exactly one of them, or SYNTAX."""

        self.assertEqual(set(DEFECTS), {TEMPLATE, LOCKED, MISSING, SKEW})
        self.assertEqual(FAULT_WORDS, {TEMPLATE, LOCKED, MISSING, SKEW, SYNTAX})
        seen: set[str] = set()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec, contract = _paths(root)
            plants = Path(__file__).resolve().parents[2] / "plants"
            targets = [fixture_path(name) for name in ("sealed", "hazy", "shifted", "esprit")]
            targets += sorted(p for p in plants.rglob("*.py") if "counterfeit" in p.parts)
            build = root / "build"
            build.mkdir()
            (build / "ok.py").write_text(fixture_path("sealed").read_text(encoding="utf-8"), encoding="utf-8")
            (build / "mid.py").write_text("def still_writing(:\n", encoding="utf-8")
            targets.append(build)
            for target in targets:
                for row in Watch().hold(str(spec), str(contract), str(target))["issues"]:
                    seen.add(row["fault"])
            drifted = json.loads(spec.read_text(encoding="utf-8"))
            drifted["b_roll_atoms"]["tok_human"]["phrase"] = "Yeah, this is Michael."
            moved = root / "drifted.json"
            moved.write_text(json.dumps(drifted), encoding="utf-8")
            for row in Watch().hold(str(moved), str(contract), str(fixture_path("sealed")))["issues"]:
                seen.add(row["fault"])
        # Every warrant the scanner can write, including the malformed codes the fixtures do not hit.
        synthetic = {
            "waiting": False,
            "closer_warrants": [
                {"warrant_type": "CARTOUCHE_MISSING_GLYPH", "missing_primitive": "a", "line_range": [1, 1]},
                {"warrant_type": "CARTOUCHE_COUNTERFEIT_STUB", "missing_primitive": "b", "line_range": [1, 1]},
                {"warrant_type": "CARTOUCHE_TOPOLOGY_BREAK", "broken_edge": ["a", "b"], "line_range": [1, 1]},
                {"warrant_type": "CARTOUCHE_UNPARSED", "line_range": [1, 1]},
                {
                    "warrant_type": "CARTOUCHE_MALFORMED_GLYPH",
                    "malformed_primitive": "c",
                    "line_range": [1, 2],
                    "faults": ["MISSING_PARAMS(x)", "DEGENERATE_CONSTANT_RETURN", "SWALLOWED_BARE_EXCEPT", "LOW_AST_DENSITY(0<4)"],
                },
            ],
        }
        for row in issues_of(synthetic):
            seen.add(row["fault"])
            self.assertNotIn(",", row["fault"])
        self.assertEqual(seen, FAULT_WORDS, seen)
        self.assertTrue(seen <= FAULT_WORDS)


class McpStdioTests(unittest.TestCase):
    def test_the_server_lists_the_four_tools_and_looks(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.Popen(
            [sys.executable, "-m", "cartouche.mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=root,
            text=True,
        )
        assert proc.stdin and proc.stdout
        try:
            def rpc(message_id: int, method: str, params: dict | None = None) -> dict:
                body: dict = {"jsonrpc": "2.0", "id": message_id, "method": method}
                if params is not None:
                    body["params"] = params
                proc.stdin.write(json.dumps(body) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                self.assertTrue(line, "server closed stdout")
                return json.loads(line)

            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            proc.stdin.flush()
            started = rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
            self.assertEqual(started["result"]["serverInfo"]["name"], "cartouche")
            self.assertIn("ct_look", started["result"]["instructions"])
            listed = rpc(2, "tools/list")
            names = [tool["name"] for tool in listed["result"]["tools"]]
            self.assertEqual(names, ["ct_watch", "ct_look", "ct_stop", "ct_hold", "ct_chart", "ct_wanted", "ct_search", "ct_offer", "ct_withdraw", "ct_render"])
            unbound = rpc(3, "tools/call", {"name": "ct_look", "arguments": {}})
            self.assertTrue(unbound["result"]["isError"])
            with tempfile.TemporaryDirectory() as tmp:
                spec, contract = _paths(Path(tmp))
                target = Path(tmp) / "build.py"
                target.write_text(textwrap.dedent(fixture_path("sealed").read_text(encoding="utf-8")), encoding="utf-8")
                # sealed fixture imports nothing; copy bytes
                target.write_text(fixture_path("sealed").read_text(encoding="utf-8"), encoding="utf-8")
                watched = rpc(
                    4,
                    "tools/call",
                    {
                        "name": "ct_watch",
                        "arguments": {"spec": str(spec), "contract": str(contract), "target": str(target)},
                    },
                )
                payload = json.loads(watched["result"]["content"][0]["text"])
                self.assertTrue(payload["sealed"], payload)
                self.assertFalse(watched["result"]["isError"])
        finally:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

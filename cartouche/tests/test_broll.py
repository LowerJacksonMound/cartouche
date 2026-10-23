"""B-roll fetch seeks every reachable decision visual and does not invent clips."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.broll_fetcher import BRollFetcher
from cartouche.cli import main
from cartouche.domain import EXAMPLE_DIR, domain_spec


def _node(token: str, fxn: str, slot: int, branches: list[str], edge: bool = False) -> dict:
    return {
        "token_id": token,
        "primitive_fxn": fxn,
        "glyph_slot": slot,
        "is_edge_case": edge,
        "branches": [{"target_node": target} for target in branches],
    }


class PhoneFetchTests(unittest.TestCase):
    def test_seeks_every_decision_and_finds_nothing(self) -> None:
        report = BRollFetcher(domain_spec(), base_dir=EXAMPLE_DIR).fetch()
        self.assertEqual(
            [item["node_id"] for item in report["sought"]],
            ["n0", "n1", "n2", "n3", "n_vm"],
        )
        self.assertEqual(report["sought"][1]["decides"], ["n2", "n_vm"])
        self.assertEqual(report["unreached"], [])
        self.assertEqual(
            report["counts"],
            {"sought": 5, "found": 0, "missing": 5, "undeclared": 0, "unreached": 0},
        )
        self.assertTrue(all(item["status"] == "missing" for item in report["sought"]))

    def test_library_hit_does_not_fill_the_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            (library / "tok_vm.mp4").write_bytes(b"clip")
            report = BRollFetcher(domain_spec(), base_dir=EXAMPLE_DIR, library=library).fetch()
            by_node = {item["node_id"]: item["status"] for item in report["sought"]}
            self.assertEqual(by_node["n_vm"], "found")
            self.assertEqual(by_node["n0"], "missing")
            self.assertEqual(report["counts"]["found"], 1)


class SeekGuardTests(unittest.TestCase):
    def test_orphan_is_unreached_and_a_hole_is_undeclared(self) -> None:
        spec = {
            "domain_id": "guard",
            "root_id": "a",
            "b_roll_atoms": {"ta": {"phrase": "alpha", "clip_path": "clips/ta.mp4"}},
            "nodes": {
                "a": _node("ta", "fxn_a", 0, ["b"]),
                "b": _node("tb", "fxn_b", 1, []),
                "orphan": _node("to", "fxn_o", 2, []),
            },
        }
        report = BRollFetcher(spec).fetch()
        self.assertEqual([item["node_id"] for item in report["sought"]], ["a", "b"])
        self.assertEqual(report["sought"][1]["status"], "undeclared")
        self.assertEqual(report["unreached"][0]["node_id"], "orphan")
        self.assertEqual(report["unreached"][0]["status"], "unreached")

    def test_cycle_seeks_each_node_once(self) -> None:
        spec = {
            "domain_id": "cycle",
            "root_id": "a",
            "b_roll_atoms": {
                "ta": {"phrase": "a", "clip_path": "a.mp4"},
                "tb": {"phrase": "b", "clip_path": "b.mp4"},
            },
            "nodes": {
                "a": _node("ta", "fxn_a", 0, ["b"]),
                "b": _node("tb", "fxn_b", 1, ["a"]),
            },
        }
        report = BRollFetcher(spec).fetch()
        self.assertEqual([item["node_id"] for item in report["sought"]], ["a", "b"])

    def test_declared_file_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            clip = base / "clips"
            clip.mkdir()
            (clip / "ta.mp4").write_bytes(b"clip")
            spec = {
                "domain_id": "hit",
                "root_id": "a",
                "b_roll_atoms": {"ta": {"phrase": "alpha", "clip_path": "clips/ta.mp4"}},
                "nodes": {"a": _node("ta", "fxn_a", 0, [])},
            }
            report = BRollFetcher(spec, base_dir=base).fetch()
            self.assertEqual(report["sought"][0]["status"], "found")
            self.assertTrue(report["sought"][0]["clip_path"].endswith("clips/ta.mp4"))


class ShelfPathTests(unittest.TestCase):
    def test_a_clip_on_the_shelf_path_is_found(self) -> None:
        from cartouche.clip_library import LibraryFiller, empty_dictionary

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
            before = BRollFetcher(domain_spec(), base_dir=base).fetch()["counts"]
            self.assertEqual((before["found"], before["missing"]), (0, 5))
            for clip in report["clips"]:
                path = base / clip["clip_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"clip")
            after = BRollFetcher(domain_spec(), base_dir=base).fetch()
            self.assertEqual((after["counts"]["found"], after["counts"]["missing"]), (5, 0))
            self.assertTrue(all("/library/phone_conversation/" in item["clip_path"] for item in after["sought"]))

    def test_the_declared_path_wins_over_the_shelf(self) -> None:
        from cartouche.clip_library import LibraryFiller, empty_dictionary

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
            for clip in report["clips"]:
                path = base / clip["clip_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"clip")
            declared = base / "clips" / "tok_vm.mp4"
            declared.parent.mkdir(parents=True)
            declared.write_bytes(b"declared")
            found = {item["node_id"]: item["clip_path"] for item in BRollFetcher(domain_spec(), base_dir=base).fetch()["sought"]}
            self.assertTrue(found["n_vm"].endswith("clips/tok_vm.mp4"))
            self.assertIn("/library/phone_conversation/", found["n0"])


class FetchCliTests(unittest.TestCase):
    def test_fetch_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "broll.json"
            code = main(
                ["fetch", str(EXAMPLE_DIR / "domain_spec.json"), "-o", str(out)]
            )
            self.assertEqual(code, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["sought"], 5)
            self.assertEqual(report["counts"]["found"], 0)

    def test_fetch_without_o_writes_beside_the_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            self.assertEqual(main(["fetch", str(spec)]), 0)
            out = Path(tmp) / "spec.fetch.json"
            self.assertTrue(out.is_file())
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["counts"]["sought"], 5)


if __name__ == "__main__":
    unittest.main()

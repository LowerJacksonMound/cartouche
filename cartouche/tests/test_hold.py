"""A scan is pinned to a release. A miss on either side does not rewrite the other."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.build_release import release
from cartouche.cli import main
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary
from cartouche.hold import hold
from cartouche.domain import INTERACTION, domain_spec, fixture_path
from cartouche.tests.signoff import see_shelf
from cartouche.tests.test_stitcher import PHASE1_SHA


def _covered() -> dict:
    dictionary = empty_dictionary()
    _dictionary, report = LibraryFiller().fill(domain_spec(), dictionary)
    base = Path(tempfile.mkdtemp())
    see_shelf(dictionary, base)
    for clip in report["clips"]:
        approve(dictionary, INTERACTION, clip["phrase"], base)
    return release(domain_spec(), dictionary)


class HoldTests(unittest.TestCase):
    def test_an_open_shelf_is_not_scanned(self) -> None:
        contract = release(domain_spec(), empty_dictionary())
        result = hold(domain_spec(), contract, fixture_path("sealed"))
        self.assertFalse(result["held"])
        self.assertEqual(result["reason"], "unreleased")
        self.assertFalse(result["scanned"])
        self.assertNotIn("scan", result)

    def test_a_moved_lock_is_not_scanned(self) -> None:
        contract = _covered()
        contract["cartouche_sha256"] = "0" * 64
        result = hold(domain_spec(), contract, fixture_path("sealed"))
        self.assertEqual(result["reason"], "intent")
        self.assertFalse(result["scanned"])
        self.assertEqual(result["cartouche_sha256"], PHASE1_SHA)
        self.assertEqual(result["contract_sha256"], "0" * 64)

    def test_a_sealed_agent_holds_and_a_broken_one_does_not_touch_the_contract(self) -> None:
        contract = _covered()
        frozen = json.dumps(contract)
        sealed = hold(domain_spec(), contract, fixture_path("sealed"))
        self.assertTrue(sealed["held"])
        self.assertTrue(sealed["is_sealed"])
        self.assertEqual(sealed["projection_residual"], 0.0)
        self.assertEqual(sealed["cartouche_sha256"], PHASE1_SHA)
        broken = hold(domain_spec(), contract, fixture_path("esprit"))
        self.assertTrue(broken["held"])
        self.assertFalse(broken["is_sealed"])
        self.assertGreater(broken["warrant_count"], 0)
        self.assertEqual(sealed["issues"], [])
        by_function = {row["function"]: row for row in broken["issues"]}
        self.assertEqual(by_function["fxnD_voicemail_fallback"]["fault"], "missing")
        self.assertEqual(by_function["fxnE_confirm_slot"]["fault"], "template")
        self.assertEqual(by_function["fxnE_confirm_slot"]["detail"], "HOLLOW_STUB")
        self.assertEqual(json.dumps(contract), frozen)

    def test_cli_keeps_the_contract_file_when_the_scan_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            contract_path = root / "build_input.json"
            contract_path.write_text(json.dumps(_covered(), indent=2) + "\n", encoding="utf-8")
            before = contract_path.read_text(encoding="utf-8")
            report = root / "hold.json"
            code = main(
                ["hold", str(spec), str(contract_path), str(fixture_path("esprit")), "-o", str(report)]
            )
            self.assertEqual(code, 2)
            self.assertEqual(contract_path.read_text(encoding="utf-8"), before)
            body = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(body["reason"], "scan")
            self.assertFalse(body["is_sealed"])
            self.assertEqual(set(row["fault"] for row in body["issues"]), {"missing", "template", "skew"})


if __name__ == "__main__":
    unittest.main()

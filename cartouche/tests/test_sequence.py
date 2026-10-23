"""Build order is the packed path. A later cartouche cannot seal while an earlier one is open."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cartouche_scanner import CartoucheScanner
from cartouche.cli import main
from cartouche.domain import domain_spec, fixture_path, signal_track
from cartouche.sequence import pack_cartouches, project_sequence, symbol_order
from cartouche.tests.test_stitcher import PHASE1_SHA


def _project(target: Path, spec: dict | None = None) -> dict:
    spec = domain_spec() if spec is None else spec
    master = CartoucheCompiler(signal_track()).compile_cartouche()
    report = CartoucheScanner(master).scan_file(target)
    return project_sequence(spec, master, report, target)


class SequenceTests(unittest.TestCase):
    def test_phone_packs_three_then_two_and_the_lock_stays(self) -> None:
        order = symbol_order(domain_spec())
        self.assertEqual(
            order,
            [
                "fxnA_dial",
                "fxnB_verify_human",
                "fxnC_transmit_request",
                "fxnE_confirm_slot",
                "fxnD_voicemail_fallback",
            ],
        )
        bands = pack_cartouches(domain_spec())
        self.assertEqual([len(band["symbols"]) for band in bands], [3, 2])
        result = _project(fixture_path("sealed"))
        self.assertTrue(result["order_held"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["cartouche_sha256"], PHASE1_SHA)

    def test_a_later_cartouche_stays_open_without_breaking_the_order(self) -> None:
        result = _project(fixture_path("esprit"))
        self.assertTrue(result["order_held"])
        self.assertFalse(result["complete"])
        self.assertTrue(result["cartouches"][0]["sealed"])
        self.assertFalse(result["cartouches"][1]["sealed"])
        self.assertEqual(result["cartouche_sha256"], PHASE1_SHA)

    def test_a_symbol_ahead_of_its_cartouche_breaks_the_order(self) -> None:
        source = (
            "def fxnE_confirm_slot(slot: str) -> str:\n"
            "    window = parse_slot(slot)\n"
            "    if window is None:\n"
            "        raise ValueError('bad slot')\n"
            "    return write_booking(window)\n\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "early.py"
            target.write_text(source + Path(fixture_path("sealed")).read_text(encoding="utf-8"), encoding="utf-8")
            result = _project(target)
        self.assertFalse(result["order_held"])
        self.assertFalse(result["complete"])

    def test_a_later_cartouche_cannot_seal_over_an_open_one(self) -> None:
        sealed = Path(fixture_path("sealed")).read_text(encoding="utf-8")
        stubbed = sealed.replace(
            "    channel = open_line(shop_number)\n"
            "    if channel is None:\n"
            '        raise ConnectionError("dial failed")\n'
            "    armed = arm_channel(channel)\n"
            "    fxnB_verify_human(armed)\n"
            "    return armed\n",
            "    pass\n",
            1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "leap.py"
            target.write_text(stubbed, encoding="utf-8")
            result = _project(target)
        self.assertFalse(result["cartouches"][0]["sealed"])
        self.assertTrue(result["cartouches"][1]["sealed"])
        self.assertFalse(result["order_held"])
        self.assertFalse(result["complete"])

    def test_cli_complete_exits_clean_and_incomplete_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            out = root / "sequence.json"
            self.assertEqual(main(["sequence", str(spec), str(fixture_path("sealed")), "-o", str(out)]), 0)
            self.assertEqual(main(["sequence", str(spec), str(fixture_path("esprit")), "-o", str(out)]), 2)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(body["cartouche_sha256"], PHASE1_SHA)
            self.assertTrue(body["order_held"])
            self.assertFalse(body["complete"])


if __name__ == "__main__":
    unittest.main()

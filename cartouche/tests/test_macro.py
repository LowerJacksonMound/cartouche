"""A complete sequence is one reusable symbol. Compose does not mint the missing ones."""

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
from cartouche.macro_library import admit, compose, empty_shelf
from cartouche.domain import domain_spec, fixture_path, signal_track
from cartouche.sequence import project_sequence
from cartouche.tests.test_stitcher import PHASE1_SHA


def _sequence(fixture_id: str) -> dict:
    master = CartoucheCompiler(signal_track()).compile_cartouche()
    report = CartoucheScanner(master).scan_file(fixture_path(fixture_id))
    return project_sequence(domain_spec(), master, report, fixture_path(fixture_id))


def _image(*locks: tuple[str, str], capacity: int = 3) -> dict:
    return {
        "app_id": "book_service_appointment",
        "cartouche_capacity": capacity,
        "symbols": [{"name": name, "lock": lock} for name, lock in locks],
    }


class MacroTests(unittest.TestCase):
    def test_an_open_sequence_is_not_stored(self) -> None:
        shelf = empty_shelf()
        entry = admit(shelf, _sequence("esprit"))
        self.assertFalse(entry["admitted"])
        self.assertEqual(shelf["cartouches"], {})

    def test_a_complete_sequence_is_one_symbol_and_admit_is_stable(self) -> None:
        shelf = empty_shelf()
        first = admit(shelf, _sequence("sealed"))
        second = admit(shelf, _sequence("sealed"))
        self.assertTrue(first["admitted"])
        self.assertEqual(first["cartouche_sha256"], PHASE1_SHA)
        self.assertEqual(
            first["symbols"],
            [
                "fxnA_dial",
                "fxnB_verify_human",
                "fxnC_transmit_request",
                "fxnE_confirm_slot",
                "fxnD_voicemail_fallback",
            ],
        )
        self.assertIs(first, second)
        self.assertEqual(len(shelf["cartouches"]), 1)

    def test_compose_reuses_the_lock_and_leaves_a_hole_where_none_is_admitted(self) -> None:
        shelf = empty_shelf()
        admit(shelf, _sequence("sealed"))
        frozen = json.dumps(shelf)
        image = _image(("make_the_call", PHASE1_SHA), ("unset", "0" * 64))
        result = compose(image, shelf)
        again = compose(image, shelf)
        self.assertFalse(result["complete"])
        self.assertTrue(result["symbols"][0]["admitted"])
        self.assertFalse(result["symbols"][1]["admitted"])
        self.assertEqual(result["image_sha256"], again["image_sha256"])
        self.assertNotEqual(result["image_sha256"], PHASE1_SHA)
        self.assertEqual(json.dumps(shelf), frozen)
        whole = compose(_image(("make_the_call", PHASE1_SHA)), shelf)
        self.assertTrue(whole["complete"])

    def test_cli_refuses_esprit_and_composes_the_sealed_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            sequence = root / "sequence.json"
            shelf = root / "cartouches.json"
            self.assertEqual(
                main(["sequence", str(spec), str(fixture_path("esprit")), "-o", str(sequence)]),
                2,
            )
            self.assertEqual(main(["admit", str(sequence), "-o", str(shelf)]), 2)
            self.assertFalse(shelf.exists())
            self.assertEqual(
                main(["sequence", str(spec), str(fixture_path("sealed")), "-o", str(sequence)]),
                0,
            )
            self.assertEqual(main(["admit", str(sequence), "-o", str(shelf)]), 0)
            image = root / "image.json"
            image.write_text(
                json.dumps(_image(("make_the_call", PHASE1_SHA))),
                encoding="utf-8",
            )
            out = root / "composition.json"
            before = shelf.read_text(encoding="utf-8")
            self.assertEqual(main(["compose", str(image), str(shelf), "-o", str(out)]), 0)
            self.assertEqual(shelf.read_text(encoding="utf-8"), before)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(body["complete"])
            self.assertEqual(body["symbols"][0]["lock"], PHASE1_SHA)


if __name__ == "__main__":
    unittest.main()

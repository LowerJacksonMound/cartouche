"""A signed-off clip is a signal lock. A near line is not, and an unsigned line is not."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import compute_signal_hash
from cartouche.cli import main
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary
from cartouche.domain import INTERACTION, domain_spec
from cartouche.resolve import resolve_phrase
from cartouche.tests.signoff import see_saved, see_shelf


def _signed(phrase: str) -> dict:
    dictionary, _report = LibraryFiller().fill(domain_spec(), empty_dictionary())
    base = Path(tempfile.mkdtemp())
    see_shelf(dictionary, base)
    approve(dictionary, INTERACTION, phrase, base)
    return dictionary


class ResolveTests(unittest.TestCase):
    def test_sign_off_writes_the_lock_and_unsigned_text_is_not_a_signal(self) -> None:
        phrase = "Yeah, this is Mike."
        dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        pending = next(clip for clip in report["clips"] if clip["phrase"] == phrase)
        self.assertIsNone(pending["signal_lock"])
        unsigned = resolve_phrase(domain_spec(), phrase, dictionary)
        self.assertEqual(unsigned["reason"], "unsigned")
        self.assertNotIn("signal_hash", unsigned)
        base = Path(tempfile.mkdtemp())
        see_shelf(dictionary, base)
        entry = approve(dictionary, INTERACTION, phrase, base)
        expected = compute_signal_hash("tok_human", phrase, "fxnB_verify_human")
        self.assertEqual(entry["signal_lock"], expected)
        locked = resolve_phrase(domain_spec(), f"  {phrase}  ", dictionary)
        self.assertTrue(locked["resolved"])
        self.assertEqual(locked["signal_lock"], expected)
        again = approve(dictionary, INTERACTION, phrase, base)
        self.assertEqual(again["signal_lock"], expected)

    def test_a_near_line_is_not_snapped_onto_a_signed_clip(self) -> None:
        dictionary = _signed("Yeah, this is Mike.")
        result = resolve_phrase(dictionary and domain_spec(), "Yeah, this is Michael.", dictionary)
        self.assertEqual(result["reason"], "off_script")
        self.assertNotIn("signal_lock", result)
        garage = resolve_phrase(domain_spec(), "Yeah, Dick's Garage, whaddya need?", dictionary)
        self.assertEqual(garage["reason"], "off_script")

    def test_one_surface_on_two_signals_is_ambiguous(self) -> None:
        spec = domain_spec()
        spec["b_roll_atoms"]["tok_other"] = {
            "phrase": "Dick's Automotive, how can I help you?",
            "clip_path": "clips/tok_other.mp4",
        }
        spec["nodes"]["n_other"] = {
            "token_id": "tok_other",
            "primitive_fxn": "fxn_other",
            "glyph_slot": 9,
            "is_edge_case": False,
            "branches": [],
        }
        result = resolve_phrase(spec, "Dick's Automotive, how can I help you?", empty_dictionary())
        self.assertEqual(result["reason"], "ambiguous")
        self.assertEqual(len(result["signals"]), 2)

    def test_cli_reads_the_shelf_and_does_not_write_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            shelf = root / "clip_dictionary.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(shelf)]), 0)
            out = root / "resolution.json"
            unsigned = main(
                ["resolve", str(spec), str(shelf), "--phrase", "Yeah, this is Mike.", "-o", str(out)]
            )
            self.assertEqual(unsigned, 2)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["reason"], "unsigned")
            see_saved(shelf, root)
            self.assertEqual(
                main(
                    [
                        "approve",
                        str(shelf),
                        "--interaction",
                        INTERACTION,
                        "--phrase",
                        "Yeah, this is Mike.",
                        "--base",
                        str(root),
                    ]
                ),
                0,
            )
            before = shelf.read_text(encoding="utf-8")
            code = main(
                ["resolve", str(spec), str(shelf), "--phrase", "Yeah, this is Mike.", "-o", str(out)]
            )
            self.assertEqual(code, 0)
            self.assertEqual(shelf.read_text(encoding="utf-8"), before)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(body["signal_lock"], compute_signal_hash("tok_human", "Yeah, this is Mike.", "fxnB_verify_human"))


if __name__ == "__main__":
    unittest.main()

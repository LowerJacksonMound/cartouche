"""A cartouche is compiled only from signed-off signal locks."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cli import main
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary
from cartouche.lock_build import lock_cartouche
from cartouche.domain import INTERACTION, domain_spec
from cartouche.tests.signoff import see_saved, see_shelf
from cartouche.tests.test_stitcher import PHASE1_SHA


def _signed_shelf() -> dict:
    dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
    base = Path(tempfile.mkdtemp())
    see_shelf(dictionary, base)
    for clip in report["clips"]:
        approve(dictionary, INTERACTION, clip["phrase"], base)
    return dictionary


class LockTests(unittest.TestCase):
    def test_an_open_shelf_does_not_compile(self) -> None:
        result = lock_cartouche(domain_spec(), empty_dictionary())
        self.assertFalse(result["locked"])
        self.assertEqual(len(result["open"]), 5)
        self.assertNotIn("cartouche", result)

    def test_signed_locks_compile_the_phone_cartouche(self) -> None:
        dictionary = _signed_shelf()
        frozen = json.dumps(dictionary)
        result = lock_cartouche(domain_spec(), dictionary)
        self.assertTrue(result["locked"])
        self.assertEqual(result["open"], [])
        self.assertEqual(result["cartouche"]["cartouche_sha256"], PHASE1_SHA)
        self.assertEqual(json.dumps(dictionary), frozen)

    def test_a_tampered_lock_is_not_a_cartouche(self) -> None:
        dictionary = _signed_shelf()
        entry = next(iter(dictionary["interactions"][INTERACTION].values()))
        entry["signal_lock"] = "0" * 16
        result = lock_cartouche(domain_spec(), dictionary)
        self.assertFalse(result["locked"])
        self.assertEqual(result["mismatched"], [entry["phrase_key"]])
        self.assertNotIn("cartouche", result)

    def test_cli_writes_the_cartouche_only_when_every_line_is_signed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            shelf = root / "clip_dictionary.json"
            out = root / "master_cartouche.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(shelf)]), 0)
            self.assertEqual(main(["lock", str(spec), str(shelf), "-o", str(out)]), 2)
            self.assertFalse(out.exists())
            see_saved(shelf, root)
            phrases = [
                clip["phrase"]
                for clip in json.loads(shelf.read_text(encoding="utf-8"))["interactions"][INTERACTION].values()
            ]
            for phrase in phrases:
                self.assertEqual(
                    main(["approve", str(shelf), "--interaction", INTERACTION, "--phrase", phrase, "--base", str(root)]),
                    0,
                )
            before = shelf.read_text(encoding="utf-8")
            self.assertEqual(main(["lock", str(spec), str(shelf), "-o", str(out)]), 0)
            self.assertEqual(shelf.read_text(encoding="utf-8"), before)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(body["cartouche_sha256"], PHASE1_SHA)


if __name__ == "__main__":
    unittest.main()

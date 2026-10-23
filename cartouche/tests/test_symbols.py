"""A part's sign is chosen from how many signal locks it holds. The same locks stay on that sign."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cli import main
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary
from cartouche.domain import INTERACTION, domain_spec, signal_track
from cartouche.symbols import SIGNS, assign_symbol, mark_cartouche
from cartouche.tests.signoff import see_saved, see_shelf
from cartouche.tests.test_stitcher import PHASE1_SHA


def _shelf() -> dict:
    dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
    base = Path(tempfile.mkdtemp())
    see_shelf(dictionary, base)
    for clip in report["clips"]:
        approve(dictionary, INTERACTION, clip["phrase"], base)
    return dictionary


class SymbolTests(unittest.TestCase):
    def test_the_same_locks_keep_the_same_sign(self) -> None:
        first = assign_symbol(["lock-b", "lock-a"])
        second = assign_symbol(["lock-a", "lock-b"])
        self.assertEqual(first, second)
        self.assertEqual(first["holds"], 2)
        self.assertIn(first["id"], {sign["id"] for sign in SIGNS if sign["holds"] == 2})
        self.assertEqual(assign_symbol(["only-one"])["id"], "D46")
        self.assertEqual(assign_symbol(["only-one"])["name"], "the hand")
        self.assertEqual(assign_symbol(["lock-a", "lock-b", "lock-c"])["holds"], 3)

    def test_four_functions_have_no_sign(self) -> None:
        with self.assertRaises(ValueError):
            assign_symbol(["a", "b", "c", "d"])

    def test_phone_parts_mark_from_the_signed_cartouche(self) -> None:
        master = CartoucheCompiler(signal_track()).compile_cartouche()
        self.assertEqual(master["cartouche_sha256"], PHASE1_SHA)
        marked = mark_cartouche(domain_spec(), master)
        holds = [band["holds"] for band in marked["cartouches"]]
        self.assertEqual(holds, [3, 2])
        self.assertEqual([band["id"] for band in marked["cartouches"]], ["G5", "G1"])
        ones = {sign["id"] for sign in SIGNS if sign["holds"] == 1}
        for band in marked["cartouches"]:
            self.assertTrue(all(item["id"] in ones for item in band["functions"]))

    def test_an_open_shelf_is_not_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            shelf = root / "clip_dictionary.json"
            out = root / "marks.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(shelf)]), 0)
            self.assertEqual(main(["mark", str(spec), str(shelf), "-o", str(out)]), 2)
            self.assertFalse(out.exists())
            see_saved(shelf, root)
            for entry in json.loads(shelf.read_text(encoding="utf-8"))["interactions"][INTERACTION].values():
                self.assertEqual(
                    main(["approve", str(shelf), "--interaction", INTERACTION, "--phrase", entry["phrase"], "--base", str(root)]),
                    0,
                )
            before = shelf.read_text(encoding="utf-8")
            self.assertEqual(main(["mark", str(spec), str(shelf), "-o", str(out)]), 0)
            self.assertEqual(shelf.read_text(encoding="utf-8"), before)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual([band["holds"] for band in body["cartouches"]], [3, 2])


if __name__ == "__main__":
    unittest.main()

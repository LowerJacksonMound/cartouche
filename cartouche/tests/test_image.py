"""The cartouche drawing is the signed signs, in order, and it does not name them."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cartouche_image import render_cartouche
from cartouche.cli import main
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary
from cartouche.domain import INTERACTION, domain_spec, signal_track
from cartouche.symbols import mark_cartouche
from cartouche.tests.signoff import see_saved


class ImageTests(unittest.TestCase):
    def test_the_rings_follow_the_marks_and_carry_no_names(self) -> None:
        master = CartoucheCompiler(signal_track()).compile_cartouche()
        marked = mark_cartouche(domain_spec(), master)
        image = render_cartouche(marked)
        again = render_cartouche(marked)
        self.assertEqual(image["svg"], again["svg"])
        self.assertEqual(
            [
                (band["seal"], band["name"], [sign["id"] for sign in band["signs"]])
                for band in image["cartouches"]
            ],
            [
                (band["id"], band["name"], [item["id"] for item in band["functions"]])
                for band in marked["cartouches"]
            ],
        )
        self.assertEqual([band["name"] for band in image["cartouches"]], ["the falcon", "the vulture"])
        self.assertIn("<title>the falcon</title>", image["svg"])
        self.assertIn("<title>the vulture</title>", image["svg"])
        lowered = image["svg"].lower()
        self.assertNotIn("dial", lowered)
        self.assertNotIn("appointment", lowered)

    def test_an_open_shelf_is_not_drawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            shelf = root / "clip_dictionary.json"
            out = root / "image.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(shelf)]), 0)
            self.assertEqual(main(["image", str(spec), str(shelf), "-o", str(out)]), 2)
            self.assertFalse(out.exists())
            see_saved(shelf, root)
            for entry in json.loads(shelf.read_text(encoding="utf-8"))["interactions"][INTERACTION].values():
                self.assertEqual(
                    main(["approve", str(shelf), "--interaction", INTERACTION, "--phrase", entry["phrase"], "--base", str(root)]),
                    0,
                )
            before = shelf.read_text(encoding="utf-8")
            self.assertEqual(main(["image", str(spec), str(shelf), "-o", str(out)]), 0)
            self.assertEqual(shelf.read_text(encoding="utf-8"), before)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual([band["seal"] for band in body["cartouches"]], ["G5", "G1"])


if __name__ == "__main__":
    unittest.main()

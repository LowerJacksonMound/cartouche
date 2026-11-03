"""Defects do not belong to one drawing. Any sign takes the same five."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.domain import signal_track
from cartouche.project_symbol import project_sign
from cartouche.symbols import assign_symbol
from cartouche.tests.test_stitcher import PHASE1_SHA


class ProjectTests(unittest.TestCase):
    def test_a_sign_is_sealed_or_not_on_any_sign(self) -> None:
        eye = assign_symbol(["a", "b", "c"])
        other = assign_symbol(["only-one"])
        self.assertNotEqual(eye["svg"], other["svg"])
        for sign in (eye, other):
            locked = project_sign(sign["svg"], 1.0, False)
            partial = project_sign(sign["svg"], 0.4, False)
            missing = project_sign(sign["svg"], 0.0, False)
            skew = project_sign(sign["svg"], 1.0, True)
            self.assertIn('stroke-dasharray="2 2"', locked)
            self.assertIn('color="#10b981"', locked)
            self.assertNotIn("feGaussianBlur", locked)
            self.assertNotIn("skewX", locked)
            self.assertNotIn("feGaussianBlur", partial)  # no in-between: below 1.0 draws as not sealed
            self.assertEqual(partial, project_sign(sign["svg"], 0.0, False))
            self.assertIn('color="#ef4444"', missing)
            self.assertIn('stroke-dasharray="4 3"', missing)
            self.assertNotIn("feGaussianBlur", missing)
            self.assertIn("skewX(8)", skew)

    def test_projecting_a_sign_does_not_move_the_lock(self) -> None:
        master = CartoucheCompiler(signal_track()).compile_cartouche()
        self.assertEqual(master["cartouche_sha256"], PHASE1_SHA)
        sign = assign_symbol([next(iter(master["sub_glyphs"].values()))["signal_hash"]])
        project_sign(sign["svg"], 0.4, True)
        again = CartoucheCompiler(signal_track()).compile_cartouche()
        self.assertEqual(again["cartouche_sha256"], PHASE1_SHA)


if __name__ == "__main__":
    unittest.main()

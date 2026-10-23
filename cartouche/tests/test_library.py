"""Library fill: one pending line per path step, reuse only after approval."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cli import main
from cartouche.clip_library import LibraryFiller, approve, empty_dictionary, view
from cartouche.domain import INTERACTION, domain_spec
from cartouche.tests.signoff import see_shelf


def _leaf(token: str, phrase: str) -> dict:
    return {
        "domain_id": "later_phone_app",
        "interaction": INTERACTION,
        "root_id": "a",
        "b_roll_atoms": {token: {"phrase": phrase, "clip_path": f"clips/{token}.mp4"}},
        "nodes": {
            "a": {
                "token_id": token,
                "primitive_fxn": "fxn_later",
                "glyph_slot": 0,
                "is_edge_case": False,
                "branches": [],
            }
        },
    }


class LibraryFillTests(unittest.TestCase):
    def test_every_path_gets_a_pending_line_and_nothing_is_covered(self) -> None:
        dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        self.assertEqual(report["interaction"], INTERACTION)
        self.assertEqual(report["counts"]["clips"], 5)
        self.assertEqual(report["counts"]["pending"], 5)
        self.assertEqual(report["counts"]["paths_covered"], 0)
        self.assertEqual(len(dictionary["interactions"][INTERACTION]), 5)
        self.assertFalse(report["paths"][0]["covered"])
        self.assertFalse(report["paths"][1]["covered"])

    def test_second_fill_does_not_duplicate(self) -> None:
        dictionary, _first = LibraryFiller().fill(domain_spec(), empty_dictionary())
        dictionary, again = LibraryFiller().fill(domain_spec(), dictionary)
        self.assertEqual(len(dictionary["interactions"][INTERACTION]), 5)
        self.assertEqual(again["counts"]["pending"], 5)

    def test_approved_line_is_reused_and_a_new_wording_is_not(self) -> None:
        phrase = "Yeah, this is Mike."
        dictionary, _report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        base = Path(tempfile.mkdtemp())
        see_shelf(dictionary, base)
        approve(dictionary, INTERACTION, phrase, base)
        dictionary, again = LibraryFiller().fill(_leaf("t_mike", phrase), dictionary)
        self.assertEqual(again["clips"][0]["status"], "reused")
        self.assertEqual(dictionary["interactions"][INTERACTION]["yeah, this is mike."]["domain_id"], domain_spec()["domain_id"])
        self.assertEqual(again["paths"][0]["covered"], True)
        self.assertEqual(len(dictionary["interactions"][INTERACTION]), 5)
        dictionary, extra = LibraryFiller().fill(
            _leaf("t_other", "Someone else is speaking."), dictionary
        )
        self.assertEqual(extra["clips"][0]["status"], "pending")
        self.assertEqual(len(dictionary["interactions"][INTERACTION]), 6)

    def test_path_covers_only_when_every_line_is_approved(self) -> None:
        dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        base = Path(tempfile.mkdtemp())
        see_shelf(dictionary, base)
        for clip in report["clips"]:
            approve(dictionary, INTERACTION, clip["phrase"], base)
        _dictionary, again = LibraryFiller().fill(domain_spec(), dictionary)
        # Signed off for this request: approved, not reused. Reused is a later request's word.
        self.assertEqual(again["counts"]["approved"], 5)
        self.assertEqual(again["counts"]["reused"], 0)
        self.assertEqual(again["counts"]["paths_covered"], 2)

    def test_an_edge_case_has_its_own_clip_even_when_the_words_match(self) -> None:
        spec = {
            "domain_id": "edge_words",
            "interaction": "talk",
            "root_id": "ask",
            "b_roll_atoms": {
                "t_ask": {"phrase": "Hold on.", "clip_path": "clips/ask.mp4"},
                "t_ok": {"phrase": "Go ahead.", "clip_path": "clips/ok.mp4"},
                "t_edge": {"phrase": "Hold on.", "clip_path": "clips/edge.mp4"},
            },
            "nodes": {
                "ask": {
                    "token_id": "t_ask",
                    "primitive_fxn": "fxn_ask",
                    "glyph_slot": 0,
                    "is_edge_case": False,
                    "branches": [{"target_node": "ok"}, {"target_node": "edge"}],
                },
                "ok": {
                    "token_id": "t_ok",
                    "primitive_fxn": "fxn_ok",
                    "glyph_slot": 1,
                    "is_edge_case": False,
                    "branches": [],
                },
                "edge": {
                    "token_id": "t_edge",
                    "primitive_fxn": "fxn_edge",
                    "glyph_slot": 2,
                    "is_edge_case": True,
                    "branches": [],
                },
            },
        }
        dictionary, report = LibraryFiller().fill(spec, empty_dictionary())
        self.assertEqual(report["counts"]["clips"], 3)
        edge = next(clip for clip in report["clips"] if clip["edge"])
        ordinary = next(clip for clip in report["clips"] if clip["phrase"] == "Hold on." and not clip["edge"])
        self.assertNotEqual(edge["clip_path"], ordinary["clip_path"])
        base = Path(tempfile.mkdtemp())
        self.assertEqual(approve(dictionary, "talk", "Hold on.", base)["reason"], "ambiguous")
        for clip, node in ((ordinary, "ask"), (edge, "edge")):
            path = base / clip["clip_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"clip")
            self.assertTrue(view(dictionary, "talk", "Hold on.", base, node_id=node)["seen"])
        approve(dictionary, "talk", "Hold on.", base, node_id="ask")
        _dictionary, again = LibraryFiller().fill(spec, dictionary)
        self.assertFalse(next(path for path in again["paths"] if path["is_edge_case"])["covered"])

    def test_an_empty_file_is_not_seen_and_a_replaced_file_is_not_the_sign_off(self) -> None:
        dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        phrase = report["clips"][0]["phrase"]
        base = Path(tempfile.mkdtemp())
        entry = dictionary["interactions"][INTERACTION][report["clips"][0]["phrase_key"]]
        path = base / entry["clip_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        from cartouche.clip_library import view, clip_holds

        self.assertFalse(view(dictionary, INTERACTION, phrase, base)["seen"])
        path.write_bytes(b"the clip that was seen")
        self.assertTrue(view(dictionary, INTERACTION, phrase, base)["seen"])
        path.write_bytes(b"a different clip")
        refused = approve(dictionary, INTERACTION, phrase, base)
        self.assertEqual(refused["reason"], "replaced")
        self.assertNotEqual(entry.get("status"), "approved")
        path.write_bytes(b"the clip that was seen")
        view(dictionary, INTERACTION, phrase, base)
        approve(dictionary, INTERACTION, phrase, base)
        path.write_bytes(b"replaced after sign-off")
        self.assertEqual(clip_holds(dictionary, base)[0]["reason"], "replaced")

    def test_unknown_phrase_is_not_approved(self) -> None:
        dictionary, _report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        with self.assertRaises(KeyError):
            approve(dictionary, INTERACTION, "This line was never on the chart.", Path("."))


class LibraryCliTests(unittest.TestCase):
    def test_fill_then_approve_writes_the_shelf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            out = root / "clip_dictionary.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(out)]), 0)
            phrase = "Yeah, this is Mike."
            self.assertEqual(
                main(["approve", str(out), "--interaction", INTERACTION, "--phrase", phrase, "--base", str(root)]),
                2,
            )
            shelf = json.loads(out.read_text(encoding="utf-8"))
            see_shelf(shelf, root)
            out.write_text(json.dumps(shelf), encoding="utf-8")
            self.assertEqual(
                main(["approve", str(out), "--interaction", INTERACTION, "--phrase", phrase, "--base", str(root)]),
                0,
            )
            shelf = json.loads(out.read_text(encoding="utf-8"))["interactions"][INTERACTION]
            approved = [entry for entry in shelf.values() if entry["status"] == "approved"]
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["phrase"], phrase)
            self.assertEqual(main(["fill", str(spec), "-o", str(out)]), 0)
            shelf = json.loads(out.read_text(encoding="utf-8"))["interactions"][INTERACTION]
            self.assertEqual(sum(1 for entry in shelf.values() if entry["status"] == "approved"), 1)


if __name__ == "__main__":
    unittest.main()

"""A covered shelf is the build input. An open path refuses, and the lock does not move."""

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
from cartouche.domain import INTERACTION, domain_spec
from cartouche.tests.signoff import see_saved, see_shelf
from cartouche.tests.test_stitcher import PHASE1_SHA


def _approve_all(dictionary: dict) -> None:
    _dictionary, report = LibraryFiller().fill(domain_spec(), dictionary)
    base = Path(tempfile.mkdtemp())
    see_shelf(dictionary, base)
    for clip in report["clips"]:
        approve(dictionary, INTERACTION, clip["phrase"], base)


class ReleaseTests(unittest.TestCase):
    def test_open_paths_refuse_and_the_lock_is_the_phone_hash(self) -> None:
        contract = release(domain_spec(), empty_dictionary())
        self.assertFalse(contract["released"])
        self.assertEqual(contract["cartouche_sha256"], PHASE1_SHA)
        self.assertEqual(contract["paths_covered"], 0)
        self.assertEqual(contract["paths"], 2)
        self.assertEqual(len(contract["blocks"]), 5)
        self.assertFalse(contract["files_present"])
        self.assertFalse(contract["rendered"])

    def test_one_open_path_still_refuses(self) -> None:
        dictionary, report = LibraryFiller().fill(domain_spec(), empty_dictionary())
        base = Path(tempfile.mkdtemp())
        see_shelf(dictionary, base)
        voicemail = "please leave a message after the tone."
        for clip in report["clips"]:
            if clip["phrase_key"] != voicemail:
                approve(dictionary, INTERACTION, clip["phrase"], base)
        contract = release(domain_spec(), dictionary)
        self.assertFalse(contract["released"])
        self.assertEqual(contract["paths_covered"], 1)
        self.assertEqual(contract["blocks"], [voicemail])
        self.assertEqual(contract["cartouche_sha256"], PHASE1_SHA)

    def test_covered_shelf_is_the_input_and_does_not_invent_files(self) -> None:
        dictionary = empty_dictionary()
        before = json.dumps(dictionary)
        _approve_all(dictionary)
        frozen = json.dumps(dictionary)
        contract = release(domain_spec(), dictionary)
        self.assertEqual(json.dumps(dictionary), frozen)
        self.assertNotEqual(before, frozen)
        self.assertTrue(contract["released"])
        self.assertEqual(contract["blocks"], [])
        self.assertEqual(len(contract["clips"]), 5)
        self.assertTrue(all(clip["status"] == "approved" for clip in contract["clips"]))
        self.assertTrue(all(clip["signal_lock"] for clip in contract["clips"]))
        self.assertFalse(contract["files_present"])
        self.assertFalse(contract["rendered"])
        self.assertEqual(contract["cartouche_sha256"], PHASE1_SHA)

    def test_a_line_signed_under_an_earlier_request_is_reused(self) -> None:
        dictionary = empty_dictionary()
        _approve_all(dictionary)
        shelf = dictionary["interactions"][INTERACTION]
        # The same entry, signed off under an earlier request on this shelf (or before the
        # request was recorded on it), comes back as reused. The lock does not move either way.
        shelf["yeah, this is mike."]["domain_id"] = "an_earlier_request"
        del shelf["please leave a message after the tone.::edge::fxnD_voicemail_fallback"]["domain_id"]
        contract = release(domain_spec(), dictionary)
        self.assertTrue(contract["released"])
        by_key = {clip["phrase_key"]: clip["status"] for clip in contract["clips"]}
        self.assertEqual(by_key["yeah, this is mike."], "reused")
        self.assertEqual(by_key["please leave a message after the tone."], "reused")
        self.assertEqual(by_key["dick's automotive, how can i help you?"], "approved")
        self.assertEqual(contract["cartouche_sha256"], PHASE1_SHA)

    def test_cli_open_release_names_the_blocking_lines_and_not_the_lock(self) -> None:
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            shelf = root / "clip_dictionary.json"
            out = root / "build_input.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(shelf)]), 0)
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                code = main(["release", str(spec), str(shelf), "-o", str(out)])
            self.assertEqual(code, 2)
            lines = captured.getvalue().splitlines()
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(lines[0], "released=false paths=0/2 files=false")
            self.assertEqual(lines[1:], [f"block: {line}" for line in body["blocks"]])
            self.assertEqual(len(body["blocks"]), 5)
            self.assertNotIn(PHASE1_SHA, captured.getvalue())
            self.assertEqual(body["cartouche_sha256"], PHASE1_SHA)

    def test_a_file_on_disk_is_seen_and_still_not_rendered(self) -> None:
        dictionary = empty_dictionary()
        _approve_all(dictionary)
        preview = release(domain_spec(), dictionary)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for clip in preview["clips"]:
                path = root / clip["clip_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"not a generated clip")
            contract = release(domain_spec(), dictionary, root)
        self.assertTrue(contract["released"])
        self.assertTrue(contract["files_present"])
        self.assertFalse(contract["rendered"])

    def test_cli_refuses_then_releases_without_moving_the_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            shelf = root / "clip_dictionary.json"
            out = root / "build_input.json"
            self.assertEqual(main(["fill", str(spec), "-o", str(shelf)]), 0)
            self.assertEqual(main(["release", str(spec), str(shelf), "-o", str(out)]), 2)
            first = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(first["released"])
            self.assertEqual(first["cartouche_sha256"], PHASE1_SHA)
            see_saved(shelf, root)
            for clip in first["clips"]:
                self.assertEqual(
                    main(
                        [
                            "approve",
                            str(shelf),
                            "--interaction",
                            INTERACTION,
                            "--phrase",
                            clip["phrase"],
                            "--base",
                            str(root),
                        ]
                    ),
                    0,
                )
            self.assertEqual(main(["release", str(spec), str(shelf), "-o", str(out)]), 0)
            second = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(second["released"])
            self.assertEqual(second["cartouche_sha256"], first["cartouche_sha256"])
            self.assertFalse(second["rendered"])


if __name__ == "__main__":
    unittest.main()

"""A session stays up for the build. A defect is reported and does not stop it."""

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
from cartouche.domain import INTERACTION, domain_spec, fixture_path
from cartouche.session import run_session, stop_path, watch_once
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


class SessionTests(unittest.TestCase):
    def test_a_defect_is_reported_and_the_session_is_still_running(self) -> None:
        state = watch_once(domain_spec(), _covered(), fixture_path("hazy"), fixture_path("hazy").parent)
        self.assertTrue(state["running"])
        self.assertFalse(state["sealed"])
        self.assertEqual(len(state["issues"]), 1)
        line = state["issues"][0]
        self.assertTrue(line.startswith("fault=template "), line)
        self.assertIn("function=fxnB_verify_human", line)
        self.assertIn("sign=the mouth", line)
        self.assertIn("detail=DEGENERATE_CONSTANT_RETURN", line)

    def test_a_drifted_request_is_reported_as_locked(self) -> None:
        drifted = json.loads(json.dumps(domain_spec()))
        drifted["b_roll_atoms"]["tok_human"]["phrase"] = "Yeah, this is Michael."
        state = watch_once(drifted, _covered(), fixture_path("sealed"), fixture_path("sealed").parent)
        self.assertTrue(state["running"])
        self.assertFalse(state["scanned"])
        self.assertEqual(state["reason"], "intent")
        self.assertTrue(state["issues"][0].startswith("fault=locked "), state["issues"])

    def test_nothing_written_yet_is_not_a_stop(self) -> None:
        state = watch_once(domain_spec(), _covered(), Path("/tmp/cartouche-no-such-build"), Path("."))
        self.assertTrue(state["running"])
        self.assertEqual(state["issues"], ["The build has not written anything yet."])

    def test_stop_ends_the_session_without_rewriting_the_contract(self) -> None:
        contract = _covered()
        before = json.dumps(contract)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "session.json"
            stop_path(session).write_text("stop\n", encoding="utf-8")
            code = run_session(
                domain_spec(),
                contract,
                fixture_path("sealed"),
                session,
                fixture_path("sealed").parent,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(code, 0)
            saved = json.loads(session.read_text(encoding="utf-8"))
            self.assertFalse(saved["running"])
            self.assertTrue(saved["sealed"])
            self.assertEqual(saved["issues"], [])
            self.assertEqual(saved["cartouche_sha256"], PHASE1_SHA)
        self.assertEqual(json.dumps(contract), before)

    def test_cli_will_not_start_an_unsigned_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec.json"
            contract_path = root / "contract.json"
            session = root / "session.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            contract_path.write_text(json.dumps(release(domain_spec(), empty_dictionary())), encoding="utf-8")
            code = main(
                ["start", str(spec), str(contract_path), str(fixture_path("sealed")), "--session", str(session)]
            )
            self.assertEqual(code, 2)
            self.assertFalse(session.exists())


if __name__ == "__main__":
    unittest.main()

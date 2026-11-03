"""The live cartouche: each sign fills as its function is written, and the page only reads."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.domain import domain_spec, fixture_path
from cartouche.live import live_view
from cartouche.page import PAGE, build_reader, session_reader
from cartouche.session import run_session, stop_path
from cartouche.tests.test_session import _covered

ORDER = ["fxnA_dial", "fxnB_verify_human", "fxnC_transmit_request", "fxnE_confirm_slot", "fxnD_voicemail_fallback"]


def _staged(count: int) -> str:
    """The sealed build, cut after its first `count` functions: what a writer has staged so far."""

    parts = fixture_path("sealed").read_text(encoding="utf-8").split("\ndef ")
    return "\ndef ".join(parts[: count + 1]) + "\n"


class LiveViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = domain_spec()
        self.contract = _covered()
        self.work = Path(tempfile.mkdtemp())
        self.target = self.work / "agent.py"

    def view(self, spec: dict | None = None) -> dict:
        return live_view(spec or self.spec, self.contract, self.target, self.work)

    def test_nothing_written_is_waiting_and_every_sign_is_a_ghost(self) -> None:
        view = self.view()
        self.assertEqual(view["state"], "waiting")
        self.assertEqual([row["fault"] for row in view["signs"]], [""] * 5)
        self.assertEqual(view["signs_sealed"], 0)
        self.assertIn('stroke-dasharray="2 2"', view["svg"])

    def test_signs_seal_one_at_a_time_as_functions_are_written(self) -> None:
        view: dict = {}
        for count in range(1, 6):
            self.target.write_text(_staged(count), encoding="utf-8")
            view = self.view()
            by_name = {row["function"]: row for row in view["signs"]}
            self.assertEqual(view["signs_sealed"], count, count)
            for name in ORDER[:count]:
                self.assertEqual(by_name[name]["fault"], "sealed", (count, name))
                self.assertEqual(by_name[name]["fidelity"], 1.0)
            for name in ORDER[count:]:
                self.assertEqual(by_name[name]["fault"], "missing", (count, name))
        self.assertEqual(view["state"], "sealed")
        self.assertTrue(view["sealed"])

    def test_a_seal_lights_only_when_its_ring_is_complete(self) -> None:
        ring = 'rx="40" fill="none" stroke="#10b981"'
        self.target.write_text(_staged(2), encoding="utf-8")
        self.assertEqual(self.view()["svg"].count(ring), 0)
        self.target.write_text(_staged(3), encoding="utf-8")
        svg = self.view()["svg"]
        self.assertEqual(svg.count(ring), 1)  # the first ring closes, the second does not
        self.target.write_text(_staged(5), encoding="utf-8")
        self.assertEqual(self.view()["svg"].count(ring), 2)

    def test_faults_land_on_the_sign_they_name(self) -> None:
        cases = {"shifted": ("fxnB_verify_human", "skew"), "hazy": ("fxnB_verify_human", "template")}
        for fixture, (name, word) in cases.items():
            self.target.write_text(fixture_path(fixture).read_text(encoding="utf-8"), encoding="utf-8")
            view = self.view()
            row = next(row for row in view["signs"] if row["function"] == name)
            self.assertEqual(row["fault"], word, fixture)
            self.assertEqual(view["state"], "open", fixture)
            self.assertTrue(row["lines"], fixture)

    def test_an_edited_request_is_locked_on_every_sign(self) -> None:
        self.target.write_text(_staged(5), encoding="utf-8")
        edited = json.loads(json.dumps(self.spec))
        token = next(iter(edited["b_roll_atoms"]))
        edited["b_roll_atoms"][token]["phrase"] += " (edited)"
        view = self.view(edited)
        self.assertEqual(view["state"], "locked")
        self.assertEqual({row["fault"] for row in view["signs"]}, {"locked"})

    def test_a_file_that_does_not_parse_is_syntax_not_a_miss(self) -> None:
        self.target.write_text("def fxnA_dial(:\n", encoding="utf-8")
        view = self.view()
        self.assertEqual(view["state"], "SYNTAX")
        self.assertEqual([row["fault"] for row in view["signs"]], [""] * 5)

    def test_each_row_carries_its_signed_line(self) -> None:
        phrases = {atom["phrase"] for atom in self.spec["b_roll_atoms"].values()}
        for row in self.view()["signs"]:
            self.assertIn(row["phrase"], phrases)
            self.assertTrue(row["sign"])

    def test_the_view_writes_nothing(self) -> None:
        self.target.write_text(_staged(3), encoding="utf-8")
        before = sorted(p.name for p in self.work.iterdir())
        self.view()
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), before)


class SessionRowsTests(unittest.TestCase):
    def test_the_session_file_carries_one_row_per_sign_and_the_drawing(self) -> None:
        work = Path(tempfile.mkdtemp())
        target, session = work / "agent.py", work / "session.json"
        target.write_text(_staged(5), encoding="utf-8")
        stop_path(session).write_text("", encoding="utf-8")  # one look, then stop
        run_session(domain_spec(), _covered(), target, session, work, interval=0.01)
        state = json.loads(session.read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "sealed")
        self.assertEqual(len(state["signs"]), 5)
        self.assertEqual(state["signs_sealed"], 5)
        self.assertTrue(state["svg"].startswith("<svg"))
        self.assertTrue(state["sealed"])


class PageTests(unittest.TestCase):
    def serve(self, read) -> str:
        from cartouche import page

        ready: list[str] = []
        thread = threading.Thread(target=page.serve, args=(read, 0, ready.append), daemon=True)
        thread.start()
        for _ in range(200):
            if ready:
                break
            threading.Event().wait(0.01)
        self.assertTrue(ready)
        return ready[0]

    def test_session_reader_waits_for_a_file_and_then_follows_it(self) -> None:
        session = Path(tempfile.mkdtemp()) / "session.json"
        read = session_reader(session)
        self.assertEqual(read()["state"], "waiting")
        session.write_text(json.dumps({"state": "open", "signs": [], "running": True}), encoding="utf-8")
        self.assertEqual(read()["state"], "open")

    def test_build_reader_looks_at_the_build(self) -> None:
        work = Path(tempfile.mkdtemp())
        spec, contract, target = work / "spec.json", work / "build_input.json", work / "agent.py"
        spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
        contract.write_text(json.dumps(_covered()), encoding="utf-8")
        read = build_reader(spec, contract, target, every=0.0)
        self.assertEqual(read()["state"], "waiting")
        target.write_text(_staged(5), encoding="utf-8")
        state = read()
        self.assertEqual(state["state"], "sealed")
        self.assertEqual(state["issues"], [])

    def test_the_page_serves_the_view_and_the_state_on_localhost(self) -> None:
        url = self.serve(lambda: {"state": "open", "signs": [], "svg": "<svg/>"})
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        with urllib.request.urlopen(url) as response:
            self.assertIn("CARTOUCHE", response.read().decode("utf-8"))
        with urllib.request.urlopen(url + "state.json") as response:
            self.assertEqual(json.loads(response.read())["state"], "open")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(url + "anything-else")

    def test_the_page_only_reads(self) -> None:
        self.assertNotIn("method:'POST'", PAGE)
        self.assertNotIn('method:"POST"', PAGE)


if __name__ == "__main__":
    unittest.main()

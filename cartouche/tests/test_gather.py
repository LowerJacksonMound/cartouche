"""Gather and sign-off: the agent offers candidates, the person signs one off, Cartouche locks it.

Offline: candidates come from local video files (source "file"), made with ffmpeg.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche import gather
from cartouche.domain import domain_spec
from cartouche.studio import Studio, serve_studio

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _video(path: Path, seconds: float = 2.0, colour: str = "0x204060") -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:d={seconds}:r=15",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


class ChartTests(unittest.TestCase):
    def test_a_good_chart_passes_and_names_its_signs(self) -> None:
        checked = gather.check_chart(domain_spec(), Path(tempfile.mkdtemp()))
        self.assertTrue(checked["ok"], checked["problems"])
        self.assertEqual(checked["lines"], 5)
        self.assertEqual(checked["functions"], 5)
        self.assertTrue(all(band["signs"] for band in checked["signs"]))

    def test_broken_charts_are_refused_with_plain_problems(self) -> None:
        spec = domain_spec()
        cases = {
            "missing root": lambda s: s.pop("root_id"),
            "branch to nowhere": lambda s: next(iter(s["nodes"].values())).setdefault("branches", []).append({"target_node": "nowhere"}),
            "token without a line": lambda s: s["b_roll_atoms"].pop(next(iter(s["b_roll_atoms"]))),
            "function without params": lambda s: s["primitive_params"].pop(next(iter(s["primitive_params"]))),
        }
        for name, breaks in cases.items():
            broken = json.loads(json.dumps(spec))
            breaks(broken)
            checked = gather.check_chart(broken, Path(tempfile.mkdtemp()))
            self.assertFalse(checked["ok"], name)
            self.assertTrue(checked["problems"], name)


class SubtitleTests(unittest.TestCase):
    def test_rolling_auto_captions_are_deduplicated(self) -> None:
        vtt = (
            "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\n<00:00:01.200><c>please</c> leave a message\n\n"
            "00:00:03.500 --> 00:00:05.000\nplease leave a message\nafter the tone\n"
        )
        cues = gather.parse_vtt(vtt)
        self.assertEqual([c["text"] for c in cues], ["please leave a message", "after the tone"])
        self.assertEqual(cues[1]["start"], 3.5)

    def test_small_words_do_not_count_as_a_match(self) -> None:
        cues = [{"start": 1.0, "end": 2.0, "text": "it is a good day"}, {"start": 9.0, "end": 10.0, "text": "leave a message after the tone"}]
        moments = gather._score(cues, set(gather._WORD.findall("leave message tone")) - gather._SMALL, 3)
        self.assertEqual([m["start"] for m in moments], [9.0])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to make test clips")
class OfferAndSignOffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp())
        self.spec_path = self.base / "spec.json"
        self.spec_path.write_text(json.dumps(domain_spec()), encoding="utf-8")
        self.spec = domain_spec()
        self.lines = gather.wanted(self.spec, self.base / "clip_dictionary.json", self.base)["lines"]
        self.src = Path(tempfile.mkdtemp())

    def offer_all(self) -> None:
        clips = []
        for k, line in enumerate(self.lines):
            for n in range(2):
                clip = _video(self.src / f"{k}_{n}.mp4", colour=f"0x{(k * 40) % 255:02x}{n * 90:02x}60")
                clips.append({"phrase": line["phrase"], "source": "file", "url": str(clip), "start": 0, "seconds": 1.5, "why": "test"})
        results = gather.offer_many(self.spec, self.base, clips)
        self.assertTrue(all(r["offered"] for r in results), [r.get("reason") for r in results])

    def test_wanted_reserves_every_slot(self) -> None:
        self.assertEqual(len(self.lines), 5)
        self.assertTrue(all(line["slot"] and line["status"] == "pending" for line in self.lines))
        self.assertTrue((self.base / "clip_dictionary.json").is_file())

    def test_offer_refuses_a_line_off_the_chart_and_anything_not_video(self) -> None:
        clip = _video(self.src / "a.mp4")
        self.assertFalse(gather.offer(self.spec, self.base, "a line nobody wrote", "file", str(clip))["offered"])
        text = self.src / "not.mp4"
        text.write_text("hello", encoding="utf-8")
        self.assertFalse(gather.offer(self.spec, self.base, self.lines[0]["phrase"], "file", str(text))["offered"])
        self.assertFalse(gather.offer(self.spec, self.base, self.lines[0]["phrase"], "file", str(clip), seconds=99)["offered"])

    def test_an_offer_records_where_it_came_from(self) -> None:
        clip = _video(self.src / "a.mp4")
        record = gather.offer(self.spec, self.base, self.lines[0]["phrase"], "file", str(clip), seconds=1.5, why="the shop")
        self.assertTrue(record["offered"])
        self.assertEqual(record["why"], "the shop")
        self.assertTrue((self.base / record["clip"]).is_file())
        self.assertEqual(len(gather.candidates(self.spec, self.base, self.lines[0]["phrase"])), 1)

    def test_sign_off_locks_the_chosen_bytes_then_release_then_watch(self) -> None:
        self.offer_all()
        studio = Studio(self.spec_path)
        self.assertEqual(studio.state()["stage"], "gather")
        self.assertFalse(studio.release()["released"])
        for line in self.lines:
            pick = gather.candidates(self.spec, self.base, line["phrase"])[1]
            answer = studio.sign_off(line["phrase"], pick["id"])
            self.assertTrue(answer["signed"], answer)
            slot = self.base / line["slot"]
            self.assertEqual(slot.read_bytes(), (self.base / pick["clip"]).read_bytes())
        self.assertEqual(studio.state()["stage"], "release")
        released = studio.release()
        self.assertTrue(released["released"], released)
        state = studio.state()
        self.assertEqual(state["stage"], "watch")
        self.assertEqual(state["watch"]["signs_total"], 5)
        self.assertFalse(studio.sign_off(self.lines[0]["phrase"], "anything")["signed"])

    def test_a_candidate_changed_after_it_was_offered_is_refused(self) -> None:
        self.offer_all()
        pick = gather.candidates(self.spec, self.base, self.lines[0]["phrase"])[0]
        (self.base / pick["clip"]).write_bytes(b"swapped")
        self.assertFalse(Studio(self.spec_path).sign_off(self.lines[0]["phrase"], pick["id"])["signed"])

    def test_the_page_serves_only_clip_files_and_refuses_cross_origin_posts(self) -> None:
        self.offer_all()
        studio = Studio(self.spec_path)
        ready: list[str] = []
        threading.Thread(target=serve_studio, args=(studio, 0, ready.append), daemon=True).start()
        for _ in range(200):
            if ready:
                break
            threading.Event().wait(0.01)
        url = ready[0]
        state = json.load(urllib.request.urlopen(url + "state.json"))
        clip = state["lines"][0]["candidates"][0]["clip"]
        self.assertEqual(urllib.request.urlopen(url + "media/" + clip).headers.get_content_type(), "video/mp4")
        for bad in ("media/spec.json", "media/../spec.json", "media/clip_dictionary.json"):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url + bad)
        request = urllib.request.Request(url + "release", data=b"{}", headers={"Origin": "http://evil.example", "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 403)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to make test clips")
class IncomingFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        import os

        self.os = os
        self.base = Path(tempfile.mkdtemp())
        self.spec_path = self.base / "spec.json"
        self.spec_path.write_text(json.dumps(domain_spec()), encoding="utf-8")
        self.spec = domain_spec()
        self.lines = gather.wanted(self.spec, self.base / "clip_dictionary.json", self.base)["lines"]

    def drop(self, line: dict, name: str, seconds: float = 2.0) -> Path:
        target = self.base / line["incoming"] / name
        _video(target, seconds)
        old = target.stat().st_mtime - 10  # settled, not still being written
        self.os.utime(target, (old, old))
        return target

    def test_wanted_makes_a_drop_folder_per_line_naming_the_line(self) -> None:
        for line in self.lines:
            folder = self.base / line["incoming"]
            self.assertTrue(folder.is_dir())
            self.assertIn(line["phrase"], (folder / "LINE.txt").read_text(encoding="utf-8"))
            self.assertEqual(folder.name, line["function"])

    def test_a_dropped_clip_becomes_a_candidate_once(self) -> None:
        line = self.lines[2]
        self.drop(line, "render_01.mp4")
        taken = gather.sweep_incoming(self.spec, self.base)
        self.assertEqual([t["offered"] for t in taken], [True])
        self.assertEqual(gather.sweep_incoming(self.spec, self.base), [])
        found = gather.candidates(self.spec, self.base, line["phrase"])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["dropped"], f"{line['incoming']}/render_01.mp4")
        self.assertIn("yours", found[0]["licence"])

    def test_a_sidecar_names_the_licence_and_why(self) -> None:
        line = self.lines[0]
        clip = self.drop(line, "scene.mp4")
        clip.with_suffix(".json").write_text(json.dumps({"why": "the shop at dawn", "licence": "rendered by us", "title": "scene 1"}), encoding="utf-8")
        gather.sweep_incoming(self.spec, self.base)
        found = gather.candidates(self.spec, self.base, line["phrase"])[0]
        self.assertEqual((found["why"], found["licence"], found["title"]), ("the shop at dawn", "rendered by us", "scene 1"))

    def test_a_file_still_being_written_waits_and_non_video_is_refused(self) -> None:
        line = self.lines[1]
        fresh = self.base / line["incoming"] / "fresh.mp4"
        _video(fresh)
        self.assertEqual(gather.sweep_incoming(self.spec, self.base), [])
        junk = self.base / line["incoming"] / "junk.mp4"
        junk.write_text("not a video", encoding="utf-8")
        old = junk.stat().st_mtime - 10
        self.os.utime(junk, (old, old))
        self.os.utime(fresh, (old, old))
        taken = {t["file"]: t["offered"] for t in gather.sweep_incoming(self.spec, self.base)}
        self.assertTrue(taken.get("fresh.mp4"))
        self.assertNotIn("junk.mp4", taken)  # not playable: recorded and skipped, never offered

    def test_the_page_offers_a_dropped_clip_on_its_next_poll_and_it_can_be_signed(self) -> None:
        studio = Studio(self.spec_path)
        line = self.lines[3]
        self.drop(line, "late.mp4")
        state = studio.state()
        row = next(l for l in state["lines"] if l["phrase"] == line["phrase"])
        self.assertEqual(len(row["candidates"]), 1)
        self.assertTrue(studio.sign_off(line["phrase"], row["candidates"][0]["id"])["signed"])


class TreeOrderTests(unittest.TestCase):
    def chart(self) -> dict:
        lines = [("a", False, ["b"]), ("b", False, ["c", "d", "e"]), ("c", False, ["f"]), ("d", True, ["g"]),
                 ("g", True, ["c"]), ("e", True, ["c"]), ("f", False, [])]
        spec = domain_spec()
        spec["root_id"] = "a"
        spec["nodes"] = {n: {"token_id": f"t_{n}", "primitive_fxn": f"fx_{n}", "glyph_slot": i, "is_edge_case": e,
                             "branches": [{"target_node": b} for b in br]} for i, (n, e, br) in enumerate(lines)}
        spec["b_roll_atoms"] = {f"t_{n}": {"phrase": f"line {n}", "clip_path": f"clips/{n}.mp4"} for n, _, _ in lines}
        spec["primitive_params"] = {f"fx_{n}": ["x"] for n, _, _ in lines}
        spec["primitive_invariants"] = {}
        return spec

    def test_main_path_first_then_alternatives_each_reply_under_its_line(self) -> None:
        spec = self.chart()
        lines = [{"node_id": n, "phrase": f"line {n}"} for n in spec["nodes"]]
        ordered = [line["node_id"] for line in gather.tree_order(spec, lines)]
        self.assertEqual(ordered, ["a", "b", "c", "d", "g", "e", "f"])
        by = {line["node_id"]: line for line in gather.tree_order(spec, lines)}
        self.assertEqual(by["d"]["instead_of"], "line c")
        self.assertIsNone(by["g"]["instead_of"])
        self.assertEqual(by["g"]["after"], ["line d"])

    def test_a_chart_of_more_than_nine_functions_gets_distinct_real_signs(self) -> None:
        from cartouche.symbols import ALL_SIGNS, SIGNS, assign_distinct

        named = [(f"fx_{i}", f"lock{i:02d}") for i in range(14)]
        chosen = assign_distinct(named)
        ids = [c["id"] for c in chosen.values()]
        self.assertEqual(len(set(ids)), 14)
        self.assertTrue(set(ids) <= {s["id"] for s in ALL_SIGNS})
        ten = assign_distinct(named[:9])
        original = {sign["id"] for sign in SIGNS if sign["holds"] == 1}
        self.assertEqual(len(original), 9)
        self.assertTrue(all(c["id"] in original for c in ten.values()))


class HeardTests(unittest.TestCase):
    """Only our lines are signed. What the other party may say rides on the branches, and the lock covers it."""

    def chart(self) -> dict:
        spec = json.loads(json.dumps(domain_spec()))
        for node in spec["nodes"].values():
            for k, branch in enumerate(node.get("branches", [])):
                branch["heard"] = f"they say {node['primitive_fxn']} {k}"
        return spec

    def lock(self, spec: dict) -> str:
        from cartouche.hold import refused_master

        return refused_master(spec, Path(tempfile.mkdtemp()))["cartouche_sha256"]

    def test_a_chart_without_heard_keeps_its_lock(self) -> None:
        self.assertEqual(self.lock(domain_spec()), "cd093843aefe1778ba3e8a43c951fb3fc2531ca7ff8632898c3d278acaf0c6f5")

    def test_heard_lines_are_part_of_the_lock(self) -> None:
        spec = self.chart()
        first = self.lock(spec)
        self.assertNotEqual(first, self.lock(domain_spec()))
        edited = json.loads(json.dumps(spec))
        branch = next(b for n in edited["nodes"].values() for b in n.get("branches", []))
        branch["heard"] += " (edited)"
        self.assertNotEqual(self.lock(edited), first)

    def test_once_heard_is_used_every_fork_must_name_it(self) -> None:
        spec = self.chart()
        fork = next(n for n in spec["nodes"].values() if len(n.get("branches", [])) > 1)
        del fork["branches"][0]["heard"]
        checked = gather.check_chart(spec, Path(tempfile.mkdtemp()))
        self.assertFalse(checked["ok"])
        self.assertIn("each needs heard", " ".join(checked["problems"]))

    def test_each_line_lists_what_they_might_say_next(self) -> None:
        spec = self.chart()
        base = Path(tempfile.mkdtemp())
        lines = gather.wanted(spec, base / "clip_dictionary.json", base)["lines"]
        root = next(line for line in lines if line["step"] == 1)
        self.assertTrue(root["heard_next"])
        self.assertTrue(all(h["heard"].startswith("they say") for h in root["heard_next"]))
        later = [line for line in lines if line["heard_before"]]
        self.assertTrue(later)


if __name__ == "__main__":
    unittest.main()


class SearchHoning(unittest.TestCase):
    def test_english_title_drops_other_scripts(self):
        from cartouche.gather import english_title
        self.assertTrue(english_title("How to play Minesweeper"))
        self.assertTrue(english_title("Café résumé: naïve façade — 100% ok!"))
        self.assertFalse(english_title("ドライブスルーで注文 take your time"))
        self.assertFalse(english_title("得来速 drive thru"))
        self.assertFalse(english_title("Как играть в сапёра"))

    def test_rank_by_moment_puts_best_match_first(self):
        from cartouche.gather import rank_by_moment
        hits = [{"url": "a"}, {"url": "b", "moments": [{"match": 0.5}]}, {"url": "c", "moments": [{"match": 0.9}, {"match": 0.2}]},
                {"url": "d", "moments": []}]
        self.assertEqual([h["url"] for h in rank_by_moment(hits)], ["c", "b", "a", "d"])


@unittest.skipUnless(HAVE_FFMPEG and shutil.which("say"), "ffmpeg and macOS say are needed to render a card")
class RenderCardTests(IncomingFolderTests):
    def test_render_missing_offers_a_card_for_each_empty_line_only(self) -> None:
        self.drop(self.lines[0], "found.mp4")
        gather.sweep_incoming(self.spec, self.base)
        rows = gather.render_missing(self.spec, self.base)
        self.assertEqual([r["phrase"] for r in rows], [l["phrase"] for l in self.lines[1:]])
        self.assertTrue(all(r["offered"] for r in rows), rows)
        found = gather.candidates(self.spec, self.base, self.lines[1]["phrase"])
        self.assertEqual(len(found), 1)
        self.assertIn("rendered", found[0]["why"])
        self.assertIn("yours", found[0]["licence"])
        self.assertGreater(found[0]["seconds"], 1.0)
        self.assertEqual(gather.render_missing(self.spec, self.base), [])  # nothing left empty

    def test_render_missing_refuses_a_phrase_not_in_the_request(self) -> None:
        with self.assertRaises(ValueError):
            gather.render_missing(self.spec, self.base, ["not a line"])


class ConstantReturnRule(unittest.TestCase):
    def info(self, src):
        import ast
        from cartouche.cartouche_scanner import ASTTopologyExtractor
        return ASTTopologyExtractor._audit_malformations(ast.parse(src).body[0])

    def test_one_literal_from_every_return_is_degenerate(self):
        self.assertTrue(self.info("def f(x):\n    if x:\n        return 'a'\n    return 'a'\n")["only_constant_returns"])
        self.assertTrue(self.info("def f(x):\n    return None\n")["only_constant_returns"])

    def test_labels_chosen_by_testing_a_parameter_are_not(self):
        src = ("def f(frame):\n    speech = frame['speech']\n    text = frame['text']\n"
               "    if 'tone' in text.lower():\n        return 'voicemail'\n    if speech and text:\n        return 'human'\n    return 'silence'\n")
        self.assertFalse(self.info(src)["only_constant_returns"])

    def test_labels_chosen_without_reading_a_parameter_are_degenerate(self):
        self.assertTrue(self.info("def f(x):\n    if True:\n        return 'a'\n    return 'b'\n")["only_constant_returns"])

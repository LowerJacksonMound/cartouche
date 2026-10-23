"""Phase-2 stitcher: path order, hashes, cycle guard, invariant passthrough."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import CartoucheCompiler, compute_signal_hash
from cartouche.cli import main
from cartouche.domain import EDGES, EXAMPLE_DIR, PHRASES, SLOTS, domain_spec, invariants, signal_track
from cartouche.signal_stitcher import SignalStitcher

PHASE1_SHA = "cd093843aefe1778ba3e8a43c951fb3fc2531ca7ff8632898c3d278acaf0c6f5"


def _atom(token: str, phrase: str) -> dict:
    return {"phrase": phrase, "clip_path": f"clips/{token}.mp4"}


def _node(token: str, fxn: str, slot: int, branches: list[str], edge: bool = False) -> dict:
    return {
        "token_id": token,
        "primitive_fxn": fxn,
        "glyph_slot": slot,
        "is_edge_case": edge,
        "branches": [{"target_node": target} for target in branches],
    }


class PhoneStitchTests(unittest.TestCase):
    def test_happy_path_precedes_edge_case(self) -> None:
        stitcher = SignalStitcher(domain_spec(), base_dir=EXAMPLE_DIR)
        raw = stitcher.extract_all_paths()
        self.assertEqual(raw, [["n0", "n1", "n2", "n3"], ["n0", "n1", "n_vm"]])
        track = signal_track()
        self.assertEqual(track["total_permutations"], 2)
        self.assertEqual(track["permutations"][0]["node_path"], ["n0", "n1", "n2", "n3"])
        self.assertFalse(track["permutations"][0]["is_edge_case"])
        self.assertEqual(track["permutations"][1]["node_path"], ["n0", "n1", "n_vm"])
        self.assertTrue(track["permutations"][1]["is_edge_case"])
        self.assertEqual(track["montage_status"], "skipped")

    def test_edges_hashes_slots_and_invariants_pass_through(self) -> None:
        track = signal_track()
        self.assertEqual(track["required_edges"], sorted(EDGES))
        self.assertEqual(track["glyph_slots"], SLOTS)
        self.assertEqual(track["primitive_params"]["fxnB_verify_human"], ["audio_frame"])
        self.assertEqual(track["primitive_invariants"], invariants())
        for name, (token, phrase) in PHRASES.items():
            self.assertEqual(
                track["required_primitives"][name],
                compute_signal_hash(token, phrase, name),
            )
        happy = track["permutations"][0]["signal_vector"]
        self.assertEqual(len(happy), 4)
        self.assertEqual(happy[0], track["required_primitives"]["fxnA_dial"])

    def test_cartouche_sha_is_unchanged(self) -> None:
        master = CartoucheCompiler(signal_track()).compile_cartouche()
        self.assertEqual(master["cartouche_sha256"], PHASE1_SHA)

    def test_track_is_stable_and_checked_in(self) -> None:
        self.assertEqual(signal_track(), signal_track())
        from cartouche.domain import write_checked_in_json

        write_checked_in_json()
        on_disk = json.loads(
            (EXAMPLE_DIR / "certified_signal_track.json").read_text(encoding="utf-8")
        )
        self.assertEqual(on_disk, signal_track())

    def test_concat_puts_edge_clip_last_and_skips_missing_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            track = SignalStitcher(domain_spec(), base_dir=EXAMPLE_DIR).compile_montage_and_signals(
                concat_list_path=out / "concat.txt",
                signal_track_path=out / "certified_signal_track.json",
                output_mp4_path=out / "rehearsal.mp4",
            )
            lines = (out / "concat.txt").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 7)
            self.assertTrue(lines[-1].endswith("tok_vm.mp4'"))
            self.assertNotIn("tok_vm.mp4", "\n".join(lines[:4]))
            self.assertEqual(track["montage_status"], "skipped_missing_clips")
            self.assertFalse((out / "rehearsal.mp4").exists())


class GuardTests(unittest.TestCase):
    def _spec(self, nodes: dict, root: str = "a") -> dict:
        atoms = {}
        for node in nodes.values():
            atoms[node["token_id"]] = _atom(node["token_id"], node["token_id"])
        return {
            "domain_id": "guard",
            "root_id": root,
            "b_roll_atoms": atoms,
            "nodes": nodes,
            "primitive_params": {},
            "primitive_invariants": {},
        }

    def test_cycle_does_not_hang_and_keeps_the_exit(self) -> None:
        nodes = {
            "a": _node("ta", "fxn_a", 0, ["b"]),
            "b": _node("tb", "fxn_b", 1, ["a", "c"]),
            "c": _node("tc", "fxn_c", 2, []),
        }
        paths = SignalStitcher(self._spec(nodes)).extract_all_paths()
        self.assertEqual(paths, [["a", "b", "c"]])

    def test_pure_cycle_ends_instead_of_looping(self) -> None:
        nodes = {
            "a": _node("ta", "fxn_a", 0, ["b"]),
            "b": _node("tb", "fxn_b", 1, ["a"]),
        }
        paths = SignalStitcher(self._spec(nodes)).extract_all_paths()
        self.assertEqual(paths, [["a", "b"]])

    def test_edge_case_sorts_after_a_longer_happy_path(self) -> None:
        nodes = {
            "a": _node("ta", "fxn_a", 0, ["b", "e"]),
            "b": _node("tb", "fxn_b", 1, ["c"]),
            "c": _node("tc", "fxn_c", 2, []),
            "e": _node("te", "fxn_e", 3, [], edge=True),
        }
        track = SignalStitcher(self._spec(nodes)).compile_montage_and_signals()
        self.assertEqual(
            [perm["node_path"] for perm in track["permutations"]],
            [["a", "b", "c"], ["a", "e"]],
        )
        self.assertFalse(track["permutations"][0]["is_edge_case"])
        self.assertTrue(track["permutations"][1]["is_edge_case"])

    def test_duplicate_slot_rejected(self) -> None:
        nodes = {
            "a": _node("ta", "fxn_a", 0, ["b"]),
            "b": _node("tb", "fxn_a", 1, []),
        }
        with self.assertRaises(ValueError):
            SignalStitcher(self._spec(nodes)).compile_montage_and_signals()

    def test_missing_ffmpeg_skips_when_clips_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            clip = base / "clips"
            clip.mkdir()
            (clip / "ta.mp4").write_bytes(b"not a movie")
            nodes = {"a": _node("ta", "fxn_a", 0, [])}
            track = SignalStitcher(self._spec(nodes), base_dir=base).compile_montage_and_signals(
                concat_list_path=base / "concat.txt",
                output_mp4_path=base / "out.mp4",
                ffmpeg_bin=None,
            )
            self.assertEqual(track["montage_status"], "skipped_no_ffmpeg")
            self.assertFalse((base / "out.mp4").exists())


class StitchCliTests(unittest.TestCase):
    def test_stitch_command_writes_track_and_concat(self) -> None:
        from cartouche.domain import write_checked_in_json

        write_checked_in_json()
        with tempfile.TemporaryDirectory() as tmp:
            code = main(
                ["stitch", str(EXAMPLE_DIR / "domain_spec.json"), "-o", tmp]
            )
            self.assertEqual(code, 0)
            track = json.loads((Path(tmp) / "certified_signal_track.json").read_text(encoding="utf-8"))
            self.assertEqual(track["total_permutations"], 2)
            self.assertTrue((Path(tmp) / "concat.txt").is_file())


if __name__ == "__main__":
    unittest.main()

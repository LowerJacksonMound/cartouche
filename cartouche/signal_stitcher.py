"""Compile a domain DAG into a certified signal track and an ffmpeg concat list."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from cartouche.cartouche_compiler import compute_signal_hash


class SignalStitcher:
    """Happy paths first, edge cases at the tail. The film is optional. The track is the lock."""

    def __init__(self, spec_data: dict[str, Any], base_dir: Path | None = None) -> None:
        self.domain_id: str = spec_data["domain_id"]
        self.b_roll_map: dict[str, dict[str, str]] = spec_data.get("b_roll_atoms", {})
        self.nodes: dict[str, dict[str, Any]] = spec_data["nodes"]
        self.root_id: str = spec_data["root_id"]
        self.primitive_params: dict[str, list[str]] = spec_data.get("primitive_params", {})
        self.primitive_invariants: dict[str, dict[str, Any]] = spec_data.get(
            "primitive_invariants", {}
        )
        self.base_dir = base_dir or Path.cwd()
        if self.root_id not in self.nodes:
            raise ValueError(f"root_id {self.root_id} is not a node")

    def extract_all_paths(self) -> list[list[str]]:
        """DFS root-to-leaf paths. A back-edge is dropped. If every branch cycles, the path ends."""
        paths: list[list[str]] = []
        stack: list[tuple[str, list[str]]] = [(self.root_id, [self.root_id])]
        while stack:
            curr_id, path = stack.pop()
            branches = self.nodes[curr_id].get("branches", [])
            pushed = False
            for branch in reversed(branches):
                next_id = branch["target_node"]
                if next_id in path:
                    continue
                if next_id not in self.nodes:
                    raise ValueError(f"branch target {next_id} is not a node")
                stack.append((next_id, path + [next_id]))
                pushed = True
            if not pushed:
                paths.append(path)
        return paths

    def _sorted_paths(self) -> list[list[str]]:
        paths = self.extract_all_paths()
        paths.sort(
            key=lambda node_path: (
                any(self.nodes[node_id].get("is_edge_case", False) for node_id in node_path),
                len(node_path),
            )
        )
        return paths

    def _clip_file(self, clip_path: str) -> Path:
        clip = Path(clip_path)
        if not clip.is_absolute():
            clip = self.base_dir / clip
        return clip.resolve()

    def compile_montage_and_signals(
        self,
        concat_list_path: Path | None = None,
        signal_track_path: Path | None = None,
        output_mp4_path: Path | None = None,
        ffmpeg_bin: str | None = "auto",
    ) -> dict[str, Any]:
        paths = self._sorted_paths()
        concat_lines: list[str] = []
        signal_sequences: list[dict[str, Any]] = []
        required_primitives: dict[str, str] = {}
        required_edges: set[tuple[str, str]] = set()
        glyph_slots: dict[str, int] = {}
        missing_clips: list[str] = []

        for path_idx, node_path in enumerate(paths):
            seq_signals: list[str] = []
            prev_fxn: str | None = None
            for node_id in node_path:
                node = self.nodes[node_id]
                token_id = node["token_id"]
                if token_id not in self.b_roll_map:
                    raise ValueError(f"node {node_id} token {token_id} has no b-roll atom")
                atom = self.b_roll_map[token_id]
                fxn_name = node["primitive_fxn"]
                if "glyph_slot" not in node:
                    raise ValueError(f"node {node_id} is missing glyph_slot")
                slot = node["glyph_slot"]
                if fxn_name in glyph_slots and glyph_slots[fxn_name] != slot:
                    raise ValueError(
                        f"glyph_slot conflict on {fxn_name}: {glyph_slots[fxn_name]} vs {slot}"
                    )
                glyph_slots[fxn_name] = slot
                sig_hash = compute_signal_hash(token_id, atom["phrase"], fxn_name)
                seq_signals.append(sig_hash)
                required_primitives[fxn_name] = sig_hash
                if prev_fxn and prev_fxn != fxn_name:
                    required_edges.add((prev_fxn, fxn_name))
                prev_fxn = fxn_name
                clip = self._clip_file(atom["clip_path"])
                if not clip.is_file():
                    missing_clips.append(clip.as_posix())
                concat_lines.append(f"file '{clip.as_posix()}'")
            signal_sequences.append(
                {
                    "permutation_index": path_idx,
                    "is_edge_case": any(
                        self.nodes[node_id].get("is_edge_case", False) for node_id in node_path
                    ),
                    "node_path": node_path,
                    "signal_vector": seq_signals,
                }
            )

        if concat_list_path is not None:
            concat_list_path.parent.mkdir(parents=True, exist_ok=True)
            concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        montage_status, rendered = self._render(
            concat_list_path, output_mp4_path, ffmpeg_bin, missing_clips
        )
        track = {
            "domain_id": self.domain_id,
            "total_permutations": len(paths),
            "required_primitives": required_primitives,
            "required_edges": sorted([list(edge) for edge in required_edges]),
            "glyph_slots": glyph_slots,
            "primitive_params": {key: list(value) for key, value in self.primitive_params.items()},
            "primitive_invariants": {
                key: dict(value) for key, value in self.primitive_invariants.items()
            },
            "permutations": signal_sequences,
            "montage_status": montage_status,
        }
        if signal_track_path is not None:
            signal_track_path.parent.mkdir(parents=True, exist_ok=True)
            signal_track_path.write_text(json.dumps(track, indent=2) + "\n", encoding="utf-8")
        if rendered:
            track["montage_path"] = str(output_mp4_path)
        return track

    def _render(
        self,
        concat_list_path: Path | None,
        output_mp4_path: Path | None,
        ffmpeg_bin: str | None,
        missing_clips: list[str],
    ) -> tuple[str, bool]:
        if output_mp4_path is None:
            return "skipped", False
        if missing_clips:
            return "skipped_missing_clips", False
        binary = shutil.which("ffmpeg") if ffmpeg_bin == "auto" else ffmpeg_bin
        if not binary:
            return "skipped_no_ffmpeg", False
        if concat_list_path is None:
            raise ValueError("output_mp4_path requires concat_list_path")
        cmd = [
            binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            str(output_mp4_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return "ffmpeg_failed", False
        return "rendered", True

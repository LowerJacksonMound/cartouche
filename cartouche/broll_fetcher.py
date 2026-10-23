"""Seek every visual the decision tree can reach, then look for its clip."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cartouche.signal_stitcher import SignalStitcher


def phrase_key(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


def shelf_key(phrase: str, visual: dict[str, Any]) -> str:
    """An edge case is its own clip even when the words are the same."""

    key = phrase_key(phrase)
    if visual.get("is_edge_case"):
        return f"{key}::edge::{visual['primitive_fxn']}"
    return key


def shelf_clip_path(interaction: str, key: str) -> str:
    """Where fill reserves a clip: library/<interaction>/<digest>.mp4, relative to the request."""

    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"library/{interaction}/{digest}.mp4"


class BRollFetcher:
    """A visual is sought only if some root-to-leaf path reaches it. Clips are not invented."""

    def __init__(
        self,
        spec_data: dict[str, Any],
        base_dir: Path | None = None,
        library: Path | None = None,
    ) -> None:
        self.spec = spec_data
        self.base_dir = base_dir or Path.cwd()
        self.library = library
        self.interaction: str = spec_data.get("interaction") or spec_data["domain_id"]
        self.nodes: dict[str, dict[str, Any]] = spec_data["nodes"]
        self.atoms: dict[str, dict[str, str]] = spec_data.get("b_roll_atoms", {})
        self.stitcher = SignalStitcher(spec_data, base_dir=self.base_dir)

    def rehearsal_paths(self) -> list[list[str]]:
        paths = self.stitcher.extract_all_paths()
        paths.sort(
            key=lambda node_path: (
                any(self.nodes[node_id].get("is_edge_case", False) for node_id in node_path),
                len(node_path),
            )
        )
        return paths

    def fetch(self) -> dict[str, Any]:
        seen: list[str] = []
        reached: set[str] = set()
        for node_path in self.rehearsal_paths():
            for node_id in node_path:
                if node_id in reached:
                    continue
                reached.add(node_id)
                seen.append(node_id)
        sought = [self._visual(node_id, seek=True) for node_id in seen]
        unreached = [
            self._visual(node_id, seek=False)
            for node_id in self.nodes
            if node_id not in reached
        ]
        counts = {
            "sought": len(sought),
            "found": sum(1 for item in sought if item["status"] == "found"),
            "missing": sum(1 for item in sought if item["status"] == "missing"),
            "undeclared": sum(1 for item in sought if item["status"] == "undeclared"),
            "unreached": len(unreached),
        }
        return {
            "domain_id": self.spec["domain_id"],
            "sought": sought,
            "unreached": unreached,
            "counts": counts,
        }

    def write(self, path: Path) -> dict[str, Any]:
        report = self.fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    def _visual(self, node_id: str, seek: bool) -> dict[str, Any]:
        node = self.nodes[node_id]
        token_id = node["token_id"]
        atom = self.atoms.get(token_id)
        status, clip = ("unreached", None)
        if seek:
            status, clip = self._resolve(token_id, atom, node)
        return {
            "node_id": node_id,
            "token_id": token_id,
            "phrase": "" if atom is None else atom.get("phrase", ""),
            "primitive_fxn": node["primitive_fxn"],
            "is_edge_case": bool(node.get("is_edge_case", False)),
            "decides": [branch["target_node"] for branch in node.get("branches", [])],
            "status": status,
            "clip_path": clip,
        }

    def _resolve(
        self, token_id: str, atom: dict[str, str] | None, node: dict[str, Any]
    ) -> tuple[str, str | None]:
        declared = None if atom is None else atom.get("clip_path")
        if declared:
            declared_path = self._abs(declared)
            if declared_path.is_file():
                return "found", declared_path.as_posix()
        phrase = "" if atom is None else atom.get("phrase", "")
        if phrase:
            # The path fill reserves and view/approve read: the shelf, beside the request.
            shelved = self._abs(shelf_clip_path(self.interaction, shelf_key(phrase, node)))
            if shelved.is_file():
                return "found", shelved.as_posix()
        if self.library is not None:
            library_path = (self.library / f"{token_id}.mp4").resolve()
            if library_path.is_file():
                return "found", library_path.as_posix()
        if atom is None:
            return "undeclared", None
        if declared:
            return "missing", self._abs(declared).as_posix()
        return "missing", None

    def _abs(self, clip_path: str) -> Path:
        clip = Path(clip_path)
        if not clip.is_absolute():
            clip = self.base_dir / clip
        return clip.resolve()

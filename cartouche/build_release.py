"""Release a covered shelf as the build input. The intent hash does not move."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.clip_library import LibraryFiller
from cartouche.signal_stitcher import SignalStitcher
import hashlib

_USABLE = {"approved", "reused"}


def release(
    spec_data: dict[str, Any],
    dictionary: dict[str, Any],
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Read the shelf. Do not approve lines, invent files, or render a montage."""

    base = base_dir or Path(".")
    track = SignalStitcher(spec_data, base_dir=base).compile_montage_and_signals()
    master = CartoucheCompiler(track).compile_cartouche()
    working = json.loads(json.dumps(dictionary))
    _dictionary, report = LibraryFiller().fill(spec_data, working)
    clips = []
    for clip in report["clips"]:
        clip_path = clip["clip_path"]
        present = bool(clip_path) and (base / clip_path).is_file()
        clips.append(
            {
                "phrase_key": clip["phrase_key"],
                "phrase": clip["phrase"],
                "status": clip["status"],
                "clip_path": clip_path,
                "file_present": present,
                "signal_lock": clip.get("signal_lock"),
            }
        )
    blocks = sorted(clip["phrase_key"] for clip in clips if clip["status"] not in _USABLE)
    path_count = report["counts"]["paths"]
    covered = report["counts"]["paths_covered"]
    released = path_count > 0 and covered == path_count and not blocks
    chosen = [clip for clip in clips if clip["status"] in _USABLE] if released else clips
    return {
        "released": released,
        "domain_id": master["domain_id"],
        "cartouche_sha256": master["cartouche_sha256"],
        "interaction": report["interaction"],
        "paths_covered": covered,
        "paths": path_count,
        "blocks": [] if released else blocks,
        "clips": chosen,
        "files_present": bool(chosen) and all(clip["file_present"] for clip in chosen),
        "rendered": False,
        "closer": closer_lock(spec_data.get("closer")),
    }


def closer_lock(closer: dict[str, Any] | None) -> dict[str, Any] | None:
    """The spec's CLOSER block with its plan hash, computed as closer_mcp.plan does. None when the spec has none."""

    if closer is None:
        return None
    contracts = []
    for i, c in enumerate(closer.get("contracts") or []):
        if not isinstance(c, dict) or not {"file", "name", "params", "checks"} <= set(c):
            raise ValueError(f"contract {i}: needs file, name, params and checks")
        contracts.append({**c, "kind": c.get("kind", "def")})
    rec = {
        "intent": str(closer.get("intent", "")).strip(),
        "expectation": str(closer.get("expectation", "")).strip(),
        "contracts": contracts,
    }
    sha = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    return {**closer, **rec, "sha256": sha}

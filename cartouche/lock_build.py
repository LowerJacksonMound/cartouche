"""Compile a cartouche only from clips the user has signed off."""

from __future__ import annotations

import json
from typing import Any

from cartouche.cartouche_compiler import CartoucheCompiler, compute_signal_hash
from cartouche.clip_library import LibraryFiller
from cartouche.signal_stitcher import SignalStitcher


def lock_cartouche(spec_data: dict[str, Any], dictionary: dict[str, Any]) -> dict[str, Any]:
    """Return the master cartouche, or the lines that are not signed off. Do not invent a partial one."""

    working = json.loads(json.dumps(dictionary))
    working, report = LibraryFiller().fill(spec_data, working)
    shelf = working["interactions"][report["interaction"]]
    open_lines: list[str] = []
    mismatched: list[str] = []
    locks: dict[str, str] = {}
    for clip in report["clips"]:
        entry = shelf.get(clip.get("shelf_key") or clip["phrase_key"])
        lock = None if entry is None else entry.get("signal_lock")
        if entry is None or entry.get("status") != "approved" or not lock:
            open_lines.append(clip["phrase_key"])
            continue
        expected = compute_signal_hash(entry["token_id"], entry["phrase"], entry["primitive_fxn"])
        if lock != expected:
            mismatched.append(clip["phrase_key"])
            continue
        locks[entry["primitive_fxn"]] = lock
    if open_lines or mismatched:
        return {
            "locked": False,
            "open": sorted(open_lines),
            "mismatched": sorted(mismatched),
        }
    track = SignalStitcher(spec_data).compile_montage_and_signals()
    master = CartoucheCompiler(track).compile_cartouche()
    chart = {name: glyph["signal_hash"] for name, glyph in master["sub_glyphs"].items()}
    if chart != locks:
        drifted = sorted(set(chart) ^ set(locks))
        return {"locked": False, "open": drifted, "mismatched": []}
    return {
        "locked": True,
        "open": [],
        "mismatched": [],
        "cartouche": master,
    }

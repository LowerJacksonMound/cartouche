"""Bind a request to the certified phrases. A mismatch does not mint a new lock."""

from __future__ import annotations

from typing import Any

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.signal_stitcher import SignalStitcher


def instantiate(spec_data: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    certified = spec_data.get("parameters")
    if not isinstance(certified, dict) or not certified:
        raise ValueError("spec has no parameters")
    phrases = [atom["phrase"] for atom in spec_data["b_roll_atoms"].values()]
    for key, value in certified.items():
        if not isinstance(value, str) or not any(value in phrase for phrase in phrases):
            raise ValueError(f"parameter {key} is not in the certified phrases")
    unknown = sorted(key for key in request if key not in certified)
    mismatches = [key for key, value in certified.items() if request.get(key) != value]
    track = SignalStitcher(spec_data).compile_montage_and_signals()
    master = CartoucheCompiler(track).compile_cartouche()
    return {
        "held": not mismatches and not unknown,
        "mismatches": mismatches,
        "unknown": unknown,
        "parameters": dict(certified),
        "cartouche_sha256": master["cartouche_sha256"],
    }

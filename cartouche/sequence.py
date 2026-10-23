"""Pack a certified path into cartouches and check that a file follows that order."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from cartouche.signal_stitcher import SignalStitcher

DEFAULT_CAPACITY = 3


def symbol_order(spec_data: dict[str, Any]) -> list[str]:
    """Happy path first, then tail symbols that only the edge paths use."""

    stitcher = SignalStitcher(spec_data)
    order: list[str] = []
    seen: set[str] = set()
    for node_path in stitcher._sorted_paths():
        for node_id in node_path:
            name = stitcher.nodes[node_id]["primitive_fxn"]
            if name not in seen:
                seen.add(name)
                order.append(name)
    return order


def pack_cartouches(spec_data: dict[str, Any]) -> list[dict[str, Any]]:
    capacity = spec_data.get("cartouche_capacity", DEFAULT_CAPACITY)
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("cartouche_capacity must be an integer >= 1")
    order = symbol_order(spec_data)
    bands = []
    for index, start in enumerate(range(0, len(order), capacity)):
        symbols = order[start : start + capacity]
        bands.append({"order": index, "symbols": symbols})
    return bands


def _defined(target: Path) -> dict[str, int]:
    tree = ast.parse(target.read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in found:
            found[node.name] = node.lineno
    return found


def project_sequence(
    spec_data: dict[str, Any],
    master: dict[str, Any],
    report: dict[str, Any],
    target: Path,
) -> dict[str, Any]:
    """Read the file. Do not change the cartouche hash."""

    defined = _defined(target)
    diagnostics = report["glyph_diagnostics"]
    bands = []
    flat: list[str] = []
    for band in pack_cartouches(spec_data):
        symbols = []
        for name in band["symbols"]:
            flat.append(name)
            fidelity = diagnostics.get(name, {}).get("fidelity", 0.0)
            symbols.append(
                {
                    "name": name,
                    "fidelity": fidelity,
                    "present": name in defined,
                }
            )
        bands.append(
            {
                "order": band["order"],
                "sealed": all(item["fidelity"] == 1.0 for item in symbols),
                "symbols": symbols,
            }
        )
    present = [name for name in flat if name in defined]
    by_line = sorted(present, key=lambda name: defined[name])
    seen_open = False
    jumped = False
    for band in bands:
        if band["sealed"]:
            jumped = jumped or seen_open
        else:
            seen_open = True
    order_held = by_line == present and not jumped
    sealed_count = sum(1 for band in bands if band["sealed"])
    return {
        "order_held": order_held,
        "complete": order_held and sealed_count == len(bands) and len(bands) > 0,
        "capacity": spec_data.get("cartouche_capacity", DEFAULT_CAPACITY),
        "cartouche_sha256": master["cartouche_sha256"],
        "sealed_count": sealed_count,
        "cartouche_count": len(bands),
        "cartouches": bands,
    }

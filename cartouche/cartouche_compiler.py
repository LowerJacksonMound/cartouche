"""Compile a certified signal track into a cartouche and a sign projection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from cartouche.project_symbol import project_sign
from cartouche.symbols import SIGNS, assign_distinct

_FXN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def compute_signal_hash(token_id: str, phrase: str, primitive_fxn: str) -> str:
    payload = f"{token_id}::{phrase.strip().lower()}::{primitive_fxn}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _xml_text(value: str) -> str:
    amp, lt, gt = "&" + "amp;", "&" + "lt;", "&" + "gt;"
    return value.replace("&", amp).replace("<", lt).replace(">", gt)


class CartoucheCompiler:
    """Maps a signal track onto bitmask slots, invariants, and sign names."""

    def __init__(self, signal_track: dict[str, Any]) -> None:
        self.signal_track = signal_track

    def compile_cartouche(self, output_path: Path | None = None) -> dict[str, Any]:
        primitives: dict[str, str] = self.signal_track["required_primitives"]
        slots: dict[str, int] = self.signal_track["glyph_slots"]
        params: dict[str, list[str]] = self.signal_track.get("primitive_params", {})
        invariant_map: dict[str, dict[str, Any]] = self.signal_track.get(
            "primitive_invariants", {}
        )

        if set(slots) != set(primitives):
            raise ValueError("glyph_slots must name exactly the required primitives")

        used: dict[int, str] = {}
        for fxn_name, slot in slots.items():
            if not _FXN_NAME.match(fxn_name):
                raise ValueError(f"primitive name is not SVG-id safe: {fxn_name}")
            if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
                raise ValueError(f"glyph_slot for {fxn_name} must be an integer >= 0")
            if slot in used:
                raise ValueError(
                    f"duplicate glyph_slot {slot} on {fxn_name} and {used[slot]}"
                )
            used[slot] = fxn_name

        known = set(primitives)
        edges: list[list[str]] = []
        for edge in self.signal_track["required_edges"]:
            if len(edge) != 2 or edge[0] not in known or edge[1] not in known:
                raise ValueError(f"required edge is not a pair of primitives: {edge}")
            edges.append([edge[0], edge[1]])
        edges.sort()

        sub_glyphs: dict[str, dict[str, Any]] = {}
        full_bitmask = 0
        distinct = assign_distinct([(fxn_name, primitives[fxn_name]) for fxn_name in used.values()])
        for slot, fxn_name in sorted(used.items()):
            bit_flag = 1 << slot
            full_bitmask |= bit_flag
            sign = distinct[fxn_name]
            inv = invariant_map.get(fxn_name, {})
            sub_glyphs[fxn_name] = {
                "bit_index": slot,
                "bit_mask": bit_flag,
                "signal_hash": primitives[fxn_name],
                "sign_id": sign["id"],
                "sign_name": sign["name"],
                "required_invariants": {
                    "min_ast_nodes": inv.get("min_ast_nodes", 4),
                    "forbid_bare_except": inv.get("forbid_bare_except", True),
                    "forbid_constant_return": inv.get("forbid_constant_return", True),
                    "required_params": list(params.get(fxn_name, [])),
                },
            }

        canonical_payload = json.dumps(
            {
                "domain_id": self.signal_track["domain_id"],
                "sub_glyphs": sub_glyphs,
                "required_edges": edges,
            },
            sort_keys=True,
        )
        cartouche_sha256 = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        master_cartouche = {
            "domain_id": self.signal_track["domain_id"],
            "cartouche_sha256": cartouche_sha256,
            "expected_full_bitmask": full_bitmask,
            "sub_glyphs": sub_glyphs,
            "required_edges": edges,
        }
        if output_path is not None:
            output_path.write_text(
                json.dumps(master_cartouche, indent=2), encoding="utf-8"
            )
        return master_cartouche

    @staticmethod
    def render_svg(
        master_cartouche: dict[str, Any],
        glyph_diagnostics: dict[str, dict[str, Any]],
        broken_edges: list[list[str]],
        svg_path: Path | None = None,
    ) -> str:
        """The same five defects, drawn on each sign."""
        broken_callers = {edge[0] for edge in broken_edges}
        parts: list[str] = []
        for index, (fxn_name, meta) in enumerate(master_cartouche["sub_glyphs"].items()):
            diag = glyph_diagnostics[fxn_name]
            fidelity = diag["fidelity"]
            sign = next(item for item in SIGNS if item["id"] == meta["sign_id"])
            drawn = project_sign(sign["svg"], fidelity, fxn_name in broken_callers)
            fault_text = ", ".join(diag["faults"]) or "None"
            title = _xml_text(f"{fxn_name} | Fidelity: {fidelity:.2f} | Faults: {fault_text}")
            body = drawn.split(">", 1)[1].rsplit("</svg>", 1)[0]
            parts.append(
                f'<g transform="translate(0,{index * 88})"><title>{title}</title>{body}</g>'
            )
        height = max(88, 88 * len(parts))
        total_residual = sum(1.0 - d["fidelity"] for d in glyph_diagnostics.values()) + len(broken_edges)
        if total_residual == 0.0:
            status_color = "#10b981"
        elif total_residual < 1.5:
            status_color = "#f59e0b"
        else:
            status_color = "#ef4444"
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 {height + 24}">'
            f"{''.join(parts)}"
            f'<text x="4" y="{height + 16}" fill="{status_color}" font-family="monospace" font-size="9">'
            f"Projection Residual: {total_residual:.2f} | Edge Faults: {len(broken_edges)}</text>"
            f"</svg>"
        )
        if svg_path is not None:
            svg_path.write_text(svg, encoding="utf-8")
        return svg

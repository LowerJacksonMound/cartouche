"""The cartouche as it stands right now: each sign drawn as far as its function is written.

The glyph is the release's own: the same parts, seals and signs `cartouche image` draws. Each sign is
drawn by `project_sign` at the function's fidelity from the same scan `hold` runs, so a sign fills
in as the function it stands for is written. A seal lights when every sign in its ring is sealed.
Nothing here writes the build, the request, or the release.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cartouche.cartouche_image import render_cartouche
from cartouche.hold import hold_tree, refused_master
from cartouche.project_symbol import DEFECTS, LOCKED, SYNTAX, issues_of, project_sign
from cartouche.symbols import mark_cartouche

SEALED = "sealed"
SKEW_WORD = "skew"
# when one function has more than one fault, the row names the one to fix first
_RANK = {word: index for index, word in enumerate(("missing", "locked", "skew"))}
_RING_ON, _RING_OFF = "#10b981", "#30363d"


def _phrases(spec_data: dict[str, Any]) -> dict[str, str]:
    atoms = spec_data.get("b_roll_atoms") or {}
    found: dict[str, str] = {}
    for node in (spec_data.get("nodes") or {}).values():
        name, token = node.get("primitive_fxn"), node.get("token_id")
        if name and token in atoms and name not in found:
            found[name] = atoms[token].get("phrase", "")
    return found


def _ghost(svg: str) -> str:
    """The sign's outline only: nothing is judged yet."""

    head, rest = svg.split(">", 1)
    inner = rest.rsplit("</svg>", 1)[0]
    head = head.replace('viewBox="0 0 64 64"', 'viewBox="-8 -10 80 84"')
    return (
        f'{head}><g color="#30363d" fill="none" stroke="currentColor" stroke-width="0.9" '
        f'stroke-dasharray="2 2" opacity="0.85">{inner}</g></svg>'
    )


def _own_ids(svg: str, key: str) -> str:
    """project_sign names its blur `haze`; many signs share one page, so each gets its own id."""

    return svg.replace('id="haze"', f'id="haze-{key}"').replace("url(#haze)", f"url(#haze-{key})")


def live_view(
    spec_data: dict[str, Any], contract: dict[str, Any], target: Path, base_dir: Path | None = None
) -> dict[str, Any]:
    """One look, drawn. `signs` has a row per function; `svg` is the cartouche as it stands."""

    base = base_dir or Path(".")
    probe = hold_tree(spec_data, contract, target, base)
    master = refused_master(spec_data, base)
    marked = mark_cartouche(spec_data, master)
    phrases = _phrases(spec_data)
    scan = probe.get("scan") or {}
    reason = probe.get("reason")
    judged = bool(probe.get("scanned")) and not scan.get("waiting")
    diagnostics = scan.get("glyph_diagnostics") or {}
    broken = {edge[0] for edge in scan.get("broken_edges") or []}
    rows_by_fault: dict[str, dict[str, Any]] = {}
    syntax = False
    for row in issues_of(scan) if judged else []:
        if row["fault"] == SYNTAX:
            syntax = True
            continue
        name = row.get("function")
        if name and (name not in rows_by_fault or _RANK.get(row["fault"], 9) < _RANK.get(rows_by_fault[name]["fault"], 9)):
            rows_by_fault[name] = row
    signs: list[dict[str, Any]] = []
    rings: list[str] = []
    drawn_bands = []
    for band in marked["cartouches"]:
        functions = []
        band_sealed = True
        for function in band["functions"]:
            name = function["function"]
            fidelity = float(diagnostics.get(name, {}).get("fidelity", 0.0)) if judged else 0.0
            issue = rows_by_fault.get(name)
            if reason == "intent":
                word = LOCKED
            elif not judged or syntax:
                word = ""
            elif issue is not None:
                word = issue["fault"]
            else:
                # no row: sealed. A stub or fake-shaped body is CLOSER's (2026-11-11); fidelity still draws the sign.
                word = SKEW_WORD if name in broken else SEALED
            band_sealed = band_sealed and word == SEALED
            svg = (
                project_sign(function["svg"], fidelity, name in broken)
                if judged and not syntax and reason != "intent"
                else _ghost(function["svg"])
            )
            functions.append({**function, "svg": _own_ids(svg, function["id"])})
            signs.append(
                {
                    "function": name,
                    "sign_id": function["id"],
                    "sign": function["name"],
                    "part": band["name"],
                    "phrase": phrases.get(name, ""),
                    "fidelity": round(fidelity, 3),
                    "fault": word,
                    "lines": issue.get("lines") if issue else None,
                    "detail": issue.get("detail") if issue else None,
                    "file": issue.get("file") if issue else None,
                }
            )
        seal = project_sign(band["svg"], 1.0, False) if band_sealed else _ghost(band["svg"])
        drawn_bands.append({**band, "svg": _own_ids(seal, f"seal-{band['order']}"), "functions": functions})
        rings.append(_RING_ON if band_sealed else _RING_OFF)
    image = render_cartouche({"cartouches": drawn_bands}, ring_colors=rings)
    if reason == "intent":
        state = LOCKED
    elif reason == "unreleased":
        state = "unreleased"
    elif not judged:
        state = "waiting"
    elif syntax:
        state = SYNTAX
    elif probe.get("is_sealed") and all(sign["fault"] == SEALED for sign in signs):
        state = SEALED
    else:
        state = "open"
    return {
        "state": state,
        "sealed": state == SEALED,
        "signs_sealed": sum(1 for sign in signs if sign["fault"] == SEALED),
        "signs_total": len(signs),
        "residual": scan.get("projection_residual") if judged else None,
        "svg": image["svg"],
        "signs": signs,
    }


assert set(_RANK) == set(DEFECTS)

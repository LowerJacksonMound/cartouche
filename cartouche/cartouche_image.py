"""Draw the signed signs in order, inside the ring. Each sign keeps its own name."""

from __future__ import annotations

from typing import Any


def _xml(text: str) -> str:
    return text.replace("&", "&").replace("<", "<")


def _place(svg: str, x: int, y: int, size: int, name: str) -> str:
    head, rest = svg.split(">", 1)
    head = head.replace(' width="100%" height="100%"', "")
    return f'{head} x="{x}" y="{y}" width="{size}" height="{size}"><title>{_xml(name)}</title>{rest}'


def render_cartouche(marked: dict[str, Any], ring_colors: list[str] | None = None) -> dict[str, Any]:
    """One ring per part. The seal is the part sign. The signs inside are the functions, in order.

    `ring_colors` gives each ring its own stroke (the live view closes a ring in green when every
    sign in it is sealed). Left out, every ring draws in currentColor, as before.
    """

    columns: list[str] = []
    bands: list[dict[str, Any]] = []
    cursor = 0
    column_width = 96
    gap = 20
    height = 0
    for position, band in enumerate(marked["cartouches"]):
        functions = band["functions"]
        ring = ring_colors[position] if ring_colors and position < len(ring_colors) else "currentColor"
        inner_top = 72
        sign_size = 48
        step = 56
        oval_height = 20 + len(functions) * step
        column_height = inner_top + oval_height + 8
        height = max(height, column_height)
        oval_x = cursor + 8
        body = [
            (
                f'<rect x="{oval_x}" y="{inner_top}" width="80" height="{oval_height}" '
                f'rx="40" fill="none" stroke="{ring}" stroke-width="3"/>'
            ),
            _place(band["svg"], cursor + 20, 4, 56, band["name"]),
        ]
        for index, function in enumerate(functions):
            body.append(
                _place(function["svg"], cursor + 24, inner_top + 10 + index * step, sign_size, function["name"])
            )
        columns.append("".join(body))
        bands.append(
            {
                "order": band["order"],
                "seal": band["id"],
                "name": band["name"],
                "signs": [{"id": function["id"], "name": function["name"]} for function in functions],
            }
        )
        cursor += column_width + gap
    width = max(cursor - gap, column_width)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="100%" fill="none" stroke="currentColor">{"".join(columns)}</svg>'
    )
    return {"svg": svg, "cartouches": bands}
"""Fixed cartouche signs. The same signal locks always select the same sign."""

from __future__ import annotations

import hashlib
from typing import Any


def _svg(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="100%" height="100%" '
        'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


# Geometric drawings of standard signs. One function, two, or three.
SIGNS: tuple[dict[str, Any], ...] = (
    {"id": "M17", "name": "the reed", "holds": 1, "svg": _svg('<path d="M32 8v40M32 14h10"/>')},
    {"id": "N35", "name": "the water", "holds": 1, "svg": _svg('<path d="M8 24h12l6-8 6 8h12l6-8 6 8h6M8 40h12l6-8 6 8h12l6-8 6 8h6"/>')},
    {"id": "D21", "name": "the mouth", "holds": 1, "svg": _svg('<ellipse cx="32" cy="32" rx="22" ry="10"/>')},
    {"id": "O1", "name": "the house", "holds": 1, "svg": _svg('<path d="M10 22h44v30H10zM28 52V34h12v18"/>')},
    {"id": "X1", "name": "the bread", "holds": 1, "svg": _svg('<path d="M12 40c0-12 10-20 20-20s20 8 20 20z"/>')},
    {"id": "S29", "name": "the cloth", "holds": 1, "svg": _svg('<path d="M16 14h24v28c-8 8-16 8-24 0z"/>')},
    {"id": "Q3", "name": "the stool", "holds": 1, "svg": _svg('<path d="M14 24h36v8H14zM18 32v16M46 32v16"/>')},
    {"id": "V28", "name": "the wick", "holds": 1, "svg": _svg('<path d="M32 50V22M32 22c8-8 8-14 0-14"/>')},
    {"id": "D46", "name": "the hand", "holds": 1, "svg": _svg('<path d="M12 36h28l8-8M16 36v12M24 36v12M32 36v12"/>')},
    {"id": "G17", "name": "the owl", "holds": 2, "svg": _svg('<circle cx="32" cy="22" r="10"/><path d="M18 30l14 22 14-22M26 20h.1M38 20h.1"/>')},
    {"id": "G1", "name": "the vulture", "holds": 2, "svg": _svg('<path d="M8 34c10-16 22-18 36-8 6 4 12 4 14-2-8 10-8 16-14 20-10 6-24 4-36-10z"/>')},
    {"id": "D36", "name": "the arm", "holds": 2, "svg": _svg('<path d="M6 36h40l8-10M46 26v14M40 40v8"/>')},
    {"id": "I10", "name": "the cobra", "holds": 2, "svg": _svg('<path d="M40 10c8 8 8 16 0 20-10 6-18 4-22 12 8-2 16 2 16 12"/>')},
    {"id": "D4", "name": "the eye", "holds": 3, "svg": _svg('<path d="M6 32c10-12 18-16 26-16s16 4 26 16c-10 12-18 16-26 16S16 44 6 32z"/><circle cx="32" cy="32" r="6"/>')},
    {"id": "G5", "name": "the falcon", "holds": 3, "svg": _svg('<path d="M14 28c8-14 20-16 28-8 4 4 10 6 12 2-6 8-4 14-12 16l8 14H30L24 40c-8 2-16-2-18-12 2 2 6 2 8 0z"/>')},
    {"id": "G26", "name": "the ibis", "holds": 3, "svg": _svg('<path d="M10 26c16-4 28 0 36 8"/><path d="M46 34c6 2 10 8 8 14H28c-8-6-6-14 2-16l16 2"/>')},
    {"id": "N5", "name": "the sun", "holds": 3, "svg": _svg('<circle cx="32" cy="32" r="14"/><circle cx="32" cy="32" r="3" fill="currentColor" stroke="none"/>')},
)


def assign_symbol(locks: list[str]) -> dict[str, Any]:
    """Pick the sign for this many signal locks. The digest is the whole decision."""

    if not locks or any(not isinstance(lock, str) or lock == "" for lock in locks):
        raise ValueError("a symbol needs signal locks")
    holds = len(locks)
    row = [sign for sign in SIGNS if sign["holds"] == holds]
    if not row:
        raise ValueError(f"no cartouche symbol holds {holds} functions")
    payload = f"{holds}::" + "::".join(sorted(locks))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    sign = row[int(digest[:8], 16) % len(row)]
    return {"id": sign["id"], "name": sign["name"], "holds": holds, "svg": sign["svg"]}


def assign_distinct(named_locks: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    """Give each signal its own sign. The same set always gets the same signs."""

    if not named_locks:
        raise ValueError("a symbol needs signal locks")
    row = [sign for sign in SIGNS if sign["holds"] == 1]
    if len(named_locks) > len(row):
        raise ValueError(f"no distinct cartouche symbol for {len(named_locks)} functions")
    ordered = sorted(named_locks, key=lambda item: item[1])
    payload = "1::" + "::".join(lock for _name, lock in ordered)
    start = int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16) % len(row)
    chosen: dict[str, dict[str, Any]] = {}
    for offset, (name, _lock) in enumerate(ordered):
        sign = row[(start + offset) % len(row)]
        chosen[name] = {"id": sign["id"], "name": sign["name"], "holds": 1, "svg": sign["svg"]}
    return chosen


def mark_cartouche(spec_data: dict[str, Any], master: dict[str, Any]) -> dict[str, Any]:
    """Map each part, and each function in it, from the signed signal locks."""

    glyphs = master["sub_glyphs"]
    from cartouche.sequence import pack_cartouches

    cartouches = []
    for band in pack_cartouches(spec_data):
        locks = [glyphs[name]["signal_hash"] for name in band["symbols"]]
        part = assign_symbol(locks)
        functions = []
        drawn = {sign["id"]: sign for sign in SIGNS}
        for name in band["symbols"]:
            sign = drawn[glyphs[name]["sign_id"]]
            functions.append(
                {"function": name, "id": sign["id"], "name": sign["name"], "svg": sign["svg"]}
            )
        cartouches.append({**part, "order": band["order"], "functions": functions})
    return {"marked": True, "cartouches": cartouches}

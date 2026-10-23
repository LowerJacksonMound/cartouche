"""A completed sequence can be reused as one symbol. An open one cannot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def empty_shelf() -> dict[str, Any]:
    return {"cartouches": {}}


def load_shelf(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_shelf()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("cartouches", {})
    return data


def save_shelf(path: Path, shelf: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(shelf, indent=2) + "\n", encoding="utf-8")


def admit(shelf: dict[str, Any], sequence: dict[str, Any]) -> dict[str, Any]:
    """Return the shelf entry. Do not store a sequence that is not complete."""

    cartouches = shelf.setdefault("cartouches", {})
    sha = sequence.get("cartouche_sha256")
    if sequence.get("complete") is not True or not isinstance(sha, str):
        return {"admitted": False, "cartouche_sha256": sha}
    current = cartouches.get(sha)
    if current is not None:
        return current
    symbols = [
        item["name"]
        for band in sequence.get("cartouches", [])
        for item in band["symbols"]
    ]
    current = {
        "admitted": True,
        "status": "admitted",
        "cartouche_sha256": sha,
        "capacity": sequence.get("capacity"),
        "symbols": symbols,
    }
    cartouches[sha] = current
    return current


def _image_sha(image: dict[str, Any]) -> str:
    payload = {
        "app_id": image["app_id"],
        "symbols": [{"name": item["name"], "lock": item["lock"]} for item in image["symbols"]],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def compose(image: dict[str, Any], shelf: dict[str, Any]) -> dict[str, Any]:
    """Read the shelf. A missing lock is an open symbol, not a new cartouche."""

    capacity = image.get("cartouche_capacity", 3)
    symbols = image["symbols"]
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("cartouche_capacity must be an integer >= 1")
    if len(symbols) > capacity:
        raise ValueError(f"image holds {len(symbols)} symbols and the capacity is {capacity}")
    names = [item["name"] for item in symbols]
    if len(names) != len(set(names)):
        raise ValueError("image symbol names must be unique")
    admitted = shelf.get("cartouches", {})
    rows = []
    for item in symbols:
        entry = admitted.get(item["lock"])
        rows.append(
            {
                "name": item["name"],
                "lock": item["lock"],
                "admitted": bool(entry and entry.get("status") == "admitted"),
            }
        )
    return {
        "app_id": image["app_id"],
        "image_sha256": _image_sha(image),
        "capacity": capacity,
        "complete": bool(rows) and all(row["admitted"] for row in rows),
        "symbols": rows,
    }

from __future__ import annotations

import json
from pathlib import Path

from cartouche.clip_library import view


def see_shelf(dictionary: dict, base: Path) -> None:
    for interaction, entries in dictionary["interactions"].items():
        for entry in entries.values():
            path = base / entry["clip_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"clip")
            node_id = entry.get("node_id")
            nodes = entry.get("node_ids") or []
            if node_id is None and len(nodes) == 1:
                node_id = nodes[0]
            result = view(dictionary, interaction, entry["phrase"], base, node_id=node_id)
            if not result.get("seen"):
                raise AssertionError(result)


def see_saved(path: Path, base: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    see_shelf(data, base)
    path.write_text(json.dumps(data), encoding="utf-8")

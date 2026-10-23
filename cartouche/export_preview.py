"""The app ships with no request. A spec is supplied later. Nothing here is an example."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "data" / "phase1" / "manifest.ts"

EMPTY = {
    "domain_id": "",
    "cartouche_sha256": "",
    "expected_bitmask": 0,
    "glyph_order": [],
    "sub_glyphs": {},
    "required_edges": [],
    "rehearsal": {
        "montage_status": "none",
        "total_permutations": 0,
        "broll": {"sought": 0, "found": 0, "missing": 0, "undeclared": 0, "unreached": 0},
        "paths": [],
    },
    "library": {
        "interaction": "",
        "clips": [],
        "paths": [],
        "counts": {
            "clips": 0,
            "pending": 0,
            "reused": 0,
            "approved": 0,
            "paths": 0,
            "paths_covered": 0,
        },
    },
    "parameters": {},
    "image": None,
    "fixtures": [],
}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(EMPTY, indent=2)
    OUT.write_text(
        'import type { Manifest } from "./types";\n\n'
        f"export const manifest: Manifest = {payload};\n",
        encoding="utf-8",
    )
    print(OUT)


if __name__ == "__main__":
    main()

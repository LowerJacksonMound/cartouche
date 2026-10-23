"""Fill the clip dictionary. Approval is what makes a line reusable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cartouche.broll_fetcher import BRollFetcher, phrase_key, shelf_clip_path, shelf_key
from cartouche.cartouche_compiler import compute_signal_hash

__all__ = ["phrase_key", "shelf_key", "shelf_clip_path"]


def empty_dictionary() -> dict[str, Any]:
    return {"interactions": {}}


def load_dictionary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_dictionary()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("interactions", {})
    return data


def save_dictionary(path: Path, dictionary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dictionary, indent=2) + "\n", encoding="utf-8")


class LibraryFiller:
    """One dictionary entry per distinct line. A path is covered only when every line is approved."""

    def fill(
        self, spec_data: dict[str, Any], dictionary: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        interaction = spec_data.get("interaction") or spec_data["domain_id"]
        shelf: dict[str, dict[str, Any]] = dictionary.setdefault("interactions", {}).setdefault(
            interaction, {}
        )
        fetcher = BRollFetcher(spec_data)
        sought = fetcher.fetch()["sought"]
        by_node: dict[str, dict[str, Any]] = {}
        for visual in sought:
            phrase = visual["phrase"]
            if not phrase:
                by_node[visual["node_id"]] = {
                    "phrase_key": "",
                    "phrase": "",
                    "status": "undeclared",
                    "clip_path": None,
                    "edge": bool(visual.get("is_edge_case")),
                    "node_ids": [visual["node_id"]],
                    "decides": visual["decides"],
                }
                continue
            key = phrase_key(phrase)
            entry_key = shelf_key(phrase, visual)
            current = shelf.get(entry_key)
            if current is None:
                current = {
                    "phrase": phrase,
                    "phrase_key": key,
                    "shelf_key": entry_key,
                    "interaction": interaction,
                    "domain_id": spec_data["domain_id"],
                    "status": "pending",
                    "clip_path": shelf_clip_path(interaction, entry_key),
                    "token_id": visual["token_id"],
                    "primitive_fxn": visual["primitive_fxn"],
                    "edge": bool(visual.get("is_edge_case")),
                    "node_id": visual["node_id"] if visual.get("is_edge_case") else None,
                    "node_ids": [visual["node_id"]],
                    "signal_lock": None,
                    "clip_sha256": None,
                    "seen": False,
                }
                shelf[entry_key] = current
                status = "pending"
            elif current["status"] == "approved":
                # Signed off for this request: approved. Signed off under an earlier request on
                # the same shelf (or an entry with no request recorded): reused.
                status = "approved" if current.get("domain_id") == spec_data["domain_id"] else "reused"
            else:
                status = current["status"]
            nodes = current.setdefault("node_ids", [])
            if visual["node_id"] not in nodes:
                nodes.append(visual["node_id"])
            if (
                current.get("token_id") not in (None, visual["token_id"])
                or current.get("primitive_fxn") not in (None, visual["primitive_fxn"])
            ):
                current["ambiguous"] = True
            entry = by_node.get(visual["node_id"])
            if entry is None:
                entry = {
                    "phrase_key": key,
                    "shelf_key": entry_key,
                    "phrase": phrase,
                    "status": status,
                    "clip_path": current["clip_path"],
                    "signal_lock": current.get("signal_lock"),
                    "clip_sha256": current.get("clip_sha256"),
                    "seen": bool(current.get("seen")),
                    "edge": bool(current.get("edge")),
                    "node_ids": [],
                    "decides": visual["decides"],
                }
                by_node[visual["node_id"]] = entry
            if visual["node_id"] not in entry["node_ids"]:
                entry["node_ids"].append(visual["node_id"])
        clips = []
        seen_keys: set[str] = set()
        for visual in sought:
            entry = by_node[visual["node_id"]]
            key = entry["shelf_key"]
            if key in seen_keys or not key:
                continue
            seen_keys.add(key)
            node_ids = [
                node_id
                for node_id, item in by_node.items()
                if item.get("shelf_key") == key
            ]
            clips.append({**entry, "node_ids": node_ids})
        paths = []
        for index, node_path in enumerate(fetcher.rehearsal_paths()):
            covered = all(by_node[node_id]["status"] in {"approved", "reused"} for node_id in node_path)
            paths.append(
                {
                    "permutation_index": index,
                    "node_path": node_path,
                    "is_edge_case": any(
                        fetcher.nodes[node_id].get("is_edge_case", False) for node_id in node_path
                    ),
                    "covered": covered,
                }
            )
        report = {
            "interaction": interaction,
            "clips": clips,
            "paths": paths,
            "counts": {
                "clips": len(clips),
                "pending": sum(1 for clip in clips if clip["status"] == "pending"),
                "reused": sum(1 for clip in clips if clip["status"] == "reused"),
                "approved": sum(1 for clip in clips if clip["status"] == "approved"),
                "paths": len(paths),
                "paths_covered": sum(1 for path in paths if path["covered"]),
            },
        }
        return dictionary, report


def _pick(
    dictionary: dict[str, Any], interaction: str, phrase: str, node_id: str | None = None
) -> dict[str, Any] | None:
    try:
        shelf = dictionary["interactions"][interaction]
    except KeyError as exc:
        raise KeyError(f"{interaction} has no clip for {phrase!r}") from exc
    key = phrase_key(phrase)
    matches = [entry for entry in shelf.values() if phrase_key(entry.get("phrase", "")) == key]
    if node_id:
        matches = [
            entry
            for entry in matches
            if node_id == entry.get("node_id") or node_id in entry.get("node_ids", [])
        ]
    if not matches:
        raise KeyError(f"{interaction} has no clip for {phrase!r}")
    if len(matches) > 1:
        return None
    return matches[0]


def _clip_file(entry: dict[str, Any], base_dir: Path) -> Path:
    clip = Path(entry["clip_path"])
    if not clip.is_absolute():
        clip = base_dir / clip
    return clip


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def view(
    dictionary: dict[str, Any],
    interaction: str,
    phrase: str,
    base_dir: Path,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Record the bytes that were seen. An empty file is not a viewing."""

    entry = _pick(dictionary, interaction, phrase, node_id)
    if entry is None:
        return {"seen": False, "reason": "ambiguous", "phrase": phrase}
    path = _clip_file(entry, base_dir)
    data = path.read_bytes() if path.is_file() else b""
    if not data:
        return {"seen": False, "reason": "empty" if path.is_file() else "unseen", "phrase": entry["phrase"]}
    entry["seen"] = True
    entry["clip_sha256"] = _digest(data)
    return {"seen": True, "reason": "seen", "phrase": entry["phrase"], "clip_sha256": entry["clip_sha256"]}


def approve(
    dictionary: dict[str, Any],
    interaction: str,
    phrase: str,
    base_dir: Path,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Sign off the clip that was seen. A different file is not that sign-off."""

    entry = _pick(dictionary, interaction, phrase, node_id)
    if entry is None:
        return {"approved": False, "reason": "ambiguous", "phrase": phrase}
    if entry.get("ambiguous"):
        raise ValueError(f"{phrase!r} is more than one signal")
    if not entry.get("seen") or not entry.get("clip_sha256"):
        return {"approved": False, "reason": "unseen", "phrase": entry["phrase"], "phrase_key": entry["phrase_key"]}
    path = _clip_file(entry, base_dir)
    data = path.read_bytes() if path.is_file() else b""
    if not data or _digest(data) != entry["clip_sha256"]:
        entry["seen"] = False
        entry["clip_sha256"] = None
        return {"approved": False, "reason": "replaced", "phrase": entry["phrase"], "phrase_key": entry["phrase_key"]}
    token_id = entry.get("token_id")
    fxn_name = entry.get("primitive_fxn")
    if not token_id or not fxn_name:
        raise ValueError(f"{phrase!r} has no signal to lock")
    if not entry.get("signal_lock"):
        entry["signal_lock"] = compute_signal_hash(token_id, entry["phrase"], fxn_name)
    entry["status"] = "approved"
    entry["approved"] = True
    return entry


def clip_holds(dictionary: dict[str, Any], base_dir: Path) -> list[dict[str, str]]:
    """Signed clips whose bytes are no longer the ones that were seen."""

    drifted: list[dict[str, str]] = []
    for entries in dictionary.get("interactions", {}).values():
        for entry in entries.values():
            if entry.get("status") != "approved":
                continue
            path = _clip_file(entry, base_dir)
            data = path.read_bytes() if path.is_file() else b""
            if not data or _digest(data) != entry.get("clip_sha256"):
                drifted.append({"phrase": entry["phrase"], "reason": "replaced"})
    return drifted

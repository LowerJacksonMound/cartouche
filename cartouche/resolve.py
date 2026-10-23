"""A phrase is one certified signal, or it is not. A near line is not snapped to one."""

from __future__ import annotations

from typing import Any

from cartouche.cartouche_compiler import compute_signal_hash


def _norm(phrase: str) -> str:
    return phrase.strip().lower()


def resolve_phrase(
    spec_data: dict[str, Any],
    phrase: str,
    dictionary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A signed-off clip is a signal. A near line is not snapped onto one."""

    norm = _norm(phrase)
    if norm == "":
        return {"resolved": False, "reason": "empty"}
    token_fxn: dict[str, str] = {}
    for node in spec_data["nodes"].values():
        token_fxn.setdefault(node["token_id"], node["primitive_fxn"])
    matches: dict[str, dict[str, str]] = {}
    for token_id, atom in spec_data["b_roll_atoms"].items():
        if _norm(atom["phrase"]) != norm:
            continue
        fxn_name = token_fxn.get(token_id)
        if fxn_name is None:
            continue
        signal = compute_signal_hash(token_id, atom["phrase"], fxn_name)
        matches[signal] = {
            "token_id": token_id,
            "primitive_fxn": fxn_name,
            "signal_hash": signal,
            "phrase": atom["phrase"],
        }
    if len(matches) > 1:
        return {"resolved": False, "reason": "ambiguous", "signals": sorted(matches)}
    if len(matches) == 0:
        return {"resolved": False, "reason": "off_script"}
    found = next(iter(matches.values()))
    lock = _signed_lock(dictionary or {}, found["phrase"])
    if lock is None:
        return {"resolved": False, "reason": "unsigned", "phrase": found["phrase"]}
    if lock != found["signal_hash"]:
        return {"resolved": False, "reason": "lock", "phrase": found["phrase"]}
    return {"resolved": True, "reason": "signal", "signal_lock": lock, **found}


def _signed_lock(dictionary: dict[str, Any], phrase: str) -> str | None:
    norm = _norm(phrase)
    for shelf in dictionary.get("interactions", {}).values():
        if not isinstance(shelf, dict):
            continue
        for entry in shelf.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("status") != "approved":
                continue
            if _norm(entry.get("phrase", "")) != norm:
                continue
            lock = entry.get("signal_lock")
            if isinstance(lock, str) and lock:
                return lock
    return None

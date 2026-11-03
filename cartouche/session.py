"""Keep the lock up for a whole build. A problem is reported. The watch does not stop."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.hold import hold
from cartouche.live import live_view
from cartouche.project_symbol import LOCKED, issue_line, issues_of
from cartouche.signal_stitcher import SignalStitcher


def stop_path(session_path: Path) -> Path:
    return session_path.with_name(session_path.name + ".stop")


def _names(spec_data: dict[str, Any], base_dir: Path) -> dict[str, str]:
    track = SignalStitcher(spec_data, base_dir=base_dir).compile_montage_and_signals()
    master = CartoucheCompiler(track).compile_cartouche()
    return {name: glyph["sign_name"] for name, glyph in master["sub_glyphs"].items()}


def _files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(path for path in target.rglob("*.py") if path.is_file())
    return []


def _issues(result: dict[str, Any], names: dict[str, str]) -> list[str]:
    """One line per issue, in the five words. The sign is named; the word is the fault."""

    if not result.get("scanned"):
        if result.get("reason") == "unreleased":
            return ["The request is not signed off, so nothing is being watched."]
        return [f"fault={LOCKED} detail=INTENT: the request no longer matches the lock"]
    lines: list[str] = []
    for row in issues_of(result["scan"]):
        row = {**row, "file": None, "sign": names.get(row.get("function") or "", row.get("sign"))}
        lines.append(issue_line(row))
    return lines


def watch_once(
    spec_data: dict[str, Any], contract: dict[str, Any], target: Path, base_dir: Path
) -> dict[str, Any]:
    """One look at the build. A defect does not end the session."""

    names = _names(spec_data, base_dir)
    files = _files(target)
    if not files:
        return {
            "running": True,
            "sealed": False,
            "scanned": False,
            "cartouche_sha256": contract.get("cartouche_sha256"),
            "issues": ["The build has not written anything yet."],
        }
    issues: list[str] = []
    sealed = True
    scanned = True
    sha = contract.get("cartouche_sha256")
    for path in files:
        result = hold(spec_data, contract, path, base_dir)
        sha = result.get("cartouche_sha256", sha)
        if not result.get("scanned"):
            return {
                "running": True,
                "sealed": False,
                "scanned": False,
                "reason": result.get("reason"),
                "cartouche_sha256": sha,
                "issues": _issues(result, names),
            }
        found = _issues(result, names)
        issues.extend(f"{path.name}: {line}" if target.is_dir() else line for line in found)
        sealed = sealed and result["is_sealed"] and not found
    return {
        "running": True,
        "sealed": sealed and not issues,
        "scanned": scanned,
        "cartouche_sha256": sha,
        "issues": issues,
    }


def _drawn(spec_data: dict[str, Any], contract: dict[str, Any], target: Path, base_dir: Path) -> dict[str, Any]:
    """The cartouche as it stands, for the live page: one row per sign and the drawing.

    A directory is one scan here, as it is for ct_look. A failure to draw never ends the watch.
    """

    try:
        view = live_view(spec_data, contract, target, base_dir)
    except Exception as error:  # the drawing is a view; the watch keeps reporting issues without it
        return {"view_error": f"{type(error).__name__}: {error}"[:300]}
    return {
        "state": view["state"],
        "signs_sealed": view["signs_sealed"],
        "signs_total": view["signs_total"],
        "residual": view["residual"],
        "signs": view["signs"],
        "svg": view["svg"],
        "updated": time.time(),
    }


def run_session(
    spec_data: dict[str, Any],
    contract: dict[str, Any],
    target: Path,
    session_path: Path,
    base_dir: Path,
    interval: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Stay up until stop. Print an issue when it appears. Do not rewrite the contract."""

    if contract.get("released") is not True:
        print("started=false reason=unreleased")
        return 2
    flag = stop_path(session_path)
    announced: list[str] | None = None
    code = 2
    while True:
        state = watch_once(spec_data, contract, target, base_dir)
        state.update(_drawn(spec_data, contract, target, base_dir))
        stopping = flag.is_file()
        state["running"] = not stopping
        state["target"] = str(target)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        if state["issues"] != announced:
            if state["issues"]:
                for line in state["issues"]:
                    print(f"issue: {line}")
            else:
                print("clear")
            announced = list(state["issues"])
        if stopping:
            code = 0 if state["sealed"] else 2
            print(f"stopped sealed={str(state['sealed']).lower()}")
            print(state["cartouche_sha256"])
            return code
        sleep(interval)

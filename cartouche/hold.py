"""Pin a scan to a released contract. Neither side rewrites the other."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cartouche_scanner import CartoucheScanner
from cartouche.project_symbol import issues_of
from cartouche.signal_stitcher import SignalStitcher
import json
from cartouche.project_symbol import LOCKED, MISSING


def hold(
    spec_data: dict[str, Any],
    contract: dict[str, Any],
    target: Path,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Scan only when the contract was released and the spec still hashes to it."""

    track = SignalStitcher(spec_data, base_dir=base_dir or Path(".")).compile_montage_and_signals()
    master = CartoucheCompiler(track).compile_cartouche()
    contract_sha = contract.get("cartouche_sha256")
    if contract.get("released") is not True:
        return {
            "held": False,
            "reason": "unreleased",
            "scanned": False,
            "cartouche_sha256": contract_sha,
        }
    if master["cartouche_sha256"] != contract_sha:
        return {
            "held": False,
            "reason": "intent",
            "scanned": False,
            "cartouche_sha256": master["cartouche_sha256"],
            "contract_sha256": contract_sha,
        }
    report = CartoucheScanner(master).scan_file(target)
    return {
        "held": True,
        "reason": "scan",
        "scanned": True,
        "cartouche_sha256": master["cartouche_sha256"],
        "is_sealed": report["is_sealed"],
        "projection_residual": report["projection_residual"],
        "warrant_count": report["warrant_count"],
        "issues": issues_of(report),
        "scan": report,
    }


def hold_tree(
    spec_data: dict[str, Any],
    contract: dict[str, Any],
    target: Path,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Same pin as hold, over one file or a whole tree. A missing tree is not a miss."""

    if target.is_file():
        try:
            return hold(spec_data, contract, target, base_dir)
        except SyntaxError:
            pass
    refused = _refuse(spec_data, contract, base_dir)
    if refused is not None:
        return refused
    master = refused_master(spec_data, base_dir)
    report = CartoucheScanner(master).scan_tree(target)
    if report.get("waiting"):
        return {
            "held": True,
            "reason": "waiting",
            "scanned": False,
            "waiting": True,
            "cartouche_sha256": master["cartouche_sha256"],
            "is_sealed": False,
            "projection_residual": 0.0,
            "warrant_count": 0,
            "issues": [],
            "scan": report,
        }
    return _held_scan(master, report)


def refused_master(spec_data: dict[str, Any], base_dir: Path | None) -> dict[str, Any]:
    track = SignalStitcher(spec_data, base_dir=base_dir or Path(".")).compile_montage_and_signals()
    return CartoucheCompiler(track).compile_cartouche()


def _refuse(
    spec_data: dict[str, Any], contract: dict[str, Any], base_dir: Path | None
) -> dict[str, Any] | None:
    master = refused_master(spec_data, base_dir)
    contract_sha = contract.get("cartouche_sha256")
    if contract.get("released") is not True:
        return {
            "held": False,
            "reason": "unreleased",
            "scanned": False,
            "cartouche_sha256": contract_sha,
        }
    if master["cartouche_sha256"] != contract_sha:
        return {
            "held": False,
            "reason": "intent",
            "scanned": False,
            "cartouche_sha256": master["cartouche_sha256"],
            "contract_sha256": contract_sha,
        }
    return None


def _held_scan(master: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return {
        "held": True,
        "reason": "scan",
        "scanned": True,
        "waiting": False,
        "cartouche_sha256": master["cartouche_sha256"],
        "is_sealed": report["is_sealed"],
        "projection_residual": report["projection_residual"],
        "warrant_count": report["warrant_count"],
        "issues": issues_of(report),
        "scan": report,
    }


def closer_state(release: dict[str, Any], target: Path | str) -> dict[str, Any] | None:
    """What CLOSER's own files say about this release: its hash, the approved plan's, the hole count, the issue rows.

    None when the release carries no closer block or CLOSER's modules are not importable: it is optional, never a crash.
    """

    lock = release.get("closer")
    if not lock:
        return None
    try:
        import holes
        import judge
    except ImportError:
        return None
    path = Path(target)
    state = judge.state_dir(path if path.is_dir() else path.parent)
    answer: dict[str, Any] = {"sha256": lock.get("sha256"), "plan": None, "holes": 0, "issues": []}
    if not state.is_dir():
        return answer
    plans = holes._lines(state / holes.PLANS)
    plan = next((p for p in reversed(plans) if p.get("approved") is True), None)
    if plan is not None:
        answer["plan"] = plan.get("sha256")
        if plan.get("sha256") != lock.get("sha256") or plan.get("contracts") != lock.get("contracts"):
            answer["issues"].append(
                {
                    "file": None,
                    "function": None,
                    "lines": None,
                    "fault": LOCKED,
                    "detail": "CONTRACTS",
                    "sign": None,
                    "directive": "The approved CLOSER plan does not match the release's contracts: re-plan from the release.",
                    "warrant_type": None,
                }
            )
    found = (getattr(holes, "latest_holes", None) or holes.read_holes)(state)
    answer["holes"] = len(found)
    for hole in found:
        answer["issues"].append(
            {
                "file": hole.get("file"),
                "function": hole.get("function"),
                "lines": None,
                "fault": MISSING,
                "detail": f"HOLE({hole.get('kind', 'counterfeit')})",
                "sign": None,
                "directive": "; ".join(str(r) for r in hole.get("reasons") or []),
                "warrant_type": None,
            }
        )
    return answer


def closer_wire(release: dict[str, Any], target: Path | str) -> str | None:
    """The wire (Ian 2026-11-11): the signed release's hashed intent IS the approved plan. Written once into
    CLOSER's state for this target as an approved plan record, action "cartouche"; CLOSER reads it and no cl_plan
    pause follows. Returns the plan sha when it was written now, None when it was already there or there is no lock."""

    lock = release.get("closer")
    if not lock or not lock.get("sha256"):
        return None
    try:
        import holes
        import judge
    except ImportError:
        return None
    path = Path(target).expanduser().resolve()  # closer_mcp hashes the resolved repo path; /tmp is /private/tmp
    state = judge.state_dir(path if path.is_dir() else path.parent)
    plan = holes.approved_plan(state) if state.is_dir() else None
    if plan and plan.get("sha256") == lock["sha256"]:
        return None
    state.mkdir(parents=True, exist_ok=True)
    holes.record_plan(state, {"intent": lock["intent"], "expectation": lock["expectation"], "contracts": lock["contracts"],
                              "sha256": lock["sha256"], "approved": True, "action": "cartouche",
                              "cartouche_sha256": release.get("cartouche_sha256")})
    return str(lock["sha256"])


def closer_issues(release: dict[str, Any], target: Path | str) -> list[dict[str, Any]]:
    """The CLOSER rows for this release and target, or none when CLOSER has nothing to say."""

    state = closer_state(release, target)
    return list(state["issues"]) if state else []

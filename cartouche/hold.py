"""Pin a scan to a released contract. Neither side rewrites the other."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cartouche_scanner import CartoucheScanner
from cartouche.project_symbol import issues_of
from cartouche.signal_stitcher import SignalStitcher


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

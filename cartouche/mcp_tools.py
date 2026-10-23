"""The tools a build agent calls. The lock is not rewritten. CLOSER and CodeRadar are not started."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cartouche.hold import hold_tree
from cartouche.project_symbol import LOCKED, issues_of  # noqa: F401  (issues_of is this module's door too)

NO_TARGET = "no target — call ct_watch with the spec, the release, and the build path"


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


class Watch:
    """One build. The release on disk is only read."""

    def __init__(self) -> None:
        self.spec_path: Path | None = None
        self.contract_path: Path | None = None
        self.target: Path | None = None

    def bound(self) -> bool:
        return self.spec_path is not None

    def watch(self, spec: str, contract: str, target: str) -> dict[str, Any]:
        spec_path = resolve_path(spec)
        contract_path = resolve_path(contract)
        target_path = resolve_path(target)
        if not spec_path.is_file():
            return {"error": f"no such spec: {spec_path}"}
        if not contract_path.is_file():
            return {"error": f"no such release: {contract_path}"}
        if (
            self.bound()
            and (self.spec_path, self.contract_path, self.target)
            != (spec_path, contract_path, target_path)
        ):
            return {"error": "ct_stop first — a build is already being watched"}
        spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
        contract_data = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract_data.get("released") is not True:
            return {"error": "the request is not signed off, so nothing is being watched"}
        probe = hold_tree(spec_data, contract_data, target_path, spec_path.parent)
        if probe.get("reason") == "intent":
            return {"error": "the request no longer matches the lock"}
        if probe.get("reason") == "unreleased":
            return {"error": "the request is not signed off, so nothing is being watched"}
        self.spec_path = spec_path
        self.contract_path = contract_path
        self.target = target_path
        looked = self._from_probe(probe, target_path)
        looked["bound"] = True
        return looked

    def look(self) -> dict[str, Any]:
        if not self.bound():
            return {"error": NO_TARGET}
        assert self.spec_path is not None and self.contract_path is not None and self.target is not None
        before_spec = self.spec_path.read_text(encoding="utf-8")
        before_contract = self.contract_path.read_text(encoding="utf-8")
        spec_data = json.loads(before_spec)
        contract_data = json.loads(before_contract)
        probe = hold_tree(spec_data, contract_data, self.target, self.spec_path.parent)
        if self.spec_path.read_text(encoding="utf-8") != before_spec:
            raise RuntimeError("look rewrote the spec")
        if self.contract_path.read_text(encoding="utf-8") != before_contract:
            raise RuntimeError("look rewrote the release")
        looked = self._from_probe(probe, self.target)
        looked["bound"] = True
        return looked

    def stop(self) -> dict[str, Any]:
        if not self.bound():
            return {"stopped": False, "error": "nothing is being watched"}
        looked = self.look()
        self.spec_path = None
        self.contract_path = None
        self.target = None
        looked["bound"] = False
        looked["stopped"] = True
        return looked

    def hold(self, spec: str, contract: str, target: str) -> dict[str, Any]:
        spec_path = resolve_path(spec)
        contract_path = resolve_path(contract)
        target_path = resolve_path(target)
        if not spec_path.is_file():
            return {"error": f"no such spec: {spec_path}"}
        if not contract_path.is_file():
            return {"error": f"no such release: {contract_path}"}
        before_spec = spec_path.read_text(encoding="utf-8")
        before_contract = contract_path.read_text(encoding="utf-8")
        probe = hold_tree(
            json.loads(before_spec),
            json.loads(before_contract),
            target_path,
            spec_path.parent,
        )
        if spec_path.read_text(encoding="utf-8") != before_spec:
            raise RuntimeError("hold rewrote the spec")
        if contract_path.read_text(encoding="utf-8") != before_contract:
            raise RuntimeError("hold rewrote the release")
        looked = self._from_probe(probe, target_path)
        looked["bound"] = self.bound()
        return looked

    @staticmethod
    def _from_probe(probe: dict[str, Any], target: Path) -> dict[str, Any]:
        """Every answer names the same target, waiting or scanned or refused."""

        if probe.get("reason") == "unreleased":
            # Not a scan and not one of the five defects: the shelf is open, so nothing is judged.
            return {
                "sealed": False,
                "waiting": False,
                "scanned": False,
                "reason": "unreleased",
                "cartouche_sha256": probe.get("cartouche_sha256"),
                "target": str(target),
                "open": 1,
                "issues": [
                    {
                        "file": None,
                        "function": None,
                        "lines": None,
                        "fault": "UNRELEASED",
                        "detail": "UNRELEASED",
                        "sign": None,
                        "directive": "The request is not signed off, so nothing is being watched.",
                        "warrant_type": None,
                    }
                ],
            }
        if probe.get("reason") == "intent":
            return {
                "sealed": False,
                "waiting": False,
                "scanned": False,
                "reason": "intent",
                "cartouche_sha256": probe.get("cartouche_sha256"),
                "target": str(target),
                "open": 1,
                "issues": [
                    {
                        "file": None,
                        "function": None,
                        "lines": None,
                        "fault": LOCKED,
                        "detail": "INTENT",
                        "sign": None,
                        "directive": "The request no longer matches the lock: it was edited after release.",
                        "warrant_type": None,
                    }
                ],
            }
        report = probe.get("scan") or {}
        waiting = bool(probe.get("waiting") or report.get("waiting"))
        issues = [] if waiting else issues_of(report)
        return {
            "sealed": bool(probe.get("is_sealed")) and not issues,
            "waiting": waiting,
            "scanned": bool(probe.get("scanned")) and not waiting,
            "reason": probe.get("reason"),
            "cartouche_sha256": probe.get("cartouche_sha256"),
            "projection_residual": probe.get("projection_residual"),
            "target": report.get("target") or str(target),
            "open": len(issues),
            "issues": issues,
        }


WATCH = Watch()

TOOLS: dict[str, dict[str, Any]] = {
    "ct_watch": {
        "description": (
            "Bind this server to one build: the spec, the signed release, and the file or "
            "directory being written. Refuses an unsigned release or a spec that no longer "
            "hashes to it. Does not write either file, and does not start CLOSER or CodeRadar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "Path to the request spec JSON."},
                "contract": {"type": "string", "description": "Path to the release JSON."},
                "target": {
                    "type": "string",
                    "description": "Python file or directory to watch. It may not exist yet.",
                },
            },
            "required": ["spec", "contract", "target"],
            "additionalProperties": False,
        },
    },
    "ct_look": {
        "description": (
            "Scan the bound build once. Each issue names the file, the function, the lines, "
            "and the fault: one of template, locked, hazy, missing, skew; the scanner's codes "
            "are in detail. A directory is one scan. A file that does not parse is a SYNTAX "
            "fault and does not end the watch. Nothing written yet is waiting, with an empty "
            "issue list. Does not rewrite the release."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "ct_stop": {
        "description": (
            "End the watch and report whether the build matches the lock, including any open "
            "issue. Does not rewrite the release. The server process stays up."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "ct_hold": {
        "description": (
            "Compare a spec, a release, and a target once, without binding a watch. "
            "Same issue rows as ct_look. Does not rewrite the release."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "Path to the request spec JSON."},
                "contract": {"type": "string", "description": "Path to the release JSON."},
                "target": {"type": "string", "description": "Python file or directory."},
            },
            "required": ["spec", "contract", "target"],
            "additionalProperties": False,
        },
    },
}


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments or {})
    if name == "ct_watch":
        return WATCH.watch(str(args["spec"]), str(args["contract"]), str(args["target"]))
    if name == "ct_look":
        return WATCH.look()
    if name == "ct_stop":
        return WATCH.stop()
    if name == "ct_hold":
        return WATCH.hold(str(args["spec"]), str(args["contract"]), str(args["target"]))
    return {"error": f"no such tool {name!r}"}

"""The tools a build agent calls. The lock is not rewritten. CLOSER and CodeRadar are not started."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from cartouche.hold import hold_tree
from cartouche.project_symbol import LOCKED, issues_of  # noqa: F401  (issues_of is this module's door too)
from cartouche.hold import closer_state, closer_wire

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
        # the wire: the signed release's hashed intent becomes CLOSER's approved plan for this target
        wired = closer_wire(contract_data, target_path)
        looked = self._from_probe(probe, target_path, contract_data)
        looked["bound"] = True
        looked["closer_plan_written"] = wired
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
        looked = self._from_probe(probe, self.target, contract_data)
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
        contract_data = json.loads(before_contract)
        probe = hold_tree(json.loads(before_spec), contract_data, target_path, spec_path.parent)
        if spec_path.read_text(encoding="utf-8") != before_spec:
            raise RuntimeError("hold rewrote the spec")
        if contract_path.read_text(encoding="utf-8") != before_contract:
            raise RuntimeError("hold rewrote the release")
        looked = self._from_probe(probe, target_path, contract_data)
        looked["bound"] = self.bound()
        return looked

    @staticmethod
    def _rows(probe: dict[str, Any], target: Path) -> dict[str, Any]:
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

    @staticmethod
    def _from_probe(probe: dict[str, Any], target: Path, contract: dict[str, Any] | None = None) -> dict[str, Any]:
        """The rows, plus what CLOSER's own files say: a plan that drifted from the release, and every hole."""

        looked = Watch._rows(probe, target)
        state = closer_state(contract or {}, target)
        looked["closer"] = None
        if state is not None:
            looked["closer"] = {"sha256": state["sha256"], "plan": state["plan"], "holes": state["holes"]}
            if looked["reason"] == "scan" and state["issues"]:
                looked["issues"] = list(looked["issues"]) + list(state["issues"])
                looked["open"] = len(looked["issues"])
                looked["sealed"] = False
        looked["summary"] = summary_of(looked)
        return looked

def summary_of(looked: dict[str, Any]) -> str:
    """One plain sentence a person can read without the issue rows or the run log."""

    where = Path(str(looked.get("target", ""))).name or "the target"
    if looked.get("reason") == "unreleased":
        return "Not watched: the request is not signed off and released yet."
    if looked.get("reason") == "intent":
        return "Locked: the request was changed after release; release it again on the page."
    if looked.get("waiting"):
        return f"Waiting: nothing is written at {where} yet."
    issues = looked.get("issues") or []
    if not issues:
        return f"Sealed: every locked line and edge is in {where}."
    named = "; ".join(
        f"{i['fault']} in {i['function'] or (Path(str(i['file'])).name if i.get('file') else i['detail'])}"
        + (f" line {i['lines'][0]}" if i.get("lines") else "")
        for i in issues[:3]
    )
    more = f" and {len(issues) - 3} more" if len(issues) > 3 else ""
    holes = sum(1 for i in issues if str(i.get("detail", "")).startswith("HOLE("))
    tail = f", {holes} CLOSER hole{'s' if holes != 1 else ''}" if holes else ""
    return f"Not sealed: {len(issues)} issue{'s' if len(issues) != 1 else ''}: {named}{more}{tail}."


WATCH = Watch()

TOOLS: dict[str, dict[str, Any]] = {
    "ct_watch": {
        "description": (
            "Bind this server to one build: the spec, the signed release, and the file or "
            "directory being written. Refuses an unsigned release or a spec that no longer "
            "hashes to it. Does not write either file, and does not start CLOSER or CodeRadar. "
            "A release with closer contracts is checked against CLOSER's approved plan and its holes; "
            "send the release's contracts to cl_plan verbatim."
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
            "and the fault: one of locked, missing, skew; the scanner's codes are in detail. "
            "A hollow or fake-shaped body and wrong parameters are CLOSER's to refuse; "
            "Cartouche reports missing, skew and locked. A directory is one scan. A file that does not parse is a SYNTAX "
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
    "ct_chart": {
        "description": (
            "GATHER, step 1. Check a chart you drafted from the person's plain app request and, if it "
            "passes, save it as the request spec. The chart is every line of the interaction (each with "
            "the function it stands for) and every decision, edge cases included. Refuses a chart the "
            "compilers would refuse and writes nothing then. Does not fetch or sign anything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "chart": {"type": "object", "description": "The chart: domain_id, interaction, cartouche_capacity, root_id, nodes, b_roll_atoms, primitive_params, and request (the plain words)."},
                "out": {"type": "string", "description": "Where to save the spec JSON. Its folder is the request folder."},
            },
            "required": ["chart", "out"],
            "additionalProperties": False,
        },
    },
    "ct_wanted": {
        "description": (
            "GATHER, step 2. Every line a path of the chart reaches: its function, whether it is an "
            "edge case, its sign-off status, how many candidate clips it has, and its incoming folder. "
            "Reserves each line's shelf slot. Any rendered clip dropped into a line's incoming folder "
            "(by the person, a subagent, or a video generator) is offered on the sign-off page."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"spec": {"type": "string", "description": "Path to the request spec JSON."}},
            "required": ["spec"],
            "additionalProperties": False,
        },
    },
    "ct_search": {
        "description": (
            "GATHER, step 3. Search clip sources for every line in ONE call (searches run in parallel). "
            "Sources: youtube (Creative Commons only unless creative_commons is false), archive (Internet "
            "Archive films), pexels (needs PEXELS_API_KEY). Give spoken to search YouTube subtitles: each hit "
            "then names the seconds where those words are said. Downloads no video."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "searches": {
                    "type": "array",
                    "description": "One search per line, all in one call; they run in parallel.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "phrase": {"type": "string", "description": "The line this search is for (echoed back)."},
                            "source": {"type": "string", "enum": ["youtube", "archive", "pexels"]},
                            "query": {"type": "string"},
                            "spoken": {"type": "string", "description": "youtube: words to find in each hit's subtitles; each hit then carries moments (seconds where they are said)."},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                        "required": ["source", "query"],
                    },
                },
                "creative_commons": {"type": "boolean", "description": "youtube: Creative Commons only (default true)."},
            },
            "required": ["searches"],
            "additionalProperties": False,
        },
    },
    "ct_offer": {
        "description": (
            "GATHER, step 4. Offer candidate clips (all lines in one call): Cartouche downloads each cut "
            "(start, seconds, at most 20) into that line's candidates folder and records its source and "
            "licence. Offer a few per line. You cannot choose or sign off a clip: the person does that "
            "on the page (cartouche page --request), and no AI takes part after it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "Path to the request spec JSON."},
                "clips": {
                    "type": "array",
                    "description": "Every offer at once; they are cut in parallel. Send all lines' candidates in one call.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "phrase": {"type": "string", "description": "The line, exactly as ct_wanted gives it."},
                            "source": {"type": "string", "enum": ["youtube", "archive", "pexels", "file"]},
                            "url": {"type": "string"},
                            "start": {"type": "number", "minimum": 0},
                            "seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 20},
                            "why": {"type": "string", "description": "One sentence: why this footage stands for the line."},
                        },
                        "required": ["phrase", "source", "url"],
                    },
                },
            },
            "required": ["spec", "clips"],
            "additionalProperties": False,
        },
    },
    "ct_withdraw": {
        "description": (
            "GATHER. Take back candidates you offered that do not fit (wrong setting, wrong speaker). "
            "Refused for a line the person has signed off."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "Path to the request spec JSON."},
                "withdraw": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"phrase": {"type": "string"}, "id": {"type": "string"}}, "required": ["phrase", "id"]},
                },
            },
            "required": ["spec", "withdraw"],
            "additionalProperties": False,
        },
    },
    "ct_render": {
        "description": (
            "GATHER, after the search rounds. Render a stand-in clip for every line that still has no candidate "
            "(or for the lines named): the line spoken by the machine over a title card, dropped into the line's "
            "incoming folder and offered at once. Use it for a line no footage says, or one whose found clips are "
            "poor; the person sees it beside the found clips and decides. macOS only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "Path to the request spec JSON."},
                "phrases": {"type": "array", "items": {"type": "string"},
                            "description": "Lines to render, exactly as ct_wanted gives them. Default: every line with no candidate."},
                "voice": {"type": "string", "description": "A `say` voice name; default the system voice."},
            },
            "required": ["spec"],
            "additionalProperties": False,
        },
    },
}


def _gather(name: str, args: dict[str, Any]) -> dict[str, Any]:
    import os

    from cartouche import gather

    if name == "ct_chart":
        out = resolve_path(str(args["out"]))
        chart = args["chart"]
        if not isinstance(chart, dict):
            return {"error": "chart must be a JSON object"}
        checked = gather.check_chart(chart, out.parent)
        if checked["ok"]:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(chart, indent=2) + "\n", encoding="utf-8")
            checked["spec"] = str(out)
        return checked
    if name == "ct_search":
        from concurrent.futures import ThreadPoolExecutor

        searches = args.get("searches")
        if not isinstance(searches, list) or not searches:
            return {"error": "searches must be a non-empty list"}
        cc, key = bool(args.get("creative_commons", True)), os.environ.get("PEXELS_API_KEY", "")

        def run(one: dict[str, Any]) -> dict[str, Any]:
            try:
                hits = gather.search(str(one.get("source", "")), str(one.get("query", "")), int(one.get("limit", 5)), cc, key, str(one.get("spoken", "")))
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                hits = [{"error": f"{type(error).__name__}: {error}"[:200]}]
            return {"phrase": one.get("phrase", ""), "query": one.get("query", ""), "hits": hits}

        with ThreadPoolExecutor(min(4, len(searches))) as pool:
            return {"results": list(pool.map(run, searches))}
    spec_path = resolve_path(str(args["spec"]))
    if not spec_path.is_file():
        return {"error": f"no such spec: {spec_path}"}
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base = spec_path.parent
    if name == "ct_withdraw":
        items = args.get("withdraw")
        if not isinstance(items, list) or not items:
            return {"error": "withdraw must be a non-empty list"}
        return {"results": [gather.withdraw(spec, base / "clip_dictionary.json", base, str(i.get("phrase", "")), str(i.get("id", ""))) for i in items]}
    if name == "ct_render":
        phrases = args.get("phrases")
        if phrases is not None and (not isinstance(phrases, list) or not all(isinstance(x, str) for x in phrases)):
            return {"error": "phrases must be a list of strings"}
        rows = gather.render_missing(spec, base, phrases or None, str(args.get("voice") or ""))
        return {"rendered": len(rows), "results": rows}
    if name == "ct_wanted":
        answer = gather.wanted(spec, base / "clip_dictionary.json", base)
        answer["swept"] = gather.sweep_incoming(spec, base)
        return answer
    clips = args.get("clips")
    if not isinstance(clips, list) or not clips:
        return {"error": "clips must be a non-empty list"}
    results = gather.offer_many(spec, base, clips)
    return {"offered": sum(1 for r in results if r.get("offered")), "results": results}


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
    if name in ("ct_chart", "ct_wanted", "ct_search", "ct_offer", "ct_withdraw", "ct_render"):
        try:
            return _gather(name, args)
        except (OSError, ValueError, KeyError) as error:
            return {"error": f"{type(error).__name__}: {error}"[:400]}
    return {"error": f"no such tool {name!r}"}

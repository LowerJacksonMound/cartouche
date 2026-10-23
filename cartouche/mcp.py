"""Cartouche over MCP. Stdio, newline-delimited JSON-RPC. No port. No extra dependency.

stdout is the transport. Anything else goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from cartouche.mcp_tools import NO_TARGET, TOOLS, call_tool

SERVER_NAME = "cartouche"
SERVER_VERSION = "1"
SUPPORTED = ("2024-11-05", "2025-03-26", "2025-06-18")

INSTRUCTIONS = """\
Cartouche holds the intent lock for one build. It does not rewrite the lock. It does not start CLOSER or CodeRadar, and it does not talk to them.

START: ct_watch(spec, contract, target). spec is the request JSON. contract is the release (cartouche release). target is one Python file, or a directory of them. Give an absolute path. A relative path resolves against the directory this server was started in, not the agent's shell. The target may not exist yet.

ct_watch refuses a missing spec, a missing release, a release that is not signed off, and a spec that no longer hashes to that release. It writes neither file. A second different target answers "ct_stop first".

THEN: after code is written, call ct_look(). Each issue names the file, the function, the lines, the fault, and what to change. The fault is one of five words: template (a hollow stub), locked (the request was edited after release), hazy (the function is there but not clear), missing (the function is not there), skew (a required edge is gone); detail keeps the scanner's codes. Do not treat a sign name alone as the fault. A directory is one scan: a function counts in whichever file defines it. A file that does not parse is a SYNTAX fault, and the watch stays up. Nothing written yet is waiting:true with an empty issues list. That is not a miss.

STOP: ct_stop() when the build is finished. It reports sealed and every issue still open, then drops the bind. It does not rewrite the release. sealed false means the build does not match. The server process stays up, so a later ct_watch can bind the next build.

ct_hold(spec, contract, target) is the same comparison without a bind. Until ct_watch, ct_look answers "no target — call ct_watch with the spec, the release, and the build path". ct_stop with nothing bound says nothing is being watched.
"""


def tool_list() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
        for name, spec in TOOLS.items()
    ]


def _result(message_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload, indent=1)}],
            "structuredContent": payload,
            "isError": payload.get("error") is not None,
        },
    }


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id", None)
    if message_id is None or "id" not in message:
        return None
    params = message.get("params") or {}
    if method == "initialize":
        requested = str(params.get("protocolVersion") or SUPPORTED[0])
        version = requested if requested in SUPPORTED else SUPPORTED[0]
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": message_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": tool_list()}}
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            return _result(message_id, {"error": f"no such tool {name!r}"})
        try:
            if not isinstance(arguments, dict):
                return _result(message_id, {"error": "arguments must be an object"})
            missing = [
                key
                for key in TOOLS[name]["inputSchema"].get("required", [])
                if key not in arguments
            ]
            if missing:
                return _result(message_id, {"error": "missing " + ", ".join(missing)})
            return _result(message_id, call_tool(name, arguments))
        except Exception as exc:
            return _result(message_id, {"error": f"{name}: {type(exc).__name__}: {exc}"})
    return _error(message_id, -32601, f"method not found: {method}")


def serve() -> None:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            continue
        reply = handle(message)
        if reply is None:
            continue
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cartouche-mcp", description="Cartouche over MCP — stdio.")
    parser.add_argument("--print-tools", action="store_true", help="print the tool surface as JSON and exit")
    args = parser.parse_args(argv)
    if args.print_tools:
        print(json.dumps(tool_list(), indent=1))
        return 0
    print(f"cartouche-mcp {SERVER_VERSION}: {len(TOOLS)} tools; {NO_TARGET}", file=sys.stderr)
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# install_cartouche_mcp.sh — register Cartouche's MCP server with Claude Code once, at user scope.
#
#   bash install_cartouche_mcp.sh            # register (user scope: every project sees it)
#   bash install_cartouche_mcp.sh --print    # print the command, change nothing
#
# The entry is cartouche-mcp.sh next to this file: one stdio process, no port, no extra package.
# The server starts with NO target; ct_watch names it. Nothing is written into any repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENTRY="$ROOT/cartouche-mcp.sh"
NAME="cartouche"

if [ ! -f "$ENTRY" ]; then
  echo "install_cartouche_mcp.sh: $ENTRY is missing" >&2
  exit 1
fi
if [ ! -x "$ENTRY" ]; then
  echo "install_cartouche_mcp.sh: $ENTRY is not executable. Run:  chmod +x $ENTRY" >&2
  exit 1
fi
if [ ! -f "$ROOT/cartouche/mcp.py" ]; then
  echo "install_cartouche_mcp.sh: $ROOT/cartouche/mcp.py is missing — run this from the CARTOUCHE folder's copy" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "install_cartouche_mcp.sh: python3 is not on PATH; cartouche-mcp.sh needs Python 3.9 or newer (macOS ships it)" >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "install_cartouche_mcp.sh: python3 is $(python3 --version 2>&1); Cartouche needs 3.9 or newer" >&2
  exit 1
fi

JSON=$(printf '{"type":"stdio","command":"%s","args":[]}' "$ENTRY")

if [ "${1:-}" = "--print" ]; then
  printf "claude mcp add-json --scope user %s '%s'\n" "$NAME" "$JSON"
  exit 0
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "install_cartouche_mcp.sh: the claude CLI is not on PATH. Register by hand with:" >&2
  printf "  claude mcp add-json --scope user %s '%s'\n" "$NAME" "$JSON" >&2
  exit 1
fi

if claude mcp get "$NAME" >/dev/null 2>&1; then
  echo "install_cartouche_mcp.sh: an MCP server named '$NAME' is already registered — replacing it"
  claude mcp remove --scope user "$NAME" >/dev/null 2>&1 || true
fi

claude mcp add-json --scope user "$NAME" "$JSON"
echo
echo "Registered '$NAME' -> $ENTRY"
echo "Next: sign off and release a request (QUICKSTART.md steps 1-5), then open Claude Code in any"
echo "directory and have the build agent call ct_watch(spec, contract, target) with absolute paths,"
echo "ct_look() after each write, and ct_stop() when the build is finished."
echo "A running Claude Code session does not reload this server: after any edit here, or a git pull, run /mcp and reconnect cartouche."

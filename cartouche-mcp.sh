#!/bin/sh
# Cartouche MCP server. stdout is the protocol. Run from anywhere.
# CLOSER_TREE: where CLOSER's judge.py and holes.py live; Cartouche reads its plan and holes. Optional.
CLOSER_TREE="${CLOSER_TREE:-$HOME/Desktop/CLOSER}"
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
export PYTHONPATH="$ROOT:$CLOSER_TREE${PYTHONPATH:+:$PYTHONPATH}"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null || { echo "cartouche-mcp.sh: python3 is missing or older than 3.9" >&2; exit 1; }
exec python3 -m cartouche.mcp "$@"

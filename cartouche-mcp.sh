#!/bin/sh
# Cartouche MCP server. stdout is the protocol. Run from anywhere.
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null || { echo "cartouche-mcp.sh: python3 is missing or older than 3.9" >&2; exit 1; }
exec python3 -m cartouche.mcp "$@"

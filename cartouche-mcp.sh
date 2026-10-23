#!/bin/sh
# Cartouche MCP server. stdout is the protocol. Run from anywhere.
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m cartouche.mcp "$@"

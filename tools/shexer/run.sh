#!/usr/bin/env bash
# usage: run.sh (file INPUT.nt | endpoint SPARQL_URL) OUTDIR
set -euo pipefail
source "$(dirname "$0")/../common.sh"
mode="$1" src="$2" out="$3"
extra=(); [ "$mode" = endpoint ] && extra=(--endpoint)
"$TOOLS_HOME/shexer-venv/bin/python" "$REPO_ROOT/tools/shexer/run_shexer.py" "$src" "$out" "${extra[@]}"

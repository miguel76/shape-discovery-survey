#!/usr/bin/env bash
# usage: run.sh file INPUT OUTDIR   (SHACLGEN loads the whole graph with rdflib; no endpoint support)
set -euo pipefail
source "$(dirname "$0")/../common.sh"
limit_memory
[ "$1" = file ] || { echo "shaclgen: only 'file' mode is supported" >&2; exit 2; }
"$TOOLS_HOME/shaclgen-venv/bin/python" "$REPO_ROOT/tools/shaclgen/run_shaclgen.py" "$2" "$3"

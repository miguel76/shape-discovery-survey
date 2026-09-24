#!/usr/bin/env bash
# QSE-Exact, keeping the output pruned by (confidence, support) thresholds
# (QSE_PRUNING, default {(0.1,100)}), which is what QSE proposes as the shapes;
# tools/qse keeps the full, unpruned output.
# usage: run.sh file INPUT.nt OUTDIR
set -euo pipefail
source "$(dirname "$0")/../common.sh"
"$REPO_ROOT/tools/qse/run.sh" "$@"
out="$(realpath -m "$3")"
pruned=$(ls "$out"/qse-output/*_QSE_*_SHACL.ttl | grep -v _QSE_FULL_ | head -1)
cp "$pruned" "$out/shapes.ttl"

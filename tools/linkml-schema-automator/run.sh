#!/usr/bin/env bash
# usage: run.sh file INPUT.ttl OUTDIR
# Two steps: `schemauto generalize-rdf` infers a LinkML schema from Turtle
# instance data, then `gen-shacl` turns the LinkML schema into SHACL.
set -euo pipefail
source "$(dirname "$0")/../common.sh"
[ "$1" = file ] || { echo "linkml-schema-automator: only 'file' mode is supported" >&2; exit 2; }
out="$3"; mkdir -p "$out"
bin="$TOOLS_HOME/linkml-venv/bin"
"$bin/schemauto" generalize-rdf "$2" -d "$out/tables" -o "$out/schema.yaml"
"$bin/gen-shacl" "$out/schema.yaml" > "$out/shapes.ttl"

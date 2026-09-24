#!/usr/bin/env bash
# usage: run.sh file INPUT.ttl OUTDIR
# Two steps: `schemauto generalize-rdf` infers a LinkML schema from Turtle
# instance data (via one TSV table per class, written to a temporary directory),
# then `gen-shacl` turns the LinkML schema into SHACL.
set -euo pipefail
source "$(dirname "$0")/../common.sh"
[ "$1" = file ] || { echo "linkml-schema-automator: only 'file' mode is supported" >&2; exit 2; }
out="$3"; mkdir -p "$out"
bin="$TOOLS_HOME/linkml-venv/bin"
tables="$(mktemp -d)"; trap 'rm -rf "$tables"' EXIT
# Raise Python's csv field limit (128 KiB): multivalued properties are joined into
# a single TSV cell, which exceeds it on large KGs.
"$bin/python" -c 'import csv, sys; csv.field_size_limit(sys.maxsize); from schema_automator.cli import main; sys.argv[0] = "schemauto"; main()' \
    generalize-rdf "$2" -d "$tables" -o "$out/schema.yaml"
"$bin/gen-shacl" "$out/schema.yaml" > "$out/shapes.ttl"

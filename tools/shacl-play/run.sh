#!/usr/bin/env bash
# usage: run.sh (file INPUT | endpoint SPARQL_URL) OUTDIR
set -euo pipefail
source "$(dirname "$0")/../common.sh"
mkdir -p "$3"
java -Xmx"${JAVA_XMX:-4g}" -Dlogback.configurationFile="$REPO_ROOT/tools/shacl-play/logback.xml" \
    -cp "$(tr -d '\n' < "$TOOLS_HOME/shacl-play.classpath")" \
    "$REPO_ROOT/tools/shacl-play/ShaclPlayGenerate.java" "$1" "$2" "$3/shapes.ttl"

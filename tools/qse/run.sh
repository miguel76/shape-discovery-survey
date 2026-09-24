#!/usr/bin/env bash
# Run QSE-Exact (file-based) on an N-Triples file.
# usage: run.sh file INPUT.nt OUTDIR
# env:   JAVA_XMX (default 4g),
#        QSE_PRUNING (default "{(0.1,100)}"; list of (confidence,support) pairs)
# QSE's query-based variants are hard-wired to a GraphDB repository
# (graphdb_url + graphdb_repository), so endpoint mode is not wired up here yet.
set -euo pipefail
source "$(dirname "$0")/../common.sh"
[ "$1" = file ] || { echo "qse: only 'file' mode is supported" >&2; exit 2; }
QSE_HOME="$TOOLS_HOME/qse"
input="$(realpath "$2")"
outdir="$(realpath -m "$3")"
mkdir -p "$outdir/qse-output"
lines=$(wc -l < "$input")
classes=$(grep -c '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>' "$input" || true)
cat > "$outdir/config.properties" <<CFG
qse_exact_file=true
qse_exact_query_based=false
qse_approximate_file=false
qse_approximate_query_based=false
qse_approximate_parallel_query_based=false
qse_approximate_parallel_qb_threads=1
qse_specific_classes=false
max_cardinality=true
min_cardinality=true
dataset_name=$(basename "$input" .nt)
expected_number_classes=$(( classes > 10 ? classes : 10 ))
expected_number_of_lines=$(( lines > 1000 ? lines : 1000 ))
is_wikidata=false
add_examples=false
label_properties=<http://www.w3.org/2000/01/rdf-schema#label>,<http://www.w3.org/2004/02/skos/core#prefLabel>
example_IRI=http://example.org/example
graphdb_url=http://localhost:7200
graphdb_repository=none
entity_sampling_threshold=100
entity_sampling_target_percentage=75
qse_validation=false
qse_validation_with_shNot=false
dataset_path=$input
resources_path=$QSE_HOME/src/main/resources
config_dir_path=$QSE_HOME/config/
output_file_path=$outdir/qse-output/
default_directory=$outdir/qse-output/
validation_input_dir=$QSE_HOME/validation/
annotateSupportConfidence=true
pruning_thresholds=${QSE_PRUNING:-{(0.1,100)\}}
CFG
# QSE writes some files relative to the working directory
cd "$outdir"
java -Xmx"${JAVA_XMX:-4g}" -jar "$QSE_HOME/jar/qse.jar" "$outdir/config.properties"
full=$(ls "$outdir"/qse-output/*_QSE_FULL_SHACL.ttl | head -1)
cp "$full" "$outdir/shapes.ttl"
# drop the intermediate RDF4J native stores QSE leaves behind
rm -rf "$outdir"/qse-output/db_*

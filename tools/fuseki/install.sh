#!/usr/bin/env bash
# Apache Jena Fuseki: used to expose a KG dump as a local SPARQL endpoint (for
# tools' endpoint mode) and, via riot, to normalise RDF serialisations.
set -euo pipefail
source "$(dirname "$0")/../common.sh"
mvn -q -B dependency:copy -Dartifact=org.apache.jena:jena-fuseki-server:5.2.0 -DoutputDirectory="$TOOLS_HOME/fuseki"

#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"
python_venv "$TOOLS_HOME/shexer-venv" shexer==2.7.3.1
# sheXer decides a literal's datatype by searching the *whole* literal for
# "xsd:", "geo:", ...; a datatype IRI such as <geo:wktLiteral> becomes
# "http://www.opengis.net/ont/geosparql#wktLiteral>" and the SHACL serialisation
# crashes. The patch only inspects the datatype part.
site="$("$TOOLS_HOME/shexer-venv/bin/python" -c 'import shexer, os; print(os.path.dirname(os.path.dirname(shexer.__file__)))')"
if patch -p1 -s -N --dry-run -d "$site" < "$REPO_ROOT/tools/shexer/literal-datatype.patch" >/dev/null 2>&1; then
    patch -p1 -s -N -d "$site" < "$REPO_ROOT/tools/shexer/literal-datatype.patch"
fi

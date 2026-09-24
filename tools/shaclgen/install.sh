#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"
# The PyPI release (0.2.5.2) crashes with rdflib >= 6 (`str.decode`), so use the
# development head (3.0.0b4).
python_venv "$TOOLS_HOME/shaclgen-venv" "git+https://github.com/alexiskeely/shaclgen@a057dc336839ff915c72fbd37abb0a028f956540"

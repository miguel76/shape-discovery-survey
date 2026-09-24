#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"
python_venv "$TOOLS_HOME/shexer-venv" shexer==2.7.3.1

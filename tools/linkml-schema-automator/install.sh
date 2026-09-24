#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"
python_venv "$TOOLS_HOME/linkml-venv" schema-automator==0.5.7 linkml==1.11.1

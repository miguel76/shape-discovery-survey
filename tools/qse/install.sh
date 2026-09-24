#!/usr/bin/env bash
# QSE ships a prebuilt fat jar (jar/qse.jar) in its repository; the queries in
# src/main/resources are also needed at run time.
set -euo pipefail
source "$(dirname "$0")/../common.sh"
git_checkout https://github.com/dkw-aau/qse "$TOOLS_HOME/qse" 4bcfb04a30c27fe3e802413b73e00e08033da2b7

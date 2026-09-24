#!/usr/bin/env bash
# Builds only the shacl-generate module of SHACL Play (the shacl-play-app CLI
# depends on artifacts only available from jitpack.io) and applies a fix for
# SELECT queries ignoring their variable bindings (see select-bindings.patch).
set -euo pipefail
source "$(dirname "$0")/../common.sh"
src="$TOOLS_HOME/shacl-play-src"
git_checkout https://github.com/sparna-git/shacl-play "$src" 4e850782d5606daeb0bee30f71f524522072fc94
git -C "$src" apply "$REPO_ROOT/tools/shacl-play/select-bindings.patch"
(cd "$src" && mvn -q -B -DskipTests -pl shacl-generate -am install \
    && mvn -q -B -pl shacl-generate dependency:build-classpath -Dmdep.outputFile="$TOOLS_HOME/shacl-play.classpath")
echo ":$src/shacl-generate/target/shacl-generate-0.12.4.jar" >> "$TOOLS_HOME/shacl-play.classpath"

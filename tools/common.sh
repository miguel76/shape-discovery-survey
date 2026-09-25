# Shared helpers for tools/*/install.sh and tools/*/run.sh (source, don't execute).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_HOME="${TOOLS_HOME:-$REPO_ROOT/.tools}"
mkdir -p "$TOOLS_HOME"

# git_checkout URL DIR COMMIT: shallow-fetch a pinned commit into DIR.
git_checkout() {
    local url="$1" dir="$2" commit="$3"
    if [ ! -d "$dir/.git" ]; then
        git init -q "$dir"
        git -C "$dir" remote add origin "$url"
    fi
    git -C "$dir" fetch -q --depth 1 origin "$commit"
    git -C "$dir" checkout -q --force FETCH_HEAD
}

# python_venv DIR PIP_ARGS...: create a venv (if missing) and pip install into it.
python_venv() {
    local dir="$1"; shift
    [ -x "$dir/bin/python" ] || python3 -m venv "$dir"
    "$dir/bin/pip" install -q --disable-pip-version-check "$@"
}

# limit_memory: cap the address space of Python-based tools (TOOL_VMEM_MB, default
# 12288) so that a run on a large KG fails with MemoryError instead of triggering
# the kernel OOM killer. Not used for Java tools, whose heap is set with -Xmx.
limit_memory() {
    ulimit -v $(( ${TOOL_VMEM_MB:-12288} * 1024 ))
}

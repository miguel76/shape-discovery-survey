#!/usr/bin/env python3
"""Run the shape discovery tools on a KG and collect their outputs.

usage: pipeline/run.py KG [--tools t1,t2] [--endpoint] [--timeout SECONDS]

KG is a directory name under data/ holding a kg.json descriptor:
  files               RDF dump files (any serialisation Jena riot can read, possibly .gz);
                      quads are merged into a single graph (union of all named graphs,
                      duplicates removed)
  endpoint            (optional) SPARQL endpoint URL of the KG, used by --endpoint
                      unless --local-endpoint is given
  reference_shapes    (optional) hand-written SHACL shapes used by evaluate.py
  reference_inference (optional) pySHACL inference mode for the reference shapes

Every tool lives in tools/<name>/ with a run.sh taking
    run.sh (file INPUT | endpoint URL) OUTDIR
and writing OUTDIR/shapes.ttl. tools/registry.json declares, per tool, the
supported modes and the input serialisation it wants (nt or ttl).

Outputs go to results/<KG>/<tool>[@endpoint]/ (shapes.ttl, run.log, run.json);
large intermediate files go to work/<KG>/.

Environment: JAVA_XMX (heap for Java tools, default 8g), FUSEKI_XMX (default 4g),
FUSEKI_PORT (default 3030), TOOL_TIMEOUT (seconds, default 3600).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_HOME = Path(os.environ.get("TOOLS_HOME", ROOT / ".tools"))
FUSEKI_JAR = TOOLS_HOME / "fuseki" / "jena-fuseki-server-5.2.0.jar"
FUSEKI_PORT = int(os.environ.get("FUSEKI_PORT", "3030"))


RIOT = ["java", "-Xmx4g", "-cp", str(FUSEKI_JAR), "riotcmd.riot"]


def stale(dest, sources):
    return not dest.exists() or dest.stat().st_mtime < max(s.stat().st_mtime for s in sources)


def prepare(kg_dir, work):
    """Build work/<KG>/data.nt (always) and data.ttl (from data.nt) with Jena riot, streaming."""
    kg = json.loads((kg_dir / "kg.json").read_text())
    sources = [kg_dir / f for f in kg.get("files", [])]
    if not sources:
        return kg, {}
    nt, ttl = work / "data.nt", work / "data.ttl"
    if stale(nt, sources):
        print(f"[prepare] {rel(nt)}", flush=True)
        # --merge turns quads into triples of the default graph (plain `--output=ntriples`
        # silently drops them); the same triple may occur in several graphs, hence sort -u.
        riot = subprocess.Popen([*RIOT, "--merge", "--output=ntriples", *map(str, sources)], stdout=subprocess.PIPE)
        with open(nt, "wb") as f:
            subprocess.run(["sort", "-u", "-S", "2G", "-T", str(work)], stdin=riot.stdout, stdout=f, check=True,
                           env={**os.environ, "LC_ALL": "C"})
        if riot.wait() != 0:
            nt.unlink()
            raise RuntimeError("riot failed")
    if stale(ttl, [nt]):
        print(f"[prepare] {rel(ttl)}", flush=True)
        with open(ttl, "wb") as f:
            subprocess.run([*RIOT, "--stream=turtle", str(nt)], stdout=f, check=True)
    return kg, {"nt": nt, "ttl": ttl}


class LocalEndpoint:
    """Serve the prepared N-Triples dump with Fuseki for the duration of a run.

    The data is loaded into a TDB2 store (work/<KG>/tdb2) rather than kept in memory:
    with an in-memory dataset Fuseki's footprint on CCKG (4.7M triples) grew from
    4 GB to over 12 GB under many small queries until it was OOM-killed.
    """

    def __init__(self, data):
        self.data, self.proc = data, None
        self.db = data.parent / "tdb2"
        self.log = data.parent / "fuseki.log"
        self.url = f"http://localhost:{FUSEKI_PORT}/kg/sparql"

    def __enter__(self):
        if stale(self.db / "loaded", [self.data]):
            print(f"[prepare] {rel(self.db)}", flush=True)
            shutil.rmtree(self.db, ignore_errors=True)
            subprocess.run(["java", "-Xmx4g", "-cp", str(FUSEKI_JAR), "tdb2.tdbloader", "--loc", str(self.db),
                            str(self.data)], check=True, stdout=subprocess.DEVNULL)
            (self.db / "loaded").touch()
        with open(self.log, "wb") as log:
            self.proc = subprocess.Popen(["java", "-Xmx" + os.environ.get("FUSEKI_XMX", "4g"), "-jar", str(FUSEKI_JAR),
                                          "--port", str(FUSEKI_PORT), "--tdb2", "--loc", str(self.db), "/kg"],
                                         stdout=log, stderr=subprocess.STDOUT)
        for _ in range(1800):
            try:
                urllib.request.urlopen(self.url + "?query=ASK%7B%7D", timeout=2)
                return self
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(1)
        raise RuntimeError("Fuseki did not start")

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait()


def rel(path):
    """Paths relative to the repository root, so run.json files are portable."""
    p = str(path)
    return p[len(str(ROOT)) + 1:] if p.startswith(str(ROOT) + os.sep) else p


def has_shapes(path):
    """Cheap check that the output declares at least one node shape (some tools exit 0
    after logging an error and write a file with prefixes only)."""
    if not path.is_file():
        return False
    with open(path, errors="replace") as f:
        return any("NodeShape" in line for line in f)


def run_tool(tool, mode, source, outdir, timeout):
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    cmd = [str(ROOT / "tools" / tool / "run.sh"), mode, str(source), str(outdir)]
    start = time.monotonic()
    with open(outdir / "run.log", "wb") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        status, timed_out = None, False
        while status is None:
            pid, st, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                status = st
            elif time.monotonic() - start > timeout:
                os.killpg(proc.pid, 9)
                timed_out = True
            else:
                time.sleep(0.2)
    meta = {
        "tool": tool, "mode": mode, "source": rel(source), "command": [rel(c) for c in cmd],
        "exit_code": os.waitstatus_to_exitcode(status), "timed_out": timed_out,
        "wall_seconds": round(time.monotonic() - start, 2),
        "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 2),
        # Linux reports ru_maxrss in KiB; this is the largest process in the tree.
        "peak_rss_mb": round(usage.ru_maxrss / 1024, 1),
        "has_output": has_shapes(outdir / "shapes.ttl"),
    }
    (outdir / "run.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kg")
    p.add_argument("--tools", help="comma-separated subset of tools/registry.json")
    p.add_argument("--endpoint", action="store_true",
                   help="also run endpoint-capable tools against a SPARQL endpoint "
                        "(the KG's own 'endpoint', or a local Fuseki serving the dump)")
    p.add_argument("--local-endpoint", action="store_true",
                   help="with --endpoint, serve the dump with a local Fuseki even if the KG declares an endpoint")
    p.add_argument("--timeout", type=float, default=float(os.environ.get("TOOL_TIMEOUT", 3600)))
    args = p.parse_args()

    registry = json.loads((ROOT / "tools" / "registry.json").read_text())
    tools = args.tools.split(",") if args.tools else list(registry)
    kg_dir = ROOT / "data" / args.kg
    work = ROOT / "work" / args.kg
    results = ROOT / "results" / args.kg
    work.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("JAVA_XMX", "8g")
    kg, prepared = prepare(kg_dir, work)

    runs = []
    for tool in tools:
        if "file" in registry[tool]["modes"] and registry[tool]["input"] in prepared:
            runs.append((tool, "file", prepared[registry[tool]["input"]], results / tool))
    endpoint_tools = [t for t in tools if args.endpoint and "endpoint" in registry[t]["modes"]]

    def go(batch):
        for tool, mode, source, outdir in batch:
            print(f"[run] {tool} ({mode})", flush=True)
            meta = run_tool(tool, mode, source, outdir, args.timeout)
            status = "ok" if meta["exit_code"] == 0 and meta["has_output"] else "FAILED"
            print(f"      {status} in {meta['wall_seconds']}s, peak RSS {meta['peak_rss_mb']} MB", flush=True)

    go(runs)
    if endpoint_tools:
        if kg.get("endpoint") and not args.local_endpoint:
            go([(t, "endpoint", kg["endpoint"], results / f"{t}@endpoint") for t in endpoint_tools])
        else:
            with LocalEndpoint(prepared["nt"]) as ep:
                go([(t, "endpoint", ep.url, results / f"{t}@endpoint") for t in endpoint_tools])


if __name__ == "__main__":
    sys.exit(main())

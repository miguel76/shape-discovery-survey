#!/usr/bin/env python3
"""Dangling links by source: links to undefined entities, compared with all links of the same kind.

usage: pipeline/link_sources.py KG [--out DIR] [--min-undefined N]

The dangling-range check of kg_checks.py counts IRI values of properties with a declared
class rdfs:range that have no rdf:type anywhere in the KG. This script breaks those links
down by where they come from and what they point to, so that the undefined targets can be
compared with all the targets of the same kind:

  source   the named graph that contains the link (the dump must be in N-Quads; for
           triple formats every link counts as coming from the default graph)
  property the predicate of the link (only properties with a declared class range)
  family   the target IRI's path with the part of each segment after its first '.' replaced
           by '*', and the last segment replaced by '*' if it has no '.':
           .../variables/mip/rv850 -> variables/mip/*,
           .../datasets/cordex.output.EUR-11.x -> datasets/cordex.*

For each (source, property, family) it reports the links and distinct targets, and how
many of them are undefined. Rows with no undefined target are summarised per source only.
Ranges and types are read from all the dump files and from the KG's ontology files.

Writes results/<KG>/dangling-by-source.md and dangling-by-source.json.
"""
import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_RANGE = "http://www.w3.org/2000/01/rdf-schema#range"
NON_CLASS_RANGES = {"http://www.w3.org/2000/01/rdf-schema#Literal",
                    "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString"}
XSD = "http://www.w3.org/2001/XMLSchema#"
TERM = r'(<[^>]*>|_:\S+)'
# subject, predicate, IRI object, optional graph; lines with literal objects do not match
LINE = re.compile(rf'^\s*{TERM}\s+<([^>]*)>\s+<([^>]*)>\s*(?:<([^>]*)>)?\s*\.\s*$')
DEFAULT_GRAPH = "(default graph)"


def statements(files):
    """(subject, predicate, IRI object, graph) for every statement with an IRI object."""
    for f in files:
        opener = gzip.open if f.suffix == ".gz" else open
        if not re.search(r"\.(nq|nt)(\.gz)?$", f.name):
            sys.exit(f"{f}: only N-Quads/N-Triples dumps are supported")
        with opener(f, "rt", encoding="utf-8") as src:
            for line in src:
                m = LINE.match(line)
                if m:
                    yield m.group(1), m.group(2), m.group(3), m.group(4) or DEFAULT_GRAPH


def family(iri):
    segments = re.sub(r"^[a-z]+://[^/]+/", "", iri).rstrip("/").split("/")
    out = [s.split(".", 1)[0] + ".*" if "." in s else s for s in segments]
    if "." not in segments[-1]:
        out[-1] = "*"
    return "/".join(out)


def common_prefix(paths):
    """The longest common prefix of whole path segments, with its trailing '/'."""
    split = [p.split("/") for p in paths]
    prefix = []
    for parts in zip(*split):
        if len(set(parts)) != 1:
            break
        prefix.append(parts[0])
    prefix = prefix[:min(len(s) for s in split) - 1] if split else prefix
    return "/".join(prefix) + "/" if prefix else ""


def short(iri, bases):
    for b in bases:
        if iri.startswith(b):
            return iri[len(b):]
    return iri


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kg")
    p.add_argument("--out", type=Path, help="output directory (default: results/<KG>)")
    p.add_argument("--min-undefined", type=int, default=1,
                   help="only list (source, property, family) rows with at least this many undefined targets")
    args = p.parse_args()
    kg_dir = ROOT / "data" / args.kg
    kg = json.loads((kg_dir / "kg.json").read_text())
    dumps = [kg_dir / f for f in kg["files"]]
    ontologies = [kg_dir / f for f in kg.get("ontologies", [])]
    out_dir = args.out or ROOT / "results" / args.kg

    # pass 1: typed IRIs and class ranges
    typed, ranges = set(), defaultdict(set)
    for s, pr, o, _ in statements(dumps + [f for f in ontologies if re.search(r"\.(nq|nt)(\.gz)?$", f.name)]):
        if pr == RDF_TYPE:
            typed.add(s)
        elif pr == RDFS_RANGE and o not in NON_CLASS_RANGES and not o.startswith(XSD):
            ranges[s[1:-1]].add(o)

    # pass 2: links of properties with a class range
    links = defaultdict(lambda: [0, 0, set(), set()])  # links, undefined links, targets, undefined targets
    families = defaultdict(lambda: [set(), set(), set()])  # targets, undefined targets, sources
    for _, pr, o, g in statements(dumps):
        if pr in ranges:
            fam = family(o)
            row = links[(g, pr, fam)]
            undefined = f"<{o}>" not in typed
            row[0] += 1
            row[2].add(o)
            families[fam][0].add(o)
            if undefined:
                row[1] += 1
                row[3].add(o)
                families[fam][1].add(o)
                families[fam][2].add(g)

    rows = [{"source": g, "property": pr, "range": sorted(ranges[pr]), "family": fam,
             "links": r[0], "undefined_links": r[1], "targets": len(r[2]), "undefined_targets": len(r[3]),
             "examples": sorted(r[3])[:3]}
            for (g, pr, fam), r in links.items()]
    rows.sort(key=lambda r: (-r["undefined_targets"], r["source"], r["property"], r["family"]))
    by_source = defaultdict(lambda: {"links": 0, "undefined_links": 0})
    for r in rows:
        by_source[r["source"]]["links"] += r["links"]
        by_source[r["source"]]["undefined_links"] += r["undefined_links"]

    by_family = {fam: {"targets": len(f[0]), "undefined_targets": len(f[1]), "sources": sorted(f[2])}
                 for fam, f in families.items() if f[1]}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dangling-by-source.json").write_text(json.dumps(
        {"by_source": by_source, "by_family": by_family, "rows": rows}, indent=2) + "\n")
    write_markdown(out_dir / "dangling-by-source.md", args.kg, by_source, by_family, rows, args.min_undefined)
    print((out_dir / "dangling-by-source.md").read_text())


def write_markdown(path, kg, by_source, by_family, rows, min_undefined):
    graph_bases = sorted({r["source"].rsplit("/", 1)[0] + "/" for r in rows if "/" in r["source"]}, key=len)
    prop_bases = sorted({r["property"].rsplit("/", 2)[0] + "/" for r in rows}, key=len)
    shown = [r for r in rows if r["undefined_targets"] >= min_undefined]
    fam_base = common_prefix([r["family"] for r in shown])
    target_base = "https://" + re.sub(r"^[a-z]+://", "", shown[0]["examples"][0]).split("/", 1)[0] + "/" + fam_base \
        if shown else ""

    def pct(a, b):
        return f"{a:,} of {b:,} ({100 * a / b:.1f}%)" if b else "0"

    lines = [f"# Dangling links by source for `{kg}`", "",
             "Generated by `pipeline/link_sources.py`; see its docstring for the definitions. A link is",
             "*dangling* when its target has no `rdf:type` anywhere in the KG. Only properties with a",
             "declared class `rdfs:range` are considered.", "",
             "## By source graph", "",
             "| source | links | dangling links |", "|---|---|---|"]
    for g, s in sorted(by_source.items(), key=lambda x: -x[1]["undefined_links"]):
        lines.append(f"| `{short(g, graph_bases)}` | {s['links']:,} | {pct(s['undefined_links'], s['links'])} |")
    lines += ["", "## By target family (all sources)", "",
              "Distinct target IRIs of each family that has undefined ones, over all sources and properties.", "",
              "| target family | undefined targets | sources linking to undefined targets |", "|---|---|---|"]
    for fam, f in sorted(by_family.items(), key=lambda x: -x[1]["undefined_targets"]):
        srcs = ", ".join(f"`{short(g, graph_bases)}`" for g in f["sources"])
        lines.append(f"| `{fam[len(fam_base):]}` | {pct(f['undefined_targets'], f['targets'])} | {srcs} |")
    lines += ["", "## By source, property and target family", "",
              f"Rows with at least one undefined target. *Targets* are distinct IRIs; families and examples "
              f"are relative to `{target_base}`.", "",
              "| source | property | target family | undefined targets | dangling links | examples |",
              "|---|---|---|---|---|---|"]
    for r in shown:
        ex = ", ".join(f"`{short(e, [target_base])}`" for e in r["examples"])
        lines.append(f"| `{short(r['source'], graph_bases)}` | `{short(r['property'], prop_bases)}` | "
                     f"`{r['family'][len(fam_base):]}` | {pct(r['undefined_targets'], r['targets'])} | "
                     f"{pct(r['undefined_links'], r['links'])} | {ex} |")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

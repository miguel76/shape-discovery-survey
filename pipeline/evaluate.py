#!/usr/bin/env python3
"""Evaluate the shapes produced by pipeline/run.py for a KG.

usage: pipeline/evaluate.py KG [--inference none|subclass|rdfs]

For each results/<KG>/<regime>/<run>/shapes.ttl it computes:
  * syntax      - does the output parse as RDF (Turtle)?
  * vocabulary  - IRIs in the sh: namespace that are not SHACL terms, or are
                  used as predicates without being SHACL properties (e.g.
                  sh:dataType or sh:NodeKind instead of sh:datatype / sh:nodeKind):
                  validators silently ignore them, so the constraint is lost;
  * well-formed - violations of the SHACL-SHACL meta-shapes;
  * profile     - number of node/property shapes and constraint components used, and
                  how many (target class, path) pairs repeat a path that is also
                  constrained on a superclass of the class (redundancy with respect
                  to the class hierarchy of the KG and its `ontologies`);
  * self-validation - validating the KG itself against the extracted shapes
                  (Jena SHACL via ShaclStats.java) under the same inference
                  regime the shapes were extracted under (pipeline/regimes.py):
                  shapes that describe the data should mostly conform, and the
                  violations are the "suspicious" nodes;
  * reference   - if data/<KG>/kg.json names reference shapes (and, optionally, the
                  `reference_regime` they are written for; `reference_inference`
                  is accepted as an alias): overlap of
                  (target class, path) pairs and agreement of the main
                  constraints on the shared pairs, plus how many of the
                  violations found by the reference shapes (validated under the
                  same regime) are also found.

Writes results/<KG>/<regime>/<run>/eval.json, results/<KG>/<regime>/summary.md and
results/<KG>/summary.md, which compares the regimes evaluated so far.
Environment: JAVA_XMX (heap for validation, default 8g), VALIDATION_BUDGET
(seconds per shapes file after which only a random sample of focus nodes has
been validated, default 3600), VALIDATION_TIMEOUT (hard limit, default budget +
1 hour). Validation results in work/<KG>/<regime>/validation/ are reused while
newer than both the data and the shapes.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pyshacl
from rdflib import RDF, RDFS, SH, Graph, URIRef
from rdflib.collection import Collection

from regimes import REGIMES, validation_data

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(pyshacl.__file__).parent / "assets"
TOOLS_HOME = Path(os.environ.get("TOOLS_HOME", ROOT / ".tools"))
JENA_JAR = TOOLS_HOME / "fuseki" / "jena-fuseki-server-5.2.0.jar"

# Constraint parameters we report on (SHACL Core).
COMPONENT_PARAMS = [
    SH["class"], SH.datatype, SH.nodeKind, SH.minCount, SH.maxCount, SH["in"], SH.hasValue,
    SH["or"], SH["and"], SH["not"], SH.xone, SH.node, SH.qualifiedValueShape, SH.pattern,
    SH.minLength, SH.maxLength, SH.minInclusive, SH.maxInclusive, SH.minExclusive, SH.maxExclusive,
    SH.languageIn, SH.uniqueLang, SH.equals, SH.disjoint, SH.lessThan, SH.closed,
]


def shacl_vocabulary():
    """(all sh: terms, sh: terms that are properties) according to the SHACL vocabulary."""
    g = Graph().parse(ASSETS / "shacl.ttl")
    terms = {t for t in g.subjects() if isinstance(t, URIRef) and str(t).startswith(str(SH))}
    return terms, set(g.subjects(RDF.type, RDF.Property)) & terms


def misused_shacl_terms(g, vocab):
    """sh: IRIs that are not SHACL terms, or SHACL non-properties used as predicates (e.g. sh:NodeKind)."""
    terms, properties = vocab
    bad = {t for t in g.all_nodes() if isinstance(t, URIRef) and str(t).startswith(str(SH)) and t not in terms}
    bad |= {p for p in g.predicates() if str(p).startswith(str(SH)) and p not in properties}
    return sorted(g.qname(t) for t in bad)


def load(path):
    g = Graph()
    g.parse(path, format="turtle")
    return g


# --------------------------------------------------------------------- profile
def node_shapes(g):
    shapes = set(g.subjects(RDF.type, SH.NodeShape))
    for p in (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf):
        shapes |= set(g.subjects(p, None))
    return shapes - set(g.subjects(SH.path, None))


def property_shapes(g):
    return set(g.subjects(SH.path, None))


def profile(g, hierarchy=None):
    usage = Counter()
    for p in COMPONENT_PARAMS:
        n = len(set(g.subjects(p, None)))
        if n:
            usage[g.qname(p)] = n
    table = constraint_table(g)
    return {
        "triples": len(g),
        "node_shapes": len(node_shapes(g)),
        "property_shapes": len(property_shapes(g)),
        "class_path_pairs": len(table),
        "pairs_repeated_from_superclass": inherited_pairs(table, hierarchy or {}),
        "constraint_usage": dict(sorted(usage.items())),
    }


# ---------------------------------------------------------- constraint summary
def _members(g, node):
    """The shape itself plus the members of its sh:or / sh:and / sh:xone lists."""
    out = [node]
    for p in (SH["or"], SH["and"], SH.xone):
        for lst in g.objects(node, p):
            for m in Collection(g, lst):
                out.extend(_members(g, m))
    return out


def constraint_table(g):
    """{(target class, path): {datatype, class, nodeKind, min, max}} for simple (IRI) paths."""
    table = {}
    for ns in node_shapes(g):
        classes = set(g.objects(ns, SH.targetClass))
        if (ns, RDF.type, RDFS.Class) in g:  # implicit class target
            classes.add(ns)
        for ps in g.objects(ns, SH.property):
            path = g.value(ps, SH.path)
            if not isinstance(path, URIRef) or path == RDF.type:
                continue
            c = {"datatype": set(), "class": set(), "nodeKind": set(), "min": 0, "max": None}
            for m in _members(g, ps):
                c["datatype"] |= {str(o) for o in g.objects(m, SH.datatype)}
                c["class"] |= {str(o) for o in g.objects(m, SH["class"])}
                c["nodeKind"] |= {str(o) for o in g.objects(m, SH.nodeKind)}
            mn, mx = g.value(ps, SH.minCount), g.value(ps, SH.maxCount)
            c["min"] = int(mn) if mn is not None else 0
            c["max"] = int(mx) if mx is not None else None
            for cls in classes:
                key = (str(cls), str(path))
                if key in table:  # several property shapes for one path: keep the loosest reading
                    old = table[key]
                    for k in ("datatype", "class", "nodeKind"):
                        old[k] |= c[k]
                    old["min"] = min(old["min"], c["min"])
                    old["max"] = None if None in (old["max"], c["max"]) else max(old["max"], c["max"])
                else:
                    table[key] = c
    return table


def class_hierarchy(work):
    """{class: all its named superclasses}, from the rdfs:subClassOf triples between IRIs in
    the dump and in the kg.json `ontologies` (work/<KG>/data.nt, work/<KG>/ontologies.nt)."""
    parents = {}
    for f in (work / "data.nt", work / "ontologies.nt"):
        if not f.exists():
            continue
        with open(f, "rb") as src:
            for line in src:
                if b" <http://www.w3.org/2000/01/rdf-schema#subClassOf> <" not in line or not line.startswith(b"<"):
                    continue
                sub, _, sup = line.decode().split(" ", 3)[:3]
                parents.setdefault(sub[1:-1], set()).add(sup[1:-1])
    closure = {}

    def supers(c, seen):
        for p in parents.get(c, ()):
            if p not in seen:
                seen.add(p)
                supers(p, seen)
        return seen

    for c in parents:
        closure[c] = supers(c, set()) - {c}
    return closure


def inherited_pairs(table, hierarchy):
    """(class, path) pairs whose path is also constrained on a superclass of the class."""
    return sum(1 for c, path in table if any((s, path) in table for s in hierarchy.get(c, ())))


def compare_to_reference(table, ref):
    shared = sorted(set(table) & set(ref))
    precision = len(shared) / len(table) if table else 0.0
    recall = len(shared) / len(ref) if ref else 0.0

    def agree(key, test):
        return sum(1 for k in shared if test(table[k], ref[k]) and key(ref[k])), sum(1 for k in shared if key(ref[k]))

    checks = {
        # the reference fixes a datatype and the tool proposes exactly that one
        "datatype": agree(lambda r: r["datatype"], lambda t, r: t["datatype"] == r["datatype"]),
        # the reference fixes a class (possibly a disjunction) and the tool proposes exactly those
        "class": agree(lambda r: r["class"], lambda t, r: t["class"] == r["class"]),
        # mandatory (minCount >= 1) vs optional
        "required": agree(lambda r: True, lambda t, r: (t["min"] >= 1) == (r["min"] >= 1)),
        # single-valued (maxCount 1) vs multi-valued
        "functional": agree(lambda r: True, lambda t, r: (t["max"] == 1) == (r["max"] == 1)),
    }
    return {
        "pairs_extracted": len(table),
        "pairs_reference": len(ref),
        "pairs_shared": len(shared),
        "pair_precision": round(precision, 3),
        "pair_recall": round(recall, 3),
        "missing_pairs": [list(k) for k in sorted(set(ref) - set(table))],
        "constraint_agreement": {k: {"agree": a, "of": n} for k, (a, n) in checks.items()},
    }


# ------------------------------------------------------------------ validation
def validate_kg(data_file, shapes_file, out_file, focus_paths=False):
    """Validate the KG dump against a shapes file with Jena SHACL (scales to millions of triples)."""
    fresh = out_file.exists() and out_file.stat().st_size > 0 and \
        out_file.stat().st_mtime > max(data_file.stat().st_mtime, shapes_file.stat().st_mtime)
    if not fresh:
        budget = int(os.environ.get("VALIDATION_BUDGET", 3600))
        cmd = ["java", f"-Xmx{os.environ.get('JAVA_XMX', '8g')}", "-cp", str(JENA_JAR),
               str(ROOT / "pipeline" / "ShaclStats.java"), str(data_file),
               *(["--focus-paths"] if focus_paths else []), str(out_file), str(shapes_file)]
        try:
            with open(out_file.with_suffix(".log"), "w") as log:
                proc = subprocess.run(cmd, stderr=log, stdout=subprocess.DEVNULL,
                                      env={**os.environ, "VALIDATION_BUDGET": str(budget)},
                                      timeout=float(os.environ.get("VALIDATION_TIMEOUT", budget + 3600)))
        except subprocess.TimeoutExpired:
            out_file.unlink(missing_ok=True)
            return {"error": "validation timed out"}
        if proc.returncode != 0 or not out_file.exists() or out_file.stat().st_size == 0:
            out_file.unlink(missing_ok=True)
            tail = out_file.with_suffix(".log").read_text().strip()[-300:]
            return {"error": f"validator exited with {proc.returncode}: {tail}"}
    res = json.loads(out_file.read_text())
    if "focus_paths" in res:
        res["_focus_paths"] = {tuple(fp) for fp in res.pop("focus_paths")}
    return res


def validate(data, shapes, inference="none"):
    """pySHACL validation of in-memory graphs (used for the small shapes-vs-meta-shapes check)."""
    try:
        conforms, report, _ = pyshacl.validate(data, shacl_graph=shapes, inference=inference,
                                               allow_warnings=True, abort_on_first=False)
    except Exception as e:  # pySHACL rejects some ill-formed shapes graphs outright
        return {"error": f"{type(e).__name__}: {e}"[:500]}
    results = list(report.subjects(RDF.type, SH.ValidationResult))
    focus = {(str(report.value(r, SH.focusNode)), str(report.value(r, SH.resultPath))) for r in results}
    by_component = Counter(report.qname(report.value(r, SH.sourceConstraintComponent)) for r in results)
    return {
        "conforms": bool(conforms),
        "violations": len(results),
        "focus_nodes": len({f for f, _ in focus}),
        "by_component": dict(by_component.most_common()),
        "_focus_paths": focus,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kg")
    p.add_argument("--inference", choices=REGIMES, default="none",
                   help="inference regime the shapes were extracted under (default: none)")
    args = p.parse_args()

    kg_dir, results = ROOT / "data" / args.kg, ROOT / "results" / args.kg / args.inference
    kg = json.loads((kg_dir / "kg.json").read_text())
    work = ROOT / "work" / args.kg
    data_file = validation_data(work, args.inference,
                                lambda msg: print(msg.replace(str(ROOT) + os.sep, ""), flush=True))
    val_dir = work / args.inference / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    vocab = shacl_vocabulary()
    hierarchy = class_hierarchy(work)
    meta_shapes = Graph().parse(ASSETS / "shacl-shacl.ttl")

    ref_table, ref_validation = None, None
    if kg.get("reference_shapes"):
        ref = load(kg_dir / kg["reference_shapes"])
        ref_table = constraint_table(ref)
        print("[validate] reference shapes", flush=True)
        ref_validation = validate_kg(data_file, kg_dir / kg["reference_shapes"], val_dir / "reference.json",
                                     focus_paths=True)

    evaluations = {}
    for run_dir in sorted(d for d in results.iterdir() if d.is_dir()):
        ev = {"run": run_dir.name, **json.loads((run_dir / "run.json").read_text())}
        shapes_file = run_dir / "shapes.ttl"
        try:
            g = load(shapes_file)
        except Exception as e:
            ev["syntax"] = f"error: {type(e).__name__}: {e}"[:500]
            ev["inference"] = args.inference
            (run_dir / "eval.json").write_text(json.dumps(ev, indent=2, default=list) + "\n")
            evaluations[run_dir.name] = ev
            continue
        ev["syntax"] = "ok"
        ev["non_shacl_terms"] = misused_shacl_terms(g, vocab)
        wf = validate(g, meta_shapes)
        ev["well_formedness"] = {k: v for k, v in wf.items() if not k.startswith("_")}
        ev["profile"] = profile(g, hierarchy)
        print(f"[validate] {run_dir.name}", flush=True)
        sv = validate_kg(data_file, shapes_file, val_dir / f"{run_dir.name}.json",
                         focus_paths=ref_table is not None)
        ev["self_validation"] = {k: v for k, v in sv.items() if not k.startswith("_")}
        if ref_table is not None:
            ev["reference"] = compare_to_reference(constraint_table(g), ref_table)
            if "_focus_paths" in sv and "_focus_paths" in (ref_validation or {}):
                expected = ref_validation["_focus_paths"]
                ev["reference"]["reference_violations_found"] = {
                    "found": len(expected & sv["_focus_paths"]), "of": len(expected)}
        ev["inference"] = args.inference
        (run_dir / "eval.json").write_text(json.dumps(ev, indent=2, default=list) + "\n")
        evaluations[run_dir.name] = ev

    write_summary(results / "summary.md", args.kg, args.inference, kg, evaluations, ref_validation)
    write_regime_comparison(results.parent / "summary.md", args.kg, kg)
    print((results / "summary.md").read_text())


def write_summary(path, name, regime, kg, evs, ref_validation):
    lines = [f"# Results for `{name}`, inference regime `{regime}`", "", kg.get("description", ""), "",
             f"Shapes extracted and validated under the `{regime}` regime (see `pipeline/regimes.py`). "
             "Generated by `pipeline/evaluate.py`; see `eval.json` in each run directory for details.", "",
             "## Execution and output profile", "",
             "| run | exit | wall s | peak RSS MB | node shapes | property shapes | (class, path) pairs | "
             "of which also on a superclass | non-SHACL terms | SHACL-SHACL violations |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r, ev in evs.items():
        pr = ev.get("profile", {})
        wf = ev.get("well_formedness", {})
        lines.append(f"| {r} | {ev['exit_code']}{' (timeout)' if ev['timed_out'] else ''} | {ev['wall_seconds']} | "
                     f"{ev['peak_rss_mb']} | {pr.get('node_shapes', '-')} | {pr.get('property_shapes', '-')} | "
                     f"{pr.get('class_path_pairs', '-')} | {pr.get('pairs_repeated_from_superclass', '-')} | "
                     f"{', '.join(ev.get('non_shacl_terms', [])) or '-'} | "
                     f"{wf.get('violations', wf.get('error', '-'))} |")
    lines += ["", "## Constraint components used (number of shapes using each)", ""]
    comps = sorted({c for ev in evs.values() for c in ev.get("profile", {}).get("constraint_usage", {})})
    lines += ["| run | " + " | ".join(comps) + " |", "|---|" + "---|" * len(comps)]
    for r, ev in evs.items():
        u = ev.get("profile", {}).get("constraint_usage", {})
        lines.append(f"| {r} | " + " | ".join(str(u.get(c, "")) for c in comps) + " |")
    lines += ["", "## Validating the KG against the extracted shapes", ""]
    ref_regime = kg.get("reference_regime", kg.get("reference_inference"))
    if ref_validation is not None and ref_regime and ref_regime != regime:
        lines += [f"Note: the reference shapes are written for the `{ref_regime}` regime; here they are "
                  f"validated under `{regime}`, like the extracted shapes.", ""]
    if ref_validation is not None:
        lines += [f"Reference shapes: {ref_validation.get('violations')} violations on "
                  f"{ref_validation.get('focus_nodes')} focus nodes "
                  f"({', '.join(f'{k}: {v}' for k, v in ref_validation.get('by_component', {}).items())}).", ""]
    lines += ["| run | conforms | violations | focus nodes | by component | reference violations also found |",
              "|---|---|---|---|---|---|"]
    for r, ev in evs.items():
        sv = ev.get("self_validation", {})
        rv = ev.get("reference", {}).get("reference_violations_found")
        if "error" in sv:
            lines.append(f"| {r} | error: {sv['error'][:80]} | | | | |")
            continue
        if sv.get("partial"):
            r = f"{r} (sample: {sv['validated_focus_nodes']}/{sv['target_focus_nodes']} focus nodes)"
        lines.append(f"| {r} | {sv.get('conforms', '-')} | {sv.get('violations', '-')} | {sv.get('focus_nodes', '-')} | "
                     f"{', '.join(f'{k}: {v}' for k, v in sv.get('by_component', {}).items()) or '-'} | "
                     f"{str(rv['found']) + '/' + str(rv['of']) if rv else '-'} |")
    if any("reference" in ev for ev in evs.values()):
        lines += ["", "## Comparison with the reference shapes", "",
                  "Pairs are (target class, property path) with an IRI path, excluding `rdf:type`. "
                  "Agreement is computed on the shared pairs where the reference states the constraint.", "",
                  "| run | pairs | shared | precision | recall | datatype | class | required | functional |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r, ev in evs.items():
            ref = ev.get("reference")
            if not ref:
                continue
            ca = ref["constraint_agreement"]
            lines.append(f"| {r} | {ref['pairs_extracted']} | {ref['pairs_shared']} | {ref['pair_precision']} | "
                         f"{ref['pair_recall']} | " + " | ".join(f"{ca[k]['agree']}/{ca[k]['of']}" for k in
                                                                ("datatype", "class", "required", "functional")) + " |")
    path.write_text("\n".join(lines) + "\n")


def write_regime_comparison(path, name, kg):
    """results/<KG>/summary.md: one row per run, one column group per evaluated regime."""
    table = {}
    regimes = [r for r in REGIMES if (path.parent / r / "summary.md").exists()]
    for regime in regimes:
        for ev_file in sorted((path.parent / regime).glob("*/eval.json")):
            ev = json.loads(ev_file.read_text())
            table.setdefault(ev["run"], {})[regime] = ev
    lines = [f"# Results for `{name}`: inference regimes compared", "", kg.get("description", ""), "",
             "Each regime is applied to both shape discovery and validation (see `pipeline/regimes.py`); "
             "details per regime in " + ", ".join(f"[`{r}/summary.md`]({r}/summary.md)" for r in regimes) + ".", "",
             "Each cell: node shapes / property shapes; (target class, property) pairs constrained, and how "
             "many of them are also constrained on a superclass of the class; then, validating the KG "
             "against the extracted shapes, the share of focus nodes with at least one violation and the "
             "violations per focus node (over a random sample when validation hit its time budget).", "",
             "| run | " + " | ".join(regimes) + " |", "|---|" + "---|" * len(regimes)]

    def cell(ev):
        if ev is None:
            return "-"
        pr, sv = ev.get("profile", {}), ev.get("self_validation", {})
        if not ev.get("has_output"):
            return "no output"
        head = (f"{pr.get('node_shapes', '?')} / {pr.get('property_shapes', '?')} shapes, "
                f"{pr.get('class_path_pairs', '?')} pairs ({pr.get('pairs_repeated_from_superclass', '?')} also on a superclass)")
        if "error" in sv:
            return f"{head}; validation error"
        # rates over the validated focus nodes stay comparable when validation stopped on a sample
        validated = sv.get("validated_focus_nodes") or sv.get("target_focus_nodes") or 0
        if not validated:
            return f"{head}; {sv.get('violations', 0):,} violations"
        return (f"{head}; {100 * sv.get('focus_nodes', 0) / validated:.1f}% of "
                f"{'a sample of ' if sv.get('partial') else ''}{validated:,} focus nodes flagged, "
                f"{sv.get('violations', 0) / validated:.2f} violations per node")

    for run in sorted(table):
        lines.append(f"| {run} | " + " | ".join(cell(table[run].get(r)) for r in regimes) + " |")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

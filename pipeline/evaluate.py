#!/usr/bin/env python3
"""Evaluate the shapes produced by pipeline/run.py for a KG.

usage: pipeline/evaluate.py KG

For each results/<KG>/<run>/shapes.ttl it computes:
  * syntax      - does the output parse as RDF (Turtle)?
  * vocabulary  - IRIs in the sh: namespace that are not SHACL terms, or are
                  used as predicates without being SHACL properties (e.g.
                  sh:dataType or sh:NodeKind instead of sh:datatype / sh:nodeKind):
                  validators silently ignore them, so the constraint is lost;
  * well-formed - violations of the SHACL-SHACL meta-shapes;
  * profile     - number of node/property shapes and constraint components used;
  * self-validation - validating the KG itself against the extracted shapes
                  (pySHACL, no inference): shapes that describe the data should
                  mostly conform, and the violations are the "suspicious" nodes;
  * reference   - if data/<KG>/kg.json names reference shapes: overlap of
                  (target class, path) pairs and agreement of the main
                  constraints on the shared pairs, plus how many of the
                  violations found by the reference shapes are also found.

Writes results/<KG>/<run>/eval.json and results/<KG>/summary.md.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyshacl
from rdflib import RDF, RDFS, SH, BNode, Graph, Literal, URIRef
from rdflib.collection import Collection

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(pyshacl.__file__).parent / "assets"

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


def profile(g):
    usage = Counter()
    for p in COMPONENT_PARAMS:
        n = len(set(g.subjects(p, None)))
        if n:
            usage[g.qname(p)] = n
    return {
        "triples": len(g),
        "node_shapes": len(node_shapes(g)),
        "property_shapes": len(property_shapes(g)),
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
def validate(data, shapes, inference="none"):
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
    args = p.parse_args()

    kg_dir, results = ROOT / "data" / args.kg, ROOT / "results" / args.kg
    kg = json.loads((kg_dir / "kg.json").read_text())
    data = Graph().parse(ROOT / "work" / args.kg / "data.nt", format="nt")
    vocab = shacl_vocabulary()
    meta_shapes = Graph().parse(ASSETS / "shacl-shacl.ttl")

    ref_table, ref_validation = None, None
    if kg.get("reference_shapes"):
        ref = load(kg_dir / kg["reference_shapes"])
        ref_table = constraint_table(ref)
        ref_validation = validate(data, ref, kg.get("reference_inference", "none"))

    evaluations = {}
    for run_dir in sorted(d for d in results.iterdir() if d.is_dir()):
        ev = {"run": run_dir.name, **json.loads((run_dir / "run.json").read_text())}
        shapes_file = run_dir / "shapes.ttl"
        try:
            g = load(shapes_file)
        except Exception as e:
            ev["syntax"] = f"error: {type(e).__name__}: {e}"[:500]
            evaluations[run_dir.name] = ev
            continue
        ev["syntax"] = "ok"
        ev["non_shacl_terms"] = misused_shacl_terms(g, vocab)
        wf = validate(g, meta_shapes)
        ev["well_formedness"] = {k: v for k, v in wf.items() if not k.startswith("_")}
        ev["profile"] = profile(g)
        sv = validate(data, g)
        ev["self_validation"] = {k: v for k, v in sv.items() if not k.startswith("_")}
        if ref_table is not None:
            ev["reference"] = compare_to_reference(constraint_table(g), ref_table)
            if "_focus_paths" in sv and "_focus_paths" in ref_validation:
                expected = ref_validation["_focus_paths"]
                ev["reference"]["reference_violations_found"] = {
                    "found": len(expected & sv["_focus_paths"]), "of": len(expected)}
        (run_dir / "eval.json").write_text(json.dumps(ev, indent=2, default=list) + "\n")
        evaluations[run_dir.name] = ev

    write_summary(results / "summary.md", args.kg, kg, evaluations, ref_validation)
    print((results / "summary.md").read_text())


def write_summary(path, name, kg, evs, ref_validation):
    lines = [f"# Results for `{name}`", "", kg.get("description", ""), "",
             "Generated by `pipeline/evaluate.py`; see `eval.json` in each run directory for details.", "",
             "## Execution and output profile", "",
             "| run | exit | wall s | peak RSS MB | node shapes | property shapes | non-SHACL terms | SHACL-SHACL violations |",
             "|---|---|---|---|---|---|---|---|"]
    for r, ev in evs.items():
        pr = ev.get("profile", {})
        wf = ev.get("well_formedness", {})
        lines.append(f"| {r} | {ev['exit_code']}{' (timeout)' if ev['timed_out'] else ''} | {ev['wall_seconds']} | "
                     f"{ev['peak_rss_mb']} | {pr.get('node_shapes', '-')} | {pr.get('property_shapes', '-')} | "
                     f"{', '.join(ev.get('non_shacl_terms', [])) or '-'} | "
                     f"{wf.get('violations', wf.get('error', '-'))} |")
    lines += ["", "## Constraint components used (number of shapes using each)", ""]
    comps = sorted({c for ev in evs.values() for c in ev.get("profile", {}).get("constraint_usage", {})})
    lines += ["| run | " + " | ".join(comps) + " |", "|---|" + "---|" * len(comps)]
    for r, ev in evs.items():
        u = ev.get("profile", {}).get("constraint_usage", {})
        lines.append(f"| {r} | " + " | ".join(str(u.get(c, "")) for c in comps) + " |")
    lines += ["", "## Validating the KG against the extracted shapes", ""]
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


if __name__ == "__main__":
    sys.exit(main())

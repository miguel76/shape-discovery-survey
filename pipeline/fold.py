#!/usr/bin/env python3
"""Fold SHACL shapes along a class hierarchy: the inverse of factoring (pipeline/factor.py).

usage: pipeline/fold.py SHAPES.ttl OUT.ttl --hierarchy FILE [FILE ...] [--report OUT.json]
                        [--compare ORIGINAL.ttl]

Factoring removes from the shape of a class C the constraints implied by the shapes of its
superclasses, so that a factored shape only makes sense under subclass entailment, together
with the shapes of the superclasses. Folding does the opposite: it adds to the shape of each
class the constraints of the shapes of all its superclasses, so that each folded shape states
by itself everything that its class's instances must satisfy.

With K(D, p) the constraints that the node shapes targeting class D put on path p (p = None
for node-level constraints), the folded shape of a class C has, for every path p,

    F(C, p) = K(C, p) ∪ ⋃ { K(D, p) | C ≤ D, D ≠ C }

where ≤ is the subclass order (equivalent classes included). The inherited constraints of a path
go into additional property shapes for that path, and node-level ones into the node shape or,
where SHACL allows only one value per shape (two sh:nodeKind, say), into anonymous node shapes
that it refers to with sh:node: in both cases the result is the conjunction of the constraints. Folding touches the same node
shapes that factoring may change (pipeline/factor.py: one target class, not referenced by
sh:node and the like, not closed); other shapes are kept as they are. Constraints that depend
on their sibling property shapes (sh:closed, qualified value shapes with
sh:qualifiedValueShapesDisjoint) are not copied: they stay with the shape that has them.

Faithfulness. For every class C with a node shape and every path p, the folded factored shapes
must be equivalent to the folded original shapes (the effective constraints of C under subclass
entailment), modulo implication and shape names:

    fold(factor(S))(C, p)  ≡  fold(S)(C, p)

Factoring only removes constraints, so ⊆ holds as sets. --compare checks ⊇: that every
constraint of the folded ORIGINAL is in the folded result or derivable from it with the
implication rules of factor.implies(), applied repeatedly. The check is per class with a node
shape in both graphs; a class whose shape factoring removed entirely (all its constraints were
implied) has no shape to fold, and is reported separately.

The result is written as Turtle that keeps every literal term unchanged (factor.write_turtle).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import RDF, SH, BNode, Graph, Literal

from factor import TARGET_PARAMS, ShapeIndex, constraints_of, implies, load_hierarchy, target_classes, write_turtle


def superclasses(c, hierarchy):
    """The classes D ≠ c with c ≤ D (strict superclasses and equivalent classes)."""
    return {d for d in hierarchy.get(c, ()) if d != c}


def copyable(k):
    """Constraints whose meaning does not depend on the sibling shapes of the shape holding them."""
    if k.param == SH.closed:
        return False
    if k.param == SH.qualifiedValueShape:
        return not any(p == SH.qualifiedValueShapesDisjoint and o == Literal(True) for _, p, o in k.triples)
    return True


# parameters that may have several values in one shape; every other parameter has at most one
# value per shape in SHACL Core (sh:minCount, sh:nodeKind, sh:in, ...), or forms a group that
# does (qualified value shapes, sh:pattern with sh:flags)
MULTI_VALUED = {SH["class"], SH.hasValue, SH.node, SH["and"], SH["or"], SH.xone, SH["not"], SH.equals,
                SH.disjoint, SH.lessThan, SH.lessThanOrEquals, SH.sparql}


def layers(ks, taken=()):
    """Split constraints into groups that can each go into one shape: no group has two
    constraints with the same single-valued parameter. The first group must also avoid the
    parameters in `taken` (those of the shape it is added to)."""
    groups = [(set(taken), [])]
    for k in ks:
        for params, group in groups:
            if k.param in MULTI_VALUED or k.param not in params:
                params.add(k.param)
                group.append(k)
                break
        else:
            groups.append(({k.param}, [k]))
    return [group for _, group in groups if group]


def copy_term(src, dst, node, memo):
    """Copy the blank-node tree under node from src to dst, with fresh blank nodes."""
    if not isinstance(node, BNode):
        return node
    if node not in memo:
        memo[node] = BNode()
        for _, p, o in src.triples((node, None, None)):
            dst.add((memo[node], p, copy_term(src, dst, o, memo)))
    return memo[node]


def fold(g, hierarchy):
    """Fold shapes graph g in place; return a report. All decisions are made on the input
    constraints, so the result does not depend on the order in which shapes are folded."""
    idx = ShapeIndex(g)
    snapshot = Graph()  # the input, to copy constraint values from after g has changed
    for t in g:
        snapshot.add(t)
    report = {"node_shapes": len(idx.node_shapes), "folded_node_shapes": 0, "constraints_added": 0,
              "property_shapes_added": 0, "node_shapes_added": 0, "not_copied_sibling_dependent": 0}
    for ns in sorted(idx.node_shapes, key=str):
        if not idx.factorable(ns):
            continue
        (c,) = target_classes(g, ns)  # factorable: exactly one target class
        own = {path: {k for n, _, k in entries if n == ns} for path, entries in idx.by_class[c].items()}
        added = False
        paths = defaultdict(list)
        for d in sorted(superclasses(c, hierarchy), key=str):
            for path, entries in idx.by_class.get(d, {}).items():
                for _, _, k in entries:
                    if not copyable(k):
                        report["not_copied_sibling_dependent"] += 1
                    elif k not in own.get(path, set()) and k not in paths[path]:
                        paths[path].append(k)
        for path, ks in sorted(paths.items(), key=lambda x: str(x[0])):
            ks = sorted(ks, key=lambda k: str(k.key))  # canonical order: the result is deterministic
            if path is None:
                # node-level: into the node shape itself while that keeps it valid SHACL, then
                # into anonymous node shapes it refers to with sh:node (a conjunction)
                taken = {k.param for k in own.get(None, set())}
                for n, group in enumerate(layers(ks, taken)):
                    target = ns
                    if n > 0 or any(k.param not in MULTI_VALUED and k.param in taken for k in group):
                        target = BNode()
                        g.add((ns, SH.node, target))
                        report["node_shapes_added"] += 1
                    add_constraints(snapshot, g, target, group)
            else:
                # one more property shape for the path per group (property shapes are a conjunction)
                for group in layers(ks):
                    target = BNode()
                    g.add((ns, SH.property, target))
                    g.add((target, RDF.type, SH.PropertyShape))
                    g.add((target, SH.path, copy_term(snapshot, g, idx.path_terms[path], {})))
                    add_constraints(snapshot, g, target, group)
                    report["property_shapes_added"] += 1
            report["constraints_added"] += len(ks)
            added = True
        report["folded_node_shapes"] += added
    return report


def add_constraints(src, dst, shape, ks):
    for k in ks:
        memo = {}
        for _, p, o in k.triples:
            dst.add((shape, p, copy_term(src, dst, o, memo)))


def flatten(g, ks, seen=frozenset()):
    """Node-level constraints with each sh:node to an anonymous node shape without targets
    replaced by that shape's own constraints (the same conjunction)."""
    out = set()
    for k in ks:
        v = k.value
        if (k.param == SH.node and isinstance(v, BNode) and v not in seen
                and not any((v, p, None) in g for p in TARGET_PARAMS) and (v, SH.path, None) not in g):
            out |= flatten(g, constraints_of(g, v), seen | {v})
            if any(True for _ in g.objects(v, SH.property)):
                out.add(k)  # property shapes of the anonymous shape: keep the reference
        else:
            out.add(k)
    return out


def own_constraints(idx, c):
    """The constraints of the node shapes targeting c, per path, without inheritance."""
    out = {path: {k for _, _, k in entries} for path, entries in idx.by_class.get(c, {}).items()}
    if None in out:
        out[None] = flatten(idx.g, out[None])
    return out


def effective(idx, c, hierarchy):
    """The constraints that instances of c must satisfy under subclass entailment, per path."""
    out = defaultdict(set)
    for d in {c} | superclasses(c, hierarchy):
        for path, ks in own_constraints(idx, d).items():
            out[path] |= ks
    return out


def derivable(base, targets, hierarchy):
    """The constraints of targets that are neither in base nor derivable from it by applying
    factor.implies() repeatedly (each derived constraint becomes a premise)."""
    known, pending = set(base), set(targets) - set(base)
    progress = True
    while pending and progress:
        progress = False
        for k in list(pending):
            if implies(known, k, hierarchy):
                known.add(k)
                pending.discard(k)
                progress = True
    return pending


def compare(original, folded, hierarchy):
    """Check fold(original) ≡ folded per (class, path), modulo implication. Returns a report.
    Classes whose shapes folding keeps as they are (referenced, closed) are compared with their
    original constraints, without inheritance."""
    oi, fi = ShapeIndex(original), ShapeIndex(folded)
    folded_classes = {c for ns in fi.node_shapes if fi.factorable(ns) for c in target_classes(folded, ns)}
    report = {"classes": 0, "paths": 0, "constraints_expected": 0, "constraints_in_folded": 0,
              "derived": 0, "missing": [], "extra": [], "classes_without_shape": []}
    for c in sorted(set(oi.by_class), key=str):
        expected = effective(oi, c, hierarchy)
        if c not in fi.by_class:
            report["classes_without_shape"].append(str(c))
            continue
        if c not in folded_classes:
            expected = own_constraints(oi, c)  # shapes kept as they are (referenced, closed)
        report["classes"] += 1
        got = own_constraints(fi, c)
        for path in set(expected) | set(got):
            report["paths"] += 1
            exp, have = expected.get(path, set()), got.get(path, set())
            report["constraints_expected"] += len(exp)
            report["constraints_in_folded"] += len(have)
            missing = derivable({k for k in have}, {k for k in exp if copyable(k)}, hierarchy)
            report["derived"] += len({k for k in exp if copyable(k)} - have - missing)
            for k in missing:
                report["missing"].append([str(c), str(oi.path_terms.get(path)), str(k.key)])
            # the folded shape must not say more than the original: everything in it comes from
            # the original constraints of c and its superclasses
            for k in have - exp:
                report["extra"].append([str(c), str(fi.path_terms.get(path)), str(k.key)])
    report["equivalent"] = not report["missing"] and not report["extra"]
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("shapes")
    p.add_argument("out")
    p.add_argument("--hierarchy", nargs="+", required=True, help="files with the rdfs:subClassOf triples")
    p.add_argument("--report", help="write the folding report (JSON) here")
    p.add_argument("--compare", help="original (unfactored) shapes: check that the result is equivalent "
                                     "to them, folded, modulo implication")
    args = p.parse_args()
    hierarchy = load_hierarchy(args.hierarchy)
    g = Graph().parse(args.shapes, format="turtle")
    report = fold(g, hierarchy)
    write_turtle(g, args.out)
    if args.compare:
        report["comparison"] = compare(Graph().parse(args.compare, format="turtle"), g, hierarchy)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    summary = {k: v for k, v in report.items() if k != "comparison"}
    if args.compare:
        cmp = report["comparison"]
        summary["comparison"] = {k: (len(v) if isinstance(v, list) else v) for k, v in cmp.items()}
    print(json.dumps(summary))
    return 0 if not args.compare or report["comparison"]["equivalent"] else 1


if __name__ == "__main__":
    sys.exit(main())

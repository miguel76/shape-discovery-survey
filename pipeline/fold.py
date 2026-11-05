#!/usr/bin/env python3
"""Fold SHACL shapes along a class hierarchy: the inverse of factoring (pipeline/factor.py).

usage: pipeline/fold.py SHAPES.ttl OUT.ttl --hierarchy FILE [FILE ...] [--report OUT.json]
                        [--compare ORIGINAL.ttl]

Factoring removes from the shape of a class C the constraints implied by the shapes of its
superclasses, so that a factored shape only makes sense under subclass entailment, together
with the shapes of the superclasses, and it deletes the shapes left empty. Folding does the
opposite: it adds to the shape of each class the constraints of the shapes of all its
superclasses, so that each folded shape states by itself everything that its class's instances
must satisfy.

With K(D, p) the constraints that the node shapes targeting class D put on path p (p = None
for node-level constraints), the folded shape of a class C has, for every path p,

    F(C, p) = K(C, p) ∪ ⋃ { K(D, p) | C ≤ D, D ≠ C }

where ≤ is the subclass order (equivalent classes included).

Classes. Every class of the hierarchy is folded (every class with a superclass in the KG and
its ontologies), together with the classes targeted by a node shape. A class without a node
shape that folding may change gets a new one, [ a sh:NodeShape ; sh:targetClass C ], for the
constraints it inherits: this brings back the shapes that factoring deleted, and adds shapes for
classes that only inherit constraints. At the end, the node shapes still empty are deleted.

Folding changes the same node shapes that factoring may change (pipeline/factor.py: one target
class, not referenced by sh:node and the like, not closed); other shapes are kept as they are.
The inherited constraints of a path go into additional property shapes for that path, and
node-level ones into the node shape or, where SHACL allows only one value per shape (two
sh:nodeKind, say), into anonymous node shapes that it refers to with sh:node: in both cases the
result is the conjunction of the constraints. Constraints that depend on their sibling property
shapes (sh:closed, qualified value shapes with sh:qualifiedValueShapesDisjoint) are not copied:
they stay with the shape that has them.

Faithfulness. For every class C and every path p, the folded factored shapes must be
equivalent to the folded original shapes (the effective constraints of C under subclass
entailment), modulo implication and shape names:

    fold(factor(S))(C, p)  ≡  fold(S)(C, p)

Factoring only removes constraints, so ⊆ holds as sets. --compare checks ⊇: that every
constraint of the folded ORIGINAL is in the folded result (all the node shapes targeting C) or
derivable from it with the implication rules of factor.implies(), applied repeatedly. It also
reports the classes that have constraints to state but no node shape in the result.

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


def classes_of(idx, hierarchy):
    """The classes to fold: those of the hierarchy (every class with a superclass in the KG and
    its ontologies) and those targeted by a node shape."""
    return set(hierarchy) | {c for ns in idx.node_shapes for c in target_classes(idx.g, ns)}


def fold(g, hierarchy):
    """Fold shapes graph g in place; return a report.

    Every class of the hierarchy is considered, not only those with a node shape: a class
    without a foldable node shape gets a new one (sh:targetClass) for the constraints it
    inherits. At the end, foldable node shapes left without any constraint are deleted (as
    factoring does). All decisions are made on the input constraints, so the result does not
    depend on the order in which classes are folded."""
    idx = ShapeIndex(g)
    snapshot = Graph()  # the input, to copy constraint values from after g has changed
    for t in g:
        snapshot.add(t)
    report = {"node_shapes": len(idx.node_shapes), "classes": 0, "node_shapes_created": 0,
              "folded_node_shapes": 0, "constraints_added": 0, "property_shapes_added": 0,
              "node_shapes_added": 0, "not_copied_sibling_dependent": 0, "empty_node_shapes_deleted": 0}
    foldable = defaultdict(list)
    for ns in idx.node_shapes:
        if idx.factorable(ns):
            (c,) = target_classes(g, ns)  # factorable: exactly one target class
            foldable[c].append(ns)
    for c in sorted(classes_of(idx, hierarchy), key=str):
        report["classes"] += 1
        inherited = defaultdict(list)
        for d in sorted(superclasses(c, hierarchy), key=str):
            for path, entries in idx.by_class.get(d, {}).items():
                for _, _, k in entries:
                    if not copyable(k):
                        report["not_copied_sibling_dependent"] += 1
                    elif k not in inherited[path]:
                        inherited[path].append(k)
        shapes = sorted(foldable.get(c, []), key=str)
        if not shapes:
            if not any(inherited.values()):
                continue  # nothing to state about c
            ns = BNode()
            g.add((ns, RDF.type, SH.NodeShape))
            g.add((ns, SH.targetClass, c))
            shapes = [ns]
            report["node_shapes_created"] += 1
        for ns in shapes:
            own = {path: {k for n, _, k in entries if n == ns} for path, entries in idx.by_class[c].items()}
            added = fold_into(g, snapshot, idx, ns, own,
                              {path: [k for k in ks if k not in own.get(path, set())] for path, ks in inherited.items()},
                              report)
            report["folded_node_shapes"] += added
    # node shapes that are still empty: delete them
    for ns in list(set(g.subjects(RDF.type, SH.NodeShape)) | set(g.subjects(SH.targetClass, None))):
        if (ns, SH.path, None) in g or not ShapeIndex.factorable_in(g, ns, idx.referenced):
            continue
        if not constraints_of(g, ns) and (ns, SH.property, None) not in g:
            for t in list(g.triples((ns, None, None))):
                g.remove(t)
            report["empty_node_shapes_deleted"] += 1
    return report


def fold_into(g, snapshot, idx, ns, own, inherited, report):
    """Add the inherited constraints (per path) to node shape ns. Returns whether any was added."""
    added = False
    for path, ks in sorted(inherited.items(), key=lambda x: str(x[0])):
        if not ks:
            continue
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
    return added


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
    The classes compared are those of the hierarchy and those targeted by a node shape in either
    graph; for each, the folded graph's own constraints (all the node shapes targeting the class)
    must be equivalent to the effective constraints of the class in the original."""
    oi, fi = ShapeIndex(original), ShapeIndex(folded)
    report = {"classes": 0, "paths": 0, "constraints_expected": 0, "constraints_in_folded": 0,
              "derived": 0, "missing": [], "extra": [], "classes_without_shape": []}
    for c in sorted(classes_of(oi, hierarchy) | classes_of(fi, hierarchy), key=str):
        expected, got = effective(oi, c, hierarchy), own_constraints(fi, c)
        if not any(copyable(k) for ks in expected.values() for k in ks) and not any(got.values()):
            continue  # nothing to state about c
        report["classes"] += 1
        if not any(got.values()):
            report["classes_without_shape"].append(str(c))
        for path in set(expected) | set(got):
            report["paths"] += 1
            exp, have = expected.get(path, set()), got.get(path, set())
            report["constraints_expected"] += len(exp)
            report["constraints_in_folded"] += len(have)
            missing = derivable(have, {k for k in exp if copyable(k)}, hierarchy)
            report["derived"] += len({k for k in exp if copyable(k)} - have - missing)
            for k in missing:
                report["missing"].append([str(c), str(oi.path_terms.get(path)), str(k.key)])
            # the folded shapes must not say more than the original: everything in them comes
            # from the original constraints of c and its superclasses
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

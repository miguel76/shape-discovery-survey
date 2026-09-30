#!/usr/bin/env python3
"""Factor SHACL shapes along a class hierarchy.

usage: pipeline/factor.py SHAPES.ttl OUT.ttl --hierarchy FILE [FILE ...] [--report OUT.json]

Discovery tools learn one shape per class, independently, so under a regime with
subclass entailment (see pipeline/regimes.py) a constraint that holds for a class D
is repeated on every subclass C of D. Factoring removes from the shape of C every
constraint that is already implied by the shapes of C's superclasses. The definitions
and the proof that validation results are preserved are in docs/factoring.md.

In short: let K(C, p) be the constraints that the node shapes targeting class C put
on path p (p = None for node-level constraints), and let Sup(C, p) be the union of
K(D, p) over the strict superclasses D of C (D above C, not equivalent to it). The
factored shapes keep, for every C and p,

    K'(C, p) = { k in K(C, p) : not implies(Sup(C, p), k) }

where implies() is a sound (not complete) implication test between SHACL Core
constraints (see implies() below). Shapes that must not be changed are kept as
they are and only serve as premises:
  - node shapes that are the value of sh:node (or of sh:and/sh:or/sh:xone/sh:not/
    sh:qualifiedValueShape): such references validate a value against that shape
    alone, without the shapes of its superclasses;
  - node shapes with sh:closed true, or with a property shape using
    sh:qualifiedValueShapesDisjoint true: the meaning of these constraints depends on the
    sibling property shapes, which factoring may remove;
  - node shapes with targets other than exactly one sh:targetClass (or implicit
    class target).
Property shapes shared by several node shapes are copied before being changed.

The hierarchy files are N-Triples/Turtle files whose rdfs:subClassOf triples between
IRIs define the class hierarchy (e.g. work/<KG>/data.nt and work/<KG>/ontologies.nt).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import RDF, RDFS, SH, BNode, Graph, Literal, URIRef
from rdflib.collection import Collection

# Parameters of SHACL Core constraint components that act on the value nodes of a shape.
CONSTRAINT_PARAMS = {
    SH["class"], SH.datatype, SH.nodeKind, SH.minCount, SH.maxCount, SH.minExclusive, SH.minInclusive,
    SH.maxExclusive, SH.maxInclusive, SH.minLength, SH.maxLength, SH.pattern, SH.flags, SH.languageIn,
    SH.uniqueLang, SH.equals, SH.disjoint, SH.lessThan, SH.lessThanOrEquals, SH["not"], SH["and"], SH["or"],
    SH.xone, SH.node, SH.property, SH.qualifiedValueShape, SH.qualifiedMinCount, SH.qualifiedMaxCount,
    SH.qualifiedValueShapesDisjoint, SH.closed, SH.ignoredProperties, SH.hasValue, SH["in"], SH.sparql,
}
# Parameters that only make sense together are handled as one constraint.
GROUPS = [
    (SH.qualifiedValueShape, {SH.qualifiedValueShape, SH.qualifiedMinCount, SH.qualifiedMaxCount,
                              SH.qualifiedValueShapesDisjoint}),
    (SH.pattern, {SH.pattern, SH.flags}),
    (SH.closed, {SH.closed, SH.ignoredProperties}),
]
SHAPE_REF_PARAMS = [SH.node, SH["and"], SH["or"], SH.xone, SH["not"], SH.qualifiedValueShape]
TARGET_PARAMS = [SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf]

NODE_KINDS = {  # node kind -> set of term kinds it admits
    SH.IRI: {"I"}, SH.BlankNode: {"B"}, SH.Literal: {"L"},
    SH.BlankNodeOrIRI: {"B", "I"}, SH.BlankNodeOrLiteral: {"B", "L"}, SH.IRIOrLiteral: {"I", "L"},
}


# ------------------------------------------------------------------ hierarchy
def load_hierarchy(files):
    """{class: set of its superclasses (transitive, reflexive excluded)} from rdfs:subClassOf between IRIs."""
    parents = defaultdict(set)
    needle = f" <{RDFS.subClassOf}> <".encode()
    for f in files:
        f = Path(f)
        if not f.exists():
            continue
        if f.suffix == ".nt":  # stream: data dumps can be large
            with open(f, "rb") as src:
                for line in src:
                    if needle in line and line.startswith(b"<"):
                        s, _, o = line.decode().split(" ", 3)[:3]
                        parents[URIRef(s[1:-1])].add(URIRef(o[1:-1]))
        else:
            g = Graph().parse(f)
            for s, o in g.subject_objects(RDFS.subClassOf):
                if isinstance(s, URIRef) and isinstance(o, URIRef):
                    parents[s].add(o)
    closure = {}
    for c in list(parents):
        seen, todo = set(), [c]
        while todo:
            for p in parents.get(todo.pop(), ()):
                if p not in seen:
                    seen.add(p)
                    todo.append(p)
        closure[c] = seen - {c}
    return closure


def strict_supers(c, hierarchy):
    """Superclasses of c that are not equivalent to it (not in a subclass cycle with c)."""
    return {d for d in hierarchy.get(c, ()) if c not in hierarchy.get(d, ())}


def is_subclass(c, d, hierarchy):
    return c == d or d in hierarchy.get(c, ())


# ---------------------------------------------------------------- constraints
def canon(g, node, seen=None):
    """A canonical, hashable form of an RDF term, expanding blank nodes and RDF lists."""
    seen = seen or frozenset()
    if isinstance(node, BNode):
        if node in seen:
            return ("cycle",)
        if (node, RDF.first, None) in g or node == RDF.nil:
            return ("list",) + tuple(canon(g, m, seen | {node}) for m in Collection(g, node))
        return ("bnode",) + tuple(sorted(
            (str(p), canon(g, o, seen | {node})) for p, o in g.predicate_objects(node)))
    if isinstance(node, Literal):
        return ("literal", str(node), str(node.datatype or ""), node.language or "")
    return ("iri", str(node))


class Constraint:
    """One constraint of a shape: a component parameter (or a group of parameters that
    belong together) with its value(s). `triples` are the triples that express it."""

    def __init__(self, g, shape, param, triples):
        self.param = param
        self.triples = triples
        self.key = (str(param),) + tuple(sorted((str(p), canon(g, o)) for _, p, o in triples))
        self.value = triples[0][2] if len(triples) == 1 else None
        self.g = g

    def __eq__(self, other):
        return self.key == other.key

    def __hash__(self):
        return hash(self.key)

    def list_values(self):
        return {canon(self.g, m) for m in Collection(self.g, self.value)} if self.value is not None else set()


def constraints_of(g, shape):
    """The constraints of a node or property shape (sh:property links excluded)."""
    params = defaultdict(list)
    for _, p, o in g.triples((shape, None, None)):
        if p in CONSTRAINT_PARAMS and p != SH.property:
            params[p].append((shape, p, o))
    out = []
    for lead, members in GROUPS:
        if lead in params:  # without the lead parameter, members are kept as single constraints
            triples = [t for m in members for t in params.pop(m, [])]
            out.append(Constraint(g, shape, lead, triples))
    for p, triples in params.items():
        for t in triples:  # each value of a parameter is a separate constraint (e.g. two sh:class)
            out.append(Constraint(g, shape, p, [t]))
    return out


def class_disjuncts(q):
    """If q is an sh:or whose members are all shapes with a single sh:class, the set of classes."""
    if q.param != SH["or"] or q.value is None:
        return None
    classes = set()
    for m in Collection(q.g, q.value):
        triples = list(q.g.predicate_objects(m))
        if len(triples) != 1 or triples[0][0] != SH["class"]:
            return None
        classes.add(triples[0][1])
    return classes


def _num(v):
    try:
        return float(v.toPython())
    except (AttributeError, TypeError, ValueError):
        return None


def implies(premises, k, hierarchy):
    """True if the conjunction of `premises` (constraints on the same focus/value nodes)
    implies constraint k. Sound but incomplete: False means "not shown"."""
    if k in premises:
        return True
    p = k.param
    same = [q for q in premises if q.param == p]
    v = k.value
    if p == SH.minCount:
        return any(_num(q.value) is not None and _num(q.value) >= _num(v) for q in same)
    if p == SH.maxCount:
        return any(_num(q.value) is not None and _num(q.value) <= _num(v) for q in same)
    if p in (SH.minLength, SH.minInclusive, SH.minExclusive, SH.qualifiedMinCount):
        return p != SH.qualifiedMinCount and any(_num(q.value) is not None and _num(v) is not None
                                                 and _num(q.value) >= _num(v) for q in same)
    if p in (SH.maxLength, SH.maxInclusive, SH.maxExclusive):
        return any(_num(q.value) is not None and _num(v) is not None and _num(q.value) <= _num(v) for q in same)
    if p == SH["class"]:
        # every value is a SHACL instance of q.value, hence of its superclasses; with an sh:or of
        # classes, every value is an instance of one of them, so all of them must be subclasses of v
        return any(is_subclass(q.value, v, hierarchy) for q in same) or any(
            (s := class_disjuncts(q)) and all(is_subclass(c, v, hierarchy) for c in s) for q in premises)
    if p == SH.nodeKind:
        admitted = NODE_KINDS.get(v, set())
        for q in premises:
            if q.param == SH.nodeKind and NODE_KINDS.get(q.value, {"?"}) <= admitted:
                return True
            if q.param == SH.datatype and admitted >= {"L"}:
                return True  # sh:datatype admits literals only
            if (q.param == SH["class"] or class_disjuncts(q)) and admitted >= {"B", "I"}:
                return True  # SHACL instances are subjects of rdf:type, hence not literals
        return False
    if p == SH["in"]:
        allowed = k.list_values()
        return any(q.list_values() <= allowed for q in same)
    if p == SH.languageIn:
        allowed = k.list_values()
        return any(q.list_values() <= allowed for q in same)
    if p == SH["or"]:
        # a disjunction is implied by a disjunction over a subset of its disjuncts
        disjuncts = k.list_values()
        if any(q.list_values() <= disjuncts for q in same):
            return True
        # disjunctions of classes: every class of the premise must be a subclass of one of k's
        targets = class_disjuncts(k)
        if targets:
            def covered(c):
                return any(is_subclass(c, d, hierarchy) for d in targets)
            for q in premises:
                if q.param == SH["class"] and covered(q.value):
                    return True
                s = class_disjuncts(q)
                if s and all(covered(c) for c in s):
                    return True
        return False
    return False


# ------------------------------------------------------------------ factoring
def target_classes(g, ns):
    targets = set(g.objects(ns, SH.targetClass))
    if (ns, RDF.type, RDFS.Class) in g or (ns, RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")) in g:
        targets.add(ns)
    return targets


def factor(g, hierarchy, trace=None):
    """Factor shapes graph g in place; return a report. If `trace` is a list, append to it
    one (class, path, constraint, [(superclass, premise), ...]) tuple per removed constraint,
    with the path term (None for node-level constraints) and the premises that imply it."""
    node_shapes = {s for s in g.subjects(RDF.type, SH.NodeShape)}
    for p in TARGET_PARAMS:
        node_shapes |= set(g.subjects(p, None))
    node_shapes -= set(g.subjects(SH.path, None))

    referenced = set()
    for p in SHAPE_REF_PARAMS:
        for o in g.objects(None, p):
            referenced |= set(Collection(g, o)) if (o, RDF.first, None) in g else {o}

    def sibling_dependent(ns):
        return (ns, SH.closed, Literal(True)) in g or any(
            (ps, SH.qualifiedValueShapesDisjoint, Literal(True)) in g for ps in g.objects(ns, SH.property))

    def factorable(ns):
        if ns in referenced or sibling_dependent(ns):
            return False
        other_targets = any((ns, p, None) in g for p in TARGET_PARAMS if p != SH.targetClass)
        return len(target_classes(g, ns)) == 1 and not other_targets

    # K(C, p): per target class and path, the constraints and the shapes carrying them
    by_class = defaultdict(lambda: defaultdict(list))  # class -> path key -> [(node shape, shape, Constraint)]
    path_terms = {None: None}
    for ns in node_shapes:
        for c in target_classes(g, ns):
            for k in constraints_of(g, ns):
                by_class[c][None].append((ns, ns, k))
            for ps in g.objects(ns, SH.property):
                path = g.value(ps, SH.path)
                if path is None:
                    continue
                path_terms[canon(g, path)] = path
                for k in constraints_of(g, ps):
                    by_class[c][canon(g, path)].append((ns, ps, k))

    report = {"node_shapes": len(node_shapes), "factorable_node_shapes": 0, "kept_referenced": 0,
              "kept_sibling_dependent": 0, "kept_other_targets": 0, "constraints": 0, "constraints_removed": 0,
              "property_shapes_removed": 0, "property_shapes_copied": 0, "node_shapes_removed": 0}
    for ns in node_shapes:
        if factorable(ns):
            report["factorable_node_shapes"] += 1
        elif ns in referenced:
            report["kept_referenced"] += 1
        elif sibling_dependent(ns):
            report["kept_sibling_dependent"] += 1
        else:
            report["kept_other_targets"] += 1

    # decide on the ORIGINAL constraints (the proof relies on it), then edit
    removals = defaultdict(set)  # (node shape, shape) -> constraints to drop
    for c, paths in by_class.items():
        supers = strict_supers(c, hierarchy)
        for path, entries in paths.items():
            premises = {k for d in supers for (_, _, k) in by_class.get(d, {}).get(path, [])}
            for ns, shape, k in entries:
                report["constraints"] += 1
                if factorable(ns) and premises and implies(premises, k, hierarchy):
                    removals[(ns, shape)].add(k)
                    if trace is not None:
                        trace.append((c, path_terms[path], k, [(d, q) for d in supers
                                                               for (_, _, q) in by_class.get(d, {}).get(path, [])]))

    shape_users = defaultdict(set)
    for ns in node_shapes:
        for ps in g.objects(ns, SH.property):
            shape_users[ps].add(ns)
    for (ns, shape), ks in removals.items():
        report["constraints_removed"] += len(ks)
        if shape == ns:  # node-level constraints
            for k in ks:
                for t in k.triples:
                    g.remove(t)
            continue
        remaining = [k for k in constraints_of(g, shape) if k not in ks]
        if not remaining:  # nothing left for this class: unlink the property shape
            g.remove((ns, SH.property, shape))
            report["property_shapes_removed"] += 1
        elif shape_users[shape] - {ns}:  # shared with other node shapes: copy on write
            copy = BNode()
            for _, p, o in g.triples((shape, None, None)):
                if not any((shape, p, o) in k.triples for k in ks):
                    g.add((copy, p, o))
            g.remove((ns, SH.property, shape))
            g.add((ns, SH.property, copy))
            report["property_shapes_copied"] += 1
        else:
            for k in ks:
                for t in k.triples:
                    g.remove(t)
    # node shapes left without any constraint or property shape: remove them
    for ns in node_shapes:
        if factorable(ns) and not constraints_of(g, ns) and (ns, SH.property, None) not in g:
            for t in list(g.triples((ns, None, None))):
                g.remove(t)
            report["node_shapes_removed"] += 1
    # drop property shapes no longer used by anything
    for ps in list(set(g.subjects(SH.path, None))):
        if (None, None, ps) not in g:
            _remove_tree(g, ps)
    return report


def _remove_tree(g, node):
    for _, _, o in list(g.triples((node, None, None))):
        g.remove((node, _, o))
        if isinstance(o, BNode) and (None, None, o) not in g:
            _remove_tree(g, o)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("shapes")
    p.add_argument("out")
    p.add_argument("--hierarchy", nargs="+", required=True, help="files with the rdfs:subClassOf triples")
    p.add_argument("--report", help="write the factoring report (JSON) here")
    args = p.parse_args()
    g = Graph().parse(args.shapes, format="turtle")
    report = factor(g, load_hierarchy(args.hierarchy))
    g.serialize(args.out, format="turtle")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    sys.exit(main())

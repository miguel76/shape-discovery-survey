#!/usr/bin/env python3
"""Randomised check of pipeline/factor.py: factoring must not change which nodes conform.

usage: python tests/test_factor.py [TRIALS] [SEED]

Each trial builds a random class hierarchy (with an equivalence cycle), a random shapes
graph over it (exercising every implication rule of factor.implies, shared property
shapes, sh:node references, closed shapes, node-level constraints) and a random data
graph whose rdf:type triples are materialised along the hierarchy (the `subclass`
regime). It validates the data against the original and the factored shapes with
pySHACL and checks that the sets of (focus node, path) pairs with violations are identical.
It also checks each removal on its own: every node that violates a removed constraint
(validated alone) must violate one of the premises that justified the removal.
"""
import random
import sys
import tempfile
from pathlib import Path

import pyshacl
from rdflib import RDF, RDFS, SH, XSD, BNode, Graph, Literal, Namespace
from rdflib.collection import Collection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from factor import factor, load_hierarchy  # noqa: E402

EX = Namespace("http://example.org/t/")
CLASSES = [EX[c] for c in "ABCDEFGH"]
PROPS = [EX.p, EX.q]
DATATYPES = [XSD.integer, XSD.string]
KINDS = [SH.IRI, SH.BlankNode, SH.Literal, SH.BlankNodeOrIRI, SH.IRIOrLiteral, SH.BlankNodeOrLiteral]


def random_hierarchy(rnd):
    """subClassOf edges: a random DAG over A..F, plus G and H equivalent, G below some class."""
    edges = set()
    order = CLASSES[:6]
    for i, c in enumerate(order):
        for d in order[:i]:
            if rnd.random() < 0.3:
                edges.add((c, d))
    edges |= {(EX.G, EX.H), (EX.H, EX.G), (EX.G, rnd.choice(order))}
    return edges


def value_pool():
    return [EX[f"v{i}"] for i in range(4)] + [Literal(1), Literal(5), Literal("a"), Literal("b", lang="en")]


SINGLE_VALUED = {"min": SH.minCount, "max": SH.maxCount, "dt": SH.datatype, "kind": SH.nodeKind, "in": SH["in"],
                 "lang": SH.languageIn, "minInc": SH.minInclusive, "maxLen": SH.maxLength}


def random_constraint(rnd, g, shape):
    kind = rnd.choice(["min", "max", "dt", "class", "kind", "in", "or", "lang", "minInc", "maxLen"])
    if kind in SINGLE_VALUED and (shape, SINGLE_VALUED[kind], None) in g:
        return  # SHACL allows at most one value for these parameters per shape
    if kind == "min":
        g.add((shape, SH.minCount, Literal(rnd.randint(0, 2))))
    elif kind == "max":
        g.add((shape, SH.maxCount, Literal(rnd.randint(1, 3))))
    elif kind == "dt":
        g.add((shape, SH.datatype, rnd.choice(DATATYPES)))
    elif kind == "class":
        g.add((shape, SH["class"], rnd.choice(CLASSES)))
    elif kind == "kind":
        g.add((shape, SH.nodeKind, rnd.choice(KINDS)))
    elif kind == "in":  # small pools, so that one list is often a strict subset of another
        lst = BNode()
        Collection(g, lst, rnd.sample(value_pool()[:2] + value_pool()[4:6], rnd.randint(1, 3)))
        g.add((shape, SH["in"], lst))
    elif kind == "or":
        members = []
        for c in rnd.sample(CLASSES[:4], rnd.randint(1, 3)):
            m = BNode()
            g.add((m, SH["class"], c))
            members.append(m)
        lst = BNode()
        Collection(g, lst, members)
        g.add((shape, SH["or"], lst))
    elif kind == "lang":
        lst = BNode()
        Collection(g, lst, [Literal(x) for x in rnd.sample(["en", "it", "fr"], rnd.randint(1, 2))])
        g.add((shape, SH.languageIn, lst))
    elif kind == "minInc":
        g.add((shape, SH.minInclusive, Literal(rnd.randint(0, 4))))
    else:
        g.add((shape, SH.maxLength, Literal(rnd.randint(1, 3))))


def random_shapes(rnd):
    g = Graph()
    shared = {}
    node_shapes = []
    for c in CLASSES:
        if rnd.random() < 0.15:
            continue
        ns = EX[f"S_{c.split('/')[-1]}"]
        node_shapes.append(ns)
        g.add((ns, RDF.type, SH.NodeShape))
        g.add((ns, SH.targetClass, c))
        if rnd.random() < 0.3:
            g.add((ns, SH.nodeKind, rnd.choice([SH.IRI, SH.BlankNodeOrIRI])))
        if rnd.random() < 0.1:
            g.add((ns, SH.closed, Literal(True)))
            g.add((ns, SH.ignoredProperties, _list(g, [RDF.type])))
        for p in PROPS:
            for _ in range(rnd.randint(0, 2)):
                if p in shared and rnd.random() < 0.3:
                    g.add((ns, SH.property, shared[p]))  # a property shape shared by node shapes
                    continue
                ps = BNode() if rnd.random() < 0.5 else EX[f"P{len(g)}"]
                g.add((ns, SH.property, ps))
                g.add((ps, SH.path, p))
                for _ in range(rnd.randint(1, 3)):
                    random_constraint(rnd, g, ps)
                shared.setdefault(p, ps)
    if len(node_shapes) > 1 and rnd.random() < 0.5:  # a sh:node reference to a class shape
        ps = BNode()
        g.add((rnd.choice(node_shapes), SH.property, ps))
        g.add((ps, SH.path, EX.q))
        g.add((ps, SH.node, rnd.choice(node_shapes)))
    return g


def _list(g, items):
    lst = BNode()
    Collection(g, lst, items)
    return lst


def random_data(rnd, edges):
    supers = {}
    for c in CLASSES:
        seen, todo = set(), [c]
        while todo:
            for s, o in edges:
                if s == todo[-1] and o not in seen:
                    seen.add(o)
                    todo.append(o)
            todo.pop()
        supers[c] = seen
    g = Graph()
    for s, o in edges:  # the hierarchy is in the data graph too, as in CCKG
        g.add((s, RDFS.subClassOf, o))
    nodes = [EX[f"n{i}"] for i in range(8)] + [BNode() for _ in range(2)]
    for n in nodes:
        for c in rnd.sample(CLASSES, rnd.randint(0, 2)):
            for t in {c} | supers[c]:  # materialised along the hierarchy
                g.add((n, RDF.type, t))
        for p in PROPS:
            for _ in range(rnd.randint(0, 3)):
                g.add((n, p, rnd.choice(nodes + value_pool())))
    for v in value_pool()[:4]:
        for c in rnd.sample(CLASSES, rnd.randint(0, 1)):
            for t in {c} | supers[c]:
                g.add((v, RDF.type, t))
    return g


def _copy_tree(src, dst, node):
    """Copy the triples of the blank-node tree under `node` (lists, member shapes)."""
    if isinstance(node, BNode):
        for _, p, o in src.triples((node, None, None)):
            dst.add((node, p, o))
            _copy_tree(src, dst, o)


def single_constraint_shapes(original, targets_and_constraints, path):
    """A shapes graph with one node shape per (class, constraint): the constraint alone."""
    g = Graph()
    for c, k in targets_and_constraints:
        ns = BNode()
        g.add((ns, SH.targetClass, c))
        shape = ns
        if path is not None:
            shape = BNode()
            g.add((ns, SH.property, shape))
            g.add((shape, SH.path, path))
            _copy_tree(original, g, path)
        for _, p, o in k.triples:
            g.add((shape, p, o))
            _copy_tree(original, g, o)
    return g


def flagged_nodes(data, shapes):
    """(focus node, value node) of each result; value-based components (sh:class, sh:in, ...)
    report the offending value, so implications are checked value by value where possible."""
    _, report, _ = pyshacl.validate(data, shacl_graph=shapes, inference="none", allow_warnings=True)
    return {(report.value(r, SH.focusNode), report.value(r, SH.value))
            for r in report.subjects(RDF.type, SH.ValidationResult)}


def check_removals(data, original, trace):
    """Every node violating a removed constraint must violate one of its premises."""
    for c, path, k, premises in trace:
        violating_k = flagged_nodes(data, single_constraint_shapes(original, [(c, k)], path))
        violating_premises = flagged_nodes(data, single_constraint_shapes(original, premises, path))
        # a violation of k at a value must be matched by a premise violation at the same value,
        # or (count-based premises such as sh:maxCount report no value) at the same focus node
        premise_foci = {f for f, v in violating_premises if v is None}
        unexplained = {(f, v) for f, v in violating_k if (f, v) not in violating_premises and f not in premise_foci}
        if unexplained:
            return (c, path, k.key, [q.key for _, q in premises], unexplained)
    return None


def flagged(data, shapes):
    _, report, _ = pyshacl.validate(data, shacl_graph=shapes, inference="none", allow_warnings=True)
    # (focus node, path): factoring only removes constraints implied by constraints on the
    # same path, so violations are preserved at this granularity (docs/factoring.md)
    return {(report.value(r, SH.focusNode), report.value(r, SH.resultPath))
            for r in report.subjects(RDF.type, SH.ValidationResult)}


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rnd = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    removed = 0
    tmp = tempfile.TemporaryDirectory()
    for i in range(trials):
        edges = random_hierarchy(rnd)
        shapes = random_shapes(rnd)
        data = random_data(rnd, edges)
        hier_file = Path(tmp.name) / f"hierarchy-{i}.nt"
        h = Graph()
        for s, o in edges:
            h.add((s, RDFS.subClassOf, o))
        h.serialize(hier_file, format="nt")
        before = flagged(data, shapes)
        factored = Graph()
        for t in shapes:
            factored.add(t)
        trace = []
        report = factor(factored, load_hierarchy([hier_file]), trace)
        hier_file.unlink()
        removed += report["constraints_removed"]
        after = flagged(data, factored)
        bad_removal = check_removals(data, shapes, trace)
        if bad_removal:
            print(f"trial {i}: UNSOUND REMOVAL {bad_removal}")
            return 1
        if before != after:
            shapes.serialize(f"failing-shapes-{i}.ttl", format="turtle")
            data.serialize(f"failing-data-{i}.ttl", format="turtle")
            print(f"trial {i}: MISMATCH, only before: {before - after}, only after: {after - before}")
            return 1
    print(f"{trials} trials: violating (focus node, path) pairs identical before and after factoring "
          f"({removed} constraints removed in total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

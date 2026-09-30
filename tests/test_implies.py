#!/usr/bin/env python3
"""Exhaustive soundness check of factor.implies() on a small universe.

usage: python tests/test_implies.py

For a pool of single constraints (covering every rule of implies()) and every pair
(q, k) with implies({q}, k), checks against pySHACL that each focus node violating k
also violates q. Focus nodes cover every set of up to 3 values drawn from a universe of
IRIs and a blank node with various classes, integers, a string and a language-tagged
string. Also checks a few expected implications, so that the rules are exercised.
"""
import itertools
import sys
from pathlib import Path

import pyshacl
from rdflib import RDF, RDFS, SH, XSD, BNode, Graph, Literal, Namespace
from rdflib.collection import Collection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from factor import constraints_of, implies  # noqa: E402

EX = Namespace("http://example.org/i/")
HIERARCHY = {EX.B: {EX.A}}  # B subClassOf A; C unrelated
UNIVERSE = [EX.a1, EX.b1, EX.c1, EX.u1, BNode("bb"), Literal(1), Literal(5), Literal("x"), Literal("y", lang="en")]
TYPES = {EX.a1: [EX.A], EX.b1: [EX.B, EX.A], EX.c1: [EX.C], BNode("bb"): [EX.B, EX.A]}


def pool():
    """(label, list of (param, object-builder)) single constraints."""
    items = []
    for n in range(4):
        items += [(f"minCount {n}", SH.minCount, Literal(n)), (f"maxCount {n}", SH.maxCount, Literal(n))]
    for dt in (XSD.integer, XSD.string, RDF.langString):
        items.append((f"datatype {dt.split('#')[-1]}", SH.datatype, dt))
    for c in (EX.A, EX.B, EX.C):
        items.append((f"class {c.split('/')[-1]}", SH["class"], c))
    for k in (SH.IRI, SH.BlankNode, SH.Literal, SH.BlankNodeOrIRI, SH.BlankNodeOrLiteral, SH.IRIOrLiteral):
        items.append((f"nodeKind {k.split('#')[-1]}", SH.nodeKind, k))
    for vals in ([EX.a1], [EX.a1, EX.b1], [EX.a1, Literal(1)], [Literal(1), Literal(5), EX.b1]):
        items.append((f"in {vals}", SH["in"], ("list", vals)))
    for classes in ([EX.A], [EX.B], [EX.A, EX.C], [EX.B, EX.C], [EX.A, EX.B], [EX.B, EX.A, EX.C]):
        items.append((f"or {classes}", SH["or"], ("or", classes)))
    for langs in (["en"], ["en", "it"], ["it"]):
        items.append((f"languageIn {langs}", SH.languageIn, ("list", [Literal(x) for x in langs])))
    for n in (1, 3, 5):
        items.append((f"minInclusive {n}", SH.minInclusive, Literal(n)))
    for n in (0, 1, 3):
        items.append((f"maxLength {n}", SH.maxLength, Literal(n)))
    return items


def add_constraint(g, shape, param, obj):
    if isinstance(obj, tuple) and obj[0] == "list":
        lst = BNode()
        Collection(g, lst, obj[1])
        g.add((shape, param, lst))
    elif isinstance(obj, tuple) and obj[0] == "or":
        members = []
        for c in obj[1]:
            m = BNode()
            g.add((m, SH["class"], c))
            members.append(m)
        lst = BNode()
        Collection(g, lst, members)
        g.add((shape, param, lst))
    else:
        g.add((shape, param, obj))


def main():
    data = Graph()
    data.add((EX.B, RDFS.subClassOf, EX.A))
    for v, types in TYPES.items():
        for t in types:
            data.add((v, RDF.type, t))
    focus = []
    for n in range(4):
        for values in itertools.combinations(UNIVERSE, n):
            x = EX[f"x{len(focus)}"]
            focus.append(x)
            data.add((x, RDF.type, EX.T))
            for v in values:
                data.add((x, EX.p, v))

    constraints, violators = [], []
    for label, param, obj in pool():
        shapes = Graph()
        ns, ps = BNode(), BNode()
        shapes.add((ns, SH.targetClass, EX.T))
        shapes.add((ns, SH.property, ps))
        shapes.add((ps, SH.path, EX.p))
        add_constraint(shapes, ps, param, obj)
        (k,) = constraints_of(shapes, ps)
        _, report, _ = pyshacl.validate(data, shacl_graph=shapes, inference="none")
        violators.append({report.value(r, SH.focusNode) for r in report.subjects(RDF.type, SH.ValidationResult)})
        constraints.append((label, k))

    checked = unsound = 0
    implied_pairs = set()
    for (lq, q), vq in zip(constraints, violators):
        for (lk, k), vk in zip(constraints, violators):
            if implies({q}, k, HIERARCHY):
                checked += 1
                implied_pairs.add((lq, lk))
                if not vk <= vq:
                    unsound += 1
                    print(f"UNSOUND: {lq} => {lk} (counterexamples: {len(vk - vq)})")
    expected = [("minCount 2", "minCount 1"), ("maxCount 1", "maxCount 3"), ("class B", "class A"),
                ("datatype integer", "nodeKind Literal"), ("class A", "nodeKind BlankNodeOrIRI"),
                ("nodeKind IRI", "nodeKind IRIOrLiteral"), ("in [rdflib.term.URIRef('http://example.org/i/a1')]",
                                                            "in [rdflib.term.URIRef('http://example.org/i/a1'), rdflib.term.URIRef('http://example.org/i/b1')]"),
                ("or [rdflib.term.URIRef('http://example.org/i/A')]",
                 "or [rdflib.term.URIRef('http://example.org/i/A'), rdflib.term.URIRef('http://example.org/i/C')]"),
                ("languageIn ['en']", "languageIn ['en', 'it']"), ("minInclusive 5", "minInclusive 3"),
                ("or [rdflib.term.URIRef('http://example.org/i/B'), rdflib.term.URIRef('http://example.org/i/C')]",
                 "or [rdflib.term.URIRef('http://example.org/i/A'), rdflib.term.URIRef('http://example.org/i/C')]"),
                ("or [rdflib.term.URIRef('http://example.org/i/A'), rdflib.term.URIRef('http://example.org/i/B')]",
                 "class A"),
                ("class B", "or [rdflib.term.URIRef('http://example.org/i/A'), rdflib.term.URIRef('http://example.org/i/C')]"),
                ("or [rdflib.term.URIRef('http://example.org/i/B'), rdflib.term.URIRef('http://example.org/i/A'), rdflib.term.URIRef('http://example.org/i/C')]",
                 "nodeKind BlankNodeOrIRI"),
                ("maxLength 1", "maxLength 3")]
    missing = [e for e in expected if e not in implied_pairs]
    for e in missing:
        print(f"NOT DERIVED (expected): {e[0]} => {e[1]}")
    print(f"{len(constraints)} constraints, {len(focus)} focus nodes, {checked} implications checked, "
          f"{unsound} unsound, {len(missing)} expected implications missing")
    return 1 if unsound or missing else 0


if __name__ == "__main__":
    sys.exit(main())

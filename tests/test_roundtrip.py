#!/usr/bin/env python3
"""Factored shapes must keep every literal term exactly (lexical form, datatype, language).

usage: python tests/test_roundtrip.py

sh:in and sh:hasValue compare RDF terms, so "1.5e0"^^xsd:double and "1.5"^^xsd:double are
different values. rdflib rewrites lexical forms by default, both when parsing and when writing
Turtle (1.5e+00, true for "1"^^xsd:boolean), which once made factored SHACL Play shapes reject
the values they were learned from. This test parses shapes with such literals, factors them,
writes them with factor.write_turtle and checks that the literal terms read back are the same.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from factor import factor, load_hierarchy, write_turtle  # noqa: E402  (also turns off rdflib's literal normalisation)
from rdflib import Graph  # noqa: E402

SHAPES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <http://example.org/r/> .
ex:A_shape a sh:NodeShape ; sh:targetClass ex:A ;
  sh:property [ sh:path ex:v ;
    sh:in ( "1.5e0"^^xsd:double 4.5e0 "01"^^xsd:integer "1.50"^^xsd:decimal "1"^^xsd:boolean
            "x"@en "y" "2026-10-07T00:00:00Z"^^xsd:dateTime ) ] ;
  sh:property [ sh:path ex:w ; sh:hasValue "0.10"^^xsd:decimal ; sh:minCount 1 ] .
ex:B_shape a sh:NodeShape ; sh:targetClass ex:B ;
  sh:property [ sh:path ex:w ; sh:hasValue "0.10"^^xsd:decimal ; sh:minCount 1 ;
                sh:maxInclusive "1.0E1"^^xsd:double ] .
"""
HIERARCHY = "<http://example.org/r/B> <http://www.w3.org/2000/01/rdf-schema#subClassOf> <http://example.org/r/A> .\n"


def literal_terms(path):
    """The literal terms of a Turtle file, read in a fresh interpreter that keeps lexical forms
    (independently of the setting in factor.py)."""
    code = ("import rdflib, sys; rdflib.NORMALIZE_LITERALS = False; "
            "g = rdflib.Graph().parse(sys.argv[1], format='turtle'); "
            "print('\\n'.join(sorted(o.n3() for o in g.objects() if isinstance(o, rdflib.Literal))))")
    out = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, text=True, check=True)
    return set(out.stdout.split("\n")) - {""}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "h.nt").write_text(HIERARCHY)
        (tmp / "in.ttl").write_text(SHAPES)
        g = Graph().parse(tmp / "in.ttl", format="turtle")
        report = factor(g, load_hierarchy([tmp / "h.nt"]))
        write_turtle(g, tmp / "out.ttl")
        before, after = literal_terms(tmp / "in.ttl"), literal_terms(tmp / "out.ttl")
    removed = report["constraints_removed"]
    # B's sh:hasValue and sh:minCount are implied by A's and removed, but the same literals
    # remain in A's shape, so every literal term must survive
    missing, extra = before - after, after - before
    for t in sorted(missing):
        print(f"LOST: {t}")
    for t in sorted(extra):
        print(f"CHANGED INTO: {t}")
    print(f"{len(before)} literal terms, {removed} constraints removed, "
          f"{len(missing)} lost, {len(extra)} changed")
    return 1 if missing or extra or removed == 0 else 0


if __name__ == "__main__":
    sys.exit(main())

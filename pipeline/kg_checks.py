#!/usr/bin/env python3
"""Data-quality checks on a KG's merged dump (work/<KG>/data.nt, see run.py).

usage: pipeline/kg_checks.py KG [--data FILE.nt] [--out DIR]

The checks generalise the defects found in CCKG (docs/cckg-findings.md, D1-D7),
so that they can be re-run on new versions of a KG and on other KGs:

  prefixed-datatype    literals whose datatype IRI looks like an unexpanded prefixed
                       name, e.g. "..."^^<geo:wktLiteral> (D1)
  no-local-name        predicates whose IRI ends with '/' or '#' (D2)
  orphan-bnode         untyped blank nodes that no triple refers to (D2)
  file-iri             file: IRIs, typically relative IRIs resolved against a local path (D3)
  dangling-range       IRI values of a property with a declared rdfs:range class that have
                       no rdf:type at all (D4)
  undeclared-property  predicates in a namespace of the KG's own declared properties that
                       are not declared themselves, e.g. misspellings (D5, D6)
  bad-xsd-term         rdfs:range/rdfs:domain values in the XSD namespace that are not XSD
                       datatypes, e.g. xsd:datetime (D7)

Writes results/<KG>/data-checks.md and data-checks.json.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RDF_TYPE = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
RDFS_RANGE = "<http://www.w3.org/2000/01/rdf-schema#range>"
RDFS_DOMAIN = "<http://www.w3.org/2000/01/rdf-schema#domain>"
XSD = "http://www.w3.org/2001/XMLSchema#"
PROPERTY_CLASSES = {f"<http://www.w3.org/2002/07/owl#{c}>" for c in (
    "ObjectProperty", "DatatypeProperty", "AnnotationProperty", "FunctionalProperty",
    "InverseFunctionalProperty", "TransitiveProperty", "SymmetricProperty", "AsymmetricProperty",
    "ReflexiveProperty", "IrreflexiveProperty")} | {"<http://www.w3.org/1999/02/22-rdf-syntax-ns#Property>"}
# XSD 1.1 built-in datatypes (plus the "special" anyType/anySimpleType/anyAtomicType)
XSD_TYPES = set("""anyType anySimpleType anyAtomicType string normalizedString token language NMTOKEN NMTOKENS
Name NCName ID IDREF IDREFS ENTITY ENTITIES boolean decimal integer nonPositiveInteger negativeInteger long
int short byte nonNegativeInteger unsignedLong unsignedInt unsignedShort unsignedByte positiveInteger float
double duration dayTimeDuration yearMonthDuration dateTime dateTimeStamp time date gYearMonth gYear
gMonthDay gDay gMonth hexBinary base64Binary anyURI QName NOTATION""".split())
# schemes that are really common prefixes when they appear in a datatype IRI
PREFIX_LIKE = re.compile(r"^<(?!https?:|urn:|file:|mailto:|tag:)([A-Za-z][\w.-]*):[^/]")


def parse(line):
    """(s, p, o) from a canonical N-Triples line as written by Jena riot."""
    s, p, rest = line.rstrip("\n").split(" ", 2)
    return s, p, rest[:-2] if rest.endswith(" .") else rest


def namespace(iri):
    body = iri[1:-1]
    cut = max(body.rfind("/"), body.rfind("#"))
    return body[:cut + 1]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kg")
    p.add_argument("--data", type=Path, help="merged N-Triples dump (default: work/<KG>/data.nt)")
    p.add_argument("--out", type=Path, help="output directory (default: results/<KG>)")
    args = p.parse_args()
    data = args.data or ROOT / "work" / args.kg / "data.nt"
    out_dir = args.out or ROOT / "results" / args.kg

    typed, referenced_bnodes, declared_props = set(), set(), set()
    ranges = defaultdict(set)
    predicate_count, datatype_count, file_iris = Counter(), Counter(), Counter()
    bad_xsd = []
    subjects_bnodes = set()
    objects_by_prop = defaultdict(set)  # IRI objects, for properties that may have a range
    with open(data, encoding="utf-8") as f:
        for line in f:
            s, pr, o = parse(line)
            predicate_count[pr] += 1
            if pr == RDF_TYPE:
                typed.add(s)
                if o in PROPERTY_CLASSES:
                    declared_props.add(s)
            if s.startswith("_:"):
                subjects_bnodes.add(s)
            if o.startswith("_:"):
                referenced_bnodes.add(o)
            if o.startswith('"'):
                m = re.search(r'"\^\^(<[^>]*>)$', o)
                if m:
                    datatype_count[m.group(1)] += 1
            elif o.startswith("<"):
                objects_by_prop[pr].add(o)
            for term, where in ((s, "subject"), (o, "object")):
                if term.startswith("<file:"):
                    file_iris[(pr, where)] += 1
            if pr == RDFS_RANGE and o.startswith("<") and not o.startswith("<" + XSD):
                ranges[s].add(o)
            if pr in (RDFS_RANGE, RDFS_DOMAIN) and o.startswith("<" + XSD) and o[len(XSD) + 1:-1] not in XSD_TYPES:
                bad_xsd.append((s, pr, o))

    results = {}
    results["prefixed-datatype"] = {dt: n for dt, n in datatype_count.items() if PREFIX_LIKE.match(dt)}
    results["no-local-name"] = {pr: n for pr, n in predicate_count.items() if pr.endswith("/>") or pr.endswith("#>")}
    results["orphan-bnode"] = len(subjects_bnodes - referenced_bnodes - typed)
    results["file-iri"] = {f"{pr} ({where})": n for (pr, where), n in file_iris.most_common()}
    dangling = {}
    literal_ranges = {"<http://www.w3.org/2000/01/rdf-schema#Literal>"}
    for pr, classes in ranges.items():
        if classes <= literal_ranges or pr not in objects_by_prop:
            continue
        untyped = {o for o in objects_by_prop[pr] if o not in typed}
        if untyped:
            dangling[pr] = {"range": sorted(classes), "untyped_values": len(untyped),
                            "examples": sorted(untyped)[:3]}
    results["dangling-range"] = dangling
    # the KG's own namespaces: those of its declared properties, minus W3C vocabularies
    # (ontologies often re-declare e.g. rdfs:label as an owl:AnnotationProperty)
    own_namespaces = {namespace(p) for p in declared_props} - {ns for ns in map(namespace, declared_props)
                                                               if ns.startswith("http://www.w3.org/")}
    results["undeclared-property"] = {pr: n for pr, n in predicate_count.most_common()
                                      if namespace(pr) in own_namespaces and pr not in declared_props}
    results["bad-xsd-term"] = [" ".join(t) for t in bad_xsd]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data-checks.json").write_text(json.dumps(results, indent=2) + "\n")
    write_markdown(out_dir / "data-checks.md", args.kg, results)
    print((out_dir / "data-checks.md").read_text())


def write_markdown(path, kg, r):
    def count(v):
        if isinstance(v, int):
            return v
        if isinstance(v, dict):
            return sum(x["untyped_values"] if isinstance(x, dict) else x for x in v.values())
        return len(v)

    lines = [f"# Data checks for `{kg}`", "",
             "Generated by `pipeline/kg_checks.py` on the merged dump; see its docstring for the checks.", "",
             "| check | findings |", "|---|---|"]
    for name in ("prefixed-datatype", "no-local-name", "orphan-bnode", "file-iri", "dangling-range",
                 "undeclared-property", "bad-xsd-term"):
        lines.append(f"| {name} | {count(r[name]):,} |")
    for name in ("prefixed-datatype", "no-local-name", "file-iri", "undeclared-property"):
        if r[name]:
            lines += ["", f"## {name}", ""] + [f"- `{k}`: {v:,}" for k, v in r[name].items()]
    if r["dangling-range"]:
        lines += ["", "## dangling-range", ""]
        for pr, d in sorted(r["dangling-range"].items(), key=lambda x: -x[1]["untyped_values"]):
            lines.append(f"- `{pr}` (range {', '.join(f'`{c}`' for c in d['range'])}): "
                         f"{d['untyped_values']:,} untyped values, e.g. " + ", ".join(f"`{e}`" for e in d["examples"]))
    if r["bad-xsd-term"]:
        lines += ["", "## bad-xsd-term", ""] + [f"- `{t}`" for t in r["bad-xsd-term"]]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

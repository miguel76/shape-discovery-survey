"""Run SHACLGEN (data-graph mode) on an RDF file.

The `shaclgen` console script of 3.0.0b4 crashes on start-up
(`importlib.resources.path(__name__, ...)` with `__name__ == "shaclgen.__main__"`),
so we call the library directly, mirroring what `__main__.main` does, and make
shape-label generation robust to IRIs without a local name (see below).
"""
import argparse
import json
import os
import re
from importlib.resources import files

from rdflib import Graph
from rdflib.namespace import NamespaceManager
from rdflib.util import guess_format
from shaclgen.generator import Generator
from shaclgen.shaclgen import data_graph

# Shape IRIs are minted from prefix_localname labels (rdflib compute_qname),
# which raises on IRIs without a local name, e.g. a predicate ending in "/".
# Fall back to a label derived from the whole IRI instead of crashing.
_sh_label_gen = Generator.sh_label_gen


def _robust_sh_label_gen(self, uri):
    try:
        return _sh_label_gen(self, uri)
    except ValueError:
        return "iri_" + re.sub(r"[^A-Za-z0-9]+", "_", str(uri)).strip("_")


Generator.sh_label_gen = _robust_sh_label_gen

p = argparse.ArgumentParser()
p.add_argument("input")
p.add_argument("outdir")
args = p.parse_args()

source = Graph().parse(args.input, format=guess_format(args.input))
namespaces = NamespaceManager(graph=Graph())
for prefix, iri in json.loads((files("shaclgen") / "prefixes/namespaces.json").read_text()).items():
    namespaces.bind(prefix, iri)

shapes = data_graph(source, namespaces).gen_graph(namespace=None, implicit_class_target=False)
os.makedirs(args.outdir, exist_ok=True)
shapes.serialize(os.path.join(args.outdir, "shapes.ttl"), format="turtle")

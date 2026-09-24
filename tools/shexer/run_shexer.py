"""Run sheXer on an N-Triples file (or a SPARQL endpoint) and write SHACL + ShExC."""
import argparse
import os

from shexer.consts import NT, SHACL_TURTLE, SHEXC
from shexer.shaper import Shaper

p = argparse.ArgumentParser()
p.add_argument("input", help="N-Triples file, or SPARQL endpoint URL with --endpoint")
p.add_argument("outdir")
p.add_argument("--endpoint", action="store_true", help="treat input as a SPARQL endpoint URL")
p.add_argument("--instances-cap", type=int, default=-1)
p.add_argument("--acceptance-threshold", type=float, default=0)
args = p.parse_args()

source = {"url_endpoint": args.input} if args.endpoint else {"graph_file_input": args.input, "input_format": NT}

shaper = Shaper(
    all_classes_mode=True,
    instances_cap=args.instances_cap,
    namespaces_dict={
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
        "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
        "http://www.w3.org/2001/XMLSchema#": "xsd",
        "http://weso.es/shapes/": "",
    },
    # keep sheXer defaults for the extraction itself, but emit statistics as RDF
    # annotations rather than comments so they survive parsing.
    generate_annotations=True,
    **source,
)
os.makedirs(args.outdir, exist_ok=True)
shaper.shex_graph(output_file=os.path.join(args.outdir, "shapes.ttl"),
                  output_format=SHACL_TURTLE, acceptance_threshold=args.acceptance_threshold)
shaper.shex_graph(output_file=os.path.join(args.outdir, "shapes.shex"),
                  output_format=SHEXC, acceptance_threshold=args.acceptance_threshold)

#!/usr/bin/env python3
"""Randomised check of pipeline/fold.py: folding the factored shapes gives back the original ones.

usage: python tests/test_fold.py [TRIALS] [SEED]

Each trial uses the random hierarchies, shapes and data of tests/test_factor.py. With S the
original shapes, S' = factor(S) and F = fold(S'), it checks that:
  - F is equivalent to fold(S) for every class and path, modulo implication and shape names
    (fold.compare): nothing is missing from F and nothing is added that S does not state. The
    classes are all those of the hierarchy: every class with inherited constraints has a node
    shape in F, also those whose shape factoring removed, and no empty foldable node shape is
    left (shapes referenced with sh:node and the like are kept, as factoring keeps them);
  - fold(S) itself passes the same check (folding the unfactored shapes changes nothing either);
  - S, S' and F give the same (focus node, path) pairs with violations on the random data
    (with subclass entailment, as in test_factor.py);
  - folding is deterministic: folding S' again gives an isomorphic graph.
Two negative controls check that the comparison can fail: S' itself (not folded) must differ
from S in some trials, and F with an invented constraint added must be reported as saying more.
"""
import random
import sys
import tempfile
from pathlib import Path

from rdflib import RDFS, SH, Graph, Literal
from rdflib.compare import isomorphic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "tests"))
from factor import ShapeIndex, constraints_of, factor, load_hierarchy  # noqa: E402
from fold import compare, fold  # noqa: E402
from test_factor import flagged, random_data, random_hierarchy, random_shapes  # noqa: E402


def copy(g):
    out = Graph()
    for t in g:
        out.add(t)
    return out


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rnd = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    tmp = tempfile.TemporaryDirectory()
    totals = {"removed": 0, "added": 0, "derived": 0, "unfolded_differs": 0, "invented_caught": 0, "invented": 0}
    for i in range(trials):
        edges = random_hierarchy(rnd)
        shapes = random_shapes(rnd)
        data = random_data(rnd, edges)
        hier_file = Path(tmp.name) / f"hierarchy-{i}.nt"
        h = Graph()
        for s, o in edges:
            h.add((s, RDFS.subClassOf, o))
        h.serialize(hier_file, format="nt")
        hierarchy = load_hierarchy([hier_file])
        hier_file.unlink()

        factored = copy(shapes)
        totals["removed"] += factor(factored, hierarchy)["constraints_removed"]
        folded = copy(factored)
        totals["added"] += fold(folded, hierarchy)["constraints_added"]
        folded_original = copy(shapes)
        fold(folded_original, hierarchy)

        for name, result in [("fold(factor(S))", compare(shapes, folded, hierarchy)),
                             ("fold(S)", compare(shapes, folded_original, hierarchy))]:
            if result["classes_without_shape"]:
                print(f"trial {i}: {name} leaves classes with inherited constraints without a shape: "
                      f"{result['classes_without_shape'][:3]}")
                return 1
            if not result["equivalent"]:
                shapes.serialize(f"failing-shapes-{i}.ttl", format="turtle")
                print(f"trial {i}: {name} not equivalent to the original: "
                      f"missing {result['missing'][:3]}, extra {result['extra'][:3]}")
                return 1
        totals["derived"] += compare(shapes, folded, hierarchy)["derived"]
        for result in (folded, folded_original):
            fi = ShapeIndex(result)  # shapes referenced with sh:node etc. are kept even if empty
            empty = [ns for ns in fi.node_shapes if fi.factorable(ns)
                     and not constraints_of(result, ns) and (ns, SH.property, None) not in result]
            if empty:
                print(f"trial {i}: empty node shapes left after folding: {empty[:3]}")
                return 1
        # negative controls
        totals["unfolded_differs"] += not compare(shapes, factored, hierarchy)["equivalent"]
        tampered = copy(folded)
        target = next((ps for ps in sorted(tampered.subjects(SH.path, None), key=str)), None)
        if target is not None:
            tampered.add((target, SH.minLength, Literal(987)))  # stated nowhere in S
            totals["invented"] += 1
            totals["invented_caught"] += bool(compare(shapes, tampered, hierarchy)["extra"])

        before = flagged(data, shapes)
        if not (before == flagged(data, factored) == flagged(data, folded)):
            print(f"trial {i}: (focus node, path) pairs with violations differ")
            return 1
        again = copy(factored)
        fold(again, hierarchy)
        if not isomorphic(again, folded):
            print(f"trial {i}: folding is not deterministic")
            return 1
    if totals["unfolded_differs"] == 0 or totals["invented_caught"] != totals["invented"]:
        print(f"negative controls failed: unfolded shapes differed in {totals['unfolded_differs']} trials, "
              f"invented constraints caught {totals['invented_caught']} of {totals['invented']}")
        return 1
    print(f"{trials} trials: fold(factor(S)) equivalent to fold(S) and to S; {totals['removed']} constraints "
          f"removed by factoring, {totals['added']} added by folding, {totals['derived']} derived by implication; "
          f"negative controls: unfolded shapes differ in {totals['unfolded_differs']} trials, "
          f"{totals['invented_caught']} of {totals['invented']} invented constraints caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())

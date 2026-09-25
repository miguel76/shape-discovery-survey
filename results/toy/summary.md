# Results for `toy`: inference regimes compared

Hand-made toy KG (141 triples) for smoke-testing the pipeline; see toy.ttl header.

Each regime is applied to both shape discovery and validation (see `pipeline/regimes.py`); details per regime in [`none/summary.md`](none/summary.md), [`subclass/summary.md`](subclass/summary.md), [`rdfs/summary.md`](rdfs/summary.md).

Each cell: node shapes / property shapes; (target class, property) pairs constrained, and how many of them are also constrained on a superclass of the class; then, validating the KG against the extracted shapes, the share of focus nodes with at least one violation and the violations per focus node (over a random sample when validation hit its time budget).

| run | none | subclass | rdfs |
|---|---|---|---|
| linkml-schema-automator | 8 / 42 shapes, 34 pairs (5 also on a superclass); 100.0% of 34 focus nodes flagged, 5.79 violations per node | 8 / 42 shapes, 34 pairs (5 also on a superclass); 100.0% of 34 focus nodes flagged, 6.18 violations per node | 8 / 42 shapes, 34 pairs (5 also on a superclass); 100.0% of 34 focus nodes flagged, 6.18 violations per node |
| qse | 8 / 34 shapes, 26 pairs (4 also on a superclass); 47.1% of 34 focus nodes flagged, 0.97 violations per node | 8 / 34 shapes, 26 pairs (4 also on a superclass); 50.0% of 34 focus nodes flagged, 1.03 violations per node | 8 / 34 shapes, 26 pairs (4 also on a superclass); 50.0% of 34 focus nodes flagged, 1.03 violations per node |
| qse-pruned | no output | no output | no output |
| shacl-play | 7 / 25 shapes, 25 pairs (4 also on a superclass); 0.0% of 27 focus nodes flagged, 0.00 violations per node | 7 / 25 shapes, 25 pairs (4 also on a superclass); 0.0% of 27 focus nodes flagged, 0.00 violations per node | 7 / 25 shapes, 25 pairs (4 also on a superclass); 0.0% of 27 focus nodes flagged, 0.00 violations per node |
| shacl-play@endpoint | 7 / 25 shapes, 25 pairs (4 also on a superclass); 0.0% of 27 focus nodes flagged, 0.00 violations per node | 7 / 25 shapes, 25 pairs (4 also on a superclass); 0.0% of 27 focus nodes flagged, 0.00 violations per node | 7 / 25 shapes, 25 pairs (4 also on a superclass); 0.0% of 27 focus nodes flagged, 0.00 violations per node |
| shaclgen | 8 / 21 shapes, 26 pairs (4 also on a superclass); 0.0% of 34 focus nodes flagged, 0.00 violations per node | 8 / 21 shapes, 26 pairs (4 also on a superclass); 0.0% of 34 focus nodes flagged, 0.00 violations per node | 8 / 21 shapes, 26 pairs (4 also on a superclass); 0.0% of 34 focus nodes flagged, 0.00 violations per node |
| shexer | 8 / 37 shapes, 26 pairs (4 also on a superclass); 14.7% of 34 focus nodes flagged, 0.56 violations per node | 8 / 37 shapes, 26 pairs (4 also on a superclass); 29.4% of 34 focus nodes flagged, 0.91 violations per node | 8 / 37 shapes, 26 pairs (4 also on a superclass); 29.4% of 34 focus nodes flagged, 0.91 violations per node |
| shexer@endpoint | 8 / 37 shapes, 26 pairs (4 also on a superclass); 14.7% of 34 focus nodes flagged, 0.56 violations per node | 8 / 37 shapes, 26 pairs (4 also on a superclass); 29.4% of 34 focus nodes flagged, 0.91 violations per node | 8 / 37 shapes, 26 pairs (4 also on a superclass); 29.4% of 34 focus nodes flagged, 0.91 violations per node |

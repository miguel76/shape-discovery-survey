# Results for `cckg`: inference regimes compared

The climate change knowledge graph (CCKG) is a large-scale knowledge graph that integrates climate change-related data from various sources. It contains millions of triples and is designed to support research and analysis in the field of climate science.

Each regime is applied to both shape discovery and validation (see `pipeline/regimes.py`); details per regime in [`none/summary.md`](none/summary.md), [`subclass/summary.md`](subclass/summary.md), [`rdfs/summary.md`](rdfs/summary.md).

Each cell: node shapes / property shapes; (target class, property) pairs constrained, and how many of them are also constrained on a superclass of the class; then, validating the KG against the extracted shapes, the share of focus nodes with at least one violation and the violations per focus node (over a random sample when validation hit its time budget).

| run | none | subclass | rdfs |
|---|---|---|---|
| linkml-schema-automator | 59 / 434 shapes, 375 pairs (130 also on a superclass); 100.0% of 594,980 focus nodes flagged, 15.26 violations per node | no output | no output |
| qse | 59 / 375 shapes, 316 pairs (96 also on a superclass); 99.6% of 594,982 focus nodes flagged, 10.44 violations per node | 88 / 870 shapes, 788 pairs (644 also on a superclass); 100.0% of a sample of 94,309 focus nodes flagged, 143.08 violations per node | 91 / 1202 shapes, 1118 pairs (960 also on a superclass); 100.0% of a sample of 11,334 focus nodes flagged, 187.35 violations per node |
| qse-pruned | 21 / 124 shapes, 103 pairs (14 also on a superclass); 98.6% of 594,106 focus nodes flagged, 6.08 violations per node | 45 / 290 shapes, 249 pairs (198 also on a superclass); 100.0% of a sample of 301,188 focus nodes flagged, 103.10 violations per node | 47 / 444 shapes, 401 pairs (342 also on a superclass); 91.6% of a sample of 13,885 focus nodes flagged, 178.37 violations per node |
| shacl-play | 47 / 238 shapes, 238 pairs (96 also on a superclass); 19.3% of 594,528 focus nodes flagged, 0.50 violations per node | 77 / 710 shapes, 710 pairs (644 also on a superclass); 19.3% of 594,528 focus nodes flagged, 2.64 violations per node | 79 / 1040 shapes, 1040 pairs (960 also on a superclass); 0.0% of 654,288 focus nodes flagged, 0.00 violations per node |
| shacl-play@endpoint | 47 / 238 shapes, 238 pairs (96 also on a superclass); 19.3% of 594,528 focus nodes flagged, 0.50 violations per node | 77 / 710 shapes, 710 pairs (644 also on a superclass); 19.3% of 594,528 focus nodes flagged, 2.64 violations per node | - |
| shaclgen | 59 / 92 shapes, 316 pairs (96 also on a superclass); 19.3% of 594,982 focus nodes flagged, 0.50 violations per node | 89 / 92 shapes, 788 pairs (644 also on a superclass); 19.3% of 594,982 focus nodes flagged, 2.64 violations per node | no output |
| shexer | 59 / 425 shapes, 316 pairs (96 also on a superclass); 99.1% of 594,982 focus nodes flagged, 4.64 violations per node | 89 / 1788 shapes, 788 pairs (644 also on a superclass); 100.0% of a sample of 87,851 focus nodes flagged, 2356.93 violations per node | 92 / 2173 shapes, 1118 pairs (960 also on a superclass); 100.0% of a sample of 2,461 focus nodes flagged, 2981.74 violations per node |
| shexer@endpoint | 58 / 419 shapes, 303 pairs (96 also on a superclass); 99.2% of 594,919 focus nodes flagged, 4.64 violations per node | no output | - |

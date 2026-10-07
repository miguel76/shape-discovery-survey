# Results for `cckg`: inference regimes compared

The climate change knowledge graph (CCKG) is a large-scale knowledge graph that integrates climate change-related data from various sources. It contains millions of triples and is designed to support research and analysis in the field of climate science.

Each regime is applied to both shape discovery and validation (see `pipeline/regimes.py`); details per regime in [`none/summary.md`](none/summary.md), [`subclass/summary.md`](subclass/summary.md), [`rdfs/summary.md`](rdfs/summary.md).

Each cell: node shapes / property shapes; (target class, property) pairs constrained, and how many of them are also constrained on a superclass of the class; then, validating the KG against the extracted shapes, the share of focus nodes with at least one violation and the violations per focus node (over a random sample when validation hit its time budget).

| run | none | subclass | rdfs |
|---|---|---|---|
| linkml-schema-automator | 60 / 423 shapes, 363 pairs (148 also on a superclass); 100.0% of 595,920 focus nodes flagged, 16.52 violations per node | - | - |
| qse | 60 / 363 shapes, 303 pairs (110 also on a superclass); 99.1% of 595,920 focus nodes flagged, 7.72 violations per node | 92 / 833 shapes, 748 pairs (612 also on a superclass); 100.0% of a sample of 13,339 focus nodes flagged, 108.78 violations per node | - |
| qse+factored | - | 89 / 507 shapes, 424 pairs (285 also on a superclass); 100.0% of a sample of 17,448 focus nodes flagged, 112.08 violations per node | 91 / 683 shapes, 612 pairs (444 also on a superclass); 100.0% of a sample of 1,996 focus nodes flagged, 149.16 violations per node |
| qse-pruned | 21 / 119 shapes, 98 pairs (26 also on a superclass); 98.5% of 595,024 focus nodes flagged, 5.98 violations per node | 47 / 284 shapes, 241 pairs (199 also on a superclass); 100.0% of a sample of 52,274 focus nodes flagged, 102.65 violations per node | - |
| qse-pruned+factored | - | 45 / 168 shapes, 127 pairs (79 also on a superclass); 100.0% of a sample of 84,009 focus nodes flagged, 85.28 violations per node | 47 / 257 shapes, 214 pairs (156 also on a superclass); 99.7% of a sample of 368 focus nodes flagged, 170.40 violations per node |
| shacl-play | 49 / 228 shapes, 228 pairs (110 also on a superclass); 19.2% of 595,459 focus nodes flagged, 0.50 violations per node | 82 / 672 shapes, 672 pairs (611 also on a superclass); 19.2% of a sample of 215,357 focus nodes flagged, 2.68 violations per node | - |
| shacl-play@endpoint | 49 / 228 shapes, 228 pairs (110 also on a superclass); 19.2% of 595,459 focus nodes flagged, 0.50 violations per node | - | - |
| shaclgen | 60 / 90 shapes, 303 pairs (110 also on a superclass); 19.2% of 595,920 focus nodes flagged, 0.50 violations per node | - | - |
| shexer | 60 / 408 shapes, 303 pairs (110 also on a superclass); 99.0% of 595,920 focus nodes flagged, 4.89 violations per node | 93 / 1876 shapes, 747 pairs (611 also on a superclass); 100.0% of a sample of 11,782 focus nodes flagged, 2498.69 violations per node | - |
| shexer+factored | - | 73 / 794 shapes, 422 pairs (283 also on a superclass); 100.0% of a sample of 27,014 focus nodes flagged, 1489.21 violations per node | 77 / 1055 shapes, 625 pairs (463 also on a superclass); 100.0% of a sample of 240 focus nodes flagged, 2065.49 violations per node |
| shexer@endpoint | 59 / 404 shapes, 291 pairs (110 also on a superclass); 99.0% of 595,843 focus nodes flagged, 4.89 violations per node | - | - |

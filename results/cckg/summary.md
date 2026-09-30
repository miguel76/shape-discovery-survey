# Results for `cckg`: inference regimes compared

The climate change knowledge graph (CCKG) is a large-scale knowledge graph that integrates climate change-related data from various sources. It contains millions of triples and is designed to support research and analysis in the field of climate science.

Each regime is applied to both shape discovery and validation (see `pipeline/regimes.py`); details per regime in [`none/summary.md`](none/summary.md), [`subclass/summary.md`](subclass/summary.md), [`rdfs/summary.md`](rdfs/summary.md).

Each cell: node shapes / property shapes; (target class, property) pairs constrained, and how many of them are also constrained on a superclass of the class; then, validating the KG against the extracted shapes, the share of focus nodes with at least one violation and the violations per focus node (over a random sample when validation hit its time budget).

| run | none | subclass | rdfs |
|---|---|---|---|
| linkml-schema-automator | 60 / 425 shapes, 365 pairs (135 also on a superclass); 100.0% of 595,770 focus nodes flagged, 16.50 violations per node | - | no output |
| qse | 60 / 365 shapes, 305 pairs (103 also on a superclass); 99.5% of 595,912 focus nodes flagged, 10.17 violations per node | 89 / 812 shapes, 729 pairs (590 also on a superclass); 100.0% of a sample of 17,448 focus nodes flagged, 149.71 violations per node | - |
| qse+factored | - | 89 / 673 shapes, 590 pairs (451 also on a superclass); 100.0% of a sample of 17,448 focus nodes flagged, 112.08 violations per node | - |
| qse-pruned | 21 / 120 shapes, 99 pairs (16 also on a superclass); 98.5% of 595,032 focus nodes flagged, 5.98 violations per node | 45 / 269 shapes, 228 pairs (180 also on a superclass); 100.0% of a sample of 83,958 focus nodes flagged, 102.43 violations per node | - |
| qse-pruned+factored | - | 45 / 220 shapes, 179 pairs (131 also on a superclass); 100.0% of a sample of 83,958 focus nodes flagged, 85.27 violations per node | - |
| shacl-play | 48 / 227 shapes, 227 pairs (103 also on a superclass); 19.2% of 595,454 focus nodes flagged, 0.50 violations per node | - | - |
| shacl-play.prev-dump | - | 77 / 710 shapes, 710 pairs (644 also on a superclass); 19.5% of 595,454 focus nodes flagged, 2.58 violations per node | - |
| shacl-play.prev-dump+factored | - | 64 / 228 shapes, 228 pairs (162 also on a superclass); 19.5% of 595,454 focus nodes flagged, 0.31 violations per node | - |
| shaclgen | - | - | no output |
| shexer | 60 / 415 shapes, 305 pairs (103 also on a superclass); 99.0% of 595,912 focus nodes flagged, 5.23 violations per node | 90 / 1732 shapes, 729 pairs (590 also on a superclass); 100.0% of a sample of 27,014 focus nodes flagged, 2366.20 violations per node | - |
| shexer+factored | - | 73 / 794 shapes, 422 pairs (283 also on a superclass); 100.0% of a sample of 27,014 focus nodes flagged, 1489.21 violations per node | - |

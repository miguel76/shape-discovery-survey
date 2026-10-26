# Results for `cckg`: inference regimes compared

The climate change knowledge graph (CCKG) is a large-scale knowledge graph that integrates climate change-related data from various sources. It contains millions of triples and is designed to support research and analysis in the field of climate science.

Each regime is applied to both shape discovery and validation (see `pipeline/regimes.py`); details per regime in [`none/summary.md`](none/summary.md), [`subclass/summary.md`](subclass/summary.md), [`rdfs/summary.md`](rdfs/summary.md).

Each cell: node shapes / property shapes; (target class, property) pairs constrained, and how many of them are also constrained on a superclass of the class; then, validating the KG against the extracted shapes, the share of focus nodes with at least one violation and the violations per focus node (over a random sample when validation hit its time budget).

| run | none | subclass | rdfs |
|---|---|---|---|
| linkml-schema-automator | 67 / 515 shapes, 448 pairs (179 also on a superclass); 100.0% of 605,840 focus nodes flagged, 20.25 violations per node | - | - |
| qse | 67 / 448 shapes, 386 pairs (143 also on a superclass); 99.1% of 605,919 focus nodes flagged, 4.83 violations per node | - | - |
| qse+factored | - | 92 / 510 shapes, 425 pairs (289 also on a superclass); 100.0% of a sample of 13,339 focus nodes flagged, 90.41 violations per node | 94 / 712 shapes, 632 pairs (470 also on a superclass); 100.0% of a sample of 1,509 focus nodes flagged, 141.05 violations per node |
| qse-pruned | 25 / 144 shapes, 119 pairs (33 also on a superclass); 98.6% of 605,011 focus nodes flagged, 6.50 violations per node | - | - |
| qse-pruned+factored | - | 47 / 165 shapes, 122 pairs (80 also on a superclass); 100.0% of a sample of 52,274 focus nodes flagged, 85.43 violations per node | 49 / 256 shapes, 218 pairs (160 also on a superclass); 100.0% of a sample of 10,907 focus nodes flagged, 116.05 violations per node |
| shacl-play | 56 / 296 shapes, 296 pairs (143 also on a superclass); 0.0% of 605,417 focus nodes flagged, 0.00 violations per node | 93 / 855 shapes, 855 pairs (786 also on a superclass); 0.0% of 605,417 focus nodes flagged, 0.00 violations per node | - |
| shacl-play+factored | - | 71 / 257 shapes, 257 pairs (188 also on a superclass); 0.0% of 605,417 focus nodes flagged, 0.00 violations per node | - |
| shacl-play@endpoint | 56 / 296 shapes, 296 pairs (143 also on a superclass); 0.0% of 605,417 focus nodes flagged, 0.00 violations per node | - | - |
| shaclgen | 68 / 99 shapes, 381 pairs (143 also on a superclass); 0.0% of 605,919 focus nodes flagged, 0.00 violations per node | - | - |
| shexer | 68 / 518 shapes, 381 pairs (143 also on a superclass); 99.0% of 605,919 focus nodes flagged, 11.81 violations per node | - | - |
| shexer+factored | - | 72 / 817 shapes, 418 pairs (282 also on a superclass); 100.0% of a sample of 11,782 focus nodes flagged, 1485.85 violations per node | 73 / 1104 shapes, 656 pairs (494 also on a superclass); 100.0% of a sample of 749 focus nodes flagged, 2058.19 violations per node |
| shexer@endpoint | 67 / 514 shapes, 369 pairs (143 also on a superclass); 99.0% of 605,838 focus nodes flagged, 11.72 violations per node | - | - |

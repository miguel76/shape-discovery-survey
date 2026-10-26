# CCKG: findings

Phase 1 of the survey runs every tool on the
[Climate Change Knowledge Graph](https://hacid-project.github.io/cckg/). This document describes the
latest evaluation, on the snapshot published on figshare as
[version 14](https://doi.org/10.6084/m9.figshare.29066711.v14) (2026-10-24). Earlier dumps, the data
issues found in them and their fixes are recorded in [cckg-change-log.md](cckg-change-log.md).

The numbers are in [`results/cckg/summary.md`](../results/cckg/summary.md), with a per-run
`eval.json` in each run directory. `data/cckg/kg.json` refers to the figshare item, which the
pipeline downloads into `data/cckg/download/` ([pipeline/sources.py](../pipeline/sources.py)). To
reproduce:

```sh
make install
make run evaluate KG=cckg INFERENCE=none RUN_ARGS="--endpoint --local-endpoint --timeout 6900"
make run evaluate KG=cckg INFERENCE=subclass RUN_ARGS="--timeout 6900"
make run evaluate KG=cckg INFERENCE=rdfs RUN_ARGS="--timeout 6900"
.tools/pipeline-venv/bin/python pipeline/kg_checks.py cckg
.tools/pipeline-venv/bin/python pipeline/link_sources.py cckg
```

Tool runs were limited to 115 minutes (`--timeout`), close to the most a single command can run in
the environment that produced these results. Under `subclass` and `rdfs`, validations were limited
to 10 minutes per set of shapes (`VALIDATION_BUDGET=600`, see below), except for SHACL Play's
shapes, which were validated on all the focus nodes.

## Input

- **Dump:** `cckg.nq.gz` of figshare v14 (MD5 `be404391d81b8a4588fe149c9179b10c`): 5,275,929 quads in
  15 named graphs. Twelve hold data (`data/cs` and `data/cs/*`); three hold the ontology modules
  (`onto/*`), which also give the class hierarchy.
- **What the tools see:** the pipeline merges all graphs into one, giving 5,248,556 distinct
  triples. Of the 605,977 subjects, 605,919 are typed. There are 68 classes, including OWL/RDFS
  vocabulary classes from the ontology graphs.
- **Endpoint:** the public endpoint (`https://w3id.org/hacid/cs/sparql`) is not reachable from the
  environment that produced these results. The endpoint runs use a local Fuseki serving the dump
  from a TDB2 store (`--local-endpoint`).
- **Inference regimes:** the data are prepared under three regimes, applied to discovery and
  validation alike ([inference.md](inference.md)). `none` uses the asserted triples only (5.2M;
  validation leaves out the 221 `rdfs:subClassOf` triples). `subclass` adds `rdf:type` along the
  subclass closure (10.8M triples). `rdfs` adds the full RDFS closure (14.6M).

## Data quality

[`pipeline/kg_checks.py`](../pipeline/kg_checks.py) runs checks that generalise the defects found in
earlier dumps ([report](../results/cckg/data-checks.md)), and
[`pipeline/link_sources.py`](../pipeline/link_sources.py) breaks dangling links down by source graph
([report](../results/cckg/dangling-by-source.md)).

| check | findings |
|---|---|
| prefixed datatypes, predicates without local name, orphan blank nodes, `file:` IRIs, invalid XSD terms | 0 |
| dangling links: values of a property with a declared class range that have no `rdf:type` | 0, in all 12 data graphs |
| undefined variables ([analysis](../results/cckg/undefined-variables.md)) | 0 |
| undeclared HACID properties | `top-level:associatedWith`, 10 triples |

- **Variables are now modelled per project.** Besides the CMIP6 variables (`variables/mip/*`),
  there are `variables/mip/cmip5/*`, `variables/mip/cmip6/<data specs version>/*`,
  `variables/cordex/*` and `variables/ukcp/*`, all defined. The UKCP18 variables include their
  products (e.g. `variables/ukcp/tasAnom/1981-2000/cdf`), and some refer to the MIP variable they
  are derived from (e.g. `naodjf` from `psl`). The CF
  variables follow version 95 of the CF standard-name table.
- **`top-level:associatedWith` is no longer declared** by the ontology, but 10 triples still use it,
  linking per-model variable groups to their models (e.g. `variables/cmip5/CNRM-CM5` to
  `models/CNRM-CM5`, in `cmip5/datasets` and `cordex-cmip5/datasets`).

## Running the tools

| run | `none` | `subclass` | `rdfs` |
|---|---|---|---|
| sheXer (file) | 2.0 min, 1.7 GB | 8.1 min, 4.1 GB | 14.7 min, 5.9 GB |
| sheXer (endpoint) | 56 min, 8.8 GB | – | – |
| QSE, full | 1.0 min, 3.2 GB | 2.1 min, 6.9 GB | 3.6 min, 7.3 GB |
| QSE, pruned (confidence ≥ 0.1, support ≥ 100) | 1.0 min, 4.0 GB | 2.0 min, 6.7 GB | 3.6 min, 8.3 GB |
| SHACLGEN | 51 min, 7.0 GB | not attempted | out of memory (12 GB) |
| SHACL Play! (file) | 5.1 min, 4.5 GB | 103 min, 5.4 GB | not attempted |
| SHACL Play! (endpoint) | 4.4 min, 0.2 GB (+ Fuseki) | – | – |
| LinkML schema-automator | 15.8 min, 8.5 GB | out of memory (12 GB) | out of memory (12 GB) |

- **Not attempted:** SHACLGEN under `subclass` and SHACL Play under `rdfs` did not finish within 115
  minutes on the smaller dump of 2026-10-07, even with nothing else running. Their other runs on v14
  are slower than there (SHACLGEN 51 against 43 minutes under `none`, SHACL Play 103 against 71
  under `subclass`).
- **Endpoint runs** were made under `none` only. Under the other regimes the endpoint would serve
  the materialised data, and sheXer's endpoint mode, at about 300 queries per second, already
  takes 56 minutes on the asserted data.

What it takes to run the tools on CCKG (patches and wrappers in `tools/`):

- **sheXer:** its N-Triples reader looked for `"geo:"` anywhere in a literal and crashed on
  unusual datatype IRIs. [`tools/shexer/literal-datatype.patch`](../tools/shexer/literal-datatype.patch)
  makes it inspect only the datatype. Its endpoint mode sends one query per node and skips
  blank-node instances (`FILTER(!isBlank(?s))`), so it misses the OWL class expressions that file
  mode includes.
- **SHACLGEN** loads the graph with rdflib in a few minutes, then runs its SPARQL queries per
  property over rdflib, which takes most of its 51 minutes under `none`. The wrapper mints shape
  names from the whole IRI when a predicate has no local name.
- **schema-automator:** the wrapper raises Python's `csv` field limit (128 KiB by default) and puts
  the intermediate tables in a temporary directory. With the closures it runs out of memory.
- **Fuseki** uses TDB2: with an in-memory dataset it grew past 12 GB under sheXer's query load.
- **Validation:** pySHACL cannot handle millions of triples in reasonable time, and a whole-graph
  Jena report runs out of memory. Validation runs node by node with aggregated counts
  ([`pipeline/ShaclStats.java`](../pipeline/ShaclStats.java)). When a set of shapes takes longer
  than its budget, the counts are over a random sample of the focus nodes. The sample is seeded and
  independent of the order of the shapes, so original and factored shapes are compared on the
  same nodes.

## Validating CCKG against the extracted shapes

There are no reference shapes for CCKG yet, so the evaluation reports how the KG fares against
the shapes extracted from it, under the regime they were extracted for.

### Regime `none` (asserted triples only)

| run | node / property shapes | nodes flagged | violations | violations per node |
|---|---|---|---|---|
| SHACL Play! (file and endpoint) | 56 / 296 | 9 of 605,417 | 18 | 0.00003 |
| SHACLGEN | 68 / 99 | 28 of 605,919 | 28 | 0.00005 |
| sheXer (file) | 68 / 518 | 599,909 (99.0%) | 7,156,116 | 11.8 |
| sheXer (endpoint) | 67 / 514 | 599,943 (99.0%) | 7,099,703 | 11.7 |
| QSE, pruned | 25 / 144 | 596,244 (98.6%) | 3,932,942 | 6.5 |
| QSE, full | 67 / 448 | 600,533 (99.1%) | 2,925,450 | 4.8 |
| schema-automator | 67 / 515 | 605,840 (100%) | 12,268,117 | 20.3 |

**The descriptive tools find almost nothing left to report.** On the 2026-10-07 dump, SHACL Play
and SHACLGEN flagged 114.6k nodes, the datasets that referred to undefined variables. Now:
- **SHACL Play's 9 nodes** are the return-period distributions of the UKCP18 extremes
  (`variables/ukcp/{pr1day,pr5day,tasmax}/rp{20,50,100}/cdf`). Their
  `data:isProbabilisticRepresentationOf` points to a `DeterministicVariable`
  (`variables/ukcp/pr1day/rp100`), whereas the other 90 values of that property, the distributions
  of the anomalies, point to an `AbsoluteAnomaly` or a `RelativeAnomaly`. These distributions are
  themselves typed both `DeterministicVariable` and `QuantileFunction`. This may be intended, but
  it is the one place where the UKCP18 distributions are modelled differently.
- **SHACLGEN's 28 nodes** are in the ontology graphs: `sh:or` constraints on `owl:onProperty` and
  `rdfs:range`, and one on `owl:imports`.

**The other tools emit constraints that the data contradicts:**
- **QSE** emits `sh:maxCount 1` on `data:dependsOnVariable` for `SingleProjection`, although
  510,041 of the 521,951 projections have two values. It only ever emits `minCount 1` and
  `maxCount 1`, and its `sh:node` references pass each failure on to every node that points to a
  failing node: 1.3M of its 2.9M violations are `sh:node` violations. Pruning by confidence and
  support does not remove these constraints.
- **sheXer** turns each `rdf:type` value into its own property shape (`sh:in ( C )`,
  `maxCount 1`), which fails on every node with several types: 4.0M of its 7.2M violations. Most
  of the others (3.1M) are `sh:node` violations passed on by references.
- **schema-automator** checks IRIs as `xsd:string` literals, builds `sh:in` lists from samples of
  the values, and closes every shape, so it rejects every node.

### Regime `subclass` (plus `rdf:type` along the subclass closure)

| run | node / property shapes | (class, property) pairs, of which also on a superclass | nodes flagged | violations per node |
|---|---|---|---|---|
| SHACL Play! | 93 / 855 | 855, 786 (92%) | **0** of 605,417 | 0 |
| sheXer | 105 / 2,342 | 940, 786 (84%) | 100% (sample of 1,043) | 4,580 |
| QSE, pruned | 53 / 328 | 279, 241 (86%) | 100% (sample of 61.2k) | 141 |
| QSE, full | 103 / 1,037 | 946, 787 (83%) | 100% (sample of 13.1k) | 141 |
| SHACLGEN | not attempted | | | |
| schema-automator | out of memory | | | |

- **CCKG conforms to SHACL Play's `subclass` shapes.** The 9 nodes flagged under `none` pass here:
  SHACL Play's `sh:or` lists every class of the values, and with the subclass closure these include
  superclasses such as `Variable` that all the values share.
- **Shapes for abstract classes appear.** Classes such as `ccso:Projection` and `top-level:Entity`
  get shapes learned from all their members.
- **Redundancy grows.** 83–92% of the constrained (class, property) pairs repeat a pair constrained
  on a superclass, against 28–48% under `none`. Factoring (below) removes it.
- **sheXer's per-type `rdf:type` shapes multiply.** A projection has about 10 types, and each
  `rdf:type sh:in ( C )` shape rejects the other 9, on each of the node shapes that target the node.

### Regime `rdfs` (full RDFS closure)

The data grow to 14.6M triples. Besides 1.1M `rdf:type` triples from domains, ranges and the
subclass closure, the closure adds the superproperties of the data properties: 572k
`derivedFromVariable` and 572k `holdsSpecializationOfVariable` triples, 530k `hasPart` and
`hasProperPart`, 291k `hasVariableDerivedFrom` and 111k `isDescribedBy`.

| run | node / property shapes | (class, property) pairs, of which also on a superclass | nodes flagged | violations per node |
|---|---|---|---|---|
| sheXer | 106 / 2,834 | 1,383, 1,203 (87%) | 100% (sample of 720) | 5,963 |
| QSE, pruned | 55 / 537 | 493, 434 (88%) | 100% (sample of 7.6k) | 215 |
| QSE, full | 104 / 1,474 | 1,390, 1,206 (87%) | 100% (sample of 3.1k) | 257 |
| SHACL Play! | not attempted | | | |
| SHACLGEN, schema-automator | out of memory | | | |

- **Shapes describe the inferred superproperties too**, which adds property shapes: sheXer's grow
  from 2,342 to 2,834.
- **Validation slows down for `sh:node`-heavy shapes.** `sh:node` checks traverse the inferred links
  as well: in 10 minutes, sheXer's shapes were validated on 720 nodes.
- **Domain and range inference can hide errors.** On earlier dumps, it typed the undefined variables
  as `data:Variable`, because they were values of properties whose `rdfs:range` is `data:Variable`,
  so `sh:class data:Variable` held by construction. Now that the variables are defined, there is
  nothing for it to hide in CCKG, but the effect remains a reason to prefer `subclass`
  ([inference.md](inference.md)).

## Factoring along the class hierarchy

Under `subclass` and `rdfs`, every run is also factored along the class hierarchy
([factoring.md](factoring.md)): constraints implied by a superclass's shape are removed. The
factored shapes are validated on the same focus nodes as the originals. They must flag the same
nodes, since factoring is proven to preserve which (node, property) pairs are violated.

| regime | run | constraints removed | property shapes | node shapes | nodes flagged (original = factored) | violations | validation time |
|---|---|---|---|---|---|---|---|
| `subclass` | SHACL Play | 2,119 of 2,599 (82%) | 855 → 257 | 93 → 71 | 0 (all nodes) | 0 → 0 | 2,844 s → 1,302 s |
| `subclass` | sheXer | 3,406 of 5,585 (61%) | 2,342 → 1,011 | 105 → 80 | 1,043 (sample) | 4,776,547 → 2,935,295 (−39%) | 601 s → 134 s |
| `subclass` | QSE, full | 1,024 of 2,205 (46%) | 1,037 → 604 | 103 | 13,080 (sample) | 1,843,812 → 1,564,255 (−15%) | 601 s → 280 s |
| `subclass` | QSE, pruned | 355 of 621 (57%) | 328 → 164 | 53 | 61,210 (sample) | 8,644,390 → 7,034,792 (−19%) | 600 s → 364 s |
| `rdfs` | sheXer | 3,662 of 6,361 (58%) | 2,834 → 1,334 | 106 → 83 | 720 (sample) | 4,293,433 → 2,757,543 (−36%) | 762 s → 248 s |
| `rdfs` | QSE, full | 1,470 of 3,135 (47%) | 1,474 → 856 | 104 | 3,147 (sample) | 807,932 → 633,952 (−22%) | 1,700 s → 1,022 s |
| `rdfs` | QSE, pruned | 544 of 1,016 (54%) | 537 → 284 | 55 | 7,596 (sample) | 1,631,140 → 1,378,448 (−15%) | 600 s → 320 s |

In every run the factored shapes flag exactly the same nodes. SHACL Play's shapes, the most
factored, are also those that CCKG now conforms to, so for them the comparison only shows that
factoring introduces no violations; on the 2026-10-07 dump the sets of (node, property) pairs with
violations were compared over the whole KG and were identical (114,709 pairs).

## Tool bugs found (to report upstream)

| tool | bug |
|---|---|
| sheXer 2.7.3.1 | SHACL output uses `sh:dataType` (not a SHACL term), so every datatype constraint is lost. The literal datatype is detected by searching the whole literal. In endpoint mode `geo:asWKT` gets `xsd:string` where file mode reports the real datatype. |
| QSE (`4bcfb04`) | `sh:NodeKind` is used as a predicate instead of `sh:nodeKind`. Literals with an unusual datatype IRI are read as IRIs, with a URL-encoded class invented for them. `minCount 1` and `maxCount 1` are contradicted by the data. |
| SHACL Play! (`4e85078`) | SELECT queries ignore their variable bindings (patched here). When a query fails, it logs the error and exits 0 with an empty shapes file. |
| SHACLGEN 3.0.0b4 | Console script crashes on start-up. Crashes on property IRIs without a local name. |
| schema-automator 0.5.7 | Crashes on TSV cells over 128 KiB. Global slot definitions depend on triple order. |

## Next steps

1. **Data:** declare `top-level:associatedWith` again or replace it in the 10 triples, and check
   whether the return-period distributions of the UKCP18 extremes should represent their variables
   as the anomaly distributions do.
2. **Reference shapes for CCKG.** The evaluation has no ground truth yet. Reference shapes should
   state their regime (`reference_regime` in `kg.json`, ideally `sh:entailment` in the shapes
   graph). SHACL Play's factored `subclass` shapes, which the KG now conforms to, are a natural
   starting point, together with sheXer's cardinalities.
3. Report the tool bugs upstream. Look into QSE's cardinality extraction and its query-based mode.

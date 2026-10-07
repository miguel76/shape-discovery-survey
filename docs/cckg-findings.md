# CCKG: findings

Phase 1 of the survey runs every tool on the
[Climate Change Knowledge Graph](https://hacid-project.github.io/cckg/). This document describes the
latest evaluation, on the dump of 2026-10-07. Earlier dumps, the data issues found in them and
their fixes are recorded in [cckg-change-log.md](cckg-change-log.md).

The numbers are in [`results/cckg/summary.md`](../results/cckg/summary.md), with a per-run
`eval.json` in each run directory. To reproduce:

```sh
make install
make run evaluate KG=cckg INFERENCE=none RUN_ARGS="--endpoint --local-endpoint"
make run evaluate KG=cckg INFERENCE=subclass RUN_ARGS=
make run evaluate KG=cckg INFERENCE=rdfs RUN_ARGS=
.tools/pipeline-venv/bin/python pipeline/kg_checks.py cckg
.tools/pipeline-venv/bin/python pipeline/link_sources.py cckg
```

Tool runs were limited to 115 minutes (`TOOL_TIMEOUT`) and, under `subclass` and `rdfs`,
validations to 10 minutes per set of shapes (`VALIDATION_BUDGET`, see below).

## Input

- **Dump:** [`data/cckg/cckg_2026-10-07_10-04-53.nq.gz`](../data/cckg): 4,613,218 quads in 15
  named graphs. Twelve hold data (`data/cs` and `data/cs/*`); three hold the ontology modules
  (`onto/*`), which also give the class hierarchy.
- **What the tools see:** the pipeline merges all graphs into one, giving 4,612,318 distinct
  triples. Of the 595,977 subjects, 595,920 are typed. There are 60 classes, including OWL/RDFS
  vocabulary classes from the ontology graphs.
- **Endpoint:** the public endpoint (`https://w3id.org/hacid/cs/sparql`) is not reachable from the
  environment that produced these results. The endpoint runs use a local Fuseki serving the dump
  from a TDB2 store (`--local-endpoint`).
- **Inference regimes:** the data are prepared under three regimes, applied to discovery and
  validation alike ([inference.md](inference.md)). `none` uses the asserted triples only (4.6M;
  validation leaves out the 200 `rdfs:subClassOf` triples). `subclass` adds `rdf:type` along the
  subclass closure (8.8M triples). `rdfs` adds the full RDFS closure (11.9M).

## Data quality

### Generic checks

[`pipeline/kg_checks.py`](../pipeline/kg_checks.py) runs checks that generalise the defects found in
earlier dumps ([report](../results/cckg/data-checks.md)). All of them are now clean except one:

| check | findings |
|---|---|
| prefixed datatypes, predicates without local name, orphan blank nodes, `file:` IRIs, undeclared HACID properties, invalid XSD terms | 0 |
| dangling links: values of a property with a declared class range that have no `rdf:type` | 4,916 values |

### Dangling links by source

[`pipeline/link_sources.py`](../pipeline/link_sources.py) breaks the dangling links down by the named
graph they come from, and compares them with all the links of the same kind
([report](../results/cckg/dangling-by-source.md)).

| source graph | links (class-range properties) | dangling links |
|---|---|---|
| `cordex-cmip5/datasets` | 1,143,079 | 78,801 (6.9%) |
| `ukcp18` | 1,819,811 | 72,590 (4.0%) |
| `cmip5/datasets` | 253,039 | 31,837 (12.6%) |
| `mohc-cvs` | 1,463 | 20 (1.4%) |
| `cmip6/cmor-tables` | 9,219 | 1 |
| the other 7 graphs | 17,934 | 0 |

By source, property and family of targets:

| source | property | targets | undefined targets | dangling links |
|---|---|---|---|---|
| `ukcp18` | `hasOutput`, `hasComponent` | `datasets/cordex.*` | 2,202 of 2,869 (77%) | 2,202 of 2,869 each |
| `ukcp18` | `hasOutput`, `hasComponent` | `datasets/cmip5.*` | 9 of 26 | 9 of 26 each |
| `ukcp18` | `hasComponent` | `simulations/cmip5.*`, `simulations/cordex.*` | 9 of 26, 3 of 64 | 12 |
| `cordex-cmip5/datasets` | `holds/isSpecializationOfVariable` | `variables/mip/*` | 138 of 209 (66%) | 38,444 and 39,982 (27%) |
| `cmip5/datasets` | `holdsSpecializationOfVariable` | `variables/mip/*` | 122 of 546 (22%) | 31,837 (15%) |
| `ukcp18` | `holds/isSpecializationOfVariable` | `variables/mip/*` | 23 of 46 (50%) | 273 and 67,883 (14–16%) |
| `cordex-cmip5/datasets` | `ccso:isDownscalingOf` | `simulations/cmip5.*` | 21 of 157 (13%) | 131 |
| `mohc-cvs` | `derivedFromVariable` | `variables/mip/*` | 14 of 33 | 20 |
| `cordex-cmip5/datasets` | `dependsOnVariable`, `isSpecializedAccordingTo` | `cordex/grids/{ARC-22,SAM-20}/*` | 2 of 2 each | 61 each |
| `cmip6/cmor-tables` | `isSpecializationOfVariable` | `variables/cf/*` | 1 of 928 | 1 |

Two groups dominate:
- **2,202 CORDEX output datasets** that the UKCP18 derivations refer to as outputs and components
  but that are never described.
- **296 undefined variables.**

### Undefined variables

[cckg-variables.md](cckg-variables.md) analyses why each of the 296 variables is undefined, against
the CMIP5, CMIP6 and CORDEX CMOR tables, the CF standard-name table and the UKCP18 documentation.
CCKG defines exactly the variables of the CMIP6 CMOR tables (1,271), while the datasets come from
projects with other vocabularies:

| cause | variables |
|---|---|
| CMIP5 or CORDEX variable, not in CMIP6 (e.g. `sic`, `tro3`, `ua850`, `sund`) | 173 |
| level or product variant of a defined variable (e.g. `ta975`, `tasmax-bc`) | 34 |
| CF name under `variables/mip/`, synonym, coordinate, table entry name, typo (`mrso%20`, `var__`) | 33 |
| UKCP18 variable (e.g. `tasAnom`, `pr1day`, `naodjf`, `wtype8`) | 18 |
| not found (model-specific CORDEX and CMIP5 output) | 38 |

The 114.6k nodes flagged by the descriptive tools (below) are the datasets that refer to these
variables.

## Running the tools

| run | `none` | `subclass` | `rdfs` |
|---|---|---|---|
| sheXer (file) | 2.5 min, 1.6 GB | 5.9 min, 3.5 GB | 10.8 min, 5.3 GB |
| sheXer (endpoint) | 47 min, 7.7 GB | – | – |
| QSE, full | 1.1 min, 2.7 GB | 1.6 min, 5.9 GB | 3.1 min, 7.9 GB |
| QSE, pruned (confidence ≥ 0.1, support ≥ 100) | 1.0 min, 2.8 GB | 1.7 min, 5.9 GB | 2.9 min, 7.1 GB |
| SHACLGEN | 43 min, 6.0 GB | timeout (115 min) | out of memory (12 GB) |
| SHACL Play! (file) | 3.5 min, 3.4 GB | 71 min, 5.3 GB | RDFS_SP |
| SHACL Play! (endpoint) | 3.3 min, 0.2 GB (+ Fuseki) | – | – |
| LinkML schema-automator | 13.6 min, 7.2 GB | out of memory (12 GB) | out of memory (12 GB) |

Endpoint runs were made under `none` only. Under the other regimes the endpoint would serve the
materialised data, and sheXer's endpoint mode, at about 300 queries per second, already takes 47
minutes on the asserted data.

What it takes to run the tools on CCKG (patches and wrappers in `tools/`):

- **sheXer:** its N-Triples reader looked for `"geo:"` anywhere in a literal and crashed on
  unusual datatype IRIs. [`tools/shexer/literal-datatype.patch`](../tools/shexer/literal-datatype.patch)
  makes it inspect only the datatype. Its endpoint mode sends one query per node and skips
  blank-node instances (`FILTER(!isBlank(?s))`), so it misses the OWL class expressions that file
  mode includes.
- **SHACLGEN** loads the graph with rdflib in a few minutes, then runs its SPARQL queries per
  property over rdflib. That phase takes most of its 43 minutes under `none`, and does not finish
  in 115 minutes under `subclass`. The wrapper mints shape names from the whole IRI when a predicate has no local name.
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

| run | node / property shapes | nodes flagged (of 595,920) | violations | violations per node |
|---|---|---|---|---|
| SHACL Play! (file and endpoint) | 49 / 228 | 114,585 (19.2%) | 298,318 | 0.50 |
| SHACLGEN | 60 / 90 | 114,613 (19.2%) | 298,346 | 0.50 |
| sheXer (file) | 60 / 408 | 589,732 (99.0%) | 2,911,715 | 4.89 |
| sheXer (endpoint) | 59 / 404 | 589,902 (99.0%) | 2,912,216 | 4.89 |
| QSE, pruned | 21 / 119 | 586,035 (98.3%) | 3,560,890 | 5.98 |
| QSE, full | 60 / 363 | 590,338 (99.1%) | 4,600,222 | 7.72 |
| schema-automator | 60 / 423 | 595,920 (100%) | 9,844,910 | 16.52 |

**The descriptive tools flag real problems.** SHACL Play and SHACLGEN flag practically the same
114.6k nodes. Almost all of their violations are `sh:class data:Variable` on
`holdsSpecializationOfVariable` and `isSpecializationOfVariable` (289k), whose values are the
undefined variables described above. The rest are `sh:or` violations on `hasOutput` and
`hasComponent`, from the undescribed CORDEX outputs.

**The other tools emit constraints that the data contradicts:**
- **QSE** emits `sh:maxCount 1` on `data:dependsOnVariable` for `SingleProjection`, although
  510,330 of the 514,792 projections have two values. It only ever emits `minCount 1` and `maxCount 1`, and its `sh:node`
  references pass each failure on to every node that points to a failing node: 3.2M of its 4.6M
  violations are `sh:node` violations. Pruning by confidence and support does not remove these
  constraints.
- **sheXer** turns each `rdf:type` value into its own property shape (`sh:in ( C )`,
  `maxCount 1`), which fails on every node with several types: 2.7M of its 2.9M violations.
- **schema-automator** checks IRIs as `xsd:string` literals, builds `sh:in` lists from samples of
  the values, and closes every shape, so it rejects every node.

### Regime `subclass` (plus `rdf:type` along the subclass closure)

| run | node / property shapes | (class, property) pairs, of which also on a superclass | nodes flagged | violations per node |
|---|---|---|---|---|
| SHACL Play! | 82 / 672 | 672, 611 (91%) | 114,585 (19.2%) | 2.67 |
| sheXer | 93 / 1,876 | 747, 611 (82%) | 100% (sample of 11.8k) | 2,499 |
| QSE, pruned | 47 / 284 | 241, 199 (83%) | 100% (sample of 52.3k) | 103 |
| QSE, full | 92 / 833 | 748, 612 (82%) | 100% (sample of 13.3k) | 109 |
| SHACLGEN | timeout | | | |
| schema-automator | out of memory | | | |

- **Shapes for abstract classes appear.** Classes such as `ccso:Projection` and `top-level:Entity`
  get shapes learned from all their members.
- **Redundancy grows.** 82–91% of the constrained (class, property) pairs repeat a pair constrained
  on a superclass, against 27–48% under `none`. Factoring (below) removes it.
- **SHACL Play flags the same 114,585 nodes as under `none`,** but each problem is reported once
  per superclass shape that repeats the constraint: 1.59M violations instead of 298k.
- **sheXer's per-type `rdf:type` shapes multiply.** A projection has about 10 types, and each
  `rdf:type sh:in ( C )` shape rejects the other 9, on each of the node shapes that target the node.

### Regime `rdfs` (full RDFS closure)

The data grow to 11.9M triples. Besides 1.2M `rdf:type` triples from domains, ranges and the
subclass closure, the closure adds the superproperties of the data properties: 572k
`holdsSpecializationOfVariable` and 572k `derivedFromVariable` triples, 294k `hasPart` and
`hasProperPart`, and 107k `isDescribedBy`.

| run | node / property shapes | (class, property) pairs, of which also on a superclass | nodes flagged | violations per node |
|---|---|---|---|---|
RDFS_SP_ROW| sheXer | 95 / 2,329 | 1,144, 982 (86%) | 100% (sample of 749) | 3,509 |
| QSE, pruned | 49 / 474 | 436, 378 (87%) | 100% (sample of 10.9k) | 158 |
| QSE, full | 94 / 1,225 | 1,145, 983 (86%) | 100% (sample of 1.5k) | 175 |
| SHACLGEN, schema-automator | out of memory | | | |

- **Domain and range inference hides the undefined variables.** The variables of the previous
  section are values of properties whose `rdfs:range` is `data:Variable`, so under RDFS they are
  typed as `Variable`, and a constraint `sh:class data:Variable` holds by construction. Inference
  on domains and ranges makes the data conform wherever a constraint matches a declared range,
  which is exactly where the discovered shapes would otherwise detect errors.
- **Shapes describe the inferred superproperties too**, which adds property shapes: sheXer's grow
  from 1,876 to 2,329.
- **Validation slows down for `sh:node`-heavy shapes.** `sh:node` checks traverse the inferred links
  as well: in 10 minutes, sheXer's shapes were validated on 749 nodes, against 11.8k under
  `subclass`.
RDFS_SP_NOTE

## Factoring along the class hierarchy

Under `subclass` and `rdfs`, every run is also factored along the class hierarchy
([factoring.md](factoring.md)): constraints implied by a superclass's shape are removed. The
factored shapes are validated on the same focus nodes as the originals. They must flag the same
nodes, since factoring is proven to preserve which (node, property) pairs are violated.

| regime | run | constraints removed | property shapes | node shapes | nodes flagged (original = factored) | violations | validation time |
|---|---|---|---|---|---|---|---|
| `subclass` | SHACL Play | 1,629 of 2,039 (80%) | 672 → 220 | 82 → 65 | 114,585 (all nodes) | 1,591,075 → 185,370 (−88%) | 1,746 s → 945 s |
| `subclass` | sheXer | 2,709 of 4,444 (61%) | 1,876 → 817 | 93 → 72 | 11,778 (sample) | 29.4M → 17.5M (−41%) | 600 s → 274 s |
| `subclass` | QSE, full | 800 of 1,807 (44%) | 833 → 510 | 92 | 13,338 (sample) | 1,451,046 → 1,205,954 (−17%) | 600 s → 411 s |
| `subclass` | QSE, pruned | 288 of 580 (50%) | 284 → 165 | 47 | 52,267 (sample) | 5,365,764 → 4,465,919 (−17%) | 600 s → 384 s |
| `rdfs` | sheXer | 2,996 of 5,138 (58%) | 2,329 → 1,104 | 95 → 73 | 749 (sample) | 2,628,408 → 1,541,587 (−41%) | 747 s → 139 s |
| `rdfs` | QSE, full | 1,224 of 2,573 (48%) | 1,225 → 712 | 94 | 1,509 (sample) | 264,573 → 212,848 (−20%) | 612 s → 370 s |
| `rdfs` | QSE, pruned | 467 of 892 (52%) | 474 → 256 | 49 | 10,905 (sample) | 1,725,612 → 1,265,748 (−27%) | 600 s → 251 s |
RDFS_SP_FACTORING
In every run the factored shapes flag exactly the same nodes. For SHACL Play under `subclass`,
which was validated on the whole KG, the sets of (node, property) pairs with violations were also
compared and are identical (114,709 pairs). This comparison first found 5 nodes flagged only by
the factored shapes, the half-degree global warming levels (`GWLs/GWL1.5` … `GWL5.5`). The cause was
not factoring itself: rdflib had rewritten the literal `"1.5e0"^^xsd:double` in an `sh:in` list as
`1.5e+00`, a different RDF term. `factor.py` now keeps every literal term unchanged, and a test
checks it ([factoring.md](factoring.md#6-testing)).

## Tool bugs found (to report upstream)

| tool | bug |
|---|---|
| sheXer 2.7.3.1 | SHACL output uses `sh:dataType` (not a SHACL term), so every datatype constraint is lost. The literal datatype is detected by searching the whole literal. In endpoint mode `geo:asWKT` gets `xsd:string` where file mode reports the real datatype. |
| QSE (`4bcfb04`) | `sh:NodeKind` is used as a predicate instead of `sh:nodeKind`. Literals with an unusual datatype IRI are read as IRIs, with a URL-encoded class invented for them. `minCount 1` and `maxCount 1` are contradicted by the data. |
| SHACL Play! (`4e85078`) | SELECT queries ignore their variable bindings (patched here). When a query fails, it logs the error and exits 0 with an empty shapes file. |
| SHACLGEN 3.0.0b4 | Console script crashes on start-up. Crashes on property IRIs without a local name. |
| schema-automator 0.5.7 | Crashes on TSV cells over 128 KiB. Global slot definitions depend on triple order. |

## Next steps

1. **Define the missing variables and outputs.** Import the CMIP5 and CORDEX tables, define the
   UKCP18 and derived variables as specializations of CMIP6 ones, fix the IRIs in the wrong form
   ([cckg-variables.md](cckg-variables.md)), and describe the 2,202 CORDEX output datasets.
2. **Reference shapes for CCKG.** The evaluation has no ground truth yet. Reference shapes should
   state their regime (`reference_regime` in `kg.json`, ideally `sh:entailment` in the shapes
   graph). A starting point: SHACL Play's factored `subclass` shapes plus sheXer's cardinalities.
3. Report the tool bugs upstream. Look into QSE's cardinality extraction and its query-based mode.

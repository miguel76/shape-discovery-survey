# CCKG run: findings

Phase 1 of the survey runs every tool on the
[Climate Change Knowledge Graph](https://hacid-project.github.io/cckg/). The numbers are in
[`results/cckg/summary.md`](../results/cckg/summary.md), with a per-run `eval.json` in each run
directory. To reproduce:

```sh
make install
make run evaluate KG=cckg INFERENCE=none RUN_ARGS="--endpoint --local-endpoint"
make run evaluate KG=cckg INFERENCE=subclass RUN_ARGS="--endpoint --local-endpoint"
VALIDATION_BUDGET=1800 make run evaluate KG=cckg INFERENCE=rdfs RUN_ARGS=
```

The `subclass` and `rdfs` evaluations here used a 30-minute validation budget per set of shapes.

## Input

- **Dump:** [`data/cckg/cckg_2026-09-24_10-44-07.nq.gz`](../data/cckg): 4,731,803 quads in 15 named
  graphs. The ontology modules (`onto/*`) are included next to the data graphs (`data/cs/*`).
- **What the tools see:** the pipeline merges all graphs into one, giving 4,730,998 distinct triples.
  Of the 651,579 subjects, 594,982 are typed. There are 59 classes, including 12 OWL/RDFS
  vocabulary classes coming from the ontology graphs.
- **Endpoint:** the public endpoint (`https://w3id.org/hacid/cs/sparql`) is not reachable from
  this sandbox (egress policy). The endpoint runs therefore use a local Fuseki serving the dump
  from a TDB2 store (`--local-endpoint`).

## Execution (regime `none`)

| run | status | wall time | peak RSS | node / property shapes |
|---|---|---|---|---|
| sheXer (file) | ✅ after patch | 1.5 min | 1.6 GB | 59 / 425 |
| sheXer (endpoint) | ✅ after patch | 38 min | 7.7 GB | 58 / 419 |
| QSE, full output | ✅ | 33 s | 2.6 GB | 59 / 375 |
| QSE, pruned (confidence ≥ 0.1, support ≥ 100) | ✅ | 36 s | 2.3 GB | 21 / 124 |
| SHACLGEN | ✅ after wrapper fix | 38 min | 6.1 GB | 59 / 92 |
| SHACL Play! (file) | ✅ | 2.8 min | 2.8 GB | 47 / 238 |
| SHACL Play! (endpoint) | ✅ | 3.2 min | 0.25 GB (+ Fuseki) | 47 / 238 |
| LinkML schema-automator | ✅ after wrapper fix | 11 min | 7.4 GB | 59 / 434 |

What it took to get there:

- **sheXer** crashed after 100 s on the literals typed `<geo:wktLiteral>` (see data defect D1).
  Its N-Triples reader looks for `"geo:"` anywhere in a literal and turned the datatype into
  `…geosparql#wktLiteral>`, keeping the `>`. [`tools/shexer/literal-datatype.patch`](../tools/shexer/literal-datatype.patch)
  makes it inspect only the datatype. The patch leaves the toy output unchanged.
- **sheXer's endpoint mode** sends one `SELECT ?p ?o WHERE { <node> ?p ?o }` per node: about 300
  queries/s, 38 minutes in total. It excludes blank-node instances
  (`FILTER(!isBlank(?s))`), so it misses `owl:Restriction` and the OWL class expressions, which
  file mode includes.
- **SHACLGEN** loads the graph with rdflib in about 4 minutes. It then runs its SPARQL queries per
  property over rdflib, which took 34 minutes. On the first attempt it crashed during that phase
  because a predicate IRI has no local name (D2): it mints shape IRIs from `prefix_localname`. The
  wrapper now falls back to a label derived from the whole IRI.
- **schema-automator** crashed on a TSV cell larger than Python's default `csv` field limit
  (128 KiB). The wrapper raises the limit. Its intermediate tables (140 MB for `SingleProjection`
  alone) now go to a temporary directory.
- **Fuseki:** with an in-memory dataset, its resident memory grew from 4 GB to over 12 GB under
  sheXer's query load, and the process was OOM-killed. The local endpoint now uses TDB2 (about 1.7 GB).
- **Evaluation:** pySHACL cannot handle 4.7M triples in reasonable time, and a whole-graph Jena
  report ran out of an 8 GB heap on the LinkML shapes (20M violations). Validation now runs node by
  node with aggregated counts ([`pipeline/ShaclStats.java`](../pipeline/ShaclStats.java)). Each full
  pass takes 1–40 minutes per set of shapes. The slowest is QSE, whose `sh:node` chains re-validate
  shared neighbours for every node that points to them.

## Validating CCKG against the extracted shapes

No reference shapes exist for CCKG yet, so the evaluation is limited to the checks listed below.

**A correction to the first version of this document.** The first version reported that almost
every node violates the shapes extracted from it, and it blamed mostly "subclass reach". That was
an inconsistency in the pipeline, not a property of the tools. Discovery used only the asserted
types, but validation ran on a data graph that contains the ontology's `rdfs:subClassOf` triples,
which SHACL Core follows for `sh:targetClass` and `sh:class`. The pipeline now applies one
*inference regime* to both phases (see [inference.md](inference.md)). The figures below are for the
coherent regimes. [`results/cckg/summary.md`](../results/cckg/summary.md) has them side by side.

### Regime `none` (asserted triples only)

| run | nodes flagged | violations | violations per node |
|---|---|---|---|
| SHACL Play! (file and endpoint) | 114,559 (19.3%) | 295,607 | 0.50 |
| SHACLGEN | 114,577 (19.3%) | 295,625 | 0.50 |
| sheXer (file and endpoint) | 589,829 (99.1%) | 2,762,556 | 4.64 |
| QSE, pruned | 586,034 (98.6%) | 3,613,203 | 6.08 |
| QSE, full | 592,357 (99.6%) | 6,214,119 | 10.44 |
| schema-automator | 594,980 (100%) | 9,077,179 | 15.26 |

Two different pictures remain:

**1. Descriptive tools flag the same, real problems.** SHACL Play and SHACLGEN flag practically the
same 114.6k nodes. Almost all of their violations are `sh:class Variable` on the three
variable-specialization properties, and the flagged values are undefined variables (D4). Two tools
with quite different algorithms flagging the same nodes is a useful signal that the problem is in
the data.

**2. Tool-specific constraints that the data contradicts:**
- **QSE** emits `sh:maxCount 1` on `data:dependsOnVariable` for `SingleProjection`, although
  568,858 subjects have exactly 2 values. It only ever emits `minCount 1` and `maxCount 1`, and in
  the full output it adds `minCount 1` even to constraints with confidence 0.0001 (50 of 514,792
  instances). Its `sh:node` references, which sit outside the `sh:or` of alternative classes,
  pass these failures on to every node that points to a failing node. Pruning halves the count but
  does not remove these constraints. The toy KG showed the same pattern. The root cause in
  `ShapesExtractor` has not been traced yet.
- **sheXer** turns each `rdf:type` value into its own property shape (`sh:in ( C )`,
  `maxCount 1`), which fails on every node with several types, for example a `SingleProjection`
  that is also a `ScenarioBasedProjection`. This accounts for 2.2M of its 2.8M violations.
- **schema-automator** checks IRIs as `xsd:string` literals, adds `sh:closed`, and builds `sh:in`
  lists from table samples, so it rejects every node.

### Regime `subclass` (plus `rdf:type` along the subclass closure)

The data grows from 4.7M to 9.5M triples. Where validation hit its 30-minute budget, the rates are
over a random sample of focus nodes.

| run | node / property shapes | (class, property) pairs, of which also on a superclass | nodes flagged | violations per node |
|---|---|---|---|---|
| SHACL Play! (file and endpoint) | 77 / 710 | 710, 644 (91%) | 19.3% | 2.64 |
| SHACLGEN | 89 / 92 | 788, 644 (82%) | 19.3% | 2.64 |
| sheXer (file) | 89 / 1,788 | 788, 644 (82%) | 100% (sample of 88k) | 2,357 |
| QSE, pruned | 45 / 290 | 249, 198 (80%) | 100% (sample of 301k) | 103 |
| QSE, full | 88 / 870 | 788, 644 (82%) | 100% (sample of 94k) | 143 |
| sheXer (endpoint), schema-automator | out of memory | | | |

- **Shapes for abstract classes appear.** The ~30 abstract classes, such as `ccso:Projection`
  and `top-level:Entity`, now have shapes learned from all their members. For example, sheXer's
  `Dataset` shape describes 573k datasets (13 properties, none required) instead of 2 (2 properties,
  both required).
- **Redundancy grows.** The share of pairs that repeat a superclass constraint rises from about
  30–40% to 80–91%.
- **The descriptive tools flag the same nodes as under `none`,** but each problem is now reported
  about 5 times, once per superclass shape that repeats the constraint.
- **sheXer's per-type `rdf:type` shapes explode.** A `SingleProjection` carries about 10 types, and
  each `rdf:type sh:in ( C )` shape rejects the other 9, on each of the ~10 node shapes that target
  the node: 184M `sh:in` and 23M `maxCount` violations on `rdf:type`.

### Regime `rdfs` (full RDFS closure)

The data grows to 15.1M triples. Most of the growth is subproperty triples (3.15M
`top-level:associatedWith`, 424k `data:derivedFromVariable`, 166k `hasPart`/`hasProperPart`) and
domain/range typing. Discovery ran on the file only.

| run | node / property shapes | (class, property) pairs, of which also on a superclass | nodes flagged | violations per node |
|---|---|---|---|---|
| SHACL Play! | 79 / 1,040 | 1,040, 960 (92%) | **0%** of 654,288 | 0 |
| sheXer | 92 / 2,173 | 1,118, 960 (86%) | 100% (sample of 2.5k) | 2,982 |
| QSE, pruned | 47 / 444 | 401, 342 (85%) | 91.6% (sample of 14k) | 178 |
| QSE, full | 91 / 1,202 | 1,118, 960 (86%) | 100% (sample of 11k) | 187 |
| SHACLGEN, schema-automator | out of memory | | | |

- **SHACL Play's shapes find no violations at all, because the inference hides D4.** The 287
  undefined variables are values of properties whose `rdfs:range` is `data:Variable`. Under RDFS
  they are therefore typed as `Variable`, and `sh:class data:Variable` passes. Inference based on
  domains and ranges makes the data conform by construction wherever a constraint matches a
  declared range, which is exactly where discovered shapes would otherwise detect errors.
- **Shapes describe the ontology's inferred properties too.** `Dataset` now has 19 constrained
  properties, including superproperties such as `top-level:associatedWith`.
- **Validation cost explodes for `sh:node`-heavy shapes.** `sh:node` checks now traverse millions
  of inferred `associatedWith` links. sheXer's shapes validated only 2.5k nodes in 30 minutes.

## Data defects found in CCKG

These defects came to light while running and debugging the tools. The counts come from the dump.

| # | defect | where | size | surfaced by |
|---|---|---|---|---|
| D1 | Literal datatype written as the IRI `<geo:wktLiteral>` instead of `geo:wktLiteral` expanded (`http://www.opengis.net/ont/geosparql#wktLiteral`). `geo:` is a registered URI scheme, so the IRI is valid, but it is not the GeoSPARQL datatype. | `geo:asWKT` values in the `cordex/cvs` graph (102) and the `cs` graph (1) | 103 literals | sheXer crash. sheXer and SHACL Play then report `sh:datatype <geo:wktLiteral>`. QSE reads the literal as an IRI and invents `sh:class <%3Cgeo:wktLiteral%3E>`. |
| D2 | Broken UKCP18 conversion. For each probabilistic projection there is an orphan blank node (no type, never referenced) carrying `<…/data/cs/variables/mip/>` as a **predicate** with the variable name as a literal (`"tasAnom"`), plus `ccso:refersToScenario` pointing to a local file IRI (`file:///Users/miguel/git/climate-services-kg/data-sources/ukcp18/rdf/rcp60`). None of the `ccso:ProbabilisticProjection`s has a `refersToScenario`. | `ukcp18` graph | 56,448 blank nodes, one per `ProbabilisticProjection` | SHACLGEN crash (predicate without a local name) |
| D3 | Relative IRIs resolved against the converter's local path (`file:///Users/miguel/…/ukcp18/rdf/…`), in `refersToScenario` (56,448), `hasOutput` and `hasPart` (2,869 each), `hasStart/EndDateTime` (1,836 each), `refersToGlobalWarmingLevel` (1,520) and a few more. D2's `file://` values are a subset of these. | `ukcp18` graph | 67,402 triples | found while investigating D2 |
| D4 | Dangling references: variables used as values of `data:holdsSpecializationOfVariable`, `data:isSpecializationOfVariable` or `data:iSpecializationOfVariable` but never defined or typed. 281 are MIP variables (e.g. `variables/mip/rv850`) and 6 are CF standard names (e.g. `variables/cf/atmosphere_relative_vorticity`, referenced from the CMOR tables). | referenced from the CMOR tables and the datasets | 287 IRIs, about 290k violations | `sh:class` violations in SHACL Play and SHACLGEN |
| D5 | Misspelled property `data:iSpecializationOfVariable` (the ontology declares `data:isSpecializationOfVariable`). | all of `cordex-cmip5/datasets` (`ukcp18` uses the right IRI) | 145,461 triples | validation breakdown by property path |
| D6 | HACID properties used but not declared in the dump's ontology graphs: `ccso:outputId` (3,014), `data:hasSelectedRegion` (2,230), `ccso:simulationConfigurationId` (641), `ccso:experimentId` (93), `top-level:hasExpectedType` (65), `top-level:altLabel` (42). These may just be missing from the ontology. | several graphs | 6,085 triples | cross-check of predicates against the ontology |
| D7 | `data:hasStartDateTime` and `data:hasEndDateTime` declare `rdfs:range xsd:datetime` (lower-case t, not an XSD datatype; the intended IRI is `xsd:dateTime`), and `xsd:datetime` is declared an `owl:Class`. | `onto/data` graph | 3 axioms; 686 literal values are affected (the other 3,670 values of these properties are `file://` IRIs, see D3) | the RDFS closure: the range rule types their literal values with `xsd:datetime` |

CCKG types most nodes only with their most specific class, while a few nodes are typed explicitly
with very generic classes (2 `data:Dataset`s, 48 `top-level:Concept`s). This is a modelling choice
rather than a defect, but it decides how any SHACL shapes for CCKG behave. With the ontology in the
data graph, SHACL applies a `Dataset` shape to 573,450 nodes. Without it, the shape applies to 2.

## Tool bugs found (to report upstream)

| tool | bug |
|---|---|
| sheXer 2.7.3.1 | SHACL output uses `sh:dataType` (not a SHACL term), so every datatype constraint is lost. The literal datatype is detected by searching the whole literal (D1 crash). In endpoint mode `geo:asWKT` gets `xsd:string` where file mode reports the real datatype. |
| QSE (`4bcfb04`) | `sh:NodeKind` is used as a predicate instead of `sh:nodeKind`. Literals with an unusual datatype IRI are read as IRIs, with a URL-encoded class invented for them. `minCount 1` and `maxCount 1` are contradicted by the data. |
| SHACL Play! (`4e85078`) | SELECT queries ignore their variable bindings (patched here). When a query fails, it logs the error and exits 0 with an empty shapes file. |
| SHACLGEN 3.0.0b4 | Console script crashes on start-up. Crashes on property IRIs without a local name. |
| schema-automator 0.5.7 | Crashes on TSV cells over 128 KiB. Global slot definitions depend on triple order. |

## Next steps

1. **Reference shapes for CCKG.** The evaluation has no ground truth yet. The reference shapes
   should state the regime they are written for (`reference_regime` in `kg.json`, ideally also
   `sh:entailment` in the shapes graph). `subclass` is the natural choice if shapes are meant to be
   written at the level of abstract classes. A useful starting point is SHACL Play's `subclass`
   shapes with the constraints each class inherits from its superclasses removed, plus sheXer's
   cardinalities.
2. **Fix or report the data defects D1–D6** in the CCKG build.
3. **Factor discovered shapes along the class hierarchy** (drop constraints already stated on a
   superclass). None of the tools does this, and it is what would turn inference into less
   redundancy rather than more (see [inference.md](inference.md)).
4. Report the tool bugs upstream. Look into QSE's cardinality extraction and its query-based mode.

# CCKG run: findings

Phase 1 of the survey runs every tool on the
[Climate Change Knowledge Graph](https://hacid-project.github.io/cckg/). The numbers are in
[`results/cckg/summary.md`](../results/cckg/summary.md), with a per-run `eval.json` in each run
directory. To reproduce:

```sh
make install
make run evaluate KG=cckg RUN_ARGS="--endpoint --local-endpoint"
```

## Input

- **Dump:** [`data/cckg/cckg_2026-09-24_10-44-07.nq.gz`](../data/cckg): 4,731,803 quads in 15 named
  graphs. The ontology modules (`onto/*`) are included next to the data graphs (`data/cs/*`).
- **What the tools see:** the pipeline merges all graphs into one, giving 4,730,998 distinct triples.
  Of the 651,579 subjects, 594,982 are typed. There are 59 classes, including 12 OWL/RDFS
  vocabulary classes coming from the ontology graphs.
- **Endpoint:** the public endpoint (`https://w3id.org/hacid/cs/sparql`) is not reachable from
  this sandbox (egress policy). The endpoint runs therefore use a local Fuseki serving the dump
  from a TDB2 store (`--local-endpoint`).

## Execution

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

| run | violations (SHACL semantics) | nodes flagged | violations (explicit typing) | nodes flagged |
|---|---|---|---|---|
| sheXer | 7,854,479 | 592,474 | 2,762,556 | 589,829 |
| QSE, full | 13,085,660 | 592,454 | 6,214,119 | 592,357 |
| QSE, pruned | 6,837,851 | 589,597 | 3,613,203 | 586,034 |
| SHACLGEN | 366,302 | 114,577 | 295,625 | 114,577 |
| SHACL Play! | 4,016,867 | 586,920 | **295,607** | **114,559** |
| schema-automator | 20,113,053 | 594,982 | 9,077,179 | 594,980 |

Endpoint runs give the same numbers as file runs, except for a handful of sheXer nodes. Out of 595k
typed nodes, almost every one violates the shapes that were extracted from it. Three causes explain
most of this.

**1. Subclass reach (all tools).** CCKG types most nodes only with their most specific class. A
few explicitly typed nodes belong to very generic classes that sit at the top of the hierarchy:

| class | explicit instances | additional instances through `rdfs:subClassOf` |
|---|---|---|
| `top-level:Concept` | 48 | +586,784 |
| `data:Variable` | 6,143 | +578,132 |
| `data:Dataset` | 2 | +573,448 |
| `data:DataGeneratingProcess` | 2 | +4,991 |

Every tool learns a class's shape from its explicitly typed instances. SHACL's `sh:targetClass`
then applies that shape to every instance of every subclass, because the ontology's
`rdfs:subClassOf` triples are part of the data graph. For example, a `Dataset` shape learned from 2
nodes, with `minCount 1` on `rdfs:comment` and `isMemberOf`, is applied to 573k projections. The
"explicit typing" column removes the `rdfs:subClassOf` triples, so each shape is checked only on the
nodes it was learned from.

This variant has a side effect: `sh:class C` then also rejects values typed only with a subclass
of `C`. For SHACL Play and SHACLGEN that affects only a handful of values (for example 7
`DependentVariable`s). Their `sh:class` violations on the three variable-specialization properties
all come from untyped values, i.e. the dangling references in D4.

**2. Tool-specific constraints that the data contradicts** (these remain under explicit typing):
- **QSE** emits `sh:maxCount 1` on `data:dependsOnVariable` for `SingleProjection`, although
  568,858 subjects have exactly 2 values. It only ever emits `minCount 1` and `maxCount 1`, and in
  the full output it adds `minCount 1` even to constraints with confidence 0.0001 (50 of 514,792
  instances). Its `sh:node` references, which sit outside the `sh:or` of alternative classes,
  pass these failures on to every node that points to a failing node. Pruning halves the count but
  does not remove these constraints. The toy KG showed the same pattern. The root cause in
  `ShapesExtractor` has not been traced yet.
- **sheXer** turns each `rdf:type` value into its own property shape (`sh:in ( C )`,
  `maxCount 1`), which fails on nodes with several types. Examples are a `SingleProjection` that is
  also a `ScenarioBasedProjection`, and QSE's `rdf:type` `sh:in` likewise. This accounts for 2.2M
  of its 2.8M explicit-typing violations.
- **schema-automator** checks IRIs as `xsd:string` literals, adds `sh:closed`, and builds `sh:in`
  lists from table samples, so it rejects every node.

**3. Real problems in the data.** SHACL Play and SHACLGEN are the closest to descriptive: they
flag 114.6k nodes under explicit typing. The largest group of their remaining violations is
`sh:class Variable` on the variable-specialization properties, and the flagged values are
undefined variables (D4). Two tools with quite different algorithms flagging the same nodes is a
useful signal that the problem is in the data.

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

The distribution of explicit types described under cause 1 (a few instances of the generic
classes, most nodes typed only with a leaf class) is a modelling choice rather than a defect. It
does decide how any SHACL shapes for CCKG will behave: it matters whether they are meant to be
validated with the ontology in the data graph.

## Tool bugs found (to report upstream)

| tool | bug |
|---|---|
| sheXer 2.7.3.1 | SHACL output uses `sh:dataType` (not a SHACL term), so every datatype constraint is lost. The literal datatype is detected by searching the whole literal (D1 crash). In endpoint mode `geo:asWKT` gets `xsd:string` where file mode reports the real datatype. |
| QSE (`4bcfb04`) | `sh:NodeKind` is used as a predicate instead of `sh:nodeKind`. Literals with an unusual datatype IRI are read as IRIs, with a URL-encoded class invented for them. `minCount 1` and `maxCount 1` are contradicted by the data. |
| SHACL Play! (`4e85078`) | SELECT queries ignore their variable bindings (patched here). When a query fails, it logs the error and exits 0 with an empty shapes file. |
| SHACLGEN 3.0.0b4 | Console script crashes on start-up. Crashes on property IRIs without a local name. |
| schema-automator 0.5.7 | Crashes on TSV cells over 128 KiB. Global slot definitions depend on triple order. |

## Next steps

1. **Reference shapes for CCKG.** The evaluation has no ground truth yet. A useful starting point
   is SHACL Play's shapes intersected with sheXer's cardinalities. Decide whether the shapes
   should be validated with the ontology in the data graph (cause 1).
2. **Fix or report the data defects D1–D6** in the CCKG build.
3. **An extraction variant on RDFS-materialised data**, so that tools learn from inferred types
   and generic-class shapes describe all their instances.
4. Report the tool bugs upstream. Look into QSE's cardinality extraction and its query-based mode.

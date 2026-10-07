# CCKG change log

This file records, dump by dump, the data issues that the survey found in CCKG and how they were
fixed. [cckg-findings.md](cckg-findings.md) describes the latest evaluation only.

The checks are those of [`pipeline/kg_checks.py`](../pipeline/kg_checks.py), which generalises the
defects D1–D7 of the first dump. Since the 2026-10-07 dump, dangling links are also broken down by
source graph with [`pipeline/link_sources.py`](../pipeline/link_sources.py). Reports per dump:

| dump | distinct triples | data checks |
|---|---|---|
| `cckg_2026-09-24_10-44-07` | 4,730,998 | [data-checks-2026-09-24.md](../results/cckg/data-checks-2026-09-24.md) |
| `cckg_2026-09-30_10-40-33` | 4,612,279 | [data-checks-2026-09-30.md](../results/cckg/data-checks-2026-09-30.md) |
| `cckg_2026-10-07_10-04-53` | 4,612,318 | [data-checks.md](../results/cckg/data-checks.md), [dangling-by-source.md](../results/cckg/dangling-by-source.md) |

## Status of the issues

| # | issue | 2026-09-24 | 2026-09-30 | 2026-10-07 |
|---|---|---|---|---|
| D1 | literal datatype `<geo:wktLiteral>` | 103 | 0 ✅ | 0 |
| D2 | `…/variables/mip/` used as a predicate, on orphan blank nodes | 56,448 | 0 ✅ | 0 |
| D3 | `file:///Users/…` IRIs | 67,402 triples | 0 ✅ | 0 |
| D4 | undefined variables as values of the specialization properties | 287 (281 MIP, 6 CF) | 282 (281 MIP, 1 CF) | 282 (281 MIP, 1 CF) |
| D5 | misspelled `data:iSpecializationOfVariable` | 145,461 | 0 ✅ | 0 |
| D6 | undeclared HACID properties | 6,085 triples | 0 ✅ | 0 |
| D7 | `rdfs:range xsd:datetime` | 2 axioms | 0 ✅ | 0 |
| D8 | SRES A1B outputs without scenario, possibly duplicated | – | 2 | 0 ✅ |
| D9 | other dangling links (targets with no `rdf:type`) | 5,924 values | 5,913 values | 4,473 values |

D9 counts the untyped values of properties with a declared class range, other than those of D4,
summed over properties (a target linked by two properties counts twice). Its breakdown is below.

## Dump of 2026-09-24 (first dump)

The defects came to light while running and debugging the tools.

| # | defect | where | size | surfaced by |
|---|---|---|---|---|
| D1 | Literal datatype written as the IRI `<geo:wktLiteral>` instead of `geo:wktLiteral` expanded (`http://www.opengis.net/ont/geosparql#wktLiteral`). `geo:` is a registered URI scheme, so the IRI is valid, but it is not the GeoSPARQL datatype. | `geo:asWKT` values in the `cordex/cvs` graph (102) and the `cs` graph (1) | 103 literals | sheXer crash. sheXer and SHACL Play then report `sh:datatype <geo:wktLiteral>`. QSE reads the literal as an IRI and invents `sh:class <%3Cgeo:wktLiteral%3E>`. |
| D2 | Broken UKCP18 conversion. For each probabilistic projection there is an orphan blank node (no type, never referenced) carrying `<…/data/cs/variables/mip/>` as a **predicate** with the variable name as a literal (`"tasAnom"`), plus `ccso:refersToScenario` pointing to a local file IRI. None of the `ccso:ProbabilisticProjection`s has a `refersToScenario`. | `ukcp18` graph | 56,448 blank nodes | SHACLGEN crash (predicate without a local name) |
| D3 | Relative IRIs resolved against the converter's local path (`file:///Users/miguel/…/ukcp18/rdf/…`), in `refersToScenario` (56,448), `hasOutput` and `hasPart` (2,869 each), `hasStart/EndDateTime` (1,836 each), `refersToGlobalWarmingLevel` (1,520) and a few more. | `ukcp18` graph | 67,402 triples | found while investigating D2 |
| D4 | Variables used as values of `data:holdsSpecializationOfVariable`, `data:isSpecializationOfVariable` or `data:iSpecializationOfVariable` but never defined or typed: 281 MIP variables (e.g. `variables/mip/rv850`) and 6 CF standard names. | the CMOR tables and the datasets | 287 IRIs, about 290k violations | `sh:class` violations in SHACL Play and SHACLGEN |
| D5 | Misspelled property `data:iSpecializationOfVariable` (the ontology declares `data:isSpecializationOfVariable`). | all of `cordex-cmip5/datasets` | 145,461 triples | validation breakdown by property path |
| D6 | HACID properties used but not declared: `ccso:outputId` (3,014), `data:hasSelectedRegion` (2,230), `ccso:simulationConfigurationId` (641), `ccso:experimentId` (93), `top-level:hasExpectedType` (65), `top-level:altLabel` (42). | several graphs | 6,085 triples | cross-check of predicates against the ontology |
| D7 | `data:hasStartDateTime` and `data:hasEndDateTime` declare `rdfs:range xsd:datetime` (lower-case t, not an XSD datatype), and `xsd:datetime` is declared an `owl:Class`. | `onto/data` graph | 3 axioms, 686 literal values affected | the RDFS closure types the literals with `xsd:datetime` |

The first evaluation also had a pipeline problem, unrelated to the data: discovery used the
asserted types only, while validation ran on a data graph that includes the ontology's
`rdfs:subClassOf` triples, which SHACL follows. Almost every node was then flagged. The pipeline
now applies the same inference regime to both phases ([inference.md](inference.md)).

## Dump of 2026-09-30

Fixed D1, D2, D3, D5, D6 and D7. D4 was fixed for 5 of the 6 CF variables.

- **UKCP18 remodelling (D2).** Each derivation now has an aggregate output, typed
  `ProbabilisticProjection` or `ScenarioBasedProjection`, whose components are the datasets. The
  aggregate outputs carry `refersToScenario` or `refersToGlobalWarmingLevel`, except the two SRES
  A1B outputs (`derivations/ukcp18.prob.a1b/output` and `derivations/ukcp18.prob.sres-a1b/output`),
  which have neither and may be duplicates of each other (**D8**).
- **Dangling links (D9).** The generic check of untyped values covers every property with a class
  range, and found, besides D4:

| property | untyped values | examples |
|---|---|---|
| `data:hasOutput`, `top-level:hasComponent` | 2,893 and 2,967 | `datasets/cordex.output.EUR-11.…` (2,869), `datasets/cmip5.ACCESS1.3.rcp26.r1i1p1.output` (24) |
| `ccso:isDownscalingOf` | 22 | `simulations/cmip5.ACCESS1.3.rcp85.r1i1p1` |
| `data:derivedFromVariable` | 14 | `variables/mip/mrso%20` (trailing space) |
| `data:hasValuesOn`, `top-level:hasUnitOfMeasure` | 4 each | `unitsofmeasure/%C2%B0C%5E2` |
| `ccso:refersToGlobalWarmingLevel` | 2 | `GWLs/GWL2`, `GWLs/GWL4` |
| `data:dependsOnVariable`, `data:isSpecializedAccordingTo` | 2 each | `cordex/grids/ARC-22/ds`, `…/SAM-20/specialization` |
| `data:basedOnDimensionalSpace`, `data:hasExactBoundingRegion`, `data:hasReferencePoint` | 1 each | `…/rotated-WGS84/177.5,37.5`, `…/OSGB36/coverage` |

In the previous dump, the 2,869 CORDEX output datasets appeared as `file:` IRIs (D3) and the
`ccso:hasMemberSimulation` links had 74 untyped values, which were fixed.

## Dump of 2026-10-07

- **D8 fixed.** `derivations/ukcp18.prob.a1b/output` is gone, and
  `derivations/ukcp18.prob.sres-a1b/output` refers to the scenario `scenarios/SRES/A1B`.
- **D9 reduced.**

| property | 2026-09-30 | 2026-10-07 |
|---|---|---|
| `data:hasOutput` | 2,893 | 2,211 |
| `top-level:hasComponent` | 2,967 | 2,223 |
| `ccso:isDownscalingOf` | 22 | 21 |
| `data:derivedFromVariable` | 14 | 14 |
| `data:dependsOnVariable`, `data:isSpecializedAccordingTo` | 2 each | 2 each |
| `ccso:refersToGlobalWarmingLevel` | 2 | 0 ✅ |
| `data:hasValuesOn`, `top-level:hasUnitOfMeasure` | 4 each | 0 ✅ |
| `data:basedOnDimensionalSpace`, `data:hasExactBoundingRegion`, `data:hasReferencePoint` | 1 each | 0 ✅ |

  Of the 2,869 CORDEX output datasets linked from the `ukcp18` graph, 667 are now described and
  2,202 are still undefined. The 24 undefined CMIP5 outputs were renamed (`….output1`), and 9 of
  them are still undefined.
- **D4 unchanged** (281 MIP variables and 1 CF variable).

The remaining dangling links are described, by source, in [cckg-findings.md](cckg-findings.md).

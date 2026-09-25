# Toy KG run: findings

The run reproduces with `make install && make run evaluate KG=toy`, which uses the `none` inference
regime. The numbers are in [`results/toy/none/summary.md`](../results/toy/none/summary.md) and the
per-run `eval.json` files. [`results/toy/summary.md`](../results/toy/summary.md) compares the
three regimes (see [inference.md](inference.md)). The toy
KG ([`data/toy/toy.ttl`](../data/toy/toy.ttl), 141 triples) was built to include the typical
difficulties listed in its header. The hand-written
[reference shapes](../data/toy/reference-shapes.ttl) flag exactly 4 intended defects on 2 nodes:
`ex:sim_bad` has no model, no period, and a variable as its scenario; `ex:m_cmcc_cm2` has a string
resolution.

The toy KG is too small to measure performance. The run's purpose was to check that every tool
works end to end and to see how each one behaves.

## Pipeline status

All 5 tools produce SHACL on the file input. sheXer and SHACL Play also produce it through a local
SPARQL endpoint (Fuseki), and their endpoint results match the file results. Every run takes 0.6–11 s
and uses at most 240 MB RSS. Every output parses and passes the SHACL-SHACL meta-shapes.

## Per-tool observations

**sheXer**
- Its SHACL serialiser writes `sh:dataType` where the term is `sh:datatype`. Validators silently
  ignore the misspelled term, so none of the datatype constraints reach a SHACL validator (0/13
  datatype agreement). The ShExC output from the same run is correct.
- Class constraints are expressed as `sh:node <OtherShape>` rather than `sh:class`. That is a valid
  design, but it means the constraint checks shape conformance, not class membership.
- Each `rdf:type` value becomes its own property shape (`sh:in (C)`, `minCount 1`, `maxCount 1`).
  The SHACL output keeps `minCount 1` even where ShExC says `?` (for example, `EarthSystemModel` on
  `:ClimateModel` has a usage ratio of 0.5). On multi-typed nodes this gives 19 violations (`none` regime) on the
  tool's own input, even though sheXer's default *all-compliant* mode promises none.
- Cardinalities are the most accurate of all tools: required 20/22, functional 19/22.

**QSE (exact, full output)**
- Writes `sh:NodeKind`, the SHACL *class*, as the predicate where it should write `sh:nodeKind`. The
  node-kind constraints are therefore lost.
- Every shape carries support/confidence annotations, which make it easy to rank constraints and to
  prune them.
- In the full, unpruned output, some cardinalities contradict the data and the tool's own confidence
  values: `homepage` gets `minCount 1` at confidence 0.5, `rdfs:label` gets `maxCount 1` although
  one institution has 2 labels, and `author` gets `maxCount 1` although one simulation has 2 authors.
  Together with `sh:node` references that fail whenever the referenced node's shape fails, this
  gives 33 violations on its own input (`none` regime). This needs a closer look at the `min_cardinality`/`max_cardinality`
  options before drawing conclusions. With the default pruning thresholds (confidence 0.1, support
  100) the pruned file is empty, because every class has fewer than 100 instances.
- It uses `sh:or` for mixed value types, for example `developedBy` pointing to Institution or
  Person, and `horizontalResolutionKm` being decimal or string. That is close to the reference.

**SHACL Play! generate**
- Closest to the reference overall: pair precision 0.88, datatype 12/13, required 19/22,
  functional 19/22.
- It needed a patch: upstream, every SELECT query ignores its bindings (see
  [tools.md](tools.md)).
- Adds `sh:in` enumerations for properties with at most 3 distinct values. In the first run these
  caused its only 2 violations. The enumerations were computed from explicitly typed instances, but
  validation also applied them to `ex:m_mpi_esm` (typed only as `EarthSystemModel`) through
  SHACL's built-in `rdfs:subClassOf` semantics. That was an inconsistency in the pipeline, not in
  the tool. With the same inference regime in both phases, its shapes conform in every regime.
- Its output adds display hints (`sh:name`, `rdfs:label`, random background colours), so two runs are not
  byte-identical.

**SHACLGEN**
- Emits only `sh:class`, `sh:datatype` and `sh:nodeKind` (with `sh:or` for mixed types) and no
  cardinalities. It therefore "conforms" trivially and detects none of the defects.
- Property shapes are global per property rather than per class, so the shapes do not say which
  class uses which property.

**LinkML schema-automator → gen-shacl**
- Going through tables loses the RDF typing. IRIs become `xsd:string` literals and no `sh:class`
  constraints are produced, which gives 197 violations on its own input (`none` regime). Its shapes are also
  `sh:closed`.
- LinkML slots are global, and each slot's definition (range, `multivalued`) appears to come from
  whichever class table is processed last. The result therefore depends on the order of the input
  triples. When the pipeline switched to sorted N-Triples as the source of `data.ttl`, `rdfs:label`
  lost `multivalued` and the number of `sh:maxCount` constraints went from 34 to 39.
- It is useful mainly as a baseline, or when a LinkML schema is the goal anyway.

## Validator note

The first version of the evaluator used pySHACL and counted 72 self-validation violations for QSE.
pySHACL copies the inner results of `sh:node` checks into the top-level report, and the same result
can appear several times. For example, it reported the Person `ex:p_dan` as missing an Institution
`homepage`, and it listed the missing `homepage` of `ex:inst_ncar` 7 times. The SHACL spec expects a single `sh:NodeConstraintComponent`
result on the outer focus node. The evaluator now validates with Jena SHACL, which gives 34 on the same data, and Jena
also scales to KGs with millions of triples.

## Cross-cutting lessons for the survey

1. **Check vocabulary and well-formedness, not just syntax.** Two of the five tools emit SHACL-like
   terms that parse fine and pass SHACL-SHACL but have no effect. The evaluator now reports them as
   "non-SHACL terms".
2. **Subclass semantics.** Tools profile explicitly typed instances, but SHACL validation targets
   subclass instances too whenever `rdfs:subClassOf` triples are in the data graph. The pipeline now
   applies one inference regime to both discovery and validation (see [inference.md](inference.md)).
   The reference shapes are written for the `subclass` regime. Under `none` they flag a correct node
   (`ex:m_mpi_esm` as a `usesModel` value), so the regime has to be stated together with any set of
   shapes.
3. **Descriptive vs. prescriptive shapes.** Validating the KG against its own extracted shapes is a
   cheap signal of how faithfully a tool describes the data. Comparing the violations with the
   reference violations (the last column of the validation table) shows how useful the tool is for
   error detection. On this toy KG no tool finds more than 2 of the 4 intended defects. That is
   expected with one bad node among six: the tools either learn the defect as part of the schema or
   hide it behind an optional cardinality. Larger KGs, together with the tools' support and confidence
   thresholds, are needed to test this properly.
4. **Normalisation matters for comparison.** `sh:node` versus `sh:class`, global versus per-class
   property shapes, and `rdf:type` property shapes all affect the scores. The current metrics are
   strict. A lenient mode, for example resolving `sh:node` to the target class of the referenced
   shape, would separate modelling-style differences from real errors.

## Next steps

- Run the pipeline on CCKG (Phase 1). It needs `data/cckg/kg.json` pointing to the dump or to the
  SPARQL endpoint, plus any existing SHACL for CCKG as reference shapes.
- Wire up QSE's query-based mode (GraphDB, or check compatibility with an RDF4J/Fuseki endpoint) and
  its pruning thresholds.
- Attempt RDFminer-core headless.
- Add a lenient comparison mode and an RDFS-inference option to the evaluator.
- Report the SHACL Play binding bug, the sheXer `sh:dataType` bug and the QSE `sh:NodeKind` bug
  upstream.

# Inference and shape discovery

Most RDF KGs use terms from ontologies. Whether or not the KG includes those ontologies, their
axioms can be taken into account both when shapes are *discovered* and when they are *used to
validate*. This note covers two things:

1. why the inference regime is a design decision for shapes, with its pros and cons;
2. how the pipeline keeps discovery and validation coherent by applying the same regime to both
   phases. An earlier version of the pipeline did not, and that distorted the first CCKG results.

## 1. SHACL already contains some inference

SHACL Core is not inference-free. `sh:targetClass C` targets the *SHACL instances* of `C`, meaning
the nodes typed with `C` or with any class connected to `C` by a chain of `rdfs:subClassOf`
triples **in the data graph**. `sh:class C` uses the same rule for values. This does not depend on
any "inference" switch of the validator. SHACL also lets a shapes graph declare the entailment
regime it needs (`sh:entailment`), which processors may or may not support.

Two consequences:

- **An included ontology changes the semantics silently.** If the KG includes its ontology, as
  CCKG does, the validator applies the ontology's subclass hierarchy. If the ontology is published
  separately, the same shapes on the same instance data behave differently.
- **"No inference" needs care in both phases.** The shape discovery tools surveyed here all profile
  the *asserted* `rdf:type` triples. Shapes discovered that way describe the explicit instances of
  each class. Validating them on a data graph that contains `rdfs:subClassOf` triples applies them
  to more nodes than they were learned from.

## 2. The inconsistency in the first CCKG run

In the first CCKG run, discovery used the asserted triples only. Validation used the same data,
which includes the ontology's `rdfs:subClassOf` triples, so SHACL's built-in subclass semantics
applied. For example, a `data:Dataset` shape learned from the 2 nodes typed explicitly as `Dataset`
(with `rdfs:label` and `rdfs:comment` required) was validated against the 573,448 nodes that are
datasets only through subclasses. That inflated the violation counts by up to 14 times. The first
version of [cckg-findings.md](cckg-findings.md) reported this as a finding about the tools, but it
was an artefact of the pipeline.

The toy KG had the same kind of inconsistency, with a twist. The reference shapes were validated
on an RDFS closure, while the tool shapes were validated on the raw data.

## 3. Inference regimes in the pipeline

[`pipeline/regimes.py`](../pipeline/regimes.py) defines three regimes. `run.py --inference R` and
`evaluate.py --inference R` apply the same regime to discovery (the files the tools read and the
local SPARQL endpoint) and to validation (the extracted shapes and the reference shapes):

| regime | tools read | shapes are validated on |
|---|---|---|
| `none` | asserted triples | asserted triples without `rdfs:subClassOf`, which switches off SHACL's built-in subclass semantics |
| `subclass` | asserted triples + `rdf:type` along the `rdfs:subClassOf` closure | the same data |
| `rdfs` | the RDFS closure (subclass, subproperty, domain, range) | the same data |

- **Where the vocabulary comes from:** the axioms are taken from the KG and from the optional
  `ontologies` files in `kg.json`. Those files are for ontologies the KG uses but does not include.
  They feed the entailments only; they are not added to the data the tools profile.
- **`subclass` matches SHACL Core:** it is exactly the entailment SHACL Core already assumes, so
  validating on its data adds nothing on top of it.
- **Blank-node types are dropped:** in `subclass` and `rdfs`, inferred `rdf:type` triples whose
  class is a blank node are removed. These come from subclass, domain and range axioms whose target
  is an anonymous OWL class expression (a restriction, a union). No shape can target such a class,
  and they crash sheXer. On CCKG there are about 607k of them. Handling them properly would need an
  OWL regime such as OWL RL.

## 4. Pros and cons of inference-aware shapes

**Pros**

- **Shapes at the right level of abstraction.** With the subclass closure materialised, a shape for
  a generic class is learned from all its members. On CCKG, sheXer's `Dataset` shape goes from 2
  properties, both required (learned from 2 nodes), to 13 properties, none required (learned from
  573k). The first is a misleading description of what a dataset is in CCKG; the second is a
  faithful summary at the abstract level.
- **Less redundancy in principle.** A constraint shared by all subclasses can be stated once on the
  superclass. Validation then applies it to every subclass instance through `sh:targetClass`.
- **Independent of the typing style.** It does not matter whether a KG asserts only the most specific
  type or all of them.

**Cons**

- **The tools do not factor constraints along the hierarchy.** Each class's shape is learned
  independently from that class's (materialised) extension. So inference produces *more*
  repetition, not less, unless a post-processing step removes the constraints already stated on a
  superclass. On CCKG, sheXer's and QSE's (class, property) pairs grow from 316 to 788, and the
  share that repeats a superclass constraint grows from 30% (96) to 82% (644). The column
  "of which also on a superclass" in the summaries tracks this for every run.
- **Interpretation and validation depend on the axiomatisation and on the regime.** Shapes discovered
  under a regime are only meaningful under that regime. The regime should be recorded with the
  shapes, for example with `sh:entailment`, whose support in validators varies. The toy reference
  shapes illustrate this. They are written at an abstract level (`sh:class ex:ClimateModel`, and an
  `EarthSystemModel` shape that reuses the `ClimateModel` one). Under `none` they reject a correct
  node, `ex:m_mpi_esm`, which is typed only as `EarthSystemModel`.
- **Richer regimes bring in more of the ontology's modelling choices.** On CCKG, `rdfs` adds
  domain/range typing and subproperty triples: 3.15M `top-level:associatedWith` triples,
  424k `data:derivedFromVariable`, and more. The data grows from 4.7M to 15M triples, and every
  tool describes these inferred triples as well. Axioms whose domain or range is an OWL class
  expression yield anonymous types that RDFS cannot interpret.
- **Some constraint styles break under materialisation.** sheXer's one-property-shape-per-type
  (`rdf:type sh:in (C)`, `maxCount 1`) fails on every node with several types, and materialising
  superclasses makes almost every node multi-typed. On the toy KG its violations grow from 19 to 31.
  On CCKG they grow from about 4.6 to about 2,400 per node.
- **Domain/range inference can hide the errors shapes are meant to catch.** Under `rdfs`, a value
  of a property with `rdfs:range C` is typed `C` by inference, so `sh:class C` on that property can
  no longer fail. On CCKG, SHACL Play's shapes flag the 287 undefined variables (D4 in
  [cckg-findings.md](cckg-findings.md)) under `none` and `subclass`, but find nothing at all under
  `rdfs`. Subclass-only inference does not have this effect, because it never adds a type to a
  node that has none.
- **Cost.** The closures double (`subclass`) or triple (`rdfs`) the data. On CCKG, SHACLGEN and
  schema-automator run out of memory (12 GB cap), sheXer's endpoint mode is OOM-killed, and
  SHACL Play's discovery grows from 3 minutes to 49 minutes (`subclass`) and 1.8 hours (`rdfs`).
  Validation also gets more expensive, dramatically so for shapes with `sh:node` chains.

## 5. Results on CCKG

The CCKG results for SHACL Play, the most descriptive of the tools, show both sides of the
trade-off (full tables in [`results/cckg/summary.md`](../results/cckg/summary.md), discussion in
[cckg-findings.md](cckg-findings.md)):

| | `none` | `subclass` | `rdfs` |
|---|---|---|---|
| data (triples) | 4.7M | 9.5M | 15.1M |
| node shapes | 47 | 77 | 79 |
| (class, property) pairs | 238 | 710 | 1,040 |
| … also constrained on a superclass | 96 (40%) | 644 (91%) | 960 (92%) |
| nodes flagged when validating the KG | 114,559 (19.3%) | 114,560 (19.3%) | 0 |
| violations per node | 0.50 | 2.64 | 0 |
| discovery time | 3 min | 49 min | 1.8 h |

In CCKG's case, `subclass` gives the useful abstract shapes and keeps error detection. It needs a
factoring step to remove the constraints inherited from superclasses. `rdfs` adds little for
shapes and hides real errors. `none` gives compact shapes, but its shapes for generic classes are
learned from a few explicitly typed nodes. With the old, incoherent validation (`none` discovery,
SHACL's subclass semantics at validation), the same SHACL Play shapes flagged 586,920 nodes (98.7%).

## 6. Recommendations for the survey

- **State the regime with every set of shapes,** and use the same regime for discovery and
  validation. The pipeline enforces this. In shapes graphs, `sh:entailment` is the standard way to
  declare it.
- **Treat an ontology in the data graph as part of the regime.** If a KG includes its ontology,
  validating under `none` requires removing the `rdfs:subClassOf` triples, as the pipeline does.
- **Default to `subclass` when shapes should be read at the ontology's level of abstraction,** and
  add a post-processing step that factors constraints along the hierarchy. None of the surveyed
  tools does this.
- **Avoid domain/range inference in the discovery/validation loop,** unless the goal is to check
  conformance to the ontology's own axioms, which is a different task.

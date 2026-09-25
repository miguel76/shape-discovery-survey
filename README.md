# shape-discovery-survey
A survey of existing tools for discovery of SHACL shapes from an existing knowledge graph

## Criteria of Inclusion

Each considered tool must be able to derive a set of (candidates) shapes based on a knowledge graph available as an RDF dataset.
The input should in general be either a local dump of the dataset in a standard serialization format (e.g., Turtle) or a link to an API offering the content through a standard protocol (typically a SPARQL endpoint).
The focus is mainly on deterministic tools not based on generative AI.  

## Method

- Conforming tools are searched and listed.
- They are tested for executability within a reasonable effort and set of resources.
- A set of KGs to be used for testing purposes is identified, that should encompass significative variety in terms of schema complexity and structure, size, domain.
- A desired criterium is that a KG has a already set of SHACL shapes available for evaluation.
- Each tool is tested against each KG.
- The resulting shapes are validated by experts/AI, considering also existing SHACL if available
- More advanced analysis may include comparing this tools with results obtained by generative AI systems
- One more step would be to combine somehow multiple agents (deterministic tools, human experts, AI agents) and evaluate the results.

## Phase 1

In the first, exploratory, phase a set of tools will be identified and tested on a single KG, namely the [Climate Change Knowledge Graph (CCKG)](https://hacid-project.github.io/cckg/).
This doubles also as part of the evaluation of said KG and the design of SHACL shapes for that use case.

## Tools

The full catalogue, including execution requirements and the reason for each exclusion, is in
[docs/tools.md](docs/tools.md).

| Tool | Input | Status in the pipeline |
|---|---|---|
| [sheXer](https://github.com/weso/shexer) | file, SPARQL endpoint | ✅ file + endpoint |
| [QSE](https://github.com/dkw-aau/qse) / SHACTOR | file (N-Triples), GraphDB | ✅ file (full and pruned output, as `qse` and `qse-pruned`) |
| [SHACLGEN](https://github.com/alexiskeely/shaclgen) | file | ✅ file (wrapper around a broken CLI) |
| [SHACL Play! generate](https://github.com/sparna-git/shacl-play) | file, SPARQL endpoint | ✅ file + endpoint (patched) |
| [LinkML schema-automator](https://github.com/linkml/schema-automator) + `gen-shacl` | Turtle file | ✅ file (indirect, via LinkML) |
| [RDFminer](https://github.com/Wimmics/RDFminer) | Corese SPARQL endpoint | ⏳ multi-service stack, not yet run |
| Shape Designer, SHACLearner, ABSTAT-based induction | – | ⏳ GUI only / code not available |

## Pipeline

```
data/<kg>/kg.json ──► pipeline/run.py ──► results/<kg>/<regime>/<tool>[@endpoint]/shapes.ttl ──► pipeline/evaluate.py ──► results/<kg>/<regime>/summary.md
   (dump files,        merge graphs; apply the               + run.log, run.json                   parse, SHACL vocabulary and       results/<kg>/summary.md
    ontologies,        inference regime; optionally          (exit code, time, peak RSS)           SHACL-SHACL checks, profile,      (regimes compared)
    endpoint,          serve the data with Fuseki (TDB2);                                          self-validation (Jena SHACL)
    reference shapes)  run tools/<tool>/run.sh                                                     under the same regime,
                                                                                                   comparison with the reference shapes
```

The **inference regime** (`none`, `subclass` or `rdfs`) is applied identically to shape discovery
and to validation (see [pipeline/regimes.py](pipeline/regimes.py)). Why this matters, and the
pros and cons of inference-aware shapes, are discussed in [docs/inference.md](docs/inference.md).

Requirements are bash, git, Python ≥ 3.10, Java ≥ 17 and Maven. Docker is not needed. Every tool
is installed under `.tools/` at a pinned version:

```sh
make install          # the tools, Fuseki, and the evaluation environment (~2 min)
make run evaluate     # KG=toy, INFERENCE=none by default; results in results/toy/none/
make run evaluate KG=toy INFERENCE=subclass
make run evaluate KG=cckg INFERENCE=rdfs RUN_ARGS="--endpoint --local-endpoint"
```

On CCKG (4.7M triples) single steps peak at about 8 GB of RAM (a 16 GB machine is enough), and a full run takes a few hours, most of it spent in
SHACLGEN, in sheXer's endpoint mode and in validating the KG against every set of shapes.
`--local-endpoint` serves the dump with a local Fuseki. This sandbox cannot reach the public CCKG
endpoint, and a local endpoint also keeps the load off the public one. With a regime other than
`none` it is required, since the entailments a remote endpoint exposes are unknown. The
`subclass` and `rdfs` regimes double and triple the size of CCKG. Python tools are capped at
`TOOL_VMEM_MB` (default 12288) of address space, so they fail with a `MemoryError` rather than
exhausting the machine.

To add a KG, create `data/<kg>/kg.json` (see [data/toy/kg.json](data/toy/kg.json) and the
docstring of [pipeline/run.py](pipeline/run.py)). The file lists the dump files and, optionally,
the `ontologies` the KG uses but does not include (they feed the inference regimes only), a SPARQL
`endpoint` and `reference_shapes`. Then run `make run evaluate KG=<kg>`.

To add a tool, create `tools/<tool>/install.sh` and `tools/<tool>/run.sh`, where
`run.sh (file INPUT | endpoint URL) OUTDIR` writes `OUTDIR/shapes.ttl`. Then register the tool in
[tools/registry.json](tools/registry.json).

### First results: toy KG

The toy KG ([data/toy](data/toy)) is a small, hand-made, climate-flavoured dataset with
hand-written reference shapes. All five runnable tools complete on it; see
[results/toy/summary.md](results/toy/summary.md). The findings are in
[docs/toy-findings.md](docs/toy-findings.md). Among them, sheXer and QSE emit misspelled SHACL
terms (`sh:dataType`, `sh:NodeKind`) that validators silently ignore. SHACL Play's generator
needed a bug fix before its per-class results were meaningful.

### Phase 1: CCKG

All five tools run on the CCKG dump, and sheXer and SHACL Play also run through a SPARQL
endpoint. Getting there required fixes in three tools. The run also exposed defects in the CCKG
data itself. The survey was repeated under three inference regimes; the `rdfs` closure triples the
data and pushes some tools out of memory. See
[results/cckg/summary.md](results/cckg/summary.md), [docs/cckg-findings.md](docs/cckg-findings.md)
and, on inference, [docs/inference.md](docs/inference.md).

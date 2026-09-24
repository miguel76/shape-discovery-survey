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

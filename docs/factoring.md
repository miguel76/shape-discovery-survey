# Factoring shapes along the class hierarchy

Shape discovery tools learn one shape per class, independently of the others. When the class
hierarchy is visible (the `subclass` and `rdfs` inference regimes, see [inference.md](inference.md)),
a constraint that holds for a class `D` is learned again for every subclass of `D`. On CCKG, 82–91%
of the (class, property) pairs constrained under `subclass` repeat a pair constrained on a
superclass. *Factoring* removes from each class's shape the constraints that its superclasses'
shapes already impose. This note defines it, proves that it does not change validation results
under the regimes it is meant for, and describes the implementation
([`pipeline/factor.py`](../pipeline/factor.py)) and how it was tested.

## 1. Setting

**Class hierarchy.** Let `≤` be the reflexive-transitive closure of the `rdfs:subClassOf` triples
between IRIs in the KG and in its declared ontologies. We write `C < D` (*D is a strict superclass
of C*) when `C ≤ D` and not `D ≤ C`; classes in a subclass cycle are equivalent and are not strict
superclasses of each other.

**Assumption A (subclass entailment).** In the data graph `G` being validated, every SHACL instance
of a class `C` is a SHACL instance of every `D` with `C ≤ D`. This holds when the `rdfs:subClassOf`
triples are in `G` (SHACL Core follows them) or when the `rdf:type` triples are materialised along
the hierarchy. Both are the case under the `subclass` and `rdfs` regimes. It does **not** hold
under the `none` regime, where validation deliberately removes the subclass triples, so factoring
is not applied there.

**Constraints.** A *constraint* is one parameter of a SHACL Core constraint component together with
its value. Examples are `sh:minCount 1`, `sh:class ex:A`, `sh:in (…)` and `sh:or (…)`. Parameters
that only make sense together count as one constraint: `sh:qualifiedValueShape` with its
`sh:qualifiedMin/MaxCount` and `sh:qualifiedValueShapesDisjoint`, `sh:pattern` with `sh:flags`,
and `sh:closed` with `sh:ignoredProperties`. For a node shape `s` and a path `π` (a property
path, or `ε` for constraints of the node shape itself), `K_s(π)` is the set of constraints that
`s` puts on `π`, collected from all its property shapes with path `π`. For a class `C`,
`K(C, π) = ⋃ { K_s(π) | s targets C }`.

**Locality.** Except for the sibling-dependent constructs listed in §4, every Core constraint on
`π` is a condition on the focus node `x` and the set `π(x)` of its values. Its truth does not
depend on the other constraints. So a node `x` conforms to a node shape `s` iff it satisfies each
constraint in each `K_s(π)`, and several property shapes with the same path amount to the union of
their constraints.

**Violations.** `V_S(G)` is the set of pairs `(x, π)` such that `x` is a focus node of some shape of
`S` and violates a constraint that this shape puts on `π`. `G` conforms to `S` iff `V_S(G)` is
empty.

**Implication.** A set of constraints `P` *implies* a constraint `k` (on the same path) if every
focus node that satisfies all of `P` satisfies `k`, in every data graph that meets assumption A.
The implementation uses a test `implies(P, k)` that is **sound**: when it returns true, `P`
implies `k`. It is not complete.

## 2. Definition

For every class `C` and path `π`, let the *premises* be the constraints of the strict superclasses:

    Sup(C, π) = ⋃ { K(D, π) | C < D }

The factored shapes graph `S'` keeps, for every *factorable* node shape `s` targeting `C` and
every path `π`,

    K'_s(π) = { k ∈ K_s(π) | not implies(Sup(C, π), k) }

Non-factorable node shapes (§4) are kept unchanged and act only as premises. `Sup` is always
computed on the **original** shapes, and all removals are decided before any is applied.
Property shapes left without constraints are unlinked, and node shapes left without constraints
are removed.

## 3. Correctness

**Theorem.** Under assumption A, for every data graph `G`, `V_S'(G) = V_S(G)`. In particular, `G`
conforms to `S'` iff it conforms to `S`, and the same focus nodes are flagged.

*Proof.*

- **`V_S'(G) ⊆ V_S(G)`.** For each node shape, path and focus node, the constraints in `S'` are a
  subset of those in `S`. Factoring only removes constraints; copied property shapes are copies
  minus some constraints. So every violation under `S'` is a violation under `S`.
- **`V_S(G) ⊆ V_S'(G)`.** Let `(x, π) ∈ V_S(G)`: `x` violates some `k₀ ∈ K(C₀, π)`, where `C₀` is
  a target class of a shape that targets `x`, so `x` is a SHACL instance of `C₀`. If `k₀` is kept
  in `S'`, we are done. Otherwise `implies(Sup(C₀, π), k₀)` holds, so `x` violates some premise
  `k₁ ∈ K(C₁, π)` with `C₀ < C₁`, because a node satisfying all the premises would satisfy `k₀`.
  By assumption A, `x` is a SHACL instance of `C₁`, so the shapes targeting `C₁` target `x`. If
  `k₁` is kept, then `(x, π) ∈ V_S'(G)`. Otherwise we repeat the argument with `k₁` and obtain a
  chain `C₀ < C₁ < C₂ < …`. The chain is strictly ascending in a finite partial order (`<`
  excludes cycles), so it ends with a constraint `k_n` that is kept in `S'` and violated by `x` on
  `π`.

The second part is why removals are decided on the original constraints. Each step of the chain
uses the premises that justified the removal at that class, whether or not those premises were
removed in turn.

**What the theorem does not say.** A factored shape read on its own no longer describes its class
completely. The effective constraints of `C` are the union of the constraints of `C` and of all
its superclasses. The theorem also relies on assumption A: validating `S'` without subclass
entailment accepts nodes that `S` rejects. This is the price of the abstraction discussed in
[inference.md](inference.md). The regime has to be stated together with the shapes (for example
with `sh:entailment`).

## 4. Shapes that are not factored

Some constructs make a shape's meaning depend on more than its own target, or on its sibling
property shapes. Factoring such shapes would break the theorem, so they are kept intact. They
still serve as premises for their subclasses.

- **Shapes used as values of `sh:node`** (or inside `sh:and`, `sh:or`, `sh:xone`, `sh:not`,
  `sh:qualifiedValueShape`). Such a reference validates a value against that shape alone, not
  against the shapes of its superclasses, so assumption A does not help there. sheXer and QSE
  refer to class shapes with `sh:node` a lot, so many of their shapes stay intact. An alternative
  would be to keep the full shape for `sh:node` references under a separate IRI and factor only
  the target-based one.
- **`sh:closed true`**, whose meaning depends on which properties the sibling property shapes
  declare, and **`sh:qualifiedValueShapesDisjoint true`**, which refers to the sibling qualified
  value shapes. schema-automator/LinkML closes every shape, so nothing of it is factored.
- **Node shapes with targets other than exactly one class** (`sh:targetNode`,
  `sh:targetSubjectsOf`, several `sh:targetClass`). They take part as premises for each of their
  target classes but are not changed.

**Shared property shapes.** Some tools, SHACLGEN for instance, reuse one property shape in several
node shapes. A property shape is only edited in place when a single node shape uses it. Otherwise
the node shape gets a copy with the remaining constraints.

## 5. The implication test

`implies(P, k)` returns true if `k ∈ P`, or if one premise `q ∈ P` implies `k` by one of these rules:

| `k` | implied by `q` | why |
|---|---|---|
| `sh:minCount n` | `sh:minCount m`, `m ≥ n` | at least `m` values means at least `n` |
| `sh:maxCount n` | `sh:maxCount m`, `m ≤ n` | |
| `sh:minInclusive/minExclusive/minLength n` | the same parameter with `m ≥ n` | numeric values only |
| `sh:maxInclusive/maxExclusive/maxLength n` | the same parameter with `m ≤ n` | numeric values only |
| `sh:class C` | `sh:class D`, `D ≤ C` | a SHACL instance of `D` is one of `C` (assumption A, applied to the values) |
| `sh:nodeKind K` | `sh:nodeKind K'` with `K' ⊆ K` | e.g. `sh:IRI` ⊆ `sh:BlankNodeOrIRI` |
| `sh:nodeKind K` with literals allowed | `sh:datatype d` | only literals have a datatype |
| `sh:nodeKind K` allowing IRIs and blank nodes | `sh:class D` | a SHACL instance has an `rdf:type` triple, so it is not a literal |
| `sh:in L` | `sh:in L'`, `L' ⊆ L` | |
| `sh:languageIn L` | `sh:languageIn L'`, `L' ⊆ L` | |
| `sh:or (d₁ … dₙ)` | `sh:or (e₁ … e_m)`, every `eᵢ` among the `dⱼ` | a value conforming to some `eᵢ` conforms to that `dⱼ` |
| `sh:or` of classes `([sh:class C₁] … [sh:class Cₙ])` | `sh:class D` with `D ≤` some `Cⱼ`, or an `sh:or` of classes `D₁ … D_m` where every `Dᵢ ≤` some `Cⱼ` | a value that is an instance of `Dᵢ` is an instance of `Cⱼ` (assumption A) |
| `sh:class C` | an `sh:or` of classes `D₁ … D_m`, every `Dᵢ ≤ C` | |
| `sh:nodeKind K` allowing IRIs and blank nodes | an `sh:or` of classes | as for `sh:class` |

Constraints are compared in a canonical form that expands blank nodes and RDF lists. In nested
shapes, it leaves out predicates that are not SHACL terms, because SHACL processors ignore them.
QSE, for instance, annotates every member of its `sh:or` lists with the number of instances it was
learned from, and these counts differ between a class and its superclass. Without this, equal
disjunctions never compared equal, and QSE's removals were 620 instead of 801 under `subclass`.

Everything else is removed only when an identical constraint is among the premises: `sh:datatype`,
`sh:hasValue`, `sh:pattern`, `sh:node`, `sh:and`, `sh:not`, qualified value shapes, and property
pair constraints. The test is incomplete in known ways:
- it never combines two premises, e.g. `sh:class A` from one superclass and `sh:class B` from
  another cannot imply `sh:or ([sh:class A] [sh:class B])`;
- it does not reason inside `sh:node`/`sh:and`;
- it compares paths syntactically.

A complete test would amount to SHACL shape containment, which is undecidable for full SHACL
(Pareti et al., *SHACL Satisfiability and Containment*, ISWC 2020). A sound and simple test is
enough here, because any missed implication just leaves a redundant constraint in place.

## 6. Testing

- [`tests/test_implies.py`](../tests/test_implies.py) checks the rules of `implies()`
  exhaustively on a small universe.
  - It uses 41 constraints covering every rule (two of them with annotated `sh:or` members), and 130 focus nodes, one for every set of up to 3
    values drawn from IRIs and a blank node of various classes, integers, a string and a
    language-tagged string.
  - For each of the 139 pairs `(q, k)` with `implies({q}, k)`, pySHACL confirms that every node
    violating `k` violates `q`.
  - Fourteen deliberately wrong variants of the rules, such as reversing a comparison, letting
    `sh:class` imply `sh:nodeKind sh:IRI`, or accepting a class disjunction that is only partly
    covered, are all detected.
- [`tests/test_factor.py`](../tests/test_factor.py) runs random end-to-end trials.
  - Each trial builds a random hierarchy with an equivalence cycle, and random shapes with
    shared property shapes, `sh:node` references, closed shapes and node-level constraints.
  - The data has types materialised along the hierarchy.
  - Each trial checks that `V_S(G) = V_S'(G)`. It also checks each removal on its own: validated
    alone, every value that violates the removed constraint must violate one of its premises.
  - 3,000 trials (seeds 3, 7 and 11) found no counterexample, with 12,786 removals in total (about 4
    per trial), each checked on its own.
- The pipeline factors every run under `subclass` and `rdfs` and validates the KG against both
  versions. When the original run's validation stopped on a random sample, the `+factored` run is
  validated on exactly the same sample: `ShaclStats` sorts the focus nodes before its seeded
  shuffle and stops at the same node count. The number of nodes flagged must then match exactly
  (§7).

## 7. Results on CCKG

The pipeline factors every run of the `subclass` and `rdfs` regimes on the updated CCKG dump
(2026-09-30). The SHACL Play shapes are those discovered on the previous dump (see
[cckg-findings.md](cckg-findings.md)). Full tables are in the `## Factoring along the class
hierarchy` section of [`results/cckg/subclass/summary.md`](../results/cckg/subclass/summary.md) and
[`results/cckg/rdfs/summary.md`](../results/cckg/rdfs/summary.md).

**How much is removed.**

| regime | run | constraints | removed | property shapes | node shapes | node shapes kept intact (referenced by `sh:node`) |
|---|---|---|---|---|---|---|
| `subclass` | SHACL Play | 2,112 | 1,676 (79%) | 710 → 228 | 77 → 64 | 0 |
| `subclass` | sheXer | 4,076 | 2,402 (59%) | 1,732 → 794 | 90 → 73 | 30 |
| `subclass` | QSE, full | 1,827 | 620 (34%) | 812 → 673 | 89 | 31 |
| `subclass` | QSE, pruned | 558 | 187 (34%) | 269 → 220 | 45 | 14 |
| `rdfs` | SHACL Play | 3,012 | 2,434 (81%) | 1,040 → 319 | 79 → 66 | 0 |
| `rdfs` | sheXer | 4,722 | 2,608 (55%) | 2,114 → 1,055 | 93 → 77 | 33 |
| `rdfs` | QSE, full | 2,633 | 834 (32%) | 1,135 → 965 | 91 | 34 |
| `rdfs` | QSE, pruned | 930 | 308 (33%) | 434 → 364 | 47 | 15 |

- **SHACL Play gains the most.** It uses no `sh:node`, so every shape can be factored. Its
  class constraints are `sh:or` disjunctions of classes, which the class-disjunction rules of §5
  handle; without those rules only 1,317 constraints were removed.
- **sheXer and QSE keep about a third of their node shapes intact,** because other shapes refer to
  them with `sh:node` (§4). QSE's remaining redundancy is mostly in these shapes. Its own
  constraints also imply less: it only ever emits `sh:minCount 1` and `sh:maxCount 1`, and its
  `sh:or` lists mix classes and datatypes, which the rules do not decompose.
- **schema-automator** closes every shape (`sh:closed true`), so nothing is factored. It ran out
  of memory under both regimes anyway, as did SHACLGEN.

**Validation results are unchanged.** Each factored set of shapes was validated on the same focus
nodes as the original (§6). A factored shapes graph can only flag a subset of the nodes that the
original flags, so equal counts mean equal sets.

| regime | run | focus nodes validated | nodes flagged (original = factored) | violations (original → factored) | validation time (original → factored) |
|---|---|---|---|---|---|
| `subclass` | SHACL Play | all 595,454 | 116,012 | 1,535,280 → 187,292 (−88%) | 854 s → 527 s |
| `subclass` | sheXer | sample of 27,014 | 27,001 | 63.9M → 40.2M (−37%) | 600 s → 394 s |
| `subclass` | QSE, full | sample of 17,448 | 17,447 | 2,612,164 → 1,955,567 (−25%) | 603 s → 369 s |
| `subclass` | QSE, pruned | sample of 84,009 | 83,991 | 8,606,562 → 7,164,296 (−17%) | 600 s → 410 s |
| `rdfs` | SHACL Play | RDFS_SP_NODES | RDFS_SP_FLAGGED | RDFS_SP_VIOL | RDFS_SP_TIME |
| `rdfs` | sheXer | sample of 240 | 240 | 808,143 → 495,717 (−39%) | 637 s → 108 s |
| `rdfs` | QSE, full | sample of 1,996 | 1,996 | 443,198 → 297,725 (−33%) | 600 s → 415 s |
| `rdfs` | QSE, pruned | sample of 368 | 367 | 94,149 → 62,707 (−33%) | 611 s → 368 s |

The violations drop because the same problem is no longer reported once for each superclass
shape that repeated the constraint. For SHACL Play under `subclass`, the 116,012 flagged nodes
were reported with 13.2 violations each, and with 1.6 after factoring. Validation is 30–80% faster,
since fewer constraints are checked per node.

Under `rdfs`, the SHACL Play shapes flag no node at all, factored or not, because domain and range
inference types the undefined variables of D4 as `data:Variable` (see [inference.md](inference.md)).
The equality holds trivially there.

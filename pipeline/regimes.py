"""Inference regimes, shared by run.py (shape discovery) and evaluate.py (validation).

A regime fixes which entailments of the KG are visible, and it is applied identically
in both phases, so the shapes are validated under the same semantics they were
extracted under:

  none      Discovery sees the asserted triples only. Validation uses the same data
            without its rdfs:subClassOf triples: SHACL Core itself follows
            rdfs:subClassOf in the data graph for sh:targetClass and sh:class, which
            would otherwise bring back a subclass entailment that discovery never saw.
            Side effect: shapes that constrain the rdfs:subClassOf property of
            classes are checked against data without it.
  subclass  Both phases see the data plus rdf:type triples materialised along the
            rdfs:subClassOf closure (RDFS rules rdfs9/rdfs11). This is exactly the
            entailment SHACL Core assumes, so validation adds nothing on top.
  rdfs      Both phases see the RDFS closure computed by Jena riot --rdfs (rdfs:subClassOf,
            rdfs:subPropertyOf, rdfs:domain, rdfs:range).

In subclass and rdfs, inferred rdf:type triples whose class is a blank node are dropped
(asserted ones are kept). They come from applying RDFS rules to OWL axioms whose
superclass, domain or range is an anonymous class expression (owl:Restriction,
owl:unionOf, ...): formally valid entailments, but no shape can target such a class,
and interpreting them properly would take OWL (e.g. OWL RL) reasoning. On CCKG they
are about 600k triples, and they crash sheXer. Likewise, RDFS range rules applied to
literal values produce "generalized RDF" triples with a literal subject
("x" rdf:type rdfs:Literal); they are not RDF (serialisers such as Turtle reject them)
and are dropped too.

The vocabulary for the entailments is the KG itself plus, if kg.json lists them, the
`ontologies` files: axioms of ontologies the KG uses but does not include. They take
part in the entailments only; they are not added to the data the tools profile.

Files (all under work/<KG>/):
  data.nt                      the merged dump (asserted triples)
  ontologies.nt                the merged `ontologies` files, if any
  <regime>/data.nt, data.ttl   what the tools read (and the local endpoint serves)
  <regime>/data-validation.nt  what the extracted shapes are validated against
"""
import os
import subprocess
from pathlib import Path

REGIMES = ("none", "subclass", "rdfs")
SUBCLASS_OF = "<http://www.w3.org/2000/01/rdf-schema#subClassOf>"

TOOLS_HOME = Path(os.environ.get("TOOLS_HOME", Path(__file__).resolve().parent.parent / ".tools"))
JENA_JAR = TOOLS_HOME / "fuseki" / "jena-fuseki-server-5.2.0.jar"
RIOT = ["java", "-Xmx6g", "-cp", str(JENA_JAR), "riotcmd.riot"]


def stale(dest, sources):
    return not dest.exists() or dest.stat().st_mtime < max(Path(s).stat().st_mtime for s in sources)


BLANK_TYPE = " <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> _:"


def _sorted_unique(cmd, dest, tmpdir, keep_line=None):
    """Run cmd and write its N-Triples output to dest, sorted and deduplicated,
    keeping only the lines for which keep_line(bytes) is true, if given. The file is
    written under a temporary name and renamed at the end, so an interrupted run never
    leaves a partial file that looks up to date."""
    tmp = dest.with_name(dest.name + ".tmp")
    producer = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        with open(tmp, "wb") as f:
            sort = subprocess.Popen(["sort", "-u", "-S", "2G", "-T", str(tmpdir)], stdin=subprocess.PIPE, stdout=f,
                                    env={**os.environ, "LC_ALL": "C"})
            for line in producer.stdout:
                if keep_line is None or keep_line(line):
                    sort.stdin.write(line)
            sort.stdin.close()
            if sort.wait() != 0:
                raise RuntimeError("sort failed")
    finally:
        producer.stdout.close()
    if producer.wait() != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"command failed: {' '.join(map(str, cmd))}")
    os.replace(tmp, dest)


def merged_dump(sources, work, log=print):
    """work/data.nt: the union of all graphs of the dump files (riot --merge; plain
    `--output=ntriples` silently drops quads), deduplicated."""
    nt = work / "data.nt"
    if stale(nt, sources):
        log(f"[prepare] {nt}")
        _sorted_unique([*RIOT, "--merge", "--output=ntriples", *map(str, sources)], nt, work)
    return nt


def merged_ontologies(sources, work, log=print):
    """work/ontologies.nt from the kg.json `ontologies` files, or None."""
    if not sources:
        return None
    nt = work / "ontologies.nt"
    if stale(nt, sources):
        log(f"[prepare] {nt}")
        _sorted_unique([*RIOT, "--merge", "--output=ntriples", *map(str, sources)], nt, work)
    return nt


def regime_data(work, regime, log=print):
    """work/<regime>/data.nt: the data the tools read under the regime."""
    if regime not in REGIMES:
        raise ValueError(f"unknown inference regime {regime!r}; expected one of {REGIMES}")
    base = work / "data.nt"
    ontologies = work / "ontologies.nt"
    vocab_sources = [base] + ([ontologies] if ontologies.exists() else [])
    out_dir = work / regime
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "data.nt"
    if regime == "none":
        if dest.exists() and not stale(dest, [base]) and os.path.samefile(dest, base):
            return dest
        dest.unlink(missing_ok=True)
        os.link(base, dest)
        return dest
    if not stale(dest, vocab_sources):
        return dest
    log(f"[prepare] {dest}")
    if regime == "rdfs" and len(vocab_sources) == 1:
        vocab = base
    else:
        vocab = out_dir / "vocabulary.nt"
        with open(vocab, "wb") as f:
            for src_file in vocab_sources:
                with open(src_file, "rb") as src:
                    if regime == "subclass":
                        f.writelines(line for line in src if f" {SUBCLASS_OF} ".encode() in line)
                    else:
                        f.writelines(src)
    # asserted triples typed with a blank node class are kept, inferred ones dropped;
    # generalized triples with a literal subject are dropped
    with open(base, "rb") as src:
        asserted_blank_types = {line for line in src if BLANK_TYPE.encode() in line}
    _sorted_unique([*RIOT, f"--rdfs={vocab}", "--output=ntriples", str(base)], dest, out_dir,
                   keep_line=lambda line: not line.startswith(b'"') and
                   (BLANK_TYPE.encode() not in line or line in asserted_blank_types))
    return dest


def regime_turtle(nt, log=print):
    ttl = nt.with_suffix(".ttl")
    if stale(ttl, [nt]):
        log(f"[prepare] {ttl}")
        tmp = ttl.with_name(ttl.name + ".tmp")
        with open(tmp, "wb") as f:
            subprocess.run([*RIOT, "--stream=turtle", str(nt)], stdout=f, check=True)
        os.replace(tmp, ttl)
    return ttl


def validation_data(work, regime, log=print):
    """work/<regime>/data-validation.nt (none) or the regime data itself (subclass, rdfs)."""
    data = regime_data(work, regime, log)
    if regime != "none":
        return data
    dest = work / regime / "data-validation.nt"
    if stale(dest, [data]):
        log(f"[prepare] {dest}")
        tmp = dest.with_name(dest.name + ".tmp")
        with open(data, "rb") as src, open(tmp, "wb") as f:
            f.writelines(line for line in src if f" {SUBCLASS_OF} ".encode() not in line)
        os.replace(tmp, dest)
    return dest

#!/usr/bin/env python3
"""Why are some CCKG variables undefined? Classify them against the climate-data vocabularies.

usage: analysis/cckg_variables.py TABLES_DIR [--dump FILE.nq.gz] [--out DIR]

CCKG defines its MIP variables from the CMIP6 CMOR tables (graph cmip6/cmor-tables) and its
CF variables from the CF standard-name table. Datasets from other sources link variables
that are not defined there. This script looks each undefined variable up in:

  CMIP6, CMIP5          CMOR tables (variable out_names and coordinate names)
  CORDEX-CMIP5          the CORDEX CMOR tables
  CORDEX-CMIP6          the CORDEX-CMIP6 CMOR tables and data request
  CF                    the latest CF standard-name table, with its aliases

TABLES_DIR must hold shallow clones of these repositories (github.com/<repo>):

  git clone --depth 1 https://github.com/PCMDI/cmip6-cmor-tables
  git clone --depth 1 https://github.com/PCMDI/cmip5-cmor-tables
  git clone --depth 1 https://github.com/PCMDI/cordex-cmor-tables
  git clone --depth 1 https://github.com/WCRP-CORDEX/cordex-cmip6-cmor-tables
  git clone --depth 1 https://github.com/WCRP-CORDEX/data-request-table
  git clone --depth 1 https://github.com/cf-convention/cf-convention.github.io

Each undefined variable gets the first matching category, in this order:

  encoding error        the IRI decodes to a name with surrounding whitespace
  placeholder           names such as var__
  not a variable        coordinates and netCDF auxiliary variables (CMOR coordinate names, and
                        crs, gridspec, ensemble_member, *_bounds, *_layer)
  CF name in MIP space  a CF standard name (or alias) under variables/mip/
  table entry name      the name of a CMOR table entry whose out_name differs (hfsifrazil2d)
  CMIP5 name            a CMIP5 out_name that is not a CMIP6 out_name; CMIP6 variables with the
                        same standard name that CCKG defines are listed as candidate equivalents
  CORDEX name           a CORDEX out_name that is not a CMIP6 out_name
  UKCP18 variable       a variable of a UKCP18 product (UKCP18 below; checked by hand)
  level variant         a defined or tabulated variable plus a level the tables do not have
                        (ua975, zg50m)
  derived variant       a defined variable plus a product-specific suffix (pr-bc, tasmaxts)
  synonym               a known non-standard synonym (SYNONYMS below)
  unknown               none of the above: product- or model-specific names

Writes results/cckg/undefined-variables.md and undefined-variables.csv.
"""
import argparse
import csv
import glob
import gzip
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V = "https://w3id.org/hacid/data/cs/variables/"
SPEC_PROPS = ("holdsSpecializationOfVariable", "isSpecializationOfVariable", "derivedFromVariable")
LINE = re.compile(r'^\s*(<[^>]*>|_:\S+)\s+<([^>]*)>\s+(<[^>]*>|".*")\s*(?:<([^>]*)>)?\s*\.\s*$')
NOT_VARIABLES = re.compile(r"^(crs|gridspec|ensemble_member|.*_bounds|.*_layer)$")
SUFFIXES = re.compile(r"^(.+?)(Anom|-bc|-fl|ts|max|min)$")
LEVEL = re.compile(r"^(.+?)(\d+m?)$")
# UKCP18 variables that are in no CMOR table. The UKCP18 documentation (CEDA catalogue and UKCP
# User Interface) is not machine-readable here, so the names were checked by hand against it:
#   CEDA uuid 6e61f79cb6b0457eb84edaffcf0aab3a, 3a0012551e464e5b8b3bba3b41a7a60c (circulation
#   indices), UKCP UI product LS1_Subset_02 (extremes), UKCP18 soil-moisture factsheet (beta),
#   CEDA uuid 9f8dfaf790644dbcb2c3f69f409a70d6, UKCP UI product LS1_Sample_01 (anomalies of the
#   probabilistic projections).
UKCP18 = {
    "naodjf": "winter (DJF) Atlantic pressure gradient Iceland-Gibraltar, i.e. the winter NAO (hPa); circulation indices",
    "jetlat": "daily latitude of the North Atlantic jet stream (850 hPa zonal wind); circulation indices",
    "jetstr": "daily strength of the North Atlantic jet stream; circulation indices",
    "wtype8": "daily weather type, 8-type classification; circulation indices",
    "wtype30": "daily weather type, 30-type classification; circulation indices",
    "pr1day": "1-day total precipitation (mm) for a return period; probabilistic extremes (25km)",
    "pr5day": "5-day total precipitation (mm) for a return period; probabilistic extremes (25km)",
    "beta": "soil moisture stress factor (0-100), most likely; Global (60km) soil moisture metrics",
}
UKCP18_ANOMALIES = {"tasAnom", "tasmaxAnom", "tasminAnom", "prAnom", "sfcWindAnom", "hursAnom", "hussAnom",
                    "uasAnom", "vasAnom", "pslAnom", "rlsAnom", "rssAnom", "rsdsAnom", "cltAnom"}
# non-standard synonyms with an obvious standard counterpart (checked by hand)
SYNONYMS = {"u200": "ua200", "u500": "ua500", "u850": "ua850", "v200": "va200", "v500": "va500",
            "v850": "va850", "tmax": "tasmax", "tmin": "tasmin", "sst": "tos"}


def read_dump(dump):
    typed, uses = set(), defaultdict(lambda: defaultdict(int))
    for line in gzip.open(dump, "rt", encoding="utf-8"):
        m = LINE.match(line)
        if not m:
            continue
        s, p, o, g = m.groups()
        if p.endswith("#type"):
            typed.add(s[1:-1])
        if o.startswith("<" + V) and p.endswith(SPEC_PROPS):
            uses[o[1:-1]][(g or "").rsplit("/cs/", 1)[-1]] += 1
    return typed, uses


def read_vocabularies(tables):
    out_names = defaultdict(lambda: defaultdict(set))  # vocabulary -> out_name -> tables
    coords, std = set(), {}
    entries = {}  # table entry name -> out_name, where they differ
    for f in glob.glob(f"{tables}/cmip6-cmor-tables/Tables/CMIP6_*.json"):
        t = json.load(open(f))
        for k, e in t.get("variable_entry", {}).items():
            out_names["CMIP6"][e.get("out_name", k)].add(Path(f).stem[6:])
            if e.get("out_name", k) != k:
                entries.setdefault(k, e["out_name"])
            std.setdefault(("CMIP6", e.get("out_name", k)), e.get("standard_name"))
        for k, e in t.get("axis_entry", {}).items():
            coords |= {k, e.get("out_name", k)}
    for f in glob.glob(f"{tables}/cordex-cmip6-cmor-tables/Tables/CORDEX-CMIP6_*.json"):
        for k, e in json.load(open(f)).get("variable_entry", {}).items():
            out_names["CORDEX-CMIP6"][e.get("out_name", k)].add(Path(f).stem[13:])
            std.setdefault(("CORDEX", e.get("out_name", k)), e.get("standard_name"))
    for f in glob.glob(f"{tables}/data-request-table/data-request/dreq_*.csv"):
        for r in csv.DictReader(open(f)):
            out_names["CORDEX-CMIP6"][r["out_name"]].add(r["frequency"])
            std.setdefault(("CORDEX", r["out_name"]), r["standard_name"])
    for pattern, voc in [("cmip5-cmor-tables/Tables/CMIP5_*", "CMIP5"),
                         ("cordex-cmor-tables/Tables/CORDEX_*", "CORDEX-CMIP5")]:
        for f in glob.glob(f"{tables}/{pattern}"):
            kind = entry = None
            for line in open(f, encoding="latin-1"):
                m = re.match(r"(variable_entry|axis_entry):\s*(\S+)", line)
                if m:
                    kind, entry = m.groups()
                    if kind == "axis_entry":
                        coords.add(entry)
                m = re.match(r"(out_name|standard_name):\s*(\S+)", line)
                if m and kind == "variable_entry":
                    if m.group(1) == "out_name":
                        out_names[voc][m.group(2)].add(Path(f).name.split("_", 1)[1])
                        if m.group(2) != entry:
                            entries.setdefault(entry, m.group(2))
                        entry = m.group(2)
                    else:
                        std.setdefault(("CMIP5" if voc == "CMIP5" else "CORDEX", entry), m.group(2))
                elif m and kind == "axis_entry" and m.group(1) == "out_name":
                    coords.add(m.group(2))
    cf = sorted(glob.glob(f"{tables}/cf-convention.github.io/Data/cf-standard-names/*/src/cf-standard-name-table.xml"),
                key=lambda p: int(p.split("/")[-3]) if p.split("/")[-3].isdigit() else 0)[-1]
    root = ET.parse(cf).getroot()
    cf_names = {e.get("id") for e in root.iter("entry")}
    cf_alias = {a.get("id"): a.find("entry_id").text for a in root.iter("alias")}
    return out_names, coords, std, entries, cf_names, cf_alias, cf.split("/")[-3]


def classify(name, ns, defined_mip, defined_cf, voc, coords, std, entries, cf_names, cf_alias):
    in_voc = {v: sorted(n[name]) for v, n in voc.items() if name in n}
    tabulated = set().union(*voc.values()) | defined_mip
    if name != name.strip():
        return "encoding error", f"`{name.strip()}` " + ("is defined" if name.strip() in defined_mip else "is not defined")
    if re.fullmatch(r"var_*", name):
        return "placeholder", ""
    if name in coords or NOT_VARIABLES.match(name):
        return "not a variable", "CMOR coordinate" if name in coords else "netCDF auxiliary/coordinate variable"
    if ns == "mip" and (name in cf_names or name in cf_alias):
        alias = f"; alias of `{cf_alias[name]}`" if name in cf_alias else ""
        return "CF name in MIP space", ("`variables/cf/" + name + "` is defined" if name in defined_cf else
                                        "not defined as a CF variable either") + alias
    if ns == "cf":
        return ("CF name not defined" if name in cf_names else "not a CF standard name"), ""
    if "CMIP6" in in_voc:
        return "CMIP6 name not defined", ""
    if name in entries:
        out = entries[name]
        return "table entry name", f"CMOR table entry whose variable name is `{out}`" + (
            " (defined)" if out in defined_mip else "")
    if "CMIP5" in in_voc:
        sn = std.get(("CMIP5", name))
        cands = sorted(n for n in voc["CMIP6"] if std.get(("CMIP6", n)) == sn and n in defined_mip) if sn else []
        return "CMIP5 name", (f"`{sn}`" + (f"; CMIP6 variables with this standard name: {', '.join(cands[:4])}"
                                           if cands else "; no CMIP6 variable with this standard name"))
    if any(v.startswith("CORDEX") for v in in_voc):
        return "CORDEX name", ", ".join(f"{v} ({', '.join(t[:3])})" for v, t in in_voc.items())
    if name in UKCP18:
        return "UKCP18 variable", UKCP18[name]
    if name in UKCP18_ANOMALIES:
        return "UKCP18 variable", f"anomaly of `{name[:-4]}` (probabilistic projections)"
    m = LEVEL.match(name)
    if m and m.group(1) in tabulated:
        return "level variant", f"`{m.group(1)}` at `{m.group(2)}`"
    m = SUFFIXES.match(name)
    if m and m.group(1) in defined_mip:
        return "derived variant", f"`{m.group(1)}` + `{m.group(2)}`"
    if name in SYNONYMS:
        std_name = SYNONYMS[name]
        return "synonym", f"`{std_name}`" + (" (defined)" if std_name in defined_mip else " (not defined either)")
    return "unknown", ""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tables", type=Path)
    p.add_argument("--dump", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "results" / "cckg")
    args = p.parse_args()
    dump = args.dump or ROOT / "data" / "cckg" / json.loads((ROOT / "data/cckg/kg.json").read_text())["files"][0]
    typed, uses = read_dump(dump)
    defined_mip = {v[len(V) + 4:] for v in typed if v.startswith(V + "mip/")}
    defined_cf = {v[len(V) + 3:] for v in typed if v.startswith(V + "cf/")}
    voc, coords, std, entries, cf_names, cf_alias, cf_version = read_vocabularies(args.tables)

    rows = []
    for v, by_source in uses.items():
        if v in typed:
            continue
        ns, raw = v[len(V):].split("/", 1)
        name = urllib.parse.unquote(raw)
        cat, detail = classify(name, ns, defined_mip, defined_cf, voc, coords, std, entries, cf_names, cf_alias)
        rows.append({"variable": f"{ns}/{raw}", "category": cat, "detail": detail,
                     "links": sum(by_source.values()),
                     "sources": "; ".join(f"{g} ({n})" for g, n in sorted(by_source.items(), key=lambda x: -x[1]))})
    rows.sort(key=lambda r: (r["category"], -r["links"]))
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "undefined-variables.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_markdown(args.out / "undefined-variables.md", rows, len(defined_mip), len(defined_cf), cf_version)
    print((args.out / "undefined-variables.md").read_text())


def write_markdown(path, rows, n_mip, n_cf, cf_version):
    cats = defaultdict(list)
    for r in rows:
        cats[r["category"]].append(r)
    src = Counter()
    lines = ["# Undefined variables in CCKG", "",
             "Generated by `analysis/cckg_variables.py`; see its docstring for the vocabularies and the "
             f"categories. CCKG defines {n_mip:,} MIP and {n_cf:,} CF variables; the CF table used is "
             f"version {cf_version}. *Links* are the triples of `holdsSpecializationOfVariable`, "
             "`isSpecializationOfVariable` and `derivedFromVariable` that point to the variable.", "",
             "| category | variables | links | sources (variables) |", "|---|---|---|---|"]
    for cat, rs in sorted(cats.items(), key=lambda x: -len(x[1])):
        src = Counter(s.split(" (")[0] for r in rs for s in r["sources"].split("; "))
        lines.append(f"| {cat} | {len(rs)} | {sum(r['links'] for r in rs):,} | "
                     + ", ".join(f"`{s}` ({n})" for s, n in src.most_common()) + " |")
    for cat, rs in sorted(cats.items(), key=lambda x: -len(x[1])):
        lines += ["", f"## {cat}", "", "| variable | links | detail | sources (links) |", "|---|---|---|---|"]
        for r in sorted(rs, key=lambda r: -r["links"]):
            lines.append(f"| `{r['variable']}` | {r['links']:,} | {r['detail']} | {r['sources']} |")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

# Why some CCKG variables are undefined

In the 2026-10-07 dump, 296 variables are linked but never defined (no `rdf:type`): 295 under
`variables/mip/` and 1 under `variables/cf/`. They are the values of
`data:holdsSpecializationOfVariable`, `data:isSpecializationOfVariable` (D4 in the
[change log](cckg-change-log.md), 282 variables) and `data:derivedFromVariable` (14 more). This note
looks for the cause of each mismatch. The full list, with the evidence for each variable, is in
[`results/cckg/undefined-variables.md`](../results/cckg/undefined-variables.md); it is produced by
[`analysis/cckg_variables.py`](../analysis/cckg_variables.py).

## The vocabulary CCKG defines

- **MIP variables:** CCKG defines 1,271 of them, all in the graph `cmip6/cmor-tables`. They are
  exactly the variable names (`out_name`) of the CMIP6 CMOR tables, data specs 01.00.33, which have
  1,275. Nothing else is defined under `variables/mip/`.
- **CF variables:** CCKG defines 4,870 CF standard names, about the size of version 86 of the CF
  standard-name table (4,872 names). The current version, 95, has 5,097.

The datasets, however, come from projects that use other vocabularies: CMIP5 (`cmip5/datasets`),
CORDEX for CMIP5 (`cordex-cmip5/datasets`), UKCP18 (`ukcp18`) and the Met Office controlled
vocabularies (`mohc-cvs`). Each undefined variable was therefore looked up in the CMIP5 and CMIP6
CMOR tables, the CORDEX tables for CMIP5 and CMIP6 (with the CORDEX-CMIP6 data request) and the CF
standard-name table, version 95 with its aliases.

## Causes

| cause | variables | links | where | examples |
|---|---|---|---|---|
| CMIP5 variable, not in CMIP6 | 112 | 33,462 | `cmip5/datasets` | `sic`, `sit`, `tro3`, `rhs`, `transix`, `zosga`, `concbc` |
| CORDEX variable, not in CMIP6 | 61 | 72,298 | `cordex-cmip5/datasets` | `ua850`, `ta200`, `zg500`, `clh`, `sund`, `wsgsmax`, `ua50m` |
| derived product variable | 19 | 51,292 | `ukcp18`, `cordex-cmip5/datasets` | `tasAnom`, `prAnom`, `tasmax-bc`, `pr-fl`, `tasmaxts` |
| pressure or height level not in any table | 25 | 1,130 | `cordex-cmip5/datasets` | `ta975`, `hur850`, `wap700`, `zg50m`, `cdnc500` |
| CF standard name used as a MIP variable | 14 | 720 | `mohc-cvs`, `ukcp18` | `air_temperature`, `sea_surface_height_above_geoid` |
| non-standard synonym | 9 | 789 | `cordex-cmip5/datasets`, `mohc-cvs` | `u850` (for `ua850`), `sst` (for `tos`), `tmax` (for `tasmax`) |
| not a variable | 5 | 12,331 | all three dataset graphs | `ensemble_member`, `crs`, `soil_bounds`, `soil_layer`, `gridspec` |
| CMOR table entry name instead of variable name | 2 | 44 | `cmip5/datasets` | `hfsifrazil2d` (variable `hfsifrazil`) |
| CF name newer than CCKG's CF table | 1 | 1 | `cmip6/cmor-tables` | `isotope_ratio_of_2H_to_1H_in_sea_water_excluding_solutes_and_solids` |
| typo or placeholder | 2 | 135 | `mohc-cvs`, `ukcp18` | `mrso%20` (trailing space), `var__` |
| not found in any vocabulary | 46 | 6,238 | `cordex-cmip5/datasets`, `ukcp18`, `cmip5/datasets` | `naodjf`, `jetlat`, `wtype8`, `pr1day`, `alb`, `apet`, `clwmr850` |

*Links* counts the triples pointing to these variables; a variable can be linked from several
graphs.

### 1. Variables of other projects (173 variables, most links)

Most undefined variables are well-defined names in the CMOR tables of CMIP5 or CORDEX. They are
missing only because CCKG imports the CMIP6 tables alone.

- **CMIP5 (112 variables, from `cmip5/datasets`).** Many were renamed in CMIP6, especially the sea-ice
  variables that moved from `OImon` to the SIMIP tables: `sic` → `siconc`, `sit` → `sithick`,
  `ageice` → `siage`, `usi`/`vsi` → `siu`/`siv`, `streng` → `sicompstren`, `ssi` → `sisali`. Others
  were renamed elsewhere, e.g. `tro3` → `o3`, `rhs` → `hurs`, `tso` → `tos`. For 48 of the 112, a
  CMIP6 variable that CCKG defines has the same CF standard name. This is a candidate equivalent, to
  be confirmed by hand (`rhs` matches `hur` as well as `hurs`, for instance). The other 64 have no
  CMIP6 counterpart, e.g. the CMIP5 aerosol concentrations (`concbc`, `concso4`) and `zosga`.
- **CORDEX (61 variables, from `cordex-cmip5/datasets`).** CORDEX stores the variables of each
  pressure level separately (`ua850`, `ta200`, `zg500`) and has its own variables, such as the cloud
  layers `clh`/`cll`/`clm`, sunshine duration `sund` and gusts `wsgsmax`. CMIP6 only has a few of
  the single-level variables: `ta850`, `hus850` and `zg500` are defined, `ua850` and `ta200` are not.

**Possible fix:** import the CMIP5 and CORDEX tables as well, in their own namespaces or under
`variables/mip/`. Link renamed variables to their CMIP6 successors, e.g. with `skos:closeMatch` or a
shared `isSpecializationOfVariable` to the CF variable, which the tables already give.

### 2. Names derived from tabulated variables (44 variables)

- **Product-specific variants (19).** UKCP18 publishes anomalies under its own names (`tasAnom`,
  `prAnom`, …; 50,240 links), and some CORDEX datasets carry bias-corrected or otherwise processed
  variables (`tasmax-bc`, `pr-bc`, `pr-fl`, `tasmaxts`). The base variable is always defined.
- **Levels not in any table (25).** For example, `ta975`, `hur850`, `wap700` and `zg50m` in CORDEX
  datasets, where the tables only have some levels.

**Possible fix:** define these as specializations of the base variable, e.g. `tasAnom`
`isSpecializationOfVariable` `tas`, with the level or the processing as the specialization.

### 3. Names in the wrong place or wrong form (33 variables)

- **CF standard names under `variables/mip/` (14).** `mohc-cvs` and `ukcp18` refer to
  `variables/mip/air_temperature` or `variables/mip/sea_surface_height_above_geoid`, which exist
  under `variables/cf/`. The exception is `air_pressure_at_sea_level`, which is an *alias* in the CF
  table (of `air_pressure_at_mean_sea_level`) and is not defined at all.
- **Non-standard synonyms (9).** `u850`/`v850` (also at 200 and 500 hPa) for `ua850`/`va850`, `sst`
  for `tos`, and `tmax`/`tmin` for `tasmax`/`tasmin`.
- **Not variables (5).** `ensemble_member` (UKCP18, 12,156 links), `crs`, `soil_bounds`,
  `soil_layer` and `gridspec` are coordinates, grid mappings or grid files in the netCDF files.
  They were probably taken from the files' variable list.
- **Table entry instead of variable name (2).** `hfsifrazil2d` and `hfsithermds2d` are CMIP5 table
  entries whose variables are named `hfsifrazil` and `hfsithermds`.
- **Typo and placeholder.** `mrso%20` (with a trailing space; `mrso` is defined) and `var__`.
- **Newer CF name (1).** The CMIP6 tables use the standard name
  `isotope_ratio_of_2H_to_1H_in_sea_water_excluding_solutes_and_solids`, added in version 90 of
  the CF table, which is newer than CCKG's CF variables.

**Possible fix:** correct the IRIs in the converters, and drop links to coordinates. Update the CF
variables to a recent CF table version.

### 4. Not found (46 variables)

These names appear in none of the vocabularies.
- **UKCP18 (8):** circulation and index variables such as `naodjf` (NAO index, DJF), `jetlat`/`jetstr`
  (jet latitude and strength), `wtype8`/`wtype30` (weather types), `pr1day`/`pr5day` and `beta`.
- **CORDEX (32):** model-specific output, such as `alb`, `apet`, `ustar`, `zo`, `mrsosat`,
  `snownc`, cloud fields at pressure levels (`clfr850`, `clice500`, `clwmr200`) and `thetapw850`.
- **CMIP5 (6):** including `rtoa`, `orograw`, `pbp`, `lm` and `swit`.

These need definitions of their own, from the products' documentation.

## Per source

| source | undefined variables | links | main causes |
|---|---|---|---|
| `cordex-cmip5/datasets` | 138 | 78,426 | CORDEX variables (61), not found (32), levels (25) |
| `ukcp18` | 23 | 68,156 | UKCP18 anomalies (10), UKCP18-specific names (8), `ensemble_member` |
| `cmip5/datasets` | 122 | 31,837 | CMIP5 variables (112) |
| `mohc-cvs` | 14 | 20 | CF names under `variables/mip/` (11), synonyms, `mrso%20` |
| `cmip6/cmor-tables` | 1 | 1 | newer CF name |

Compared with all the variables each source links to (see
[dangling-by-source.md](../results/cckg/dangling-by-source.md)): `cordex-cmip5/datasets` links 209
MIP variables, of which 138 are undefined (66%); `cmip5/datasets` 546, of which 122 (22%);
`ukcp18` 46, of which 23 (50%).

# Digoxin (Serum or plasma)

## Analyte

- **Component:** Digoxin
- **System (matrix):** Serum or plasma
- **Kind of property:** Substance concentration
- **Reporting unit:** ng/mL (nmol/L)
- **Analyte id:** `dig`
- **Other spellings in the literature:** Digoxin, total; apparent digoxin

## Analytical performance specification

- **Selected APS:** 3.0% (allowable bias (relative), user-selected)

Every row was judged against this APS. The machine-readable record is `digoxin_serum_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 29 |
| Evidence tables | 25 |
| Evidence rows | 4,277 |
| Rows with a numeric percent change (plottable) | 1,789 |
| Rows exceeding the 3.0% APS | 1,859 |
| Rows within the 3.0% APS | 390 |
| Rows with a DOI | 1,355 |
| Rows with a PubMed ID | 1,883 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `dig.dlis` | Digoxin-like immunoreactive substances (DLIS) | `endogenous_substance` | 840 |
| `dig.canrenone` | Canrenone | `drug_cross_reactivity` | 465 |
| `dig.digoxigenin` | Digoxigenin and its mono- or bis-digitoxosides (digoxin metabolites) | `cardiac_glycoside` | 463 |
| `dig.oleandrin` | Oleandrin / oleander extract | `cardiac_glycoside` | 453 |
| `dig.danshen` | Danshen (Salvia miltiorrhiza) | `herbal_supplement` | 356 |
| `dig.spironolactone` | Spironolactone | `drug_cross_reactivity` | 203 |
| `dig.digoxin_immune_fab` | Digoxin immune Fab (Digibind) | `antidote` | 197 |
| `dig.convallatoxin` | Convallatoxin / lily of the valley (Convallaria majalis) | `cardiac_glycoside` | 179 |
| `dig.dihydrodigoxin` | Dihydrodigoxin | `cardiac_glycoside` | 144 |
| `dig.digitoxin` | Digitoxin | `cardiac_glycoside` | 143 |
| `dig.asian_ginseng` | Asian ginseng (Panax ginseng) | `herbal_supplement` | 128 |
| `dig.siberian_ginseng` | Siberian ginseng (Eleutherococcus senticosus) | `herbal_supplement` | 120 |
| `dig.ashwagandha` | Ashwagandha (Withania somnifera) | `herbal_supplement` | 96 |
| `dig.lu_shen_wan` | Lu-Shen-Wan (Chinese medicine) | `herbal_supplement` | 85 |
| `dig.bufalin` | Bufalin (bufadienolide of toad venom preparations) | `cardiac_glycoside` | 49 |
| `dig.cardiac_glycosides` | Cardiac glycosides and digoxin metabolites (mixed) | `cardiac_glycoside` | 47 |
| `dig.hemolysis` | Hemolysis (hemoglobin) | `hemolysis` | 44 |
| `dig.biotin` | Biotin | `biotin` | 35 |
| `dig.prednisolone` | Prednisolone | `steroid` | 32 |
| `dig.hawthorn` | Hawthorn (Crataegus spp.) | `herbal_supplement` | 31 |
| `dig.hama` | Human anti-mouse / heterophilic antibodies (HAMA) | `heterophilic_antibodies` | 28 |
| `dig.animal_immunoglobulin` | Heterologous animal immunoglobulin (goat or horse serum IgG, anti-lymphocyte globulin) | `heterophilic_antibodies` | 24 |
| `dig.enzalutamide` | Enzalutamide | `drug_cross_reactivity` | 24 |
| `dig.free_kappa` | Free kappa light chains | `paraprotein` | 23 |
| `dig.chan_su` | Chan Su (toad venom preparation) | `herbal_supplement` | 18 |
| `dig.hydrocortisone` | Hydrocortisone / cortisol | `steroid` | 18 |
| `dig.lipemia` | Lipemia (triglycerides) | `lipemia` | 14 |
| `dig.bilirubin` | Bilirubin (icterus) | `bilirubin` | 13 |
| `dig.uzara` | Uzara root extract (Xysmalobium undulatum) | `herbal_supplement` | 5 |

## Files

- `digoxin_serum_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `digoxin_serum_interferent_list.csv` - the 29 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


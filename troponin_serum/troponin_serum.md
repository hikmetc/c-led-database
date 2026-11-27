# Cardiac troponin I and T (Serum, plasma or blood)

## Analyte

- **Component:** Cardiac troponin I and T
- **System (matrix):** Serum, plasma or blood
- **Kind of property:** Mass concentration
- **Reporting unit:** ng/L (pg/mL)
- **Analyte id:** `tn`
- **Other spellings in the literature:** cTnI; cTnT; hs-cTnI; hs-cTnT; high-sensitivity cardiac troponin

## Analytical performance specification

- **Selected APS:** 13.6% (allowable bias (relative), user-selected)

Every row was judged against this APS. The machine-readable record is `troponin_serum_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 11 |
| Evidence tables | 10 |
| Evidence rows | 679 |
| Rows with a numeric percent change (plottable) | 413 |
| Rows exceeding the 13.6% APS | 317 |
| Rows within the 13.6% APS | 231 |
| Rows with a DOI | 591 |
| Rows with a PubMed ID | 149 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `tn.hemolysis` | Hemolysis (hemoglobin) | `hemolysis` | 246 |
| `tn.biotin` | Biotin | `biotin` | 239 |
| `tn.troponin_autoantibodies` | Troponin autoantibodies | `autoantibody` | 62 |
| `tn.macrotroponin` | Macrotroponin | `protein_complex` | 33 |
| `tn.alkaline_phosphatase` | Alkaline phosphatase, elevated endogenous | `endogenous_substance` | 28 |
| `tn.heterophile_antibodies` | Heterophile antibodies | `heterophilic_antibodies` | 28 |
| `tn.fibrin` | Fibrin clots / strands from incomplete separation | `specimen_quality` | 17 |
| `tn.lipemia` | Lipemia | `lipemia` | 9 |
| `tn.skeletal_tnt` | Skeletal muscle troponin T isoform cross-reactivity | `cross_reactivity` | 9 |
| `tn.rheumatoid_factor` | Rheumatoid factor | `heterophilic_antibodies` | 6 |
| `tn.asfotase_alfa` | Asfotase alfa | `drug_interference` | 2 |

## Files

- `troponin_serum_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `troponin_serum_interferent_list.csv` - the 11 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


# International Normalized Ratio (prothrombin time) (Plasma or blood)

## Analyte

- **Component:** International Normalized Ratio (prothrombin time)
- **System (matrix):** Plasma or blood
- **Kind of property:** Relative time ratio
- **Reporting unit:** ratio (INR); s (PT)
- **Analyte id:** `inr`
- **Other spellings in the literature:** INR; International Normalised Ratio; prothrombin time, PT

## Analytical performance specification

- **Selected APS:** 2.0% (allowable bias (relative), user-selected)

Every row was judged against this APS. The machine-readable record is `inr_plasma_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 24 |
| Evidence tables | 19 |
| Evidence rows | 3,669 |
| Rows with a numeric percent change (plottable) | 2,550 |
| Rows exceeding the 2.0% APS | 1,815 |
| Rows within the 2.0% APS | 1,019 |
| Rows with a DOI | 2,182 |
| Rows with a PubMed ID | 1,532 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `inr.thromboplastin_isi` | Thromboplastin reagent sensitivity / ISI value and ISI verification | `reagent_calibration` | 1443 |
| `inr.daptomycin` | Daptomycin | `drug_interference` | 950 |
| `inr.prolonged_storage` | Prolonged storage before analysis | `delayed_analysis` | 192 |
| `inr.ufh` | Unfractionated heparin contamination | `anticoagulant_contamination` | 141 |
| `inr.lupus_anticoagulant` | Lupus anticoagulant | `autoantibody` | 122 |
| `inr.mnpt` | Mean normal prothrombin time (MNPT) used in the INR calculation | `reagent_calibration` | 116 |
| `inr.lmwh` | Low-molecular-weight heparin (dalteparin) contamination | `anticoagulant_contamination` | 113 |
| `inr.lipemia` | Lipemia (intravenous lipid emulsion, triglycerides) | `lipemia` | 97 |
| `inr.dabigatran` | Dabigatran (direct thrombin inhibitor) | `anticoagulant_drug` | 69 |
| `inr.bilirubin` | Bilirubin / icterus (conjugated and unconjugated) | `bilirubin` | 57 |
| `inr.underfilled_tube` | Underfilled citrate tube | `collection_tube` | 52 |
| `inr.elevated_temperature` | Elevated temperature / hyperthermia | `temperature` | 51 |
| `inr.hemolysis` | Hemolysis | `hemolysis` | 41 |
| `inr.poor_mixing` | Poor mixing of the collection tube | `collection_technique` | 35 |
| `inr.rivaroxaban` | Rivaroxaban (direct factor Xa inhibitor) | `anticoagulant_drug` | 35 |
| `inr.apixaban` | Apixaban (direct factor Xa inhibitor) | `anticoagulant_drug` | 30 |
| `inr.citrate_concentration` | Sodium citrate concentration of the collection tube (3.2% vs 3.8%) | `collection_tube` | 24 |
| `inr.heparin_contamination` | Heparin contamination of the specimen or line draw | `anticoagulant_contamination` | 21 |
| `inr.high_hematocrit` | Elevated hematocrit / polycythemia | `specimen_matrix` | 19 |
| `inr.venous_stasis` | Venous stasis / prolonged tourniquet application | `tourniquet_stasis` | 16 |
| `inr.clotted_specimen` | Clotted specimen / micro-clots | `specimen_quality` | 15 |
| `inr.edoxaban` | Edoxaban (direct factor Xa inhibitor) | `anticoagulant_drug` | 12 |
| `inr.oxalate` | Oxalate anticoagulant used in place of citrate | `anticoagulant_contamination` | 10 |
| `inr.anticoagulant_contamination` | Anticoagulant contamination of the specimen (mixed) | `anticoagulant_contamination` | 8 |

## Files

- `inr_plasma_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `inr_plasma_interferent_list.csv` - the 24 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


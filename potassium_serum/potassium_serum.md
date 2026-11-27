# Potassium (Serum)

## Analyte

- **Component:** Potassium
- **System (matrix):** Serum
- **Kind of property:** Substance concentration
- **Reporting unit:** mmol/L
- **Analyte id:** `k`
- **Other spellings in the literature:** Potassium; K+; serum potassium; plasma potassium (comparison arms)

## Analytical performance specification

- **Selected APS:** 0.4% (allowable bias (relative), user-selected)

Every row was judged against this APS. The machine-readable record is `potassium_serum_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 12 |
| Evidence tables | 12 |
| Evidence rows | 304 |
| Rows with a numeric percent change (plottable) | 181 |
| Rows exceeding the 0.4% APS | 186 |
| Rows within the 0.4% APS | 29 |
| Rows with a DOI | 293 |
| Rows with a PubMed ID | 203 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `k.leukocytosis` | Leukocytosis | `leukocytosis` | 57 |
| `k.hemolysis` | Hemolysis | `hemolysis` | 55 |
| `k.reverse_pseudohyperkalemia` | Reverse pseudohyperkalemia | `specimen_matrix` | 41 |
| `k.indirect_ise` | Indirect ISE electrolyte-exclusion matrix effect (elevated triglycerides, total protein, cholesterol) | `analyzer_method` | 27 |
| `k.k_edta` | K-EDTA (K2EDTA / K3EDTA) contamination or carryover | `anticoagulant_contamination` | 25 |
| `k.fist_clenching` | Handgrip (fist clenching) during venipuncture | `collection_technique` | 21 |
| `k.tourniquet_stasis` | Tourniquet application / venous stasis | `tourniquet_stasis` | 19 |
| `k.delayed_centrifugation` | Delayed centrifugation / prolonged contact with cells or clot | `centrifugation` | 13 |
| `k.cold_storage` | Refrigerated or cold storage of whole blood before centrifugation | `storage_temperature` | 12 |
| `k.collection_device` | Needle gauge / blood collection device | `collection_technique` | 12 |
| `k.thrombocytosis` | Thrombocytosis | `thrombocytosis` | 12 |
| `k.order_of_draw` | Order of draw (serum tube drawn after an EDTA or heparin tube) | `collection_technique` | 10 |

## Files

- `potassium_serum_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `potassium_serum_interferent_list.csv` - the 12 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


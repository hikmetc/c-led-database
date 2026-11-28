# Oxygen partial pressure (Blood)

## Analyte

- **Component:** Oxygen partial pressure
- **System (matrix):** Blood
- **Kind of property:** Partial pressure
- **Reporting unit:** mmHg (kPa)
- **Analyte id:** `po2`
- **Other spellings in the literature:** pO2; PO2; paO2; PaO2

## Analytical performance specification

- **Selected APS:** 3.0% (allowable bias (relative), user-selected)

Every row was judged against this APS. The machine-readable record is `po2_blood_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 13 |
| Evidence tables | 13 |
| Evidence rows | 527 |
| Rows with a numeric percent change (plottable) | 164 |
| Rows exceeding the 3.0% APS | 261 |
| Rows within the 3.0% APS | 84 |
| Rows with a DOI | 363 |
| Rows with a PubMed ID | 280 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `po2.storage_temperature` | Storage temperature (room temperature versus on ice) | `storage_temperature` | 229 |
| `po2.delayed_analysis` | Delayed analysis / storage time at room temperature | `delayed_analysis` | 59 |
| `po2.syringe_material` | Plastic versus glass sampling syringe (gas permeability of plastic) | `syringe_material` | 47 |
| `po2.liquid_heparin` | Excess liquid heparin in the syringe | `anticoagulant_contamination` | 36 |
| `po2.leukocytosis` | Leukocytosis (leukocyte larceny) | `leukocytosis` | 28 |
| `po2.pneumatic_transport` | Pneumatic tube transport | `pneumatic_transport` | 27 |
| `po2.air_bubble` | Air bubble in the syringe | `air_contamination` | 25 |
| `po2.halothane` | Halothane (volatile anaesthetic) | `volatile_anaesthetic` | 20 |
| `po2.nitrous_oxide` | Nitrous oxide | `volatile_anaesthetic` | 18 |
| `po2.hemolysis` | Hemolysis | `hemolysis` | 16 |
| `po2.thrombocytosis` | Thrombocytosis (platelet larceny) | `thrombocytosis` | 16 |
| `po2.enflurane` | Enflurane (volatile anaesthetic) | `volatile_anaesthetic` | 5 |
| `po2.isoflurane` | Isoflurane (volatile anaesthetic) | `volatile_anaesthetic` | 1 |

## Files

- `po2_blood_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `po2_blood_interferent_list.csv` - the 13 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


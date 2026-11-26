# pH (Blood)

## Analyte

- **Component:** pH
- **System (matrix):** Blood
- **Kind of property:** pH (negative log of hydrogen ion activity)
- **Reporting unit:** pH unit
- **Analyte id:** `ph`
- **Other spellings in the literature:** blood pH; arterial pH

## Analytical performance specification

- **Selected APS:** 1.5% (allowable total error (relative), user-selected)
- **Note:** pH is measured in absolute units; several source studies use an allowable difference of 0.02-0.04 pH units instead of a percentage.

Every row was judged against this APS. The machine-readable record is `ph_blood_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 11 |
| Evidence tables | 10 |
| Evidence rows | 182 |
| Rows with a numeric percent change (plottable) | 67 |
| Rows exceeding the 1.5% APS | 36 |
| Rows within the 1.5% APS | 76 |
| Rows with a DOI | 161 |
| Rows with a PubMed ID | 97 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `ph.delayed_analysis` | Analysis delay at room temperature | `delayed_analysis` | 58 |
| `ph.wrong_sample_type` | Wrong sample type (peripheral or central venous, or capillary blood instead of arterial) | `sample_type` | 39 |
| `ph.patient_temperature` | Patient temperature other than 37 C (temperature correction) | `temperature` | 18 |
| `ph.air_bubble` | Air bubble / room-air contamination in the syringe | `air_contamination` | 13 |
| `ph.ice_overchilling` | Direct ice contact / over-chilling of the syringe | `storage_temperature` | 13 |
| `ph.liquid_heparin` | Liquid heparin / liquid anticoagulant or diluent | `anticoagulant_contamination` | 10 |
| `ph.tpn_lipid` | Total parenteral nutrition / lipid emulsion contamination | `lipemia` | 10 |
| `ph.reference_interval` | Inappropriate reference interval (pregnancy, age, altitude) | `interpretation` | 9 |
| `ph.dextrose_50` | Dextrose 50% (D50) contamination of the sample | `iv_fluid_contamination` | 6 |
| `ph.leukocytosis` | Leukocytosis (leukocyte larceny) | `leukocytosis` | 4 |
| `ph.ethylene_glycol` | Ethylene glycol | `toxin` | 2 |

## Files

- `ph_blood_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `ph_blood_interferent_list.csv` - the 11 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


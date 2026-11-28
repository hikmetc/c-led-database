# Carbon dioxide partial pressure (Blood)

## Analyte

- **Component:** Carbon dioxide partial pressure
- **System (matrix):** Blood
- **Kind of property:** Partial pressure
- **Reporting unit:** mmHg (kPa)
- **Analyte id:** `pco2`
- **Other spellings in the literature:** pCO2; PCO2; pCO₂; paCO2

## Analytical performance specification

- **Selected APS:** 2.7% (allowable bias (relative), user-selected)

Every row was judged against this APS. The machine-readable record is `pco2_blood_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 9 |
| Evidence tables | 8 |
| Evidence rows | 139 |
| Rows with a numeric percent change (plottable) | 69 |
| Rows exceeding the 2.7% APS | 64 |
| Rows within the 2.7% APS | 37 |
| Rows with a DOI | 111 |
| Rows with a PubMed ID | 75 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `pco2.delayed_analysis` | Delayed analysis at room temperature | `delayed_analysis` | 32 |
| `pco2.air_bubble` | Air bubble / ambient-air contamination in the syringe | `air_contamination` | 27 |
| `pco2.liquid_heparin` | Liquid heparin (excess liquid heparin or heparinized saline) | `anticoagulant_contamination` | 22 |
| `pco2.syringe_material` | Plastic versus glass sampling syringe (syringe material) | `syringe_material` | 20 |
| `pco2.leukocytosis` | Leukocytosis (leukocyte larceny) | `leukocytosis` | 14 |
| `pco2.pneumatic_transport` | Pneumatic tube transport | `pneumatic_transport` | 8 |
| `pco2.tpn_lipid` | Total parenteral nutrition / lipid emulsion contamination | `lipemia` | 8 |
| `pco2.dextrose_50` | Dextrose 50% (D50) contamination of the sample | `iv_fluid_contamination` | 6 |
| `pco2.air_bubble_30min` | Air bubble trapped in the syringe for 30 min before expulsion | `air_contamination` | 2 |

## Files

- `pco2_blood_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `pco2_blood_interferent_list.csv` - the 9 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


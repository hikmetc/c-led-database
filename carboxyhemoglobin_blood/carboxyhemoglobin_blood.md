# Carboxyhemoglobin (Blood)

## Analyte

- **Component:** Carboxyhemoglobin
- **System (matrix):** Blood
- **Kind of property:** Substance fraction of total haemoglobin
- **Reporting unit:** % of total haemoglobin
- **Analyte id:** `cohb`
- **Other spellings in the literature:** Carboxyhaemoglobin; COHb; COHb%; carboxyhemoglobin saturation

## Analytical performance specification

- **Selected APS:** 1.0% (allowable bias (relative), user-selected)
- **Note:** 1% is read as 1 percentage point of COHb saturation in several source studies.

Every row was judged against this APS. The machine-readable record is `carboxyhemoglobin_blood_analyte.csv`; the derived build also carries `pct_change` per row, so a site can re-judge every row against a user-supplied APS instead of this one.

## Contents

| | |
|---|---|
| Interference causes | 27 |
| Evidence tables | 20 |
| Evidence rows | 1,951 |
| Rows with a numeric percent change (plottable) | 1,274 |
| Rows exceeding the 1.0% APS | 1,318 |
| Rows within the 1.0% APS | 83 |
| Rows with a DOI | 1,017 |
| Rows with a PubMed ID | 0 |

## Interference causes

| interferent_id | Interferent | Concept | Rows |
|---|---|---|---|
| `cohb.low_total_hemoglobin` | Low total hemoglobin concentration | `specimen_matrix` | 496 |
| `cohb.methemoglobin` | Methemoglobin | `hemoglobin_derivative` | 271 |
| `cohb.heat_exposure` | Heat exposure / thermal coagulation of blood | `temperature` | 252 |
| `cohb.putrefaction` | Putrefaction / postmortem decomposition | `postmortem_change` | 195 |
| `cohb.hydroxocobalamin` | Hydroxocobalamin (Cyanokit) | `vitamin_b12` | 103 |
| `cohb.postmortem_storage` | Postmortem storage of the specimen | `storage_temperature` | 82 |
| `cohb.fetal_hemoglobin` | Fetal hemoglobin (HbF) | `hemoglobin_derivative` | 79 |
| `cohb.methylene_blue` | Methylene blue | `dye` | 72 |
| `cohb.pleural_fluid` | Pleural fluid used in place of blood | `specimen_matrix` | 55 |
| `cohb.uncapped_storage` | Uncapped storage / air headspace above the sample | `air_contamination` | 52 |
| `cohb.pericardial_fluid` | Pericardial fluid used in place of blood | `specimen_matrix` | 43 |
| `cohb.sulfhemoglobin` | Sulfhemoglobin | `hemoglobin_derivative` | 36 |
| `cohb.hboc` | Hemoglobin-based oxygen carriers (DCLHb, HemoLink, Apex PHP, rHb1.1, Oxyglobin) | `oxygen_carrier` | 35 |
| `cohb.formalin_fixation` | Formalin fixation / embalming (formaldehyde) | `preservative` | 29 |
| `cohb.postmortem_co_diffusion` | Postmortem carbon monoxide diffusion into the body | `postmortem_change` | 26 |
| `cohb.patent_blue_v` | Patent blue V / isosulfan blue | `dye` | 21 |
| `cohb.thoracic_cavity_fluid` | Thoracic or chest cavity fluid or blood used in place of blood | `specimen_matrix` | 21 |
| `cohb.cyanocobalamin` | Cyanocobalamin | `vitamin_b12` | 16 |
| `cohb.fluorescein` | Fluorescein (sodium fluorescein) | `dye` | 13 |
| `cohb.perflubron` | Perflubron emulsion (perfluorocarbon) | `oxygen_carrier` | 13 |
| `cohb.hb_m_variants` | Hemoglobin M variants (Hb M Saskatoon, Hb M Hyde Park, Hb M Boston) | `hemoglobin_derivative` | 11 |
| `cohb.bilirubin` | Hyperbilirubinemia (bilirubin, icteric sample) | `bilirubin` | 9 |
| `cohb.blood_ph` | Blood pH of the sample or analysis medium | `sample_condition` | 7 |
| `cohb.hemolysis` | Hemolysis / cell-free hemoglobin | `hemolysis` | 7 |
| `cohb.ascitic_fluid` | Ascites used in place of blood | `specimen_matrix` | 4 |
| `cohb.body_cavity_fluid` | Body cavity fluid used in place of blood | `specimen_matrix` | 2 |
| `cohb.bile` | Bile used in place of blood | `specimen_matrix` | 1 |

## Files

- `carboxyhemoglobin_blood_analyte.csv` - the analyte record: component, system, unit, selected APS.
- `carboxyhemoglobin_blood_interferent_list.csv` - the 27 interference causes, with ids and concepts.
- `database/` - the source evidence tables, one CSV per interferent, all sharing the same 29 columns (see `meta/data_dictionary.csv`).


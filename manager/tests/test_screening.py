#!/usr/bin/env python3
"""Direct tests of the rejection rules in scripts/screening.py. No files are changed.
Run:  .venv/bin/python manager/tests/test_screening.py"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import screening as S

failed = 0


def check(what, got, want):
    global failed
    if got != want:
        failed += 1
        print(f"  FAILED  {what}: got {got!r}, expected {want!r}")
    else:
        print(f"  ok      {what}")


# ---- criterion 22: the system is a definition; every matrix it names is accepted
def kind(system, sample):
    return S.specimen_mismatch(system, sample)[0]


check("'Plasma or blood' accepts citrated whole blood", kind("Plasma or blood", "Citrated whole blood from outpatients on oral anticoagulation therapy; centrifuged just before each test"), None)
check("'Plasma or blood' accepts plasma", kind("Plasma or blood", "Pooled normal plasma"), None)
check("'Plasma or blood' rejects serum", kind("Plasma or blood", "Serum"), "matrix")
check("'Serum or plasma' accepts plasma", kind("Serum or plasma", "Heparinized plasma"), None)
check("'Serum or plasma' accepts serum", kind("Serum or plasma", "Human serum pool"), None)
check("'Serum or plasma' rejects whole blood", kind("Serum or plasma", "Whole blood"), "matrix")
check("'Serum, plasma or whole blood' accepts whole blood", kind("Serum, plasma or whole blood", "EDTA whole blood"), None)
check("'Serum' rejects plasma", kind("Serum", "Heparinized plasma, spiked"), "matrix")
check("'Serum' accepts serum described with its blood draw", kind("Serum", "Serum (blood drawn 1 h after dosing)"), None)
check("'Platelet-poor plasma (citrated)' rejects citrated whole blood", kind("Platelet-poor plasma (citrated)", "Citrated whole blood"), "matrix")
check("'Platelet-poor plasma (citrated)' accepts plasma", kind("Platelet-poor plasma (citrated)", "Citrated plasma, pooled"), None)
check("'Blood' accepts whole blood of any vessel", kind("Blood", "Venous whole blood, heparinized syringe"), None)
check("'Blood' rejects serum", kind("Blood", "Serum"), "matrix")
check("'Blood (arterial)' rejects venous blood", kind("Blood (arterial)", "Venous whole blood, heparinized syringe"), "vessel")
check("'Blood (arterial)' rejects capillary blood", kind("Blood (arterial)", "Capillary blood"), "vessel")
check("'Blood (arterial)' accepts arterial blood", kind("Blood (arterial)", "Arterial blood, heparinized"), None)
check("'Blood (arterial)' accepts blood of an unstated vessel", kind("Blood (arterial)", "Whole blood"), None)
check("'Blood (arterial)' points out a mixed description", kind("Blood (arterial)", "Arterial and venous blood"), "mixed")
check("'Blood (arterial or venous)' accepts venous blood", kind("Blood (arterial or venous)", "Venous whole blood"), None)
check("an unstated sample type is never a mismatch", kind("Serum", "not reported in the information source"), None)
check("a sample type naming both whole blood and plasma keeps both", S.specimen_profile("Whole blood and plasma from the same donors")[1], {"blood", "plasma"})
check("the form explains 'Plasma or blood'", "accepts plasma, whole blood" in S.accepted_specimens("Plasma or blood"), True)
check("the form explains a text without a rule", S.accepted_specimens("Urine").startswith("No specimen rule"), True)

# ---- criterion 21: the specimen is animal
for text in ["Rat serum (Wistar male rats)", "Equine arterial blood (facial artery), 10 horses", "Whole blood (Dogs); anaerobic",
             "Arterial blood, anesthetized dogs (in vivo)", "Citrated plasma from 20 clinically normal dogs", "Stillborn piglet chest cavity fluid",
             "Bovine whole blood fortified in vitro with CO gas", "In vivo (dog tongue probe)"]:
    check(f"animal specimen: {text[:44]}", bool(S.animal_specimen(text)), True)
for text in ["Human serum", "Pooled normal plasma, spiked with sodium heparin (porcine intestinal mucosa)",
             "Digoxin-free human serum spiked with digoxin and digoxin immune Fab (ovine)", "Serum containing bovine serum albumin",
             "Phosphate saline buffer pH 7.4 containing bovine gamma-globulin", "Citrated plasma; rabbit brain thromboplastin",
             "Plasma from patients treated with ovine Fab fragments", "Cells in fetal bovine serum", "Whole blood, heparinized"]:
    check(f"not an animal specimen: {text[:40]}", bool(S.animal_specimen(text)), False)

# ---- a whole row: reasons, and the exception for causes that are about the specimen
HDR = ["Analyte", "Interferent", "Platform/Brand/Method", "Analyzer/Instrument", "Assay generation/version", "Direction of effect",
       "Direction (study criterion)", "Direction (user APS)", "Interferent concentration (exact, with units)", "Baseline analyte concentration",
       "Final analyte concentration", "Absolute change (as reported)", "Percentage change (as reported)", "Absolute change (calculated)",
       "Percentage change (calculated)", "Magnitude of change (verbatim from source)", "Significant-bias threshold",
       "Clinical significance vs user APS", "Sample type", "Study method details", "Physiologically realistic concentration?",
       "Study design appropriate?", "Clinically significant effect?", "Real-world conditions reflected?", "Additional sources of bias",
       "Notes", "Citation", "Full reference (from PDF)", "doi"]
NR = "not reported in the information source"
base = dict.fromkeys(HDR, NR)
base.update({"Analyte": "Oxygen partial pressure", "Interferent": "Hemolysis", "Platform/Brand/Method": "Blood gas analyser",
             "Direction of effect": "↑", "Percentage change (calculated)": "5.0", "Clinical significance vs user APS": "exceeds user APS 3%",
             "Sample type": "Venous whole blood", "Citation": "Smith 2020, Table 1", "doi": "10.1000/xyz123"})
analyte = {"folder": "nowhere_blood", "component": "Oxygen partial pressure", "prefix": "po2", "synonyms": "pO2", "aps_percent": 3.0,
           "system": "Blood (arterial)"}
res = S.screen([dict(base)], analyte, "/nonexistent")[0]
check("venous blood for an arterial analyte is rejected by criterion 22", [e["no"] for e in res["reject"]], [22])
res = S.screen([dict(base)], analyte, "/nonexistent", concept="sample_type")[0]
check("...but only pointed out when the cause is about the specimen", ([e["no"] for e in res["reject"]], [e["no"] for e in res["check"]]), ([], [22]))
res = S.screen([dict(base, **{"Sample type": "Arterial blood"})], analyte, "/nonexistent")[0]
check("arterial blood passes", res["reject"], [])
res = S.screen([dict(base, **{"Sample type": "Equine arterial blood"})], analyte, "/nonexistent")[0]
check("an animal specimen is rejected by criterion 21", [e["no"] for e in res["reject"]], [21])
res = S.screen([dict(base, **{"Sample type": "Arterial blood", "Percentage change (calculated)": "1.0"})], analyte, "/nonexistent")[0]
check("a verdict contradicting the number is rejected by criterion 17", [e["no"] for e in res["reject"]], [17])
res = S.screen([dict(base, **{"Sample type": "Arterial blood", "Percentage change (calculated)": "3.0"})], analyte, "/nonexistent")[0]
check("a change exactly equal to the APS is not a contradiction", res["reject"], [])
res = S.screen([dict(base, **{"Sample type": "Arterial blood"})] * 2, analyte, "/nonexistent")
check("the second of two identical rows is a duplicate (criterion 8)", ([e["no"] for e in res[0]["reject"]], [e["no"] for e in res[1]["reject"]]), ([], [8]))
res = S.screen([dict(base, **{"Sample type": "Arterial blood", "Citation": "file_12.pdf", "doi": NR})], analyte, "/nonexistent")[0]
check("no DOI, no reference and a citation without author and year: criterion 1", [e["no"] for e in res["reject"]], [1])
res = S.screen([dict(base, **{"Sample type": "Arterial blood", "doi": "doi unknown"})], analyte, "/nonexistent")[0]
check("a malformed DOI: criterion 9", [e["no"] for e in res["reject"]], [9])

print("\nscreening tests:", "all passed" if not failed else f"{failed} FAILED")
sys.exit(1 if failed else 0)

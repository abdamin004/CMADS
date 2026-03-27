"""Lab Verifier — Verify that a patient's labs actually reflect their target disease.

For each patient in the cohort, checks if the pre-cutoff lab values contain
abnormalities consistent with the target disease. Only patients where the
disease is "detectable" from labs pass verification.

This ensures the MAS is tested on patients where diagnosis is actually
possible from the available data.

Usage:
    python3 pipeline/lab_verifier.py
    python3 pipeline/lab_verifier.py --cohort data/gold/cohort_100_test_ids.json
"""

import json
import os
from pathlib import Path

GOLD_DIR = Path("data/gold/patient_cases")

# Disease → lab criteria that must be present for the disease to be detectable
# Each criterion: (lab_name_contains, operator, threshold, description)
DISEASE_LAB_CRITERIA = {
    "Chronic congestive heart failure (disorder)": {
        "required_any": [  # at least ONE of these must be met
            ("ejection fraction", "<", 50, "Reduced LVEF"),
            ("natriuretic", ">", 100, "Elevated BNP/NT-proBNP"),
            ("furosemide", None, None, "Furosemide in medications"),
            ("carvedilol", None, None, "Carvedilol in medications"),
        ],
        "supporting": [  # bonus signals (not required)
            ("creatinine", ">", 1.5, "Elevated creatinine (cardiorenal)"),
            ("sodium", "<", 135, "Hyponatremia"),
        ],
        "min_score": 1,  # need at least 1 required criterion
    },

    "Ischemic heart disease (disorder)": {
        "required_any": [
            ("troponin", ">", 0.04, "Elevated troponin"),
            ("cholesterol", ">", 240, "High total cholesterol"),
            ("ldl", ">", 160, "High LDL"),
            ("coronary", None, None, "Coronary history in conditions"),
            ("bypass", None, None, "CABG history in conditions"),
            ("nitroglycerin", None, None, "Nitroglycerin in medications"),
            ("clopidogrel", None, None, "Clopidogrel in medications"),
        ],
        "min_score": 1,
    },

    "Diabetes mellitus type 2 (disorder)": {
        "required_any": [
            ("a1c", ">", 6.5, "HbA1c in diabetic range"),
            ("glucose", ">", 126, "Fasting glucose elevated"),
            ("metformin", None, None, "Metformin in medications"),
            ("insulin", None, None, "Insulin in medications"),
        ],
        "min_score": 1,
    },

    "End-stage renal disease (disorder)": {
        "required_any": [
            ("glomerular", "<", 15, "eGFR < 15 (stage 5)"),
            ("creatinine", ">", 4.0, "Severely elevated creatinine"),
            ("dialysis", None, None, "Dialysis in procedures/meds"),
            ("epoetin", None, None, "Epoetin in medications"),
        ],
        "min_score": 1,
    },

    "Chronic kidney disease stage 3 (disorder)": {
        "required_any": [
            ("glomerular", "<", 60, "eGFR < 60 (stage 3)"),
            ("creatinine", ">", 1.5, "Elevated creatinine"),
        ],
        "supporting": [
            ("protein", ">", 30, "Proteinuria"),
            ("albumin", "<", 3.5, "Low albumin"),
        ],
        "min_score": 1,
    },

    "Essential hypertension (disorder)": {
        "required_any": [
            ("systolic", ">", 140, "SBP > 140"),
            ("diastolic", ">", 90, "DBP > 90"),
            ("lisinopril", None, None, "ACE inhibitor in medications"),
            ("losartan", None, None, "ARB in medications"),
            ("amlodipine", None, None, "CCB in medications"),
            ("hydrochlorothiazide", None, None, "Thiazide in medications"),
        ],
        "min_score": 1,
    },

    "Malignant neoplasm of breast (disorder)": {
        "required_any": [
            ("estrogen receptor", None, None, "ER status in labs"),
            ("progesterone receptor", None, None, "PR status in labs"),
            ("her2", None, None, "HER2 status in labs"),
            ("paclitaxel", None, None, "Chemo in medications"),
            ("doxorubicin", None, None, "Chemo in medications"),
            ("tamoxifen", None, None, "Hormonal therapy in medications"),
        ],
        "min_score": 1,
    },

    "Metabolic syndrome X (disorder)": {
        "required_any": [
            ("triglyceride", ">", 150, "Elevated triglycerides"),
            ("glucose", ">", 100, "Elevated fasting glucose"),
            ("hdl", "<", 40, "Low HDL (male) or <50 (female)"),
            ("systolic", ">", 130, "Elevated SBP"),
        ],
        "supporting": [
            ("bmi", ">", 30, "Obesity"),
        ],
        "min_score": 2,  # need at least 2 for metabolic syndrome
    },

    "Myocardial infarction (disorder)": {
        "required_any": [
            ("troponin", ">", 0.04, "Elevated troponin"),
            ("creatine kinase", ">", 200, "Elevated CK"),
            ("nitroglycerin", None, None, "Nitroglycerin in meds"),
            ("aspirin", None, None, "Aspirin in meds"),
            ("heparin", None, None, "Heparin in meds"),
        ],
        "min_score": 1,
    },

    "Sepsis (disorder)": {
        "required_any": [
            ("leukocytes", ">", 12, "Elevated WBC"),
            ("leukocytes", "<", 4, "Low WBC (leukopenia)"),
            ("lactate", ">", 2, "Elevated lactate"),
            ("procalcitonin", ">", 0.5, "Elevated procalcitonin"),
        ],
        "supporting": [
            ("heart rate", ">", 100, "Tachycardia"),
            ("systolic", "<", 90, "Hypotension"),
        ],
        "min_score": 1,
    },

    "Human immunodeficiency virus infection (disorder)": {
        "required_any": [
            ("hiv", None, None, "HIV test in labs"),
            ("cd4", None, None, "CD4 count in labs"),
            ("viral load", None, None, "Viral load in labs"),
            ("antiretroviral", None, None, "ART in medications"),
            ("tenofovir", None, None, "Tenofovir in medications"),
            ("emtricitabine", None, None, "Emtricitabine in medications"),
        ],
        "min_score": 1,
    },
}


def _check_lab_value(labs, keyword, operator, threshold):
    """Check if any lab matching keyword meets the threshold."""
    keyword_lower = keyword.lower()
    for lab in labs:
        if not isinstance(lab, dict):
            continue
        name = (lab.get("lab_name", "") or lab.get("name", "")).lower()
        if keyword_lower in name:
            try:
                value = float(lab.get("value_latest", lab.get("value", 0)))
                if operator == ">" and value > threshold:
                    return True, f"{name}: {value} > {threshold}"
                elif operator == "<" and value < threshold:
                    return True, f"{name}: {value} < {threshold}"
            except (ValueError, TypeError):
                continue
    return False, None


def _check_text_match(text_blob, keyword):
    """Check if keyword appears in a text blob (medications, conditions)."""
    return keyword.lower() in text_blob.lower()


def verify_patient(uuid):
    """Verify that a patient's labs reflect their target disease.

    Returns: (passed: bool, score: int, details: dict)
    """
    gt_path = GOLD_DIR / uuid / "ground_truth.json"
    ehr_path = GOLD_DIR / uuid / "ehr_case.json"
    lab_path = GOLD_DIR / uuid / "lab_case.json"

    if not all(p.exists() for p in [gt_path, ehr_path, lab_path]):
        return False, 0, {"error": "missing files"}

    gt = json.loads(gt_path.read_text())
    ehr = json.loads(ehr_path.read_text())
    lab = json.loads(lab_path.read_text())

    target = gt["target_condition"]["name"]
    criteria = DISEASE_LAB_CRITERIA.get(target)

    if not criteria:
        # No criteria defined — let it pass with a warning
        return True, 0, {"warning": f"No verification criteria for {target}"}

    # Collect all searchable data
    latest_labs = lab.get("latest_labs", [])
    vitals = lab.get("recent_vitals", [])
    all_labs = latest_labs + vitals

    # Build text blob for medication/condition keyword search
    meds = ehr.get("medications", {})
    active_meds = meds.get("active", []) if isinstance(meds, dict) else meds
    conditions = ehr.get("conditions", {})
    active_conds = conditions.get("active", []) if isinstance(conditions, dict) else conditions

    text_blob = json.dumps(active_meds + active_conds, default=str)

    # Check required criteria
    score = 0
    met = []
    not_met = []

    for criterion in criteria.get("required_any", []):
        keyword, operator, threshold, description = criterion

        if operator is None:
            # Text search in medications/conditions
            if _check_text_match(text_blob, keyword):
                score += 1
                met.append(description)
            else:
                not_met.append(description)
        else:
            # Lab value check
            found, detail = _check_lab_value(all_labs, keyword, operator, threshold)
            if found:
                score += 1
                met.append(f"{description} ({detail})")
            else:
                not_met.append(description)

    # Check supporting criteria (bonus, not required)
    supporting_met = []
    for criterion in criteria.get("supporting", []):
        keyword, operator, threshold, description = criterion
        if operator:
            found, detail = _check_lab_value(all_labs, keyword, operator, threshold)
            if found:
                score += 1
                supporting_met.append(f"{description} ({detail})")

    min_score = criteria.get("min_score", 1)
    passed = len(met) >= min_score

    return passed, score, {
        "target": target,
        "criteria_met": met,
        "criteria_not_met": not_met,
        "supporting_met": supporting_met,
        "score": score,
        "min_required": min_score,
    }


def verify_cohort(cohort_file):
    """Verify all patients in a cohort."""
    with open(cohort_file) as f:
        uuids = json.load(f)

    passed = []
    failed = []
    no_criteria = []

    for uuid in uuids:
        ok, score, details = verify_patient(uuid)
        entry = {"uuid": uuid, "score": score, **details}

        if details.get("warning"):
            no_criteria.append(entry)
        elif ok:
            passed.append(entry)
        else:
            failed.append(entry)

    return passed, failed, no_criteria


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Lab Verifier")
    parser.add_argument("--cohort", default="data/gold/cohort_100_test_ids.json")
    parser.add_argument("--save", action="store_true", help="Save verified cohort")
    args = parser.parse_args()

    passed, failed, no_criteria = verify_cohort(args.cohort)

    print(f"{'='*60}")
    print(f"LAB VERIFICATION RESULTS")
    print(f"{'='*60}")
    print(f"  Passed:       {len(passed)}")
    print(f"  Failed:       {len(failed)}")
    print(f"  No criteria:  {len(no_criteria)}")

    # By disease
    print(f"\nBy disease:")
    disease_stats = {}
    for p in passed:
        d = p.get("target", "?")
        if d not in disease_stats:
            disease_stats[d] = {"passed": 0, "failed": 0}
        disease_stats[d]["passed"] += 1
    for f in failed:
        d = f.get("target", "?")
        if d not in disease_stats:
            disease_stats[d] = {"passed": 0, "failed": 0}
        disease_stats[d]["failed"] += 1

    print(f"  {'Disease':<45} {'Pass':>5} {'Fail':>5} {'Rate':>6}")
    print(f"  {'─'*65}")
    for d in sorted(disease_stats.keys(), key=lambda x: -disease_stats[x]["passed"]):
        s = disease_stats[d]
        total = s["passed"] + s["failed"]
        rate = s["passed"] * 100 // max(total, 1)
        print(f"  {d[:43]:<45} {s['passed']:>5} {s['failed']:>5} {rate:>5}%")

    # Show failed patients
    if failed:
        print(f"\nFailed patients (labs don't reflect disease):")
        for f in failed[:10]:
            print(f"  {f['uuid'][:12]}... {f.get('target','?')[:35]}")
            print(f"    Met: {f.get('criteria_met', [])}")
            print(f"    Missing: {f.get('criteria_not_met', [])[:3]}")

    # Save verified cohort
    if args.save:
        verified_uuids = [p["uuid"] for p in passed] + [n["uuid"] for n in no_criteria]
        out_path = args.cohort.replace(".json", "_verified.json")
        with open(out_path, "w") as f:
            json.dump(verified_uuids, f, indent=2)
        print(f"\nVerified cohort saved to {out_path} ({len(verified_uuids)} patients)")

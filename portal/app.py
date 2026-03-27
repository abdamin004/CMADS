"""CMADS Patient Profiler — Streamlit Portal

Browse 100 test patients with demographics, conditions, lab results,
encounters, medications, risk scores, and ground truth.
"""

import json
import os
from pathlib import Path

import streamlit as st
import pandas as pd
import duckdb

# ── Config ──
GOLD_DIR = Path("data/gold/patient_cases")
COHORT_FILE = Path("data/gold/cohort_100_test_ids.json")
DB_PATH = Path("data/clinical.duckdb")
RAD_DIR = Path("data/gold/radiology_reports")

st.set_page_config(
    page_title="CMADS Patient Profiler",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Data Loading ──
@st.cache_data
def load_cohort():
    with open(COHORT_FILE) as f:
        return json.load(f)


@st.cache_data
def load_patient_gold(uuid):
    ehr = json.loads((GOLD_DIR / uuid / "ehr_case.json").read_text())
    lab = json.loads((GOLD_DIR / uuid / "lab_case.json").read_text())
    gt = json.loads((GOLD_DIR / uuid / "ground_truth.json").read_text())
    return ehr, lab, gt


@st.cache_data
def get_patient_name(uuid):
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        r = con.execute(
            "SELECT FIRST || ' ' || LAST FROM patients WHERE Id = ?", [uuid]
        ).fetchone()
        con.close()
        return r[0] if r else uuid[:12]
    except Exception:
        return uuid[:12]


@st.cache_data
def get_patient_encounters(uuid):
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        rows = con.execute("""
            SELECT SUBSTRING(CAST(START AS VARCHAR),1,10) as date,
                   ENCOUNTERCLASS as class,
                   REASONDESCRIPTION as reason,
                   DESCRIPTION as description
            FROM encounters
            WHERE PATIENT = ?
            ORDER BY START DESC
        """, [uuid]).fetchdf()
        con.close()
        return rows
    except Exception:
        return pd.DataFrame()


@st.cache_data
def get_patient_labs(uuid):
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        rows = con.execute("""
            SELECT SUBSTRING(CAST(o.DATE AS VARCHAR),1,10) as date,
                   o.DESCRIPTION as test,
                   o.VALUE as value,
                   o.UNITS as units,
                   o.CATEGORY as category
            FROM observations o
            WHERE o.PATIENT = ?
              AND o.CATEGORY IN ('laboratory', 'vital-signs')
            ORDER BY o.DATE DESC
        """, [uuid]).fetchdf()
        con.close()
        return rows
    except Exception:
        return pd.DataFrame()


@st.cache_data
def get_radiology_report(uuid):
    reports = list(RAD_DIR.glob(f"{uuid}_*.json"))
    if reports:
        with open(reports[0]) as f:
            return json.load(f)
    return None


# ── Build patient list ──
cohort = load_cohort()
patient_options = {}
for uuid in cohort:
    try:
        _, _, gt = load_patient_gold(uuid)
        target = gt["target_condition"]["name"]
        name = get_patient_name(uuid)
        patient_options[uuid] = f"{name} — {target[:30]}"
    except Exception:
        patient_options[uuid] = uuid[:12]

# ── Sidebar ──
st.sidebar.title("CMADS Patient Profiler")
st.sidebar.markdown("Browse 100 test cohort patients")

# Search by UUID
search_uuid = st.sidebar.text_input("Search by patient UUID", "")

# Disease filter
all_diseases = sorted(set(
    load_patient_gold(u)[2]["target_condition"]["name"]
    for u in cohort
    if (GOLD_DIR / u / "ground_truth.json").exists()
))
selected_disease = st.sidebar.selectbox(
    "Filter by disease", ["All"] + all_diseases
)

# Filter patients
if search_uuid:
    filtered = [u for u in cohort if search_uuid.lower() in u.lower()]
    if not filtered:
        st.sidebar.warning(f"No patient found matching '{search_uuid}'")
        filtered = cohort
elif selected_disease != "All":
    filtered = [u for u in cohort
                if load_patient_gold(u)[2]["target_condition"]["name"] == selected_disease]
else:
    filtered = cohort

selected_uuid = st.sidebar.selectbox(
    "Select patient",
    filtered,
    format_func=lambda u: patient_options.get(u, u[:12]),
)

# ── Main Content ──
if selected_uuid:
    ehr, lab, gt = load_patient_gold(selected_uuid)
    demo = ehr.get("demographics", {})
    name = get_patient_name(selected_uuid)

    # Header
    st.title(f"{name}")
    st.caption(f"UUID: {selected_uuid}")

    # Top metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Age", demo.get("age", "?"))
    col2.metric("Gender", demo.get("gender", "?"))
    col3.metric("Charlson Index", ehr.get("comorbidity", {}).get("charlson_index", "?"))
    col4.metric("Total Visits", ehr.get("visits", {}).get("total", "?"))
    col5.metric("Lab Count", lab.get("lab_count", 0))

    # Ground truth banner
    target = gt["target_condition"]
    st.warning(
        f"**Target Disease (hidden from agents):** {target['name']} "
        f"(SNOMED: {target['code']}, diagnosed: {target['diagnosis_date']})"
    )

    # Tabs
    tab_overview, tab_conditions, tab_labs, tab_encounters, tab_meds, tab_risk, tab_radiology, tab_raw = st.tabs([
        "Overview", "Conditions", "Labs & Vitals", "Encounters",
        "Medications", "Risk Scores", "Radiology", "Raw JSON"
    ])

    # ── Overview Tab ──
    with tab_overview:
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Demographics")
            demo_df = pd.DataFrame([
                {"Field": k, "Value": str(v)}
                for k, v in demo.items()
                if k != "location"
            ])
            st.dataframe(demo_df, use_container_width=True, hide_index=True)

            if demo.get("location"):
                loc = demo["location"]
                st.caption(f"Location: {loc.get('city', '?')}, {loc.get('state', '?')} {loc.get('zip', '')}")

        with col_right:
            st.subheader("Visit Summary")
            visits = ehr.get("visits", {})
            visit_df = pd.DataFrame({
                "Type": ["Emergency", "Inpatient", "Outpatient", "Wellness"],
                "Count": [
                    visits.get("emergency", 0),
                    visits.get("inpatient", 0),
                    visits.get("outpatient", 0),
                    visits.get("wellness", 0),
                ],
            }).set_index("Type")
            st.bar_chart(visit_df)

            st.subheader("Comorbidity Flags")
            flags = ehr.get("comorbidity", {}).get("flags", {})
            if flags:
                active_flags = [k.replace("has_", "").replace("_", " ").title()
                                for k, v in flags.items() if v]
                if active_flags:
                    st.markdown(" | ".join([f"**{f}**" for f in active_flags]))
                else:
                    st.info("No comorbidity flags")

    # ── Conditions Tab ──
    with tab_conditions:
        conditions = ehr.get("conditions", {})
        active = conditions.get("active", []) if isinstance(conditions, dict) else conditions

        st.subheader(f"Active Conditions ({len(active)})")
        if active:
            cond_data = []
            for c in active:
                if isinstance(c, dict):
                    cond_data.append({
                        "Condition": c.get("condition", c.get("name", "?")),
                        "SNOMED": c.get("code", "?"),
                        "Onset": c.get("start_date", "?"),
                        "End": c.get("end_date", "ongoing") or "ongoing",
                    })
            df = pd.DataFrame(cond_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Ground truth conditions
        st.subheader("All Conditions at Diagnosis (Ground Truth)")
        gt_conds = gt.get("all_conditions_at_diagnosis", [])
        if gt_conds:
            gt_df = pd.DataFrame(gt_conds)
            st.dataframe(gt_df, use_container_width=True, hide_index=True)

    # ── Labs Tab ──
    with tab_labs:
        col_gold, col_raw = st.columns(2)

        with col_gold:
            st.subheader("Latest Labs (Gold Layer)")
            latest = lab.get("latest_labs", [])
            if latest:
                lab_df = pd.DataFrame(latest)
                st.dataframe(lab_df, use_container_width=True, hide_index=True)
            else:
                st.warning("No lab results available before cutoff date")

            st.subheader("Lab Trends")
            trends = lab.get("lab_trends", [])
            if trends:
                trend_df = pd.DataFrame(trends)
                st.dataframe(trend_df, use_container_width=True, hide_index=True)

            st.subheader("Critical Flags")
            flags_raw = lab.get("critical_flags", {})
            flags_list = flags_raw.get("flags", []) if isinstance(flags_raw, dict) else flags_raw
            if flags_list:
                flag_df = pd.DataFrame(flags_list)
                st.dataframe(flag_df, use_container_width=True, hide_index=True)
            else:
                st.info("No critical lab flags")

        with col_raw:
            st.subheader("Recent Vitals")
            vitals = lab.get("recent_vitals", [])
            if vitals:
                vital_df = pd.DataFrame(vitals)
                st.dataframe(vital_df, use_container_width=True, hide_index=True)
            else:
                st.info("No vitals available")

            st.subheader("All Labs from DuckDB")
            raw_labs = get_patient_labs(selected_uuid)
            if not raw_labs.empty:
                # Filter options
                categories = raw_labs["category"].unique().tolist()
                sel_cat = st.multiselect("Filter category", categories, default=categories)
                filtered_labs = raw_labs[raw_labs["category"].isin(sel_cat)]
                st.dataframe(filtered_labs, use_container_width=True, hide_index=True,
                             height=400)
                st.caption(f"Total: {len(filtered_labs)} results")
            else:
                st.warning("No lab data in DuckDB for this patient")

    # ── Encounters Tab ──
    with tab_encounters:
        st.subheader("All Encounters")
        enc_df = get_patient_encounters(selected_uuid)
        if not enc_df.empty:
            # Summary
            enc_summary = enc_df["class"].value_counts()
            st.bar_chart(enc_summary)

            # Filter
            enc_classes = enc_df["class"].unique().tolist()
            sel_class = st.multiselect("Filter by class", enc_classes, default=enc_classes)
            filtered_enc = enc_df[enc_df["class"].isin(sel_class)]
            st.dataframe(filtered_enc, use_container_width=True, hide_index=True,
                         height=400)
            st.caption(f"Total: {len(filtered_enc)} encounters")
        else:
            st.warning("No encounters found")

    # ── Medications Tab ──
    with tab_meds:
        st.subheader("Active Medications")
        meds = ehr.get("medications", {})
        active_meds = meds.get("active", []) if isinstance(meds, dict) else meds
        if active_meds:
            med_data = []
            for m in active_meds:
                if isinstance(m, dict):
                    med_data.append({
                        "Medication": m.get("medication", m.get("name", "?")),
                        "For": m.get("condition_treated", m.get("reason", "?")),
                    })
            med_df = pd.DataFrame(med_data)
            st.dataframe(med_df, use_container_width=True, hide_index=True)
        else:
            st.info("No active medications")

        # Drug-condition links
        st.subheader("Drug-Condition Links")
        links = ehr.get("drug_condition_links", [])
        if links:
            link_df = pd.DataFrame(links)
            st.dataframe(link_df, use_container_width=True, hide_index=True)

        # Post-diagnosis medications (from ground truth)
        st.subheader("Post-Diagnosis Medications (Ground Truth)")
        post_meds = gt.get("post_diagnosis_medications", [])
        if post_meds:
            post_df = pd.DataFrame(post_meds)
            st.dataframe(post_df, use_container_width=True, hide_index=True)
        else:
            st.info("No post-diagnosis medications")

    # ── Risk Scores Tab ──
    with tab_risk:
        col_risk, col_comorb = st.columns(2)

        with col_risk:
            st.subheader("Risk Scores")
            risk = ehr.get("risk_scores", {})
            if risk:
                risk_data = [{"Metric": k, "Value": str(v)} for k, v in risk.items()]
                st.dataframe(pd.DataFrame(risk_data), use_container_width=True,
                             hide_index=True)

        with col_comorb:
            st.subheader("Comorbidity")
            comorb = ehr.get("comorbidity", {})
            if comorb:
                st.json(comorb)

    # ── Radiology Tab ──
    with tab_radiology:
        report = get_radiology_report(selected_uuid)
        if report:
            st.subheader(f"Radiology Report — {report.get('modality', '?')}")
            st.caption(
                f"Date: {report.get('scan_date', '?')} | "
                f"Body site: {report.get('body_site', '?')} | "
                f"Model: {report.get('generation_metadata', {}).get('model', '?')}"
            )
            st.markdown(report.get("report", "No report text"))

            with st.expander("Generation Metadata"):
                st.json(report.get("generation_metadata", {}))
        else:
            st.info("No radiology report generated for this patient")

        # Imaging studies from EHR
        imaging = ehr.get("imaging_studies", [])
        if imaging:
            st.subheader(f"Imaging Studies in EHR ({len(imaging)})")
            img_df = pd.DataFrame(imaging)
            st.dataframe(img_df, use_container_width=True, hide_index=True)

    # ── Raw JSON Tab ──
    with tab_raw:
        raw_tab1, raw_tab2, raw_tab3 = st.tabs(["ehr_case.json", "lab_case.json", "ground_truth.json"])
        with raw_tab1:
            st.json(ehr)
        with raw_tab2:
            st.json(lab)
        with raw_tab3:
            st.json(gt)

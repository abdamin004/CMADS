"""CMADS Doctor Portal — Clinical Decision Support Dashboard

Interactive portal for doctors to review MAS diagnostic results per patient.
Search by patient ID, view agent reasoning, final diagnosis, and confidence.

Usage:
    streamlit run portal/doctor_portal.py
"""

import json
import os
from pathlib import Path

import streamlit as st
import pandas as pd

# ── Config ──
GOLD_DIR = Path("data/gold/patient_cases")
MAS_DIR = Path("data/gold/mas_results")
DB_PATH = Path("data/clinical.duckdb")

st.set_page_config(
    page_title="CMADS Clinical Decision Support",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric { background: #1a1f2e; padding: 12px; border-radius: 8px; border: 1px solid #2d3748; }
    .diagnosis-card {
        background: linear-gradient(135deg, #1a1f2e 0%, #1e2538 100%);
        border: 1px solid #2d3748;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    .rank-badge {
        display: inline-block;
        width: 32px; height: 32px;
        border-radius: 50%;
        text-align: center;
        line-height: 32px;
        font-weight: bold;
        font-size: 16px;
        margin-right: 8px;
    }
    .rank-1 { background: #ffd700; color: #000; }
    .rank-2 { background: #c0c0c0; color: #000; }
    .rank-3 { background: #cd7f32; color: #000; }
    .rank-other { background: #4a5568; color: #fff; }
    .confidence-high { color: #48bb78; }
    .confidence-moderate { color: #ecc94b; }
    .confidence-low { color: #fc8181; }
    .agent-header {
        background: #1e2538;
        padding: 8px 16px;
        border-radius: 8px 8px 0 0;
        border: 1px solid #2d3748;
        font-weight: bold;
    }
    .status-success { color: #48bb78; }
    .status-partial { color: #ecc94b; }
    .status-error { color: #fc8181; }
    .finding-critical { border-left: 3px solid #fc8181; padding-left: 8px; }
    .finding-abnormal { border-left: 3px solid #ecc94b; padding-left: 8px; }
    .finding-normal { border-left: 3px solid #48bb78; padding-left: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Data Loading ──
@st.cache_data(ttl=30)
def get_available_patients():
    """Get all patients that have MAS results."""
    if not MAS_DIR.exists():
        return {}
    patients = {}
    for d in sorted(MAS_DIR.iterdir()):
        if not d.is_dir():
            continue
        uuid = d.name
        gt_path = GOLD_DIR / uuid / "ground_truth.json"
        fd_path = d / "final_diagnosis.json"
        trace_path = d / "execution_trace.json"
        if gt_path.exists():
            gt = json.loads(gt_path.read_text())
            target = gt["target_condition"]["name"]

            # Get patient name
            try:
                import duckdb
                con = duckdb.connect(str(DB_PATH), read_only=True)
                r = con.execute("SELECT FIRST || ' ' || LAST FROM patients WHERE Id = ?", [uuid]).fetchone()
                con.close()
                name = r[0] if r else uuid[:12]
            except Exception:
                name = uuid[:12]

            primary = "?"
            if fd_path.exists():
                fd = json.loads(fd_path.read_text())
                primary = fd.get("primary_diagnosis", "?")

            duration = 0
            if trace_path.exists():
                trace = json.loads(trace_path.read_text())
                duration = trace.get("duration_s", 0)

            patients[uuid] = {
                "name": name,
                "target": target,
                "primary": primary,
                "duration": duration,
            }
    return patients


@st.cache_data(ttl=30)
def load_patient_data(uuid):
    """Load all data for a patient."""
    data = {}
    # Gold layer
    for f in ["ehr_case.json", "lab_case.json", "ground_truth.json"]:
        path = GOLD_DIR / uuid / f
        if path.exists():
            data[f.replace(".json", "")] = json.loads(path.read_text())
    # MAS results
    mas_dir = MAS_DIR / uuid
    if mas_dir.exists():
        for f in mas_dir.iterdir():
            if f.suffix == ".json":
                data[f.stem] = json.loads(f.read_text())
    return data


# ── Sidebar ──
st.sidebar.markdown("# 🩺 CMADS")
st.sidebar.markdown("### Clinical Decision Support")
st.sidebar.markdown("---")

patients = get_available_patients()

if not patients:
    st.error("No MAS results found. Run the pipeline first.")
    st.stop()

# Search
search = st.sidebar.text_input("🔍 Search Patient ID", "")

# Disease filter
all_diseases = sorted(set(p["target"] for p in patients.values()))
disease_filter = st.sidebar.selectbox("Filter by Disease", ["All Diseases"] + all_diseases)

# Apply filters
filtered = patients
if search:
    filtered = {k: v for k, v in filtered.items() if search.lower() in k.lower() or search.lower() in v["name"].lower()}
if disease_filter != "All Diseases":
    filtered = {k: v for k, v in filtered.items() if v["target"] == disease_filter}

# Patient list
st.sidebar.markdown(f"**{len(filtered)}** patients")
selected = st.sidebar.selectbox(
    "Select Patient",
    list(filtered.keys()),
    format_func=lambda u: f"{filtered[u]['name']} — {filtered[u]['target'][:25]}",
) if filtered else None

# Stats
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Total Results:** {len(patients)}")
st.sidebar.markdown(f"**Diseases:** {len(all_diseases)}")


# ── Main Content ──
if not selected:
    st.title("🩺 CMADS Clinical Decision Support")
    st.markdown("Select a patient from the sidebar to view diagnostic results.")

    # Overview stats
    col1, col2, col3 = st.columns(3)
    col1.metric("Patients Analysed", len(patients))
    col2.metric("Diseases Covered", len(all_diseases))
    avg_time = sum(p["duration"] for p in patients.values()) / max(len(patients), 1)
    col3.metric("Avg Analysis Time", f"{avg_time:.0f}s")

    # Disease distribution
    st.subheader("Disease Distribution")
    disease_counts = {}
    for p in patients.values():
        disease_counts[p["target"]] = disease_counts.get(p["target"], 0) + 1
    df = pd.DataFrame({"Disease": disease_counts.keys(), "Patients": disease_counts.values()})
    df = df.sort_values("Patients", ascending=True)
    st.bar_chart(df.set_index("Disease"))

    st.stop()

# ── Patient View ──
data = load_patient_data(selected)
info = patients[selected]

# Header
st.markdown(f"# {info['name']}")
st.caption(f"Patient ID: `{selected}`")

# Top metrics
col1, col2, col3, col4 = st.columns(4)

ehr = data.get("ehr_case", {})
demo = ehr.get("demographics", {})
col1.metric("Age", demo.get("age", "?"))
col2.metric("Gender", "Male" if demo.get("gender") == "M" else "Female" if demo.get("gender") == "F" else "?")

trace = data.get("execution_trace", {})
col3.metric("Analysis Time", f"{trace.get('duration_s', 0):.0f}s")

# Agent success count
agents = trace.get("agents", [])
success_count = sum(1 for a in agents if a.get("status") == "success")
col4.metric("Agents Succeeded", f"{success_count}/5")


# ── Final Diagnosis (Hero Section) ──
st.markdown("---")
fd = data.get("final_diagnosis", {})

if fd and fd.get("differential"):
    st.subheader("🎯 Diagnostic Differential")

    for dx in fd.get("differential", [])[:5]:
        if not isinstance(dx, dict):
            continue
        rank = dx.get("rank", "?")
        name = dx.get("name", "?")
        prob = dx.get("probability", 0)
        confidence = dx.get("confidence", "?")

        # Color coding
        if rank == 1:
            bar_color = "#ffd700"
        elif rank == 2:
            bar_color = "#c0c0c0"
        elif rank == 3:
            bar_color = "#cd7f32"
        else:
            bar_color = "#4a5568"

        prob_pct = int(prob * 100)
        conf_color = "#48bb78" if confidence == "high" else "#ecc94b" if confidence == "moderate" else "#fc8181"

        st.markdown(f"""
        <div class="diagnosis-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span class="rank-badge rank-{'1' if rank==1 else '2' if rank==2 else '3' if rank==3 else 'other'}">{rank}</span>
                    <strong style="font-size:16px;">{name}</strong>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:24px; font-weight:bold;">{prob_pct}%</span>
                    <br><span style="color:{conf_color}; font-size:12px;">{confidence} confidence</span>
                </div>
            </div>
            <div style="background:#2d3748; border-radius:4px; height:8px; margin-top:8px;">
                <div style="background:{bar_color}; width:{prob_pct}%; height:8px; border-radius:4px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Evidence (expandable)
        evidence = dx.get("supporting_evidence", [])
        reasoning = dx.get("reasoning", "")
        if evidence or reasoning:
            with st.expander(f"Evidence for #{rank} {name[:30]}"):
                if evidence:
                    for e in evidence:
                        if isinstance(e, dict):
                            st.markdown(f"- **[{e.get('source', '?')}]** {e.get('finding', '?')}")
                if reasoning:
                    st.markdown(f"**Reasoning:** {reasoning[:300]}")

    # Summary
    if fd.get("clinical_reasoning_summary"):
        st.info(f"**Clinical Reasoning:** {fd['clinical_reasoning_summary'][:500]}")

    if fd.get("unresolved_findings"):
        st.warning(f"**Unresolved Findings:** {', '.join(fd['unresolved_findings'][:5])}")

    if fd.get("recommended_workup"):
        st.markdown("**Recommended Workup:**")
        for w in fd["recommended_workup"][:5]:
            st.markdown(f"- {w}")
else:
    st.error("No diagnostic output available for this patient.")


# ── Evaluation Result ──
ev = data.get("evaluation", {})
if ev:
    st.markdown("---")
    st.subheader("📊 Evaluation Against Ground Truth")

    gt = data.get("ground_truth", {})
    target = gt.get("target_condition", {}).get("name", "?") if gt else "?"

    col1, col2, col3 = st.columns(3)

    found_color = "#48bb78" if ev.get("found") == "YES" else "#fc8181"
    col1.markdown(f"**Target Disease:**<br>{target}", unsafe_allow_html=True)

    match_type = ev.get("match_type", "?")
    type_color = "#48bb78" if match_type == "DIRECT" else "#ecc94b" if match_type == "INDIRECT" else "#fc8181"
    col2.markdown(f"**Match:** <span style='color:{type_color}; font-size:20px; font-weight:bold;'>{match_type}</span>", unsafe_allow_html=True)

    rank = ev.get("rank", 0)
    col3.markdown(f"**Found at Rank:** <span style='font-size:20px; font-weight:bold;'>#{rank}</span>", unsafe_allow_html=True)

    if ev.get("matched_diagnosis") and ev["matched_diagnosis"] != "NONE":
        st.success(f"**Matched Diagnosis:** {ev['matched_diagnosis']}")
    if ev.get("reason"):
        st.caption(f"Reason: {ev['reason']}")


# ── Agent Details (Tabs) ──
st.markdown("---")
st.subheader("🤖 Agent Reasoning Pipeline")

# Agent status overview
if agents:
    agent_cols = st.columns(5)
    agent_labels = [
        ("EHR Analyst", "ehr_analyst"),
        ("Lab Interpreter", "lab_interpreter"),
        ("Diagnostic", "diagnostic_reasoning"),
        ("Reviewer", "clinical_reviewer"),
        ("Refiner", "final_diagnosis"),
    ]
    for col, (label, agent_id) in zip(agent_cols, agent_labels):
        agent_info = next((a for a in agents if a["agent_id"] == agent_id), {})
        status = agent_info.get("status", "?")
        time_ms = agent_info.get("execution_ms", 0)
        status_icon = "✅" if status == "success" else "⚠️" if status == "partial" else "❌"
        col.markdown(f"**{status_icon} {label}**<br>{time_ms/1000:.0f}s", unsafe_allow_html=True)

tab_ehr, tab_lab, tab_diag, tab_review, tab_meds, tab_trace = st.tabs([
    "📋 EHR Analysis", "🧪 Lab Findings", "🔬 Diagnostic Reasoning",
    "✅ Clinical Review", "💊 Treatment Plan", "⏱️ Execution Trace"
])

# ── EHR Tab ──
with tab_ehr:
    ehr_out = data.get("ehr_analyst", {})
    if ehr_out:
        if ehr_out.get("chief_complaint"):
            st.markdown(f"**Chief Complaint:** {ehr_out['chief_complaint']}")
        if ehr_out.get("history_of_present_illness"):
            st.markdown(f"**HPI:** {ehr_out['history_of_present_illness'][:500]}")

        if ehr_out.get("active_problems"):
            st.markdown("**Active Problems:**")
            prob_data = []
            for p in ehr_out["active_problems"]:
                if isinstance(p, dict):
                    prob_data.append({
                        "Significance": p.get("clinical_significance", "?"),
                        "Condition": p.get("name", "?"),
                        "Onset": p.get("onset_date", "?"),
                    })
            if prob_data:
                st.dataframe(pd.DataFrame(prob_data), use_container_width=True, hide_index=True)

        if ehr_out.get("active_medications"):
            st.markdown("**Medications:**")
            med_data = [{"Medication": m.get("name", "?"), "Purpose": m.get("purpose", "?"),
                         "Relevance": m.get("relevance", "?")}
                        for m in ehr_out["active_medications"] if isinstance(m, dict)]
            if med_data:
                st.dataframe(pd.DataFrame(med_data), use_container_width=True, hide_index=True)

        if ehr_out.get("risk_factor_summary"):
            st.info(f"**Risk Factors:** {ehr_out['risk_factor_summary'][:400]}")
        if ehr_out.get("clinical_impression"):
            st.warning(f"**Clinical Impression:** {ehr_out['clinical_impression'][:400]}")
        if ehr_out.get("data_quality_flags"):
            st.caption(f"Data Quality: {[f.get('issue','') for f in ehr_out['data_quality_flags'][:5]]}")
    else:
        st.info("EHR Analyst output not available")

# ── Lab Tab ──
with tab_lab:
    lab_out = data.get("lab_interpreter", {})
    if lab_out:
        if lab_out.get("critical_alerts"):
            for alert in lab_out["critical_alerts"]:
                st.error(f"🚨 {alert}")

        if lab_out.get("findings"):
            st.markdown("**Lab Findings (by severity):**")
            finding_data = []
            for f in lab_out["findings"]:
                if isinstance(f, dict):
                    finding_data.append({
                        "Sev": f.get("severity", "?"),
                        "Test": f.get("test_name", "?"),
                        "Value": f.get("value", "?"),
                        "Status": f.get("classification", "?"),
                        "Trend": f.get("trend", "?"),
                        "Note": f.get("clinical_note", "")[:60],
                    })
            if finding_data:
                df = pd.DataFrame(finding_data)
                st.dataframe(df, use_container_width=True, hide_index=True)

        if lab_out.get("panel_patterns"):
            st.markdown("**Panel Patterns:**")
            for p in lab_out["panel_patterns"]:
                if isinstance(p, dict):
                    st.markdown(f"- **{p.get('panel_name', '?')}:** {p.get('interpretation', '?')[:120]}")

        if lab_out.get("overall_assessment"):
            st.info(f"**Overall Assessment:** {lab_out['overall_assessment'][:400]}")

        if lab_out.get("data_gaps"):
            st.caption(f"Missing labs: {', '.join(lab_out['data_gaps'][:5])}")
    else:
        st.info("Lab Interpreter output not available")

# ── Diagnostic Tab ──
with tab_diag:
    diag_out = data.get("diagnostic_reasoning", {})
    if diag_out:
        if diag_out.get("differential"):
            st.markdown("**Initial Differential (before review):**")
            for dx in diag_out["differential"][:6]:
                if isinstance(dx, dict):
                    prob = dx.get("probability", 0)
                    st.markdown(f"**#{dx.get('rank','?')}** {dx.get('name','?')} — **{int(prob*100)}%** ({dx.get('confidence','?')})")
                    if dx.get("reasoning"):
                        st.caption(f"  {dx['reasoning'][:150]}")

        if diag_out.get("clinical_reasoning_summary"):
            st.info(f"**Reasoning:** {diag_out['clinical_reasoning_summary'][:500]}")

        if diag_out.get("unresolved_findings"):
            st.warning(f"**Unresolved:** {', '.join(diag_out['unresolved_findings'][:5])}")
    else:
        st.info("Diagnostic Reasoning output not available")

# ── Review Tab ──
with tab_review:
    rev_out = data.get("clinical_reviewer", {})
    if rev_out:
        if rev_out.get("overall_confidence") is not None:
            conf = rev_out["overall_confidence"]
            conf_color = "🟢" if conf >= 75 else "🟡" if conf >= 50 else "🔴"
            st.markdown(f"### {conf_color} Overall Confidence: {conf}/100")

        if rev_out.get("recommended_primary"):
            st.success(f"**Reviewer Recommends:** {rev_out['recommended_primary']} (confidence: {rev_out.get('recommended_primary_confidence', '?')})")

        if rev_out.get("diagnosis_verifications"):
            st.markdown("**Per-Diagnosis Verification:**")
            ver_data = []
            for v in rev_out["diagnosis_verifications"]:
                if isinstance(v, dict):
                    ver_data.append({
                        "Diagnosis": v.get("diagnosis", "?")[:35],
                        "Original P": v.get("original_probability", "?"),
                        "Adjusted P": v.get("verified_probability", "?"),
                        "Confidence": v.get("confidence_score", "?"),
                        "Evidence": v.get("evidence_strength", "?"),
                        "Verdict": v.get("verdict", "?"),
                    })
            if ver_data:
                st.dataframe(pd.DataFrame(ver_data), use_container_width=True, hide_index=True)

        if rev_out.get("top_concerns"):
            st.markdown("**Top Concerns:**")
            for c in rev_out["top_concerns"][:5]:
                st.markdown(f"- ⚠️ {c[:100]}")

        if rev_out.get("critical_findings_missed"):
            st.error(f"**Critical Findings Missed:** {', '.join(rev_out['critical_findings_missed'][:5])}")

        if rev_out.get("review_summary"):
            st.info(f"**Review Summary:** {rev_out['review_summary'][:400]}")
    else:
        st.info("Clinical Reviewer output not available")

# ── Treatment Plan Tab ──
with tab_meds:
    tp = data.get("treatment_planning", {})
    if tp and tp.get("medications"):
        # Header
        treated = tp.get("primary_diagnosis_treated", "?")
        guideline = tp.get("nice_guideline_used", "?")
        st.markdown(f"### 💊 Treatment Plan")
        st.info(f"**Treating:** {treated}\n\n**NICE Guideline:** {guideline}")

        # Medications table
        st.markdown("#### Prescribed Medications")
        for m in tp.get("medications", []):
            if not isinstance(m, dict):
                continue
            line_color = "#48bb78" if m.get("line") == "first_line" else "#ecc94b" if m.get("line") == "second_line" else "#8b949e"
            line_label = m.get("line", "").replace("_", " ").title()

            st.markdown(f"""
            <div style="background:#161b22; border-left:4px solid {line_color}; border-radius:0 8px 8px 0; padding:12px 16px; margin:8px 0;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <strong style="font-size:16px;">{m.get('medication', '?')}</strong>
                        <span style="background:{line_color}20; color:{line_color}; padding:2px 8px; border-radius:4px; font-size:11px; margin-left:8px;">{line_label}</span>
                    </div>
                    <span style="color:#8b949e; font-size:13px;">{m.get('drug_class', '')}</span>
                </div>
                <table style="width:100%; margin-top:8px; font-size:13px; color:#c9d1d9;">
                    <tr>
                        <td style="padding:4px 0;"><strong>Dose:</strong> {m.get('dose', '?')}</td>
                        <td style="padding:4px 0;"><strong>Duration:</strong> {m.get('duration', '?')}</td>
                    </tr>
                    <tr>
                        <td colspan="2" style="padding:4px 0;"><strong>Purpose:</strong> {m.get('purpose', '?')}</td>
                    </tr>
                    <tr>
                        <td colspan="2" style="padding:4px 0; color:#58a6ff;"><strong>NICE:</strong> {m.get('nice_justification', '?')}</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

        # Interactions
        interactions = tp.get("interactions_checked", [])
        if interactions:
            st.markdown("#### ⚠️ Drug Interactions")
            for ix in interactions:
                if isinstance(ix, dict):
                    severity = ix.get("severity", "?")
                    sev_color = "#fc8181" if severity == "severe" else "#ecc94b" if severity == "moderate" else "#48bb78"
                    pair = " + ".join(ix.get("drug_pair", []))
                    st.markdown(f"""
                    <div style="background:#1a1a2e; border-left:3px solid {sev_color}; padding:8px 12px; margin:4px 0; border-radius:0 6px 6px 0; font-size:13px;">
                        <strong>{pair}</strong> <span style="color:{sev_color};">({severity})</span><br>
                        {ix.get('interaction', '?')}<br>
                        <em>Action: {ix.get('action', '?')}</em>
                    </div>
                    """, unsafe_allow_html=True)

        # Contraindications
        contras = tp.get("contraindications", [])
        if contras:
            st.markdown("#### 🚫 Contraindications")
            for c in contras:
                if isinstance(c, dict):
                    st.error(f"**{c.get('drug', '?')}** — {c.get('reason', '?')}\n\nAlternative: {c.get('alternative', 'None specified')}")

        # Monitoring
        monitoring = tp.get("monitoring", [])
        if monitoring:
            st.markdown("#### 📊 Monitoring Plan")
            mon_data = [{
                "Test": m.get("test", "?"),
                "Frequency": m.get("frequency", "?"),
                "Reason": m.get("reason", ""),
            } for m in monitoring if isinstance(m, dict)]
            if mon_data:
                st.dataframe(pd.DataFrame(mon_data), use_container_width=True, hide_index=True)

        # Non-pharmacological
        non_pharm = tp.get("non_pharmacological", [])
        if non_pharm:
            st.markdown("#### 🏃 Non-Pharmacological")
            for n in non_pharm:
                st.markdown(f"- {n}")

        # Referrals
        referrals = tp.get("referral", [])
        if referrals:
            st.markdown("#### 🏥 Referrals")
            for r in referrals:
                st.markdown(f"- {r}")

        # Assumptions & Warnings
        warnings = tp.get("assumptions_warnings", [])
        if warnings:
            st.markdown("#### ⚠️ Assumptions & Missing Data")
            for w in warnings:
                st.warning(f"⚠️ {w}")

        # Summary
        if tp.get("treatment_summary"):
            st.markdown("#### Summary")
            st.success(tp["treatment_summary"])
    elif tp and "SKIPPED" in tp.get("primary_diagnosis_treated", ""):
        st.warning("Treatment plan not generated — diagnosis was not a DIRECT match. Only patients with confirmed diagnoses receive treatment plans.")
    elif tp and "ERROR" in tp.get("treatment_summary", ""):
        st.error(tp["treatment_summary"])
    else:
        st.info("No treatment plan available for this patient. Run the treatment agent first.")

# ── Trace Tab ──
with tab_trace:
    if agents:
        trace_data = []
        for a in agents:
            status_icon = "✅" if a["status"] == "success" else "⚠️" if a["status"] == "partial" else "❌"
            trace_data.append({
                "Agent": a["agent_id"],
                "Status": f"{status_icon} {a['status']}",
                "Time": f"{a['execution_ms']/1000:.1f}s",
                "Error": a.get("error", "") or "",
            })
        st.dataframe(pd.DataFrame(trace_data), use_container_width=True, hide_index=True)

        total_time = trace.get("duration_s", 0)
        st.caption(f"Total pipeline time: {total_time:.0f}s ({total_time/60:.1f} min)")

    # Raw JSON viewer
    with st.expander("Raw JSON Data"):
        json_tab = st.selectbox("Select file", [
            "final_diagnosis", "ehr_analyst", "lab_interpreter",
            "diagnostic_reasoning", "clinical_reviewer",
            "execution_trace", "evaluation", "ground_truth",
        ])
        if json_tab in data:
            st.json(data[json_tab])
        else:
            st.info(f"{json_tab}.json not available")

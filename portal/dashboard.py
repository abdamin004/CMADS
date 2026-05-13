"""CMADS Evaluation Dashboard — Batch Results & Patient Explorer

Usage:
    streamlit run portal/dashboard.py
"""

import json
import os
from pathlib import Path

import streamlit as st
import pandas as pd

GOLD_DIR = Path(os.environ.get("GOLD_DIR", "data/gold/patient_cases"))
DATA_GOLD = Path(os.environ.get("DATA_GOLD_DIR", "data/gold"))
DEFAULT_MAS_DIR = Path(os.environ.get("MAS_RESULTS_DIR", "data/gold/mas_results"))
DB_PATH = Path(os.environ.get("DUCKDB_PATH", "data/clinical.duckdb"))
BATCH_DIR = Path(os.environ.get("BATCH_DIR", "data/gold/batches"))

# ── Result-set registry ───────────────────────────────────────────────
# Each entry describes a saved MAS run cohort that the dashboard can show.
# Categories group runs by memory level + model so the user can filter.
RESULT_SET_REGISTRY = [
    {"id": "mas_results",                  "label": "270-patient baseline",         "category": "Single-level memory", "model": "GPT-OSS-120B"},
    {"id": "mas_results_baseline_no_mem",  "label": "A/B baseline (memory OFF, N=20)", "category": "Single-level memory", "model": "GPT-OSS-120B"},
    {"id": "mas_results_baseline_b3",      "label": "batch_3 baseline (memory OFF)",  "category": "Single-level memory", "model": "GPT-OSS-120B"},
    {"id": "mas_results_with_memory",      "label": "A/B memory ON (case-based, N=20)", "category": "Case-based memory only", "model": "GPT-OSS-120B"},
    {"id": "mas_results_case_based_50",    "label": "Case-based memory (N=50)",       "category": "Case-based memory only", "model": "GPT-OSS-120B"},
    {"id": "mas_results_improved_10",      "label": "Multi-level memory (N=10 test)", "category": "Multi-level memory",    "model": "GPT-OSS-120B"},
    {"id": "mas_results_improved_50",      "label": "Multi-level memory · batch_4 (N=50)", "category": "Multi-level memory","model": "GPT-OSS-120B"},
    {"id": "mas_results_improved_b3",      "label": "Multi-level memory · batch_3 cold-start (N=50)", "category": "Multi-level memory", "model": "GPT-OSS-120B"},
    {"id": "mas_results_med42",            "label": "Med42-70B A/B (N=20)",           "category": "Model comparison",      "model": "Med42-70B"},
    {"id": "mas_results_deepseek_v4_pro",  "label": "DeepSeek-V4-Pro spot-check",     "category": "Model comparison",      "model": "DeepSeek-V4-Pro"},
]


def _resolve_result_dir(result_set_id: str) -> Path:
    return DATA_GOLD / result_set_id


def _available_result_sets():
    """Filter registry to only entries whose directory exists on disk."""
    out = []
    for entry in RESULT_SET_REGISTRY:
        d = _resolve_result_dir(entry["id"])
        if d.exists() and d.is_dir():
            n = sum(1 for p in d.iterdir() if p.is_dir())
            if n:
                out.append({**entry, "path": d, "count": n})
    return out

st.set_page_config(
    page_title="CMADS Evaluation Dashboard",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    .patient-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 4px 0;
        cursor: pointer;
        transition: all 0.2s;
    }
    .patient-card:hover { border-color: #58a6ff; background: #1a2233; }
    .patient-card-selected { border-color: #58a6ff; background: #1a2744; }
    .tag-direct { background: #1a3a1a; color: #48bb78; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .tag-indirect { background: #3a3a1a; color: #ecc94b; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .tag-miss { background: #3a1a1a; color: #fc8181; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .diagnosis-row {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 6px 0;
    }
    .diagnosis-match {
        background: #1a3a1a;
        border: 2px solid #48bb78;
    }
    .rank-num {
        display: inline-block;
        width: 28px; height: 28px;
        border-radius: 50%;
        text-align: center;
        line-height: 28px;
        font-weight: bold;
        font-size: 14px;
        margin-right: 8px;
    }
    .rank-1 { background: #ffd700; color: #000; }
    .rank-2 { background: #c0c0c0; color: #000; }
    .rank-3 { background: #cd7f32; color: #000; }
    .rank-other { background: #4a5568; color: #fff; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=30)
def load_all_results(mas_dir_str: str):
    mas_dir = Path(mas_dir_str)
    if not mas_dir.exists():
        return []
    patients = []
    for d in sorted(mas_dir.iterdir()):
        if not d.is_dir():
            continue
        uuid = d.name
        gt_path = GOLD_DIR / uuid / "ground_truth.json"
        if not gt_path.exists():
            continue

        gt = json.loads(gt_path.read_text())
        target = gt["target_condition"]

        name = uuid[:12]
        try:
            import duckdb
            con = duckdb.connect(str(DB_PATH), read_only=True)
            r = con.execute("SELECT FIRST || ' ' || LAST FROM patients WHERE Id = ?", [uuid]).fetchone()
            con.close()
            if r:
                name = r[0]
        except Exception:
            pass

        ev_path = d / "evaluation.json"
        ev = json.loads(ev_path.read_text()) if ev_path.exists() else {}

        fd_path = d / "final_diagnosis.json"
        fd = json.loads(fd_path.read_text()) if fd_path.exists() else {}

        trace_path = d / "execution_trace.json"
        trace = json.loads(trace_path.read_text()) if trace_path.exists() else {}

        patients.append({
            "uuid": uuid,
            "name": name,
            "target": target["name"],
            "target_code": target.get("code", ""),
            "encounter_id": target.get("encounter_id", ""),
            "diagnosis_date": target.get("diagnosis_date", ""),
            "cutoff_date": gt.get("cutoff_date", ""),
            "match_type": ev.get("match_type", "?"),
            "match_rank": ev.get("rank", 0),
            "matched_diagnosis": ev.get("matched_diagnosis", ""),
            "eval_reason": ev.get("reason", ""),
            "primary": fd.get("primary_diagnosis", "?"),
            "differential": fd.get("differential", []),
            "unresolved": fd.get("unresolved_findings", []),
            "workup": fd.get("recommended_workup", []),
            "duration_s": trace.get("duration_s", 0),
            "agents": trace.get("agents", []),
        })
    return patients


@st.cache_data(ttl=30)
def get_batches():
    batches = {}
    if BATCH_DIR.exists():
        for bf in sorted(BATCH_DIR.glob("batch_*.json")):
            batches[bf.stem] = set(json.loads(bf.read_text()))
    return batches


@st.cache_data(ttl=60)
def aggregate_result_set(result_set_id: str):
    """Per-result-set roll-up: cohort size, DIRECT %, INDIRECT %, MISS %, Found %, Rank-1, avg time."""
    d = _resolve_result_dir(result_set_id)
    if not d.exists():
        return None
    direct = indirect = miss = rank1 = 0
    total = 0
    time_total = 0.0
    for sub in sorted(d.iterdir()):
        if not sub.is_dir():
            continue
        ev = sub / "evaluation.json"
        if not ev.exists():
            continue
        try:
            e = json.loads(ev.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        total += 1
        m = e.get("match_type")
        if m == "DIRECT":
            direct += 1
            if e.get("rank") == 1:
                rank1 += 1
        elif m == "INDIRECT":
            indirect += 1
            if e.get("rank") == 1:
                rank1 += 1
        else:
            miss += 1
        tr = sub / "execution_trace.json"
        if tr.exists():
            try:
                time_total += float(json.loads(tr.read_text()).get("duration_s") or 0)
            except (json.JSONDecodeError, OSError, TypeError):
                pass
    found = direct + indirect
    return {
        "id": result_set_id,
        "n": total,
        "direct": direct,
        "indirect": indirect,
        "miss": miss,
        "found": found,
        "rank1": rank1,
        "direct_pct": (100 * direct / total) if total else 0,
        "indirect_pct": (100 * indirect / total) if total else 0,
        "miss_pct": (100 * miss / total) if total else 0,
        "found_pct": (100 * found / total) if total else 0,
        "rank1_pct": (100 * rank1 / found) if found else 0,
        "avg_time": (time_total / total) if total else 0,
    }


# ── Sidebar ──
st.sidebar.markdown("## 📊 CMADS Dashboard")

# View toggle
view = st.sidebar.radio("", ["📈 Overview", "🔍 Patient Explorer"], label_visibility="collapsed")

st.sidebar.markdown("---")

# ── Result-set selector — drives both views ──
available_sets = _available_result_sets()
if not available_sets:
    st.title("📊 CMADS Dashboard")
    st.warning("No saved MAS runs found in `data/gold/mas_results*`. Run the pipeline first.")
    st.stop()

# Group by category for a structured selector
sets_by_category: dict[str, list[dict]] = {}
for s in available_sets:
    sets_by_category.setdefault(s["category"], []).append(s)

# Build option list with category prefix for clarity
def _set_label(s):
    return f"{s['label']}  ·  {s['count']} pts  ·  {s['model']}"

set_options = [s["id"] for s in available_sets]
set_labels = {s["id"]: _set_label(s) for s in available_sets}

st.sidebar.markdown("**Run cohort**")

# Category filter chips (compact horizontal radio)
all_categories = list(sets_by_category.keys())
selected_category = st.sidebar.radio(
    "Category",
    options=["All"] + all_categories,
    horizontal=False,
    label_visibility="collapsed",
    key="cat_filter",
)
if selected_category != "All":
    set_options = [s["id"] for s in available_sets if s["category"] == selected_category]

# Default: prefer the most recently produced multi-level run if visible.
default_id = next(
    (sid for sid in ["mas_results_improved_b3", "mas_results_improved_50", "mas_results_case_based_50", "mas_results"] if sid in set_options),
    set_options[0],
)
selected_set_id = st.sidebar.selectbox(
    "Cohort",
    options=set_options,
    format_func=lambda sid: set_labels.get(sid, sid),
    index=set_options.index(default_id) if default_id in set_options else 0,
    label_visibility="collapsed",
    key="set_picker",
)

active = next(s for s in available_sets if s["id"] == selected_set_id)
MAS_DIR = active["path"]

st.sidebar.caption(
    f"**Memory:** {active['category']}  ·  **Model:** {active['model']}"
)

st.sidebar.markdown("---")

patients = load_all_results(str(MAS_DIR))
batches = get_batches()

if not patients:
    st.title("📊 CMADS Dashboard")
    st.warning(f"No results in `{MAS_DIR.name}` — pick another cohort.")
    st.stop()

if view == "🔍 Patient Explorer":
    # Batch filter
    batch_names_explorer = ["All Batches"] + sorted(batches.keys())
    selected_batch_explorer = st.sidebar.selectbox("Batch", batch_names_explorer, key="batch_explorer")

    # Search
    search = st.sidebar.text_input("🔍 Search Patient ID", "")

    # Apply batch filter
    if selected_batch_explorer != "All Batches":
        batch_uuids = batches.get(selected_batch_explorer, set())
        filtered_patients = [p for p in patients if p["uuid"] in batch_uuids]
    else:
        filtered_patients = patients

    st.sidebar.markdown(f"**{len(filtered_patients)} patients**")
    if search:
        filtered_patients = [p for p in filtered_patients if search.lower() in p["uuid"].lower() or search.lower() in p["name"].lower()]

    # Clickable patient list
    selected_uuid = None
    for p in filtered_patients:
        mt = p["match_type"]
        tag_class = "tag-direct" if mt == "DIRECT" else "tag-indirect" if mt == "INDIRECT" else "tag-miss"
        tag_text = f"#{p['match_rank']} {mt}" if mt in ("DIRECT", "INDIRECT") else "MISS"

        if st.sidebar.button(
            f"{p['name'][:20]}  |  {p['target'][:22]}  |  {tag_text}",
            key=p["uuid"],
            use_container_width=True,
        ):
            st.session_state["selected_uuid"] = p["uuid"]

    selected_uuid = st.session_state.get("selected_uuid", filtered_patients[0]["uuid"] if filtered_patients else None)


# ═══════════════════════════════════════════════════════════════
# VIEW: OVERVIEW
# ═══════════════════════════════════════════════════════════════
if view == "📈 Overview":
    st.title("📊 Evaluation Overview")
    st.caption(
        f"Active cohort: **{active['label']}**  ·  {active['category']}  ·  {active['model']}  ·  {active['count']} patients"
    )

    # ── Run Cohort Comparison (all saved cohorts categorised) ──
    st.markdown("### Run Cohort Comparison")
    st.caption(
        "Per-cohort accuracy across every saved MAS run, grouped by memory level "
        "and model. Click a row to focus the dashboard on that cohort via the sidebar."
    )

    rs_rows = []
    for s in available_sets:
        agg = aggregate_result_set(s["id"])
        if not agg or agg["n"] == 0:
            continue
        rs_rows.append({
            "Category": s["category"],
            "Cohort": s["label"],
            "Model": s["model"],
            "N": agg["n"],
            "DIRECT %": f"{agg['direct_pct']:.0f}%",
            "INDIRECT %": f"{agg['indirect_pct']:.0f}%",
            "MISS %": f"{agg['miss_pct']:.0f}%",
            "Found %": f"{agg['found_pct']:.0f}%",
            "Rank-1 (of found)": f"{agg['rank1_pct']:.0f}%",
            "Avg time": f"{agg['avg_time']:.0f}s",
        })

    if rs_rows:
        rs_df = pd.DataFrame(rs_rows)
        # Keep category order: Single → Case-based → Multi-level → Model A/B
        cat_order = {
            "Single-level memory": 0,
            "Case-based memory only": 1,
            "Multi-level memory": 2,
            "Model comparison": 3,
        }
        rs_df["_ord"] = rs_df["Category"].map(lambda c: cat_order.get(c, 99))
        rs_df = rs_df.sort_values(["_ord", "N"], ascending=[True, False]).drop(columns=["_ord"])
        st.dataframe(rs_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Batch selector
    batch_names = ["All Batches"] + sorted(batches.keys())
    selected_batch = st.selectbox("Select Batch", batch_names)

    if selected_batch != "All Batches":
        batch_uuids = batches.get(selected_batch, set())
        display_patients = [p for p in patients if p["uuid"] in batch_uuids]
    else:
        display_patients = patients

    total = len(display_patients)
    direct = sum(1 for p in display_patients if p["match_type"] == "DIRECT")
    indirect = sum(1 for p in display_patients if p["match_type"] == "INDIRECT")
    miss = sum(1 for p in display_patients if p["match_type"] == "MISS")
    found = direct + indirect

    # Hero metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total", total)
    col2.metric("Direct Match", direct, delta=f"{direct*100//max(total,1)}%")
    col3.metric("Indirect Match", indirect, delta=f"{indirect*100//max(total,1)}%")
    col4.metric("Missed", miss, delta=f"-{miss*100//max(total,1)}%", delta_color="inverse")
    col5.metric("Total Found", f"{found*100//max(total,1)}%")

    # Accuracy bar
    st.progress(found / max(total, 1), text=f"{found}/{total} targets found ({found*100//max(total,1)}%)")

    # Rank distribution
    st.markdown("### Where was the target found?")
    col_chart, col_stats = st.columns([3, 1])

    with col_chart:
        found_patients = [p for p in display_patients if p["match_type"] in ("DIRECT", "INDIRECT")]
        if found_patients:
            rank_data = {"Rank #1": 0, "Rank #2": 0, "Rank #3": 0, "Rank #4": 0, "Rank #5": 0}
            for p in found_patients:
                r = p["match_rank"]
                key = f"Rank #{r}" if r <= 5 else "Rank #5"
                rank_data[key] = rank_data.get(key, 0) + 1
            st.bar_chart(pd.DataFrame({"Count": rank_data}))

    with col_stats:
        cumulative = 0
        for r in range(1, 6):
            count = sum(1 for p in found_patients if p["match_rank"] == r)
            cumulative += count
            if count > 0:
                st.markdown(f"**#{r}:** {count} ({count*100//max(len(found_patients),1)}%) — cum: {cumulative*100//max(len(found_patients),1)}%")

    # Per disease
    st.markdown("### By Disease")
    disease_stats = []
    for disease in sorted(set(p["target"] for p in display_patients)):
        d_patients = [p for p in display_patients if p["target"] == disease]
        d_total = len(d_patients)
        d_direct = sum(1 for p in d_patients if p["match_type"] == "DIRECT")
        d_indirect = sum(1 for p in d_patients if p["match_type"] == "INDIRECT")
        d_found = d_direct + d_indirect
        d_ranks = [p["match_rank"] for p in d_patients if p["match_type"] in ("DIRECT", "INDIRECT")]
        avg_rank = sum(d_ranks) / max(len(d_ranks), 1)

        disease_stats.append({
            "Disease": disease,
            "Total": d_total,
            "Direct": d_direct,
            "Indirect": d_indirect,
            "Miss": d_total - d_found,
            "Found %": f"{d_found*100//max(d_total,1)}%",
            "Avg Rank": f"{avg_rank:.1f}" if d_ranks else "—",
        })

    st.dataframe(pd.DataFrame(disease_stats), use_container_width=True, hide_index=True)

    # Batch comparison
    if batches:
        st.markdown("### Batch Comparison")
        batch_stats = []
        for batch_name in sorted(batches.keys()):
            b_uuids = batches[batch_name]
            b_patients = [p for p in patients if p["uuid"] in b_uuids]
            if not b_patients:
                continue
            b_total = len(b_patients)
            b_direct = sum(1 for p in b_patients if p["match_type"] == "DIRECT")
            b_indirect = sum(1 for p in b_patients if p["match_type"] == "INDIRECT")
            b_found = b_direct + b_indirect
            b_rank1 = sum(1 for p in b_patients if p["match_type"] in ("DIRECT", "INDIRECT") and p["match_rank"] == 1)
            b_rank2 = sum(1 for p in b_patients if p["match_type"] in ("DIRECT", "INDIRECT") and p["match_rank"] == 2)
            b_rank3p = sum(1 for p in b_patients if p["match_type"] in ("DIRECT", "INDIRECT") and p["match_rank"] >= 3)
            avg_time = sum(p["duration_s"] for p in b_patients) / max(b_total, 1)

            batch_stats.append({
                "Batch": batch_name,
                "Patients": b_total,
                "Found %": f"{b_found*100//max(b_total,1)}%",
                "Rank #1": b_rank1,
                "Rank #2": b_rank2,
                "Rank #3+": b_rank3p,
                "Miss": b_total - b_found,
                "Avg Time": f"{avg_time:.0f}s",
            })

        st.dataframe(pd.DataFrame(batch_stats), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# VIEW: PATIENT EXPLORER
# ═══════════════════════════════════════════════════════════════
elif view == "🔍 Patient Explorer":
    if not selected_uuid:
        st.title("Select a patient from the sidebar")
        st.stop()

    p = next((p for p in patients if p["uuid"] == selected_uuid), None)
    if not p:
        st.error("Patient not found")
        st.stop()

    # ── Header ──
    st.title(p["name"])
    st.caption(f"Patient ID: `{p['uuid']}`")

    # Load full data
    ehr = json.loads((GOLD_DIR / p["uuid"] / "ehr_case.json").read_text()) if (GOLD_DIR / p["uuid"] / "ehr_case.json").exists() else {}
    lab = json.loads((GOLD_DIR / p["uuid"] / "lab_case.json").read_text()) if (GOLD_DIR / p["uuid"] / "lab_case.json").exists() else {}
    demo = ehr.get("demographics", {})

    # Top info
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Age", demo.get("age", "?"))
    col2.metric("Gender", "Male" if demo.get("gender") == "M" else "Female" if demo.get("gender") == "F" else "?")
    col3.metric("Labs", lab.get("lab_count", 0))
    col4.metric("Conditions", len(ehr.get("conditions", {}).get("active", [])))
    col5.metric("Time", f"{p['duration_s']:.0f}s")

    # ── Target Disease ──
    st.markdown("---")
    st.markdown(f"### 🎯 Target Disease")
    st.warning(
        f"**{p['target']}**\n\n"
        f"SNOMED: `{p['target_code']}` | "
        f"Diagnosed: `{p['diagnosis_date']}` | "
        f"Encounter ID: `{p['encounter_id']}`"
    )

    # Show what happened at the target encounter
    try:
        import duckdb
        con = duckdb.connect(str(DB_PATH), read_only=True)
        enc_info = con.execute("""
            SELECT SUBSTRING(CAST(START AS VARCHAR),1,10) as date,
                   ENCOUNTERCLASS as class,
                   DESCRIPTION as description,
                   REASONDESCRIPTION as reason
            FROM encounters WHERE Id = ?
        """, [p["encounter_id"]]).fetchone()
        if enc_info:
            st.caption(f"Encounter: {enc_info[0]} | {enc_info[1]} | {enc_info[2]} | Reason: {enc_info[3] or '—'}")
        con.close()
    except Exception:
        pass

    # ── MAS Differential ──
    st.markdown("### 🔬 MAS Diagnostic Differential")
    st.caption(f"All diagnoses are for Encounter: `{p['encounter_id']}` | Date: {p['diagnosis_date']}")

    for dx in p["differential"][:5]:
        if not isinstance(dx, dict):
            continue
        rank = dx.get("rank", "?")
        name = dx.get("name", "?")
        prob = dx.get("probability", 0)
        prob_pct = int(prob * 100) if isinstance(prob, (int, float)) else 0

        is_match = (name == p.get("matched_diagnosis", "") or
                    (p["match_type"] in ("DIRECT", "INDIRECT") and rank == p["match_rank"]))

        rank_class = f"rank-{rank}" if rank <= 3 else "rank-other"
        card_class = "diagnosis-match" if is_match else ""

        enc_id_full = p['encounter_id']

        st.markdown(f"""
        <div class="diagnosis-row {card_class}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span class="rank-num {rank_class}">{rank}</span>
                    <strong>{name}</strong>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:20px; font-weight:bold;">{prob_pct}%</span>
                </div>
            </div>
            <div style="font-size:11px; color:#8b949e; margin-top:4px;">
                Encounter: <code>{enc_id_full}</code> | Patient: <code>{p['uuid']}</code>
            </div>
            <div style="background:#2d3748; border-radius:4px; height:6px; margin-top:8px;">
                <div style="background:{'#48bb78' if is_match else '#4a5568'}; width:{prob_pct}%; height:6px; border-radius:4px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if is_match:
            match_type = p["match_type"]
            reason = p.get("eval_reason", "")
            if match_type == "DIRECT":
                st.success(f"✅ **DIRECT MATCH** — This is the target disease. {reason}")
            elif match_type == "INDIRECT":
                st.warning(f"🔗 **INDIRECT MATCH** — Clinically related to the target. {reason}")

        # Evidence
        evidence = dx.get("supporting_evidence", [])
        reasoning = dx.get("reasoning", "")
        if evidence or reasoning:
            with st.expander(f"Evidence for #{rank}"):
                for e in evidence:
                    if isinstance(e, dict):
                        st.markdown(f"- **[{e.get('source', '?')}]** {e.get('finding', '?')}")
                if reasoning:
                    st.markdown(f"**Reasoning:** {reasoning[:300]}")

    # Miss message
    if p["match_type"] == "MISS":
        st.error(f"❌ **MISS** — Target disease not found in differential. {p.get('eval_reason', '')}")

    # Unresolved & workup
    if p.get("unresolved"):
        st.markdown("**Unresolved Findings:**")
        for u in p["unresolved"][:5]:
            st.markdown(f"- ❓ {u}")

    if p.get("workup"):
        st.markdown("**Recommended Workup:**")
        for w in p["workup"][:5]:
            st.markdown(f"- → {w}")

    # ── Agent Execution ──
    st.markdown("---")
    st.markdown("### 🤖 Agent Execution")

    if p["agents"]:
        agent_cols = st.columns(5)
        labels = {"ehr_analyst": "EHR Analyst", "lab_interpreter": "Lab Interpreter",
                  "diagnostic_reasoning": "Diagnostic", "clinical_reviewer": "Reviewer",
                  "final_diagnosis": "Refiner"}
        for col, a in zip(agent_cols, p["agents"]):
            status = a.get("status", "?")
            icon = "✅" if status == "success" else "⚠️" if status == "partial" else "❌"
            time_s = a.get("execution_ms", 0) / 1000
            label = labels.get(a["agent_id"], a["agent_id"])
            col.markdown(f"**{icon} {label}**<br>{time_s:.0f}s", unsafe_allow_html=True)
            if a.get("error"):
                col.caption(f"Error: {a['error'][:40]}")

    # ── EHR, Labs, Encounters (Tabs) ──
    st.markdown("---")
    tab_ehr, tab_labs, tab_meds, tab_encounters = st.tabs(["📋 EHR Record", "🧪 Lab Results", "💊 Treatment Plan", "🏥 Encounters"])

    with tab_ehr:
        conditions = ehr.get("conditions", {})
        active = conditions.get("active", []) if isinstance(conditions, dict) else conditions

        col_cond, col_meds = st.columns(2)

        with col_cond:
            st.markdown(f"**Active Conditions ({len(active)})**")
            if active:
                cond_data = [{
                    "Condition": c.get("condition", c.get("name", "?")),
                    "Onset": c.get("start_date", "?"),
                } for c in active if isinstance(c, dict)]
                st.dataframe(pd.DataFrame(cond_data), use_container_width=True, hide_index=True, height=300)

        with col_meds:
            meds = ehr.get("medications", {})
            active_meds = meds.get("active", []) if isinstance(meds, dict) else meds
            st.markdown(f"**Medications ({len(active_meds)})**")
            if active_meds:
                med_data = [{
                    "Medication": m.get("medication", m.get("name", "?"))[:45],
                    "For": m.get("condition_treated", "?")[:30],
                } for m in active_meds if isinstance(m, dict)]
                st.dataframe(pd.DataFrame(med_data), use_container_width=True, hide_index=True, height=300)
            else:
                st.info("No medications")

        # Risk scores and comorbidity
        col_risk, col_comorb = st.columns(2)
        with col_risk:
            risk = ehr.get("risk_scores", {})
            if risk:
                st.markdown("**Risk Scores**")
                risk_data = [{"Metric": k, "Value": str(v)} for k, v in risk.items() if v is not None]
                st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)

        with col_comorb:
            comorb = ehr.get("comorbidity", {})
            flags = comorb.get("flags", {})
            active_flags = [k.replace("has_", "").replace("_", " ").title() for k, v in flags.items() if v]
            if active_flags:
                st.markdown("**Comorbidity Flags**")
                st.markdown(" | ".join([f"**{f}**" for f in active_flags]))
                st.metric("Charlson Index", comorb.get("charlson_index", "?"))

    with tab_labs:
        col_latest, col_flags = st.columns([2, 1])

        with col_latest:
            latest = lab.get("latest_labs", [])
            st.markdown(f"**Latest Lab Results ({len(latest)})**")
            if latest:
                lab_data = [{
                    "Test": l.get("lab_name", l.get("name", "?"))[:40],
                    "Value": l.get("value_latest", l.get("value", "?")),
                    "Units": l.get("units", ""),
                } for l in latest if isinstance(l, dict)]
                st.dataframe(pd.DataFrame(lab_data), use_container_width=True, hide_index=True, height=400)

        with col_flags:
            flags_raw = lab.get("critical_flags", {})
            flags_list = flags_raw.get("flags", []) if isinstance(flags_raw, dict) else flags_raw
            st.markdown(f"**Critical Flags ({len(flags_list)})**")
            if flags_list:
                for f in flags_list:
                    if isinstance(f, dict):
                        sev = f.get("severity", "?")
                        icon = "🔴" if sev == "critical" else "🟡" if sev == "abnormal" else "🟢"
                        st.markdown(f"{icon} **{f.get('lab_name', '?')[:30]}**: {f.get('value_latest', f.get('value', '?'))} — {f.get('flag', '?')}")
            else:
                st.info("No critical flags")

            # Vitals
            vitals = lab.get("recent_vitals", [])
            if vitals:
                st.markdown(f"**Vitals ({len(vitals)})**")
                for v in vitals:
                    if isinstance(v, dict):
                        vname = v.get("vital", v.get("name", "?"))
                        st.markdown(f"- {vname}: **{v.get('value', '?')}** {v.get('units', '')}")

    with tab_meds:
        tp_path = MAS_DIR / selected_uuid / "treatment_planning.json"
        if tp_path.exists():
            tp = json.loads(tp_path.read_text())
            if tp.get("medications"):
                treated = tp.get("primary_diagnosis_treated", "?")
                guideline_ref = tp.get("nice_guideline_used", "?")

                # Header with guideline info
                st.markdown(f"""
                <div style="background:linear-gradient(135deg, #0a2a1a 0%, #1a3a2a 100%); border:2px solid #48bb78; border-radius:12px; padding:16px 20px; margin-bottom:16px;">
                    <div style="font-size:18px; font-weight:bold; color:#48bb78;">💊 Treatment Plan</div>
                    <div style="margin-top:8px; font-size:14px;">
                        <strong>Treating:</strong> {treated}<br>
                        <strong>NICE Guideline:</strong> <span style="background:#48bb7830; padding:2px 10px; border-radius:4px; color:#48bb78;">{guideline_ref}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Load top 3 guidelines from Qdrant (same search the agent did)
                qdrant_results = []
                try:
                    from src.vectordb.query_guidelines import search_guidelines
                    qdrant_results = search_guidelines(treated, top_k=3)
                except Exception:
                    pass

                # Show Qdrant search results — which 3 were returned and which was chosen
                if qdrant_results:
                    st.markdown("### 🔍 Guideline Search (Qdrant Vector DB)")
                    st.caption(f"Query: \"{treated}\" → BioLORD-2023 embedding → top 3 matches")

                    for i, qr in enumerate(qdrant_results):
                        is_chosen = (i == 0)
                        border_color = "#48bb78" if is_chosen else "#30363d"
                        badge = "SELECTED" if is_chosen else f"Match #{i+1}"
                        badge_color = "#48bb78" if is_chosen else "#8b949e"

                        st.markdown(f"""
                        <div style="background:#161b22; border:2px solid {border_color}; border-radius:8px; padding:12px 16px; margin:6px 0;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div>
                                    <span style="background:{badge_color}25; color:{badge_color}; padding:2px 10px; border-radius:12px; font-size:11px; font-weight:600;">{badge}</span>
                                    <strong style="margin-left:8px;">{qr['disease_name']}</strong>
                                </div>
                                <span style="font-size:14px; font-weight:bold; color:{badge_color};">Score: {qr['score']:.3f}</span>
                            </div>
                            <div style="font-size:12px; color:#8b949e; margin-top:6px;">
                                {qr['nice_guideline']} — {qr['nice_title']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                gl = qdrant_results[0]["guideline"] if qdrant_results else None

                if gl:
                    with st.expander(f"📖 NICE Guideline: {gl.get('nice_guideline', '?')} — {gl.get('nice_title', '?')}", expanded=False):
                        st.caption(f"Source: {gl.get('source', '?')}")

                        col_first, col_second = st.columns(2)

                        with col_first:
                            st.markdown("**✅ First-Line Treatment:**")
                            for t in gl.get("first_line_treatment", []):
                                if isinstance(t, dict):
                                    examples = ", ".join(t.get("examples", []))
                                    st.markdown(f"""
                                    <div style="background:#48bb7810; border-left:3px solid #48bb78; padding:6px 10px; margin:4px 0; border-radius:0 4px 4px 0; font-size:12px;">
                                        <strong>{t.get('drug_class', '?')}</strong><br>
                                        <span style="color:#8b949e;">{examples}</span><br>
                                        <em>{t.get('indication', '')}</em>
                                    </div>
                                    """, unsafe_allow_html=True)

                            if gl.get("second_line_treatment"):
                                st.markdown("**🔄 Second-Line Treatment:**")
                                for t in gl.get("second_line_treatment", []):
                                    if isinstance(t, dict):
                                        examples = ", ".join(t.get("examples", []))
                                        st.markdown(f"""
                                        <div style="background:#ecc94b10; border-left:3px solid #ecc94b; padding:6px 10px; margin:4px 0; border-radius:0 4px 4px 0; font-size:12px;">
                                            <strong>{t.get('drug_class', '?')}</strong><br>
                                            <span style="color:#8b949e;">{examples}</span>
                                        </div>
                                        """, unsafe_allow_html=True)

                        with col_second:
                            st.markdown("**🚫 Contraindicated Drugs:**")
                            for c in gl.get("contraindicated_drugs", []):
                                if isinstance(c, dict):
                                    st.markdown(f"""
                                    <div style="background:#fc818110; border-left:3px solid #fc8181; padding:6px 10px; margin:4px 0; border-radius:0 4px 4px 0; font-size:12px;">
                                        <strong>{c.get('drug', '?')}</strong><br>
                                        <span style="color:#fc8181;">{c.get('reason', '?')}</span>
                                    </div>
                                    """, unsafe_allow_html=True)

                            st.markdown("**📊 Monitoring:**")
                            mon = gl.get("monitoring", [])
                            if isinstance(mon, list):
                                for m in mon:
                                    st.markdown(f"<div style='font-size:12px; margin:2px 0;'>• {m}</div>", unsafe_allow_html=True)
                            elif isinstance(mon, dict):
                                for k, v in mon.items():
                                    st.markdown(f"<div style='font-size:12px; margin:2px 0;'>• <strong>{k}:</strong> {v}</div>", unsafe_allow_html=True)

                        # Non-pharmacological
                        non_pharm = gl.get("non_pharmacological", [])
                        if non_pharm:
                            st.markdown("**🏃 Guideline Lifestyle Recommendations:**")
                            cols = st.columns(2)
                            for i, n in enumerate(non_pharm):
                                cols[i % 2].markdown(f"<div style='font-size:12px; margin:2px 0;'>✓ {n}</div>", unsafe_allow_html=True)

                        # Full JSON
                        with st.expander("📄 Full Guideline JSON"):
                            st.json(gl)

                # Medications
                st.markdown("### 📋 Prescribed Medications")
                for i, m in enumerate(tp.get("medications", [])):
                    if not isinstance(m, dict):
                        continue
                    line = m.get("line", "").replace("_", " ").title()
                    if "First" in line:
                        line_color = "#48bb78"
                        line_bg = "#48bb7815"
                    elif "Second" in line:
                        line_color = "#ecc94b"
                        line_bg = "#ecc94b15"
                    else:
                        line_color = "#8b949e"
                        line_bg = "#8b949e15"

                    st.markdown(f"""
                    <div style="background:{line_bg}; border-left:4px solid {line_color}; border-radius:0 8px 8px 0; padding:14px 18px; margin:8px 0;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <span style="font-size:16px; font-weight:bold; color:#e6e6e6;">{m.get('medication', '?')}</span>
                                <span style="background:{line_color}25; color:{line_color}; padding:2px 10px; border-radius:12px; font-size:11px; margin-left:8px; font-weight:600;">{line}</span>
                            </div>
                            <span style="color:{line_color}; font-size:13px; font-weight:600;">{m.get('drug_class', '')}</span>
                        </div>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:10px; font-size:13px;">
                            <div><span style="color:#8b949e;">Dose:</span> <strong>{m.get('dose', '?')}</strong></div>
                            <div><span style="color:#8b949e;">Duration:</span> <strong>{m.get('duration', '?')}</strong></div>
                        </div>
                        <div style="margin-top:6px; font-size:13px;"><span style="color:#8b949e;">Purpose:</span> {m.get('purpose', '?')}</div>
                        <div style="margin-top:4px; font-size:12px; color:#58a6ff;">📘 {m.get('nice_justification', '?')}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Interactions
                interactions = tp.get("interactions_checked", [])
                if interactions:
                    st.markdown("### ⚠️ Drug Interactions")
                    for ix in interactions:
                        if not isinstance(ix, dict):
                            continue
                        severity = ix.get("severity", "moderate")
                        if severity == "severe":
                            sev_color = "#fc8181"
                            sev_bg = "#fc818115"
                            sev_icon = "🔴"
                        elif severity == "moderate":
                            sev_color = "#ecc94b"
                            sev_bg = "#ecc94b15"
                            sev_icon = "🟡"
                        else:
                            sev_color = "#48bb78"
                            sev_bg = "#48bb7815"
                            sev_icon = "🟢"
                        pair = " + ".join(ix.get("drug_pair", []))
                        st.markdown(f"""
                        <div style="background:{sev_bg}; border-left:3px solid {sev_color}; padding:10px 14px; margin:6px 0; border-radius:0 6px 6px 0;">
                            <div style="font-weight:bold; color:{sev_color};">{sev_icon} {pair} <span style="font-size:12px;">({severity})</span></div>
                            <div style="font-size:13px; margin-top:4px;">{ix.get('interaction', '?')}</div>
                            <div style="font-size:12px; color:#8b949e; margin-top:4px;"><em>Action: {ix.get('action', '?')}</em></div>
                        </div>
                        """, unsafe_allow_html=True)

                # Contraindications
                contras = tp.get("contraindications", [])
                if contras:
                    st.markdown("### 🚫 Contraindications")
                    for c in contras:
                        if not isinstance(c, dict):
                            continue
                        alt = c.get("alternative", "")
                        alt_text = f"<div style='font-size:12px; color:#48bb78; margin-top:4px;'>✅ Alternative: {alt}</div>" if alt else ""
                        st.markdown(f"""
                        <div style="background:#fc818115; border-left:3px solid #fc8181; padding:10px 14px; margin:6px 0; border-radius:0 6px 6px 0;">
                            <div style="font-weight:bold; color:#fc8181;">🚫 {c.get('drug', '?')}</div>
                            <div style="font-size:13px; margin-top:4px;">{c.get('reason', '?')}</div>
                            {alt_text}
                        </div>
                        """, unsafe_allow_html=True)

                # Assumptions & Warnings
                warnings = tp.get("assumptions_warnings", [])
                if warnings:
                    st.markdown("### ⚠️ Assumptions & Missing Data Warnings")
                    for w in warnings:
                        st.markdown(f"""
                        <div style="background:#ecc94b10; border-left:3px solid #ecc94b; padding:8px 12px; margin:4px 0; border-radius:0 6px 6px 0; font-size:13px;">
                            ⚠️ {w}
                        </div>
                        """, unsafe_allow_html=True)

                # Summary
                if tp.get("treatment_summary"):
                    st.markdown("### Summary")
                    st.success(tp["treatment_summary"])

            elif "SKIPPED" in tp.get("primary_diagnosis_treated", ""):
                st.warning("💊 Treatment not generated — diagnosis was not a DIRECT match. Only patients with confirmed diagnoses receive treatment plans.")
            elif "ERROR" in tp.get("treatment_summary", ""):
                st.error(f"💊 {tp['treatment_summary']}")
            else:
                st.info("Treatment plan is empty.")
        else:
            st.info("No treatment plan available. Run the treatment agent first.")

    with tab_encounters:
        try:
            import duckdb
            con = duckdb.connect(str(DB_PATH), read_only=True)
            enc_df = con.execute("""
                SELECT
                    Id as encounter_id,
                    SUBSTRING(CAST(START AS VARCHAR),1,10) as date,
                    ENCOUNTERCLASS as class,
                    DESCRIPTION as description,
                    REASONDESCRIPTION as reason
                FROM encounters
                WHERE PATIENT = ?
                ORDER BY START DESC
            """, [selected_uuid]).fetchdf()

            if not enc_df.empty:
                st.markdown(f"**All Encounters ({len(enc_df)})**")

                # Summary chart
                class_counts = enc_df["class"].value_counts()
                st.bar_chart(class_counts)

                # Full table
                st.dataframe(enc_df, use_container_width=True, hide_index=True, height=300)

                # Encounter search — look up conditions for a specific encounter
                st.markdown("---")
                st.markdown("**🔍 Search Encounter — View Conditions**")
                enc_search = st.text_input("Enter Encounter ID", key="enc_search")
                if enc_search:
                    cond_df = con.execute("""
                        SELECT
                            DESCRIPTION as condition,
                            CODE as snomed_code,
                            SUBSTRING(CAST(START AS VARCHAR),1,10) as start_date,
                            SUBSTRING(CAST(STOP AS VARCHAR),1,10) as end_date
                        FROM conditions
                        WHERE ENCOUNTER = ?
                        ORDER BY START
                    """, [enc_search]).fetchdf()

                    obs_df = con.execute("""
                        SELECT
                            DESCRIPTION as test,
                            VALUE as value,
                            UNITS as units,
                            CATEGORY as category
                        FROM observations
                        WHERE ENCOUNTER = ?
                        ORDER BY CATEGORY, DESCRIPTION
                    """, [enc_search]).fetchdf()

                    med_df = con.execute("""
                        SELECT
                            DESCRIPTION as medication,
                            REASONDESCRIPTION as prescribed_for,
                            SUBSTRING(CAST(START AS VARCHAR),1,10) as start_date,
                            SUBSTRING(CAST(STOP AS VARCHAR),1,10) as end_date
                        FROM medications
                        WHERE ENCOUNTER = ?
                    """, [enc_search]).fetchdf()

                    col_c, col_o = st.columns(2)

                    with col_c:
                        st.markdown(f"**Conditions recorded ({len(cond_df)})**")
                        if not cond_df.empty:
                            st.dataframe(cond_df, use_container_width=True, hide_index=True)
                        else:
                            st.info("No conditions for this encounter")

                        st.markdown(f"**Medications prescribed ({len(med_df)})**")
                        if not med_df.empty:
                            st.dataframe(med_df, use_container_width=True, hide_index=True)
                        else:
                            st.info("No medications for this encounter")

                    with col_o:
                        st.markdown(f"**Observations/Labs ({len(obs_df)})**")
                        if not obs_df.empty:
                            st.dataframe(obs_df, use_container_width=True, hide_index=True, height=400)
                        else:
                            st.info("No observations for this encounter")
            else:
                st.info("No encounters found — close Beekeeper Studio if DuckDB is locked")

            con.close()
        except Exception as e:
            st.warning(f"Cannot load encounters: {e}")

    # ── Raw JSON ──
    with st.expander("📄 Raw JSON Data"):
        raw_select = st.selectbox("File", ["final_diagnosis", "ehr_analyst", "lab_interpreter",
                                            "diagnostic_reasoning", "clinical_reviewer",
                                            "evaluation", "execution_trace", "ground_truth"])
        if raw_select == "ground_truth":
            raw_path = GOLD_DIR / selected_uuid / "ground_truth.json"
        elif raw_select in ("ehr_analyst", "lab_interpreter", "diagnostic_reasoning", "clinical_reviewer", "final_diagnosis", "evaluation", "execution_trace"):
            raw_path = MAS_DIR / selected_uuid / f"{raw_select}.json"
        else:
            raw_path = None

        if raw_path and raw_path.exists():
            st.json(json.loads(raw_path.read_text()))
        else:
            st.info(f"{raw_select}.json not found")

"""Memory Trace — inspect every memory tier for any completed patient run.

Streamlit auto-loads this as a page in the sidebar.

For a given patient + result directory, shows:
  - Tier 1 (Working) — scratchpad snapshot if it was persisted in the trace
  - Tier 2 (Episodic) — full session_memory.json timeline + per-agent digest
  - Tier 3 (Semantic) — disease-level aggregate stats from semantic_memory.json
  - Tier 4 (Case-based) — top-K similar past patients from Qdrant
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

# Make project imports work when streamlit launches us.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="CMADS · Memory Trace", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .ev-card { background: #161b22; border: 1px solid #30363d;
               border-radius: 8px; padding: 10px 14px; margin: 6px 0; }
    .ev-time { font-family: "SF Mono", "Geist Mono", monospace; font-size: 11px;
               color: #8b949e; letter-spacing: 0.05em; }
    .ev-type { display: inline-block; padding: 2px 8px; border-radius: 4px;
               font-size: 11px; font-family: monospace; letter-spacing: 0.06em;
               text-transform: uppercase; }
    .ev-critique         { background: #4c1d24; color: #fc8181; }
    .ev-confidence_check { background: #1d3a4c; color: #63b3ed; }
    .ev-decision         { background: #1f3a1d; color: #68d391; }
    .ev-agent_start      { background: #2d2d2d; color: #cbd5e0; }
    .ev-agent_complete   { background: #2d2d2d; color: #cbd5e0; }
    .ev-default          { background: #2d2d2d; color: #cbd5e0; }
    .ev-summary { color: #e6edf3; font-size: 14px; margin-top: 4px; }
    .ev-payload { font-family: monospace; font-size: 12px; color: #8b949e; margin-top: 4px; }
    .ev-tags { font-size: 11px; color: #6e7681; margin-top: 4px; font-family: monospace; }
    .tier-pill { display: inline-block; padding: 4px 10px; border-radius: 12px;
                 font-size: 12px; font-family: monospace; letter-spacing: 0.06em;
                 text-transform: uppercase; }
    .pill-t1 { background: #4d2810; color: #f6ad55; }
    .pill-t2 { background: #1b3a52; color: #63b3ed; }
    .pill-t3 { background: #103a34; color: #4fd1c5; }
    .pill-t4 { background: #2d2952; color: #b794f4; }
    .case-row { background: #161b22; border-left: 3px solid #b794f4;
                padding: 10px 14px; margin: 6px 0; border-radius: 0 6px 6px 0; }
    .small-mono { font-family: monospace; font-size: 12px; color: #8b949e; }
</style>
""", unsafe_allow_html=True)

st.title("🧠 Memory Trace")
st.caption(
    "Per-patient inspection of all four memory tiers. Pick a result "
    "directory, then a patient — see exactly what each agent wrote and read."
)

# ── Choose result directory ────────────────────────────────────────
DEFAULT = "data/gold/mas_results"
candidate_dirs = [
    ("mas_results (original / no-memory · 270-patient cohort)",
     ROOT / "data/gold/mas_results"),
    ("mas_results_with_memory (20-patient A/B · memory ON · old Tier-4)",
     ROOT / "data/gold/mas_results_with_memory"),
    ("mas_results_baseline_no_mem (20-patient A/B · memory OFF)",
     ROOT / "data/gold/mas_results_baseline_no_mem"),
    ("mas_results_case_based_50 (50-patient · memory ON · case-based Tier 4)",
     ROOT / "data/gold/mas_results_case_based_50"),
]
existing = [(label, p) for label, p in candidate_dirs if p.exists()]

if not existing:
    st.error("No result directories found. Run the pipeline first.")
    st.stop()

picker_labels = [label for label, _ in existing]
chosen_idx = st.sidebar.selectbox(
    "Result directory",
    range(len(picker_labels)),
    format_func=lambda i: picker_labels[i],
    index=0,
)
mas_dir: Path = existing[chosen_idx][1]
st.sidebar.markdown(f"**Reading:** `{mas_dir.relative_to(ROOT)}`")

# ── Pick a patient ─────────────────────────────────────────────────
patient_dirs = sorted(p for p in mas_dir.iterdir() if p.is_dir())
if not patient_dirs:
    st.warning(f"No patient subdirs in `{mas_dir}`.")
    st.stop()

uuid_list = [p.name for p in patient_dirs]
search = st.sidebar.text_input("🔍 Filter by UUID prefix", "").strip().lower()
filtered = [u for u in uuid_list if search in u.lower()] if search else uuid_list

st.sidebar.markdown(f"**Patients in folder:** {len(uuid_list)}  ·  matching: {len(filtered)}")

selected_uuid = st.sidebar.selectbox(
    "Patient",
    filtered,
    format_func=lambda u: u[:12] + "…",
)
if not selected_uuid:
    st.stop()
patient_dir = mas_dir / selected_uuid

# ── Load the patient's data ────────────────────────────────────────
def _load(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

evaluation = _load(patient_dir / "evaluation.json") or {}
final_dx = _load(patient_dir / "final_diagnosis.json") or {}
trace = _load(patient_dir / "execution_trace.json") or {}
session_memory = _load(patient_dir / "session_memory.json") or {}

# ── Header strip ───────────────────────────────────────────────────
match_type = evaluation.get("match_type", "?")
matched_diagnosis = evaluation.get("matched_diagnosis", final_dx.get("primary_diagnosis", "?"))
rank = evaluation.get("rank")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Patient", selected_uuid[:12] + "…")
c2.metric("Match type", match_type)
c3.metric("Rank when found", rank if rank else "—")
c4.metric("Run duration", f"{trace.get('duration_s', 0):.0f}s")

st.markdown(f"**Matched diagnosis:** {matched_diagnosis}")

st.divider()

# ── TIER 2 · Episodic timeline ─────────────────────────────────────
events = (session_memory or {}).get("events") or []

st.markdown('<span class="tier-pill pill-t2">TIER 2 · EPISODIC</span>', unsafe_allow_html=True)
st.markdown(f"#### Session memory  ·  {len(events)} events")
st.caption(
    "Append-only typed timeline written by every agent. Reviewer + Refiner "
    "read this as the reasoning chain."
)

if not events:
    st.info(
        "No `session_memory.json` for this patient — the run pre-dates the "
        "memory subsystem, or memory was disabled."
    )
else:
    # Filter
    filt_col1, filt_col2, filt_col3 = st.columns([1, 1, 2])
    all_agents = sorted(set(e.get("agent_id", "?") for e in events))
    all_types = sorted(set(e.get("event_type", "?") for e in events))
    sel_agents = filt_col1.multiselect("Filter by agent", all_agents, default=all_agents)
    sel_types = filt_col2.multiselect("Filter by event type", all_types, default=all_types)
    show_payload = filt_col3.checkbox("Show payload JSON", value=False)

    filtered_events = [
        e for e in events
        if e.get("agent_id") in sel_agents and e.get("event_type") in sel_types
    ]
    st.caption(f"Showing {len(filtered_events)} of {len(events)} events")

    for ev in filtered_events:
        et = ev.get("event_type", "default")
        css = f"ev-{et if et in {'critique','confidence_check','decision','agent_start','agent_complete'} else 'default'}"
        agent_id = ev.get("agent_id", "?")
        ts = ev.get("timestamp", "")
        summary = ev.get("summary", "")
        payload = ev.get("payload") or {}
        tags = ev.get("tags") or []

        st.markdown(
            f'<div class="ev-card">'
            f'<div class="ev-time">{ts}  ·  <strong>{agent_id}</strong>  ·  '
            f'<span class="ev-type {css}">{et}</span></div>'
            f'<div class="ev-summary">{summary}</div>'
            f'{"<div class=\"ev-payload\">" + json.dumps(payload) + "</div>" if (payload and show_payload) else ""}'
            f'{"<div class=\"ev-tags\">tags: " + ", ".join(tags) + "</div>" if tags else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── TIER 1 · Working memory (best-effort: from agent_outputs / trace) ───
# Working memory isn't persisted by default — it lives only in state.scratchpad
# during the run. We can show whatever the diagnostic agent stashed if it
# made it into the saved diagnostic_reasoning.json (it currently doesn't).
diagnostic_out = _load(patient_dir / "diagnostic_reasoning.json") or {}

st.markdown('<span class="tier-pill pill-t1">TIER 1 · WORKING</span>', unsafe_allow_html=True)
st.markdown("#### Working memory  ·  per-agent scratch")
st.caption(
    "Per-agent scratch space (state.scratchpad). Not persisted to disk by "
    "design — but the Diagnostic agent's confidence trajectory is "
    "reconstructable from the Tier-2 confidence_check events above."
)

confidence_events = [
    e for e in events
    if e.get("event_type") == "confidence_check"
    and e.get("agent_id") == "diagnostic_reasoning"
]
if confidence_events:
    trajectory = [
        (e.get("payload", {}).get("round"),
         e.get("payload", {}).get("confidence"))
        for e in confidence_events
    ]
    st.markdown("**Diagnostic confidence trajectory** (reconstructed):")
    cols = st.columns(len(trajectory))
    for col, (rnd, conf) in zip(cols, trajectory):
        col.metric(f"Round {rnd}", f"{conf}/100")
else:
    st.info("No diagnostic confidence_check events in this run's session memory.")

st.divider()

# ── TIER 3 · Semantic memory (cross-session disease stats) ──────────
st.markdown('<span class="tier-pill pill-t3">TIER 3 · SEMANTIC</span>', unsafe_allow_html=True)
st.markdown("#### Semantic memory  ·  cross-session disease aggregates")

# Try to find the semantic memory file — could be in several places
semantic_candidates = [
    ROOT / "data/gold/memory/semantic_memory.json",
    ROOT / "data/gold/memory_with_memory/semantic_memory.json",
    ROOT / "data/gold/memory_case_based_50/semantic_memory.json",
]
semantic_path = next((p for p in semantic_candidates if p.exists()), None)
semantic_store = _load(semantic_path) if semantic_path else None

if semantic_store:
    st.caption(f"Reading `{semantic_path.relative_to(ROOT)}`  ·  {len(semantic_store)} diseases tracked")

    # Highlight the matched-diagnosis entry first if present
    primary_entry = None
    for d_name, payload in semantic_store.items():
        if d_name.lower().strip() == (matched_diagnosis or "").lower().strip():
            primary_entry = (d_name, payload)
            break

    if primary_entry:
        d_name, p = primary_entry
        st.markdown(f"**Match for this patient → `{d_name}`**")
        kc1, kc2, kc3, kc4 = st.columns(4)
        runs = p.get("runs_observed", 0)
        direct = p.get("direct_matches", 0)
        rank1 = p.get("rank1_when_found", 0)
        avg_conf = p.get("avg_primary_confidence", 0)
        kc1.metric("Runs observed", runs)
        kc2.metric("DIRECT", f"{direct}/{runs}" if runs else "0")
        kc3.metric("Rank-1 (of DIRECT)", f"{rank1}/{direct}" if direct else "0")
        kc4.metric("Avg confidence", f"{avg_conf:.1f}")
        if p.get("common_evidence_patterns"):
            with st.expander("Evidence patterns observed"):
                for ep in p["common_evidence_patterns"]:
                    st.markdown(f"- {ep}")

    with st.expander(f"All {len(semantic_store)} diseases in store"):
        # Build a tiny dataframe
        try:
            import pandas as pd
            rows = []
            for d_name, p in semantic_store.items():
                runs = p.get("runs_observed", 0)
                rows.append({
                    "Disease": d_name,
                    "Runs": runs,
                    "DIRECT": p.get("direct_matches", 0),
                    "INDIRECT": p.get("indirect_matches", 0),
                    "MISS": p.get("misses", 0),
                    "Rank-1": p.get("rank1_when_found", 0),
                    "Avg conf": round(p.get("avg_primary_confidence", 0), 1),
                })
            df = pd.DataFrame(rows).sort_values("Runs", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError:
            st.json(semantic_store)
else:
    st.info("No semantic_memory.json found yet.")

st.divider()

# ── TIER 4 · Case-based memory ──────────────────────────────────────
st.markdown('<span class="tier-pill pill-t4">TIER 4 · CASE-BASED</span>', unsafe_allow_html=True)
st.markdown("#### Case-based memory  ·  similar past patients in Qdrant")

st.caption(
    "Pulls the patient's row from the `patient_cases` collection (was "
    "this patient indexed?), then queries the top-K most similar past "
    "patients via BioLORD-2023 embeddings."
)

show_qdrant = st.checkbox("Query Qdrant now", value=False, key="qdrant_query")

if show_qdrant:
    try:
        from src.config import cfg
        from src.memory.case_based_memory import (
            PATIENT_COLLECTION, _stable_id_from_uuid, _to_list,
            _get_client, _get_model,
        )

        client = _get_client()
        if client is None:
            st.warning("Qdrant client not available — QDRANT_URL is unset or unreachable.")
        else:
            collections = [c.name for c in client.get_collections().collections]
            st.caption(f"Collections in Qdrant: {collections}")

            if PATIENT_COLLECTION not in collections:
                st.warning(f"`{PATIENT_COLLECTION}` collection not yet created.")
            else:
                info = client.get_collection(PATIENT_COLLECTION)
                st.markdown(f"**Total cases indexed:** {info.points_count}")

                # Pull this patient's stored case
                pid = _stable_id_from_uuid(selected_uuid)
                points = client.retrieve(
                    collection_name=PATIENT_COLLECTION,
                    ids=[pid],
                    with_payload=True,
                    with_vectors=False,
                )
                if points:
                    payload = points[0].payload or {}
                    st.markdown("**This patient's stored case:**")
                    st.markdown(
                        f'<div class="case-row">'
                        f'<div><strong>Diagnosis:</strong> {payload.get("matched_diagnosis","?")}  '
                        f'·  match: <code>{payload.get("match_type","?")}</code>  '
                        f'·  rank: {payload.get("rank_when_found", "?")}</div>'
                        f'<div class="small-mono" style="margin-top:4px">'
                        f'indexed_at: {payload.get("indexed_at","?")}</div>'
                        f'<div style="margin-top:6px">{payload.get("case_text","")[:400]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Now query top-K similar (excluding self)
                    case_text = payload.get("case_text") or ""
                    if case_text:
                        model = _get_model()
                        if model is None:
                            st.warning("Embedding model not available — skipping recall.")
                        else:
                            embedding = _to_list(model.encode(case_text))
                            results = client.query_points(
                                collection_name=PATIENT_COLLECTION,
                                query=embedding,
                                limit=8,
                            )
                            sims = [
                                p for p in results.points
                                if (p.payload or {}).get("patient_uuid") != selected_uuid
                            ][:5]
                            st.markdown(f"**Top {len(sims)} similar past patients** (self-excluded):")
                            for r in sims:
                                pl = r.payload or {}
                                st.markdown(
                                    f'<div class="case-row">'
                                    f'<div><span class="small-mono">'
                                    f'similarity={r.score:.3f}  ·  uuid={(pl.get("patient_uuid","?"))[:12]}…'
                                    f'</span></div>'
                                    f'<div><strong>{pl.get("matched_diagnosis","?")}</strong>  '
                                    f'·  match: <code>{pl.get("match_type","?")}</code>  '
                                    f'·  rank: {pl.get("rank_when_found","?")}</div>'
                                    f'<div class="small-mono">'
                                    f'{(pl.get("case_text","") or "")[:180]}…</div>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                else:
                    st.warning(
                        "This patient is not yet indexed in `patient_cases` "
                        "— either the run pre-dates Tier-4, or memory was off."
                    )
    except Exception as e:  # noqa: BLE001
        st.error(f"Qdrant query failed: {e}")
else:
    st.info(
        "Click the checkbox above to query Qdrant. (Loading the BioLORD "
        "embedding model takes a few seconds on the first call.)"
    )

st.divider()
st.caption(
    f"Source · `{patient_dir.relative_to(ROOT)}`  ·  "
    f"events: {len(events)}  ·  "
    f"semantic store: {semantic_path.relative_to(ROOT) if semantic_path else 'none'}"
)

# Multi-Level Memory Extension for CMADS — Implementation Plan

**Target system:** Clinical Multi-Agent Decisioning System (CMADS), Chapter 3 methodology
**Extension:** Three-tier memory architecture (Working → Episodic → Semantic)
**Primary motivation:** Address the cross-patient learning gap identified in RareAgents [13] and mitigate the single-patient scope of the current `PipelineState`
**Estimated effort:** ~2–3 weeks of focused implementation, plus ~1 week for ablation experiments

---

## 1. Design Principles

Four principles constrain every decision in this plan. They exist to keep the extension publishable and to prevent the accuracy gain from becoming an artefact of the synthetic dataset.

1. **No ground-truth leakage into reasoning.** The Diagnostic Reasoning agent must never retrieve memory entries that contain information derived from Stage 5 ground-truth validation. Stored abstracts are always the *predicted* reasoning, never the evaluator-corrected version.
2. **Memory is additive, not replacement.** The current `PipelineState` and agent blueprint remain unchanged. Memory tiers are wired in through new namespaces and new orchestrator hooks, not by modifying existing agents.
3. **Retrieval leakage control.** Test-set patients must be excluded from the semantic store during evaluation. A disjoint train/memory/test split is a hard requirement.
4. **Opt-in via configuration.** Every memory tier must be toggleable through the existing `.env`/`Config` class, so ablation runs (MAS-only, MAS+episodic, MAS+episodic+semantic) are configuration changes rather than code changes — consistent with Section 3.10.

---

## 2. Architecture Overview

### 2.1 The Three Tiers

| Tier | Name | Scope | Lifetime | Store | Populated by | Consumed by |
|------|------|-------|----------|-------|--------------|-------------|
| 1 | Working memory | Current run | One patient | `PipelineState` (in-memory) | All agents | All agents |
| 2 | Episodic memory | Per-patient | Permanent | DuckDB table | Orchestrator post-run | Orchestrator pre-run → Stage 1 agents |
| 3 | Semantic memory | Cross-patient | Permanent | Qdrant collection `case_memory` | Orchestrator post-run (only if match ∈ {DIRECT, INDIRECT}) | Diagnostic Reasoning (Stage 2) |

### 2.2 Data Flow Diagram (Extension)

```
                    ┌──────────────────────────────────────────────┐
                    │              PRE-STAGE 1 HOOK                │
                    │  • Query episodic store by patient_uuid      │
                    │  • Query semantic store by case similarity   │
                    │  • Write episodic_context, semantic_context  │
                    │    into PipelineState                        │
                    └────────────────┬─────────────────────────────┘
                                     ▼
           Stage 1 agents (reads episodic_context if present)
                                     ▼
           Stage 2 Diagnostic Reasoning (reads semantic_context)
                                     ▼
                       Stages 3 / 4 / 5 / 6 (unchanged)
                                     ▼
                    ┌──────────────────────────────────────────────┐
                    │              POST-STAGE 5 HOOK               │
                    │  • Always write to episodic store            │
                    │  • Write to semantic store ONLY IF match     │
                    │    type ∈ {DIRECT, INDIRECT}                 │
                    │  • Abstract contains predicted reasoning     │
                    │    only — no ground-truth-derived fields     │
                    └──────────────────────────────────────────────┘
```

---

## 3. Schema Design

### 3.1 New `PipelineState` Namespaces

Two new read-only namespaces are added. They follow the same Pydantic-validated, reducer-based pattern as the existing five namespaces in Section 3.4.

```python
class EpisodicContext(BaseModel):
    patient_uuid: str
    prior_runs: list[PriorRunSummary]   # may be empty on first encounter
    n_prior_runs: int

class SemanticContext(BaseModel):
    neighbours: list[CaseNeighbour]     # top-k retrieved prior cases
    k: int
    embedding_model: str                # for provenance/reproducibility
```

The reducer for both namespaces is `replace` (not `append`) — they are populated once per run, before Stage 1, and never modified thereafter.

### 3.2 Episodic Store — DuckDB Table

Sits in the same DuckDB warehouse as the OMOP tables to avoid a second storage system.

```sql
CREATE TABLE episodic_memory (
    run_id              UUID PRIMARY KEY,
    patient_uuid        UUID NOT NULL,
    run_timestamp       TIMESTAMP NOT NULL,
    pipeline_version    VARCHAR NOT NULL,
    llm_model           VARCHAR NOT NULL,
    final_differential  JSON NOT NULL,    -- full top-5 ranked
    reviewer_flags      JSON,             -- per-diagnosis verified/refuted/uncertain
    critique_rounds     INT NOT NULL,
    confidence          FLOAT,
    conflicts_detected  JSON,             -- copy of PipelineState.conflicts
    match_type          VARCHAR,          -- DIRECT / INDIRECT / MISS / NULL if eval skipped
    INDEX idx_patient   ON (patient_uuid)
);
```

Retrieval is a bounded query: `SELECT * FROM episodic_memory WHERE patient_uuid = ? ORDER BY run_timestamp DESC LIMIT 5`. The 5-run cap prevents prompt blow-up on patients with many re-runs.

### 3.3 Semantic Store — Qdrant Collection

A second Qdrant collection alongside the existing NICE guidelines collection.

**Collection name:** `case_memory`
**Vector:** 768-dim BioLORD-2023 embedding of the case abstract text
**Distance:** Cosine
**Payload fields:**

| Field | Type | Purpose |
|-------|------|---------|
| `patient_uuid` | string | Leakage control — exclude test patients at query time |
| `run_id` | string | Join back to episodic store |
| `predicted_diagnosis` | string | The Stage 4 rank-1 diagnosis |
| `predicted_top5` | list[string] | Full differential for richer exemplars |
| `reasoning_summary` | string | Single paragraph, generated by abstract agent |
| `presenting_features` | list[string] | Extracted from Stage 1 outputs |
| `match_type` | enum | DIRECT / INDIRECT only — misses are excluded |
| `icd10_codes` | list[string] | For filtered retrieval |
| `dataset_split` | enum | train / memory / test — used as Qdrant filter |
| `created_at` | timestamp | |

**Filtered retrieval:** every query from Stage 2 includes `must_not: [{patient_uuid: current_patient}, {dataset_split: "test"}]`. This is the single most important piece of code in the whole extension — it is what prevents the evaluation from being trivially inflated.

### 3.4 The Case Abstract Schema

The Pydantic object written to both stores after every run.

```python
class CaseAbstract(BaseModel):
    # Provenance
    run_id: UUID
    patient_uuid: UUID
    created_at: datetime

    # Predicted content (NEVER ground-truth corrected)
    predicted_diagnosis: str
    predicted_top5: list[DiagnosisEntry]
    reasoning_summary: str              # ≤150 words, generated by abstract agent
    presenting_features: list[str]      # 5–10 bullet-form features from Stage 1

    # Metadata (allowed — does not leak reasoning signal)
    match_type: Literal["DIRECT", "INDIRECT", "MISS"]
    confidence: float
    icd10_codes: list[str]

    # Explicitly forbidden fields (documented to prevent future mistakes)
    # - ground_truth_diagnosis: NEVER STORED
    # - evaluator_rationale:    NEVER STORED
    # - corrected_reasoning:    DOES NOT EXIST
```

---

## 4. Component-Level Changes

### 4.1 New Components

Four new components must be built. Each is a single-responsibility module.

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `MemoryOrchestrator` | `cmads/memory/orchestrator.py` | Pre/post-run hooks; coordinates episodic and semantic stores |
| `EpisodicStore` | `cmads/memory/episodic.py` | DuckDB read/write wrapper |
| `SemanticStore` | `cmads/memory/semantic.py` | Qdrant read/write wrapper; handles embedding |
| `CaseAbstractAgent` | `cmads/agents/case_abstract.py` | LLM-powered agent that generates the reasoning summary after Stage 5 |

### 4.2 Modified Components

Three existing components need minimal modification. All changes are additive.

| Component | Change |
|-----------|--------|
| `PipelineState` TypedDict | Add `episodic_context` and `semantic_context` namespaces with `replace` reducer |
| LangGraph `StateGraph` | Add `memory_prefetch` node before Stage 1 and `memory_writeback` node after Stage 5 |
| `Config` class | Add `MEMORY_ENABLE_EPISODIC`, `MEMORY_ENABLE_SEMANTIC`, `MEMORY_K`, `MEMORY_SIMILARITY_THRESHOLD` |

### 4.3 CaseAbstractAgent Details

This is a new agent and deserves specification because it's the only new piece of LLM reasoning in the extension. It follows the standard blueprint from Section 3.5.

- **Input:** final differential (Stage 4), Stage 1 summaries, conflict log
- **Forbidden input:** ground truth file, evaluator rationale
- **Output:** `CaseAbstract` Pydantic object
- **LLM:** same as reasoning agents (`LLM_REASONING_MODEL`) — deliberately NOT the evaluator model, because using the evaluator would let ground-truth-exposed context leak in
- **Prompt template:** `prompts/case_abstract.yaml`
- **Output Gate checks:** `reasoning_summary` length ≤ 150 words; no mention of the string "ground truth"; ICD-10 codes validated against a known list

---

## 5. Prompt Design

Two new prompt templates are needed.

### 5.1 `prompts/case_abstract.yaml`

Generates the one-paragraph reasoning summary after every run. Must be prompted to describe *how the pipeline arrived at its prediction* — not whether the prediction was correct.

### 5.2 Modifications to `prompts/diagnostic_reasoning.yaml`

Stage 2 prompt gains a new conditional section:

```
{% if semantic_context.neighbours %}
# Similar prior cases (for reference only — not ground truth)
The following {{ semantic_context.k }} cases from past runs presented similarly.
These are shown to help recognise patterns, NOT as answers to copy.
{% for n in semantic_context.neighbours %}
- Case {{ n.run_id }}: features {{ n.presenting_features }};
  pipeline's prior prediction was {{ n.predicted_diagnosis }}.
{% endfor %}
{% endif %}
```

Critical wording: "pipeline's prior prediction" — not "correct diagnosis." This phrasing is the prompt-level counterpart of the schema-level leakage prevention.

Stage 1 prompts gain an analogous but smaller section referencing `episodic_context.prior_runs`.

---

## 6. The Leakage Control Protocol

This section is the single most important methodological contribution of the extension and deserves its own chapter subsection in the thesis. Five rules, enforced at different layers:

1. **Schema-level:** `CaseAbstract` has no ground-truth field. The Pydantic model physically cannot carry the target condition.
2. **Write-path-level:** `SemanticStore.write()` asserts `match_type in {"DIRECT", "INDIRECT"}` but never stores the Synthea target string itself — only the *predicted* diagnosis, which for a DIRECT match happens to be equivalent.
3. **Agent-level:** The `CaseAbstractAgent` is not given access to `ground_truth.json`. Its Input Gate explicitly rejects calls that include the ground-truth namespace.
4. **Retrieval-level:** All Stage 2 queries include `must_not` filters for the current `patient_uuid` and for `dataset_split == "test"`.
5. **Dataset-level:** The 270 cases are partitioned into three disjoint sets before any memory-enabled run:
   - **Memory seed set (~170):** used to populate the semantic store
   - **Validation set (~50):** used to tune `MEMORY_K` and `MEMORY_SIMILARITY_THRESHOLD`
   - **Test set (~50):** held out; never written to any memory store; used only for final reported metrics

This protocol is what makes the result defensible. Without it, a reviewer would reasonably ask whether the accuracy gain is real or whether the system is just retrieving near-duplicates.

---

## 7. Evaluation Plan

### 7.1 Ablation Matrix

Four configurations, each run on the 50-patient test set:

| Config | Episodic | Semantic | Expected role |
|--------|----------|----------|---------------|
| A — Baseline | off | off | Reproduces current Chapter 3 pipeline |
| B — Episodic only | on | off | Isolates benefit of per-patient re-run context (low on Synthea — most patients are single-run) |
| C — Semantic only | off | on | The main experimental condition; replicates RareAgents pattern |
| D — Full | on | on | Upper bound |

Each configuration is run 3 times for inter-run consistency (consistent with the "Inter-run consistency" metric already planned in Section 3.9.3).

### 7.2 Metrics

All five existing metrics from Section 3.9.3 are reported per configuration: direct rate, found rate, miss rate, top-1 direct rate, per-patient latency.

Three additional memory-specific metrics:

- **Retrieval precision@k:** of the k retrieved neighbours, what fraction share an ICD-10 code with the current patient's final diagnosis? Measures whether semantic retrieval is surfacing genuinely similar cases.
- **Memory-attributable lift:** top-1 direct rate of Config C minus top-1 direct rate of Config A, with bootstrapped 95% confidence interval.
- **Latency overhead:** added wall-clock time per patient from memory hooks.

### 7.3 Two Additional Checks (Recommended)

- **Shuffled-retrieval control:** Config C' where semantic retrieval is replaced with *random* prior cases. If Config C beats Config C' significantly, the gain is genuinely from similarity rather than from generic in-context learning.
- **Leakage audit:** for every Stage 2 invocation in test runs, log the retrieved `patient_uuid` values and assert none match the current patient or belong to the test split. Published as a single sentence in the results chapter: "Across N Stage 2 invocations, zero leakage events were detected."

---

## 8. Implementation Phases

A sequenced plan that produces a working system at every intermediate checkpoint.

### Phase 1 — Foundations (Days 1–3)

- Create `cmads/memory/` module skeleton
- Implement `EpisodicStore` with full CRUD + unit tests against a throwaway DuckDB file
- Add `MEMORY_*` config variables
- Extend `PipelineState` with the two new namespaces; verify existing tests still pass

**Exit criterion:** existing pipeline runs unchanged with memory flags set to off.

### Phase 2 — Episodic tier (Days 4–6)

- Implement `memory_prefetch` and `memory_writeback` orchestrator hooks for episodic only
- Modify Stage 1 agent prompts to optionally consume `episodic_context`
- Re-run a handful of patients twice and confirm second run sees the first run's context
- Run Config B on the 50-patient validation set

**Exit criterion:** episodic memory observably influences Stage 1 outputs on re-runs; no regression on first-run metrics.

### Phase 3 — Semantic tier, read-only (Days 7–10)

- Implement `SemanticStore` with BioLORD-2023 embedding wrapper
- Write a one-off backfill script to populate the semantic store from the memory seed set by running the pipeline on those 170 patients with Config A
- Implement Stage 2 prompt extension for `semantic_context`
- Run Config C on the validation set; tune `MEMORY_K` (try 3, 5, 10) and `MEMORY_SIMILARITY_THRESHOLD`

**Exit criterion:** Config C on the validation set shows a positive top-1 direct rate delta with visible changes in Stage 2 reasoning traces.

### Phase 4 — Semantic tier, write-back (Days 11–12)

- Implement `CaseAbstractAgent` with its blueprint-compliant input/output gates
- Wire it into `memory_writeback`
- Verify schema-level and agent-level leakage controls with three failing-negative tests (tests that *must* fail if ground truth leaks)

**Exit criterion:** pipeline writes to semantic store correctly; leakage audit tests pass.

### Phase 5 — Full ablation (Days 13–17)

- Run all four configurations × 3 seeds on the 50-patient test set
- Run the shuffled-retrieval control (Config C')
- Collect retrieval precision@k and leakage audit data
- Bootstrap confidence intervals for memory-attributable lift

**Exit criterion:** results table for Chapter 4 is complete with statistical tests.

### Phase 6 — Writing (Days 18–21)

- Draft new Section 3.X "Multi-Level Memory" for Chapter 3 (placed after Section 3.7 RAG Layer, since it is conceptually the second retrieval mechanism)
- Draft new Section 4.Y "Ablation: Effect of Multi-Level Memory" for Chapter 4
- Update Section 3.9.3 to reference the three new memory-specific metrics
- Add one sentence each to objectives list (Section 1.3) and research gap 1 (Section 2.4.2)

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Synthea homogeneity inflates Config C gain | High | High (external validity) | Shuffled-retrieval control (Config C'); explicit disclosure in Chapter 4 discussion; frame contribution as methodological, not purely empirical |
| Ground-truth leakage through an overlooked path | Medium | Critical (invalidates results) | Five-rule leakage protocol in §6; three failing-negative tests; leakage audit reported in results |
| Qdrant second collection conflicts with existing NICE collection | Low | Medium | Separate collection names; separate client instances; verified in Phase 3 |
| Embedding model drift if BioLORD-2023 is updated mid-study | Low | Medium | Pin model version in `Config`; record `embedding_model` in every semantic store payload |
| Episodic memory shows no effect on Synthea (most patients are single-run) | High | Low (expected) | Frame episodic tier as future-work-ready infrastructure; report its neutral result honestly |
| Latency overhead exceeds acceptable per-patient time | Medium | Low | Cache embeddings; async retrieval in `memory_prefetch`; report overhead explicitly |
| Scope creep into working-memory redesign | Medium | Medium | Keep `PipelineState` additive-only; any structural change to working memory is out of scope for this extension |

---

## 10. Thesis Integration

### 10.1 Chapters Affected

- **Section 1.3 Objectives:** add one bullet point for multi-level memory
- **Section 2.4.2 Research Gaps:** extend the RareAgents reference in gap 1 to explicitly note that cross-patient memory remains an open architectural dimension
- **Chapter 3:** insert new **Section 3.8 Multi-Level Memory Architecture** (renumber subsequent sections); extend **Section 3.9.3** with three new metrics
- **Chapter 4:** new section presenting ablation results
- **Chapter 5:** add memory tier extensions (e.g., hierarchical memory over patient cohorts, long-horizon episodic reasoning across hospital admissions) to Future Work

### 10.2 New References to Cite

- Chen et al. (2024) [13] RareAgents — already cited; strengthen the citation in the new section as the primary precedent for persistent memory
- Park et al. (2023) "Generative Agents" (Stanford/Google) — methodological precedent for the three-tier working/episodic/semantic split; add to bibliography
- Optionally: any recent survey on LLM agent memory architectures published in 2025

---

## 11. Acceptance Criteria for Completion

The extension is considered complete when **all** of the following hold:

1. All four ablation configurations run end-to-end on the 50-patient test set without errors
2. Config C shows a positive, statistically significant top-1 direct rate delta over Config A (or a clear null result is reported — either is a valid thesis outcome)
3. Shuffled-retrieval control (Config C') shows that the gain is attributable to similarity, not to in-context learning in general
4. Leakage audit reports zero leakage events across all test runs
5. Retrieval precision@k is reported and discussed
6. New Section 3.8 is drafted, integrated with surrounding sections, and follows the existing chapter's writing style
7. Chapter 4 ablation section is drafted with the full metrics table
8. All new code has unit tests including the three failing-negative leakage tests
9. Configuration flags allow any of the four configurations to be selected without code changes
10. The `CaseAbstract` schema has no field capable of carrying ground-truth information — verified by code review

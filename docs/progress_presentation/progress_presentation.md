# CMADS — Supervisor Progress Meeting
**3-minute presentation · April 2026 · Abdelrahman**

> Target runtime: **~3 minutes (≈ 420 spoken words)** · 5 slides · pacing noted on each.
> Block diagram: `methodology_block_diagram.svg` in this folder.

---

## Slide 1 — Title & Problem  *(≈ 25 s)*

### CMADS — Clinical Multi-Agent Decisioning System
*A LangGraph pipeline for differential diagnosis and NICE-guideline treatment planning on synthetic patients.*

**Speaker notes:**
> Good afternoon. Today I'll briefly cover three things: (1) the methodology I settled on, (2) where the results stand on 270 verified patients, and (3) a head-to-head comparison between a large general model and a medical-fine-tuned model that I just completed.
> The research question is: can a coordinated group of small, specialised LLM agents replicate clinical reasoning when given only structured EHR and lab data?

---

## Slide 2 — Methodology  *(≈ 55 s)*

> **Show the block diagram** (`methodology_block_diagram.svg`) — four zones top to bottom: Data Generation → Data Pipeline → Multi-Agent Pipeline → Evaluation.

**Key design choices:**
- **Synthea is the single source of truth** for every patient. No LLM-generated cases, so ground truth is rule-based and auditable.
- **Medallion data pipeline**: Bronze (Parquet) → Silver (OMOP CDM v5.4 via dbt + DuckDB) → Silver+ (derived features) → Gold (point-in-time case JSON).
- **7 agents / 6 stages orchestrated in LangGraph**. Stage 1 (EHR + Lab) runs in parallel; Stages 2–4 are the reasoning core (Diagnostic → Reviewer → Refiner); Stages 5–6 are evaluation and treatment.
- **Shared memory = LangGraph State** — no custom store, just a TypedDict with merge reducers so parallel agents never overwrite each other.
- **Provider-agnostic LLM layer** — single `.env` switches between Groq, OpenAI, Anthropic, Gemini, Ollama. This is what made the model comparison in slide 4 possible without code changes.

**Speaker notes:**
> The top half of the diagram is classical data engineering; the bottom half is where my thesis contribution sits. The critical design decision was making the shared memory *identical* to the LangGraph state, so every agent's output becomes a typed channel that downstream agents read. The Diagnostic Reasoning agent has an adaptive self-critique loop — it stops early when confidence crosses 75, otherwise it refines up to three rounds. Stage 3, the Clinical Reviewer, provides adversarial verification before the Refiner produces the final differential.

---

## Slide 3 — Results on the 270-patient cohort  *(≈ 50 s)*

**Cohort:** 270 Synthea patients, LLM-verified (Qwen3 32B, confidence ≥ 80) across 6 diseases. Evaluated: **50 patients** with the GPT-OSS 120B configuration.

| Metric | Value |
|---|---:|
| **DIRECT** match rate (strict) | **18 %** (9/50) |
| **When found, rank-1 placement** | **67 %** |
| Avg pipeline time / patient | **~100 s** |
| Cost / patient (Groq) | **≈ $0.06** |

**Per-disease (found rate):**
- Essential hypertension — **55 %** (best)
- Diabetes type 2 — 33 %
- CKD-3 — 20 %
- ESRD — 11 %
- Ischemic heart disease — **0 %**
- Metabolic syndrome — **0 %**

**Speaker notes:**
> On strict DIRECT matching the overall rate is 18 %, which on the surface looks modest. But two things matter. First: **when the system finds the right disease, it ranks it first in two-thirds of cases** — so the ranking mechanism works; the gap is in detection. Second: the failures are *clinically meaningful* rather than random. ESRD is usually scored as "CKD stage 4" — off by one stage. Ischemic heart disease is usually scored as "atherosclerotic CAD" — same pathology, different terminology. Both would score as INDIRECT under a more lenient judge. The two genuinely hard cases are metabolic syndrome (composite diagnosis the LLM doesn't unify) and IHD when renal labs dominate the record.

---

## Slide 4 — Model comparison: GPT-OSS 120B vs Med42 70B  *(≈ 50 s)*

**Setup:** 20 patients (Batch 4, seed 42) · same Qwen3 32B judge for both · same pipeline.

| Metric | **GPT-OSS 120B** (Groq) | **Med42 70B** (Ollama, local) |
|---|:---:|:---:|
| DIRECT | **50 %** | 25 % |
| Found (DIRECT+INDIRECT) | **80 %** | 75 % |
| Head-to-head wins | **8** | 2 (10 ties) |
| Avg time / patient | **2 min** | 27 min (13× slower) |
| Cost / patient | $0.06 | $0.00 |
| Agent-level reliability | 100 % | 40–85 % (JSON / timeout errors) |

**Four findings:**
1. **General > medical fine-tune at this size.** GPT-OSS wins composite diagnoses decisively (Metabolic Syndrome 5/6 vs 1/6).
2. **Med42 edges out on plain hypertension** — medical pre-training helps with vitals-based diagnoses (2/4 vs 1/4).
3. **Self-evaluation is inflated**: Med42 scored itself 45 % DIRECT; under the independent Qwen3 judge it dropped to 25 %. *Confirms the value of a fixed third-party evaluator.*
4. **Neither model resolves CKD staging** — 0 % DIRECT on stage 2/3 for both.

**Speaker notes:**
> This was the experiment I finished most recently. I ran the same 20 patients through the exact same pipeline twice, changing only the LLM, and evaluated both with a third model as judge. GPT-OSS wins 50 % to 25 % on DIRECT matches. The most interesting finding is point 3 — when Med42 evaluated its own output it scored itself at 45 %, but a neutral judge cut that almost in half. That's a methodological result worth keeping: any self-evaluation number in this domain is untrustworthy. Med42's fine-tuning does help on simple vitals-based conditions, but it costs nothing in dollars and thirteen times the wall-clock time.

---

## Slide 5 — NEW · Multi-Level Memory  *(≈ 45 s)*

**Supervisor request:** add a multi-level memory subsystem so agents share *session context*, not only the final structured outputs. Implemented as a 4-tier store layered on the existing LangGraph state.

| Tier | Scope | Where it lives | Purpose |
|---|---|---|---|
| **1. Working** | per-agent invocation | `state.scratchpad[agent_id]` (in-memory) | Tracks confidence trajectory + critique trail across the Diagnostic agent's adaptive loop |
| **2. Episodic** | current pipeline run | `state.session_memory` (append-reducer) → `session_memory.json` on disk | Typed timeline of events (`critique`, `confidence_check`, `decision`, `agent_complete`); downstream agents read the *reasoning chain*, not just the JSON |
| **3. Semantic** | cross-session, persistent | `data/gold/memory/semantic_memory.json` | Aggregate stats per disease — DIRECT/INDIRECT/MISS counts, rank-1 frequency, observed evidence patterns. Updated by a new Stage 7 *Memory Consolidation* node |
| **4. Procedural** | long-term / static | NICE guidelines via Qdrant *(existing)* | Wrapped in a uniform `recall(query)` API so all four tiers are accessed the same way |

**Architecture, in one line:** *agents read the four tiers via a single `MemoryManager` facade; writes flow through the LangGraph reducers so parallel agents never overwrite each other.*

**Why it matters (concretely):**
- The Reviewer can now cite **specific critique rounds** from the Diagnostic agent ("round 2 confidence 60 → round 3 confidence 78") instead of seeing only the final differential.
- The Refiner sees the **session timeline + cross-session priors** for the candidate diseases when producing the final dx.
- Each run **consolidates its outcome into Tier-3 semantic memory**, so the *next* run inherits aggregate observations without any model fine-tuning.
- A `MEMORY_ENABLED` flag toggles the whole subsystem off, so the before/after experiment is a clean A/B.

**Before / after on Batch 4 (20 patients · GPT-OSS 120B · same Qwen3 judge):**

| Metric | Before (memory OFF) | After (memory ON) |
|---|:---:|:---:|
| DIRECT match | _baseline pending_ | _experiment pending_ |
| Found rate | _baseline pending_ | _experiment pending_ |
| Avg time / patient | _baseline pending_ | _experiment pending_ |

> Numbers will be filled in once the two 20-patient runs complete (running tonight). Code, tests, and design are landed — the slide carries even if the experiment slips.

**Speaker notes:**
> Last week you asked for a multi-level memory system so agents could share session context, not only their final JSON outputs. This is the implementation. There are four tiers, inspired by the CoALA cognitive-architecture paper but specialised to a clinical workflow. Tier 1 is working memory — per-agent scratch space, used heavily inside the Diagnostic agent's adaptive critique loop to track its own confidence trajectory across rounds. Tier 2 is episodic — a typed timeline of events that the Reviewer and Refiner read so they can reason about the *path* to the diagnosis, not only the diagnosis itself. Tier 3 is semantic — a small JSON file on disk that accumulates per-disease statistics across runs; a new Stage 7 *Memory Consolidation* node writes into it after every patient. Tier 4 is procedural — the existing NICE-guidelines vector store, now exposed through the same uniform recall API as the other tiers, so an agent fetches priors and guidelines the same way. The whole thing is gated by a single config flag, MEMORY_ENABLED, which is what makes the before/after experiment fair. The implementation lands as a new `src/memory/` package and a `memory_consolidation_node` plugged in after Treatment; twenty-four unit tests cover all four tiers. Numbers from the 20-patient A/B run will go in the empty cells before the meeting.

---

## Slide 6 — Next steps  *(≈ 20 s)*

- **Relax DIRECT criterion** with semantic equivalence (CKD-5 ↔ ESRD, CAD ↔ IHD) — expect the found-rate to roughly double.
- **Composite-diagnosis recognition** for Metabolic Syndrome (criteria-based detector before the LLM call).
- **Rebalance lab-vs-EHR weighting** so documented MI history is not drowned by renal labs → target the 0 % IHD failure.
- **Expand the model-comparison matrix** — run the current 20-patient protocol on GPT-4o and Claude Sonnet as external baselines.
- **Validate multi-level memory at scale** — re-run the full 270-patient cohort with memory ON and quantify per-disease deltas; check whether semantic-memory priors help the weakest categories (CKD staging, plain hypertension).

**Speaker notes:**
> To close: the pipeline is stable, the evaluation loop is reproducible, the model-comparison protocol is now a one-flag change, and the multi-level memory feature you asked for is wired in and tested. The next quarter is about closing the three named gaps — lenient matching, composite diagnoses, and lab-vs-EHR balance — and quantifying the memory feature's impact at full cohort scale. Happy to take questions.

---

### Presenter crib sheet (numbers to have at fingertips)
- Pipeline: **7 agents, 6 stages, LangGraph StateGraph.**
- Cohort: **270 verified patients, 8 diseases, 6 batches of ~50.**
- Headline: **18 % DIRECT overall · 55 % on hypertension · 67 % rank-1 when found.**
- Model fight: **GPT-OSS 50 % vs Med42 25 % · 8-2 head-to-head · 13× speed gap.**
- Methodology: **Synthea → Bronze → Silver (OMOP) → Silver+ → Gold → LangGraph pipeline → Qwen3 judge.**

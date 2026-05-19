# CMADS — Clinical Multi-Agent Decisioning System

A seven-agent LangGraph system that turns synthetic patient records into a ranked differential diagnosis, a NICE-guideline-grounded treatment plan, and a doctor-facing review dashboard. Built as a Bachelor thesis at the German University in Cairo (Faculty of Media Engineering and Technology).

The system is designed to be **inspected**, not trusted blindly: every agent's output, every memory operation, and every retrieved guideline passage is exposed to a reviewing clinician through one of the two dashboards.

---

## Try it in five commands

```bash
# 1 — clone and install
git clone https://github.com/abdamin004/CMADS.git
cd CMADS && make install

# 2 — set your LLM key (defaults to Groq + GPT-OSS-120B)
cp .env.example .env        # edit and set GROQ_API_KEY=...

# 3 — run the pipeline on one patient (a pre-shipped Gold UUID)
make run-patient UUID=4b265e38-b837-001f-9059-5020ec1e3e26

# 4 — open the research evaluator dashboard (port 8503)
make dashboard

# 5 — open the doctor console (FastAPI on :8010, React on :5173)
make doctor-console-api      # in one terminal
make doctor-console-web      # in another, then open http://127.0.0.1:5173
```

Pre-shipped Gold patient cases live in `data/gold/patient_cases/` and pre-computed run artefacts live in `data/gold/mas_results*/`, so both dashboards display real outputs immediately — no fresh pipeline run required. Qdrant credentials are only needed if you want guideline retrieval and case-based memory at run time; the dashboards work read-only without them.

---

## Two dashboards, two purposes

| Dashboard | Port | Audience | What you see |
|---|---|---|---|
| **Streamlit evaluator** (`make dashboard`) | `:8503` | Researcher | Cohort-level metrics, per-result-set comparison, per-patient agent JSON, ground-truth match labels |
| **React doctor console** (`make doctor-console-api` + `make doctor-console-web`) | `:8010` + `:5173` | Clinician | Per-patient assessment, differential, NICE-grounded treatment plan, similar past cases (vector search), agent flow graph — ground truth is **not** displayed |

---

## Architecture

```
Synthea (synthetic patients)
    → Bronze (Parquet) → Silver (OMOP CDM v5.4) → Silver+ (derived features) → Gold (case JSON)
    → LLM Detectability Verifier (data-quality gate)
    → Multi-Agent Pipeline (7 agents, 6 LangGraph stages, 4-tier shared memory)
    → Ranked Differential + NICE-Guideline Treatment Plan
    → Streamlit evaluator   ─OR─   React doctor console
```

### Agent pipeline (six stages, seven agents)

| Stage | Agent | Role |
|---|---|---|
| 1 (parallel) | **EHR Analyst** | Extract structured clinical summary from patient EHR |
| 1 (parallel) | **Lab Interpreter** | Classify labs, interpret trends, rank by severity |
| 2 | **Diagnostic Reasoning** | Ranked differential with three-phase protocol (adaptive loop, max 3 rounds) |
| 3 | **Clinical Reviewer** | Adversarial verification — independent second opinion |
| 4 | **Diagnostic Refiner** | Merge diagnostic + reviewer into final differential (non-destructive) |
| 5 | **LLM Evaluator** | Compare against hidden Synthea ground truth (DIRECT / INDIRECT / MISS) |
| 6 | **Treatment Planning** | NICE guideline retrieval via Qdrant, DIRECT-gated |
| 6 (consolidate) | **Memory Consolidator** | Deterministic write-back to Tier 2–3 and conditionally Tier 4 |

Pipeline diagram: [`docs/mas_pipeline.html`](docs/mas_pipeline.html).

### Four-tier shared memory (CoALA-inspired)

| Tier | Type | Storage |
|---|---|---|
| **T1 — Working** | Per-run scratchpad and loop state | In-process |
| **T2 — Episodic** | Append-only event timeline (`session_memory.json`) | In-process + disk |
| **T3 — Semantic** | Cross-session disease-level aggregates | JSON file |
| **T4 — Case-Based** | Past patients as searchable vectors | Qdrant (`patient_cases` collection) |

---

## Tech stack

| Layer | Component | Role |
|---|---|---|
| Orchestration | **LangGraph** (`StateGraph`) | Typed graph with reducers, parallel fan-out, adaptive loop |
| Schemas | **Pydantic v2** | Agent output validation |
| LLM (primary) | **GPT-OSS-120B via Groq** | All agent reasoning by default |
| LLM (judge) | **Qwen3-32B via Groq** | LLM-as-Judge evaluator |
| LLM adapter | Provider-agnostic | Groq / OpenAI / Anthropic / Gemini / Ollama by env var |
| Memory | **Qdrant** + `sentence-transformers` + **BioLORD-2023** | Tier-4 case store, NICE guideline retrieval |
| Data lake | **dbt-core** + **DuckDB** + **PyArrow** | Bronze → Silver (OMOP CDM v5.4) → Silver⁺ → Gold |
| Data source | **Synthea** (Java) | Synthetic FHIR-R4 patient generator |
| Frontend (research) | **Streamlit** | Evaluator dashboard at `:8503` |
| Frontend (clinician) | **React + Vite + FastAPI** | Doctor console at `:5173` / `:8010` |
| Logging | **structlog** | JSON-lines structured logs |
| Tests | **pytest** + **ruff** | 37 unit tests + lint/format |

---

## Project structure

```
CMADS/
├── src/                        # Agent pipeline (core)
│   ├── orchestrator/           #   LangGraph graph + state
│   ├── agents/                 #   7 agent implementations
│   ├── memory/                 #   4-tier shared memory (working/episodic/semantic/case-based)
│   ├── schemas/                #   Pydantic output schemas
│   ├── llm/                    #   Provider-agnostic LLM adapter
│   ├── evaluation/             #   LLM-as-judge evaluation
│   └── vectordb/               #   Qdrant setup + guideline retrieval
├── prompts/                    # YAML prompt templates (one per agent)
├── pipeline/                   # Data pipeline (Bronze → Silver → Silver+ → Gold + verifier)
├── portal/                     # Streamlit evaluator dashboard
├── doctor_console/             # React + FastAPI clinician console
│   ├── backend/                #   FastAPI app
│   └── frontend/               #   Vite + TypeScript React app
├── config/                     # Pipeline configs + NICE guideline JSON
├── tests/                      # pytest test suites
├── thesis/                     # LaTeX thesis source (run `make thesis`)
├── docs/                       # System docs, evaluation methodology, decisions
├── notes/                      # Obsidian-style research vault
├── synthea/                    # Synthea generator (external, optional)
└── data/
    └── gold/
        ├── patient_cases/      # Per-patient Gold JSON (input to agents)
        ├── mas_results*/       # Saved run artefacts (multiple cohorts)
        ├── memory*/            # Persisted memory stores
        └── batches/            # Cohort batch definitions
```

---

## Configuration

All LLM settings live in `.env` — no code changes are needed to switch provider or model.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq`, `openai`, `anthropic`, `gemini`, or `ollama` |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Model name for the chosen provider |
| `LLM_EVALUATOR_MODEL` | `qwen/qwen3-32b` | Separate model for the LLM-as-Judge evaluator |
| `LLM_EVALUATOR_PROVIDER` | *(falls back to `LLM_PROVIDER`)* | Use a different provider for the judge |
| `QDRANT_URL` / `QDRANT_API_KEY` | — | Required for NICE retrieval and Tier-4 memory |
| `AGENT_TIMEOUT` | `300` | Per-agent wall-clock timeout (seconds) |
| `DIAGNOSTIC_MAX_ROUNDS` | `3` | Cap on the adaptive diagnostic loop |
| `DIAGNOSTIC_CONFIDENCE_THRESHOLD` | `75` | Early-exit threshold for the diagnostic loop |

| Provider | API key variable | Install |
|---|---|---|
| Groq (default) | `GROQ_API_KEY` | `pip install langchain-groq` |
| OpenAI | `OPENAI_API_KEY` | `pip install langchain-openai` |
| Anthropic | `ANTHROPIC_API_KEY` | `pip install langchain-anthropic` |
| Gemini | `GOOGLE_API_KEY` | `pip install langchain-google-genai` |
| Ollama (local) | *(none — runs locally)* | `pip install langchain-ollama` |

Example: switch to OpenAI for everything

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_EVALUATOR_PROVIDER=openai
LLM_EVALUATOR_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

---

## Make commands

| Command | What it does |
|---|---|
| `make install` | Install Python dependencies |
| `make run-patient UUID=…` | Run the 7-agent pipeline on one patient |
| `make run-batch BATCH=… [MAX=n]` | Run the pipeline on a cohort batch |
| `make dashboard` | Streamlit evaluator dashboard at `:8503` |
| `make doctor-console-api` | FastAPI doctor-console backend at `:8010` |
| `make doctor-console-web` | React doctor-console frontend at `:5173` |
| `make evaluate` | Re-run LLM-as-judge on saved results |
| `make setup-qdrant` | Populate Qdrant with NICE guidelines (one-time) |
| `make test` | Run all tests |
| `make test-mas` | MAS pipeline tests only |
| `make test-data` | Data pipeline tests only |
| `make lint` / `make format` | Lint and auto-format with ruff |
| `make thesis` | Build the thesis PDF (`thesis/main.pdf`) |
| `make pipeline-bronze` / `pipeline-silver` / `pipeline-gold` | Re-run data pipeline layers |

---

## Headline results

End-to-end evaluation on the principal cohort (Synthea-derived, eight target disease families) — full details in [`thesis/main.pdf`](thesis/main.pdf) Chapter 4.

| Metric | Value |
|---|---:|
| **DIRECT match** | **74 %** |
| INDIRECT match | 14 % |
| MISS | 12 % |
| **Combined found rate** | **88 %** |
| Rank-1 within found | 61 % |
| Median runtime / patient | ~129 s |

**Multi-level memory finding (aggregate A/B, leakage-controlled).** Single-level memory (disabled) achieves a higher DIRECT rate (69 % vs 49 %); multi-level memory achieves a higher combined found rate (95 % vs 88 %) and a lower miss rate (5 % vs 12 %). Multi-level memory broadens the differential and reduces misses but does not improve primary-diagnosis precision — a nuanced finding reported under a cohort-leakage protocol that holds the memory-population cohort separate from the evaluation cohort.

**Model comparison (controlled subset).** GPT-OSS-120B on Groq doubles the DIRECT rate of Med42-70B on local Ollama (50 % vs 25 %) and runs roughly thirteen times faster, supporting the architecture-over-scale finding extended with an inference-throughput observation.

The Streamlit evaluator dashboard now lets you switch between any saved cohort and see all of the above broken down per disease family and per agent.

---

## Documentation

| Document | Purpose |
|---|---|
| [`thesis/main.pdf`](thesis/main.pdf) | Full thesis (motivation, methodology, results, conclusion) |
| [`docs/SRD.md`](docs/SRD.md) | System Requirements |
| [`docs/SDD.md`](docs/SDD.md) | System Design Document |
| [`docs/TECH_STACK.md`](docs/TECH_STACK.md) | Technology selections |
| [`docs/EVALUATION_METHODOLOGY.md`](docs/EVALUATION_METHODOLOGY.md) | LLM-as-judge methodology |
| [`docs/MAS_ARCHITECTURE_EVOLUTION.md`](docs/MAS_ARCHITECTURE_EVOLUTION.md) | Architecture iterations (v1 → v4) |
| [`docs/DATA_PIPELINE_DECISIONS.md`](docs/DATA_PIPELINE_DECISIONS.md) | Data pipeline design notes |
| [`docs/MODEL_COMPARISON_GPT_OSS_vs_MED42.md`](docs/MODEL_COMPARISON_GPT_OSS_vs_MED42.md) | Head-to-head model results |
| [`notes/experiments.md`](notes/experiments.md) | Append-only experiment log |
| [`doctor_console/README.md`](doctor_console/README.md) | Doctor console build + run notes |

---

## Rebuilding from scratch (optional)

If you want to regenerate the Gold layer from scratch:

```bash
# 1 — generate synthetic patients with Synthea
cd synthea && ./run_synthea -p 1000 && cd ..

# 2 — run the medallion data pipeline
python pipeline/bronze.py batch_1k
python pipeline/silver.py
python pipeline/silver_plus.py
python pipeline/gold.py

# 3 — gate the cohort with the LLM detectability verifier
python pipeline/lab_verifier_llm.py
```

See [`pipeline/`](pipeline/) for details. The repository already ships the resulting Gold-layer artefacts, so this step is **not** required to run or evaluate the agent pipeline.

---

## Auto-review loop

Automates the manual Claude Code <-> Codex CLI back-and-forth that produces a vetted thesis review and verified fix execution. Each run snapshots `thesis/` and writes per-file diffs so you can see exactly what changed.

```bash
# from inside Claude Code
/auto-review

# direct
python scripts/auto_review.py
python scripts/auto_review.py --dry-run               # print planned steps, no LLM calls
python scripts/auto_review.py --max-plan-iters 5      # raise plan-loop cap
python scripts/auto_review.py --list-runs             # past runs + their verdicts
```

Artifacts land in `.review-cycle/<timestamp>/` (gitignored): full `thesis_before/` snapshot, per-iteration `thesis_after/`, per-file `diffs/*.diff`, and a top-level `CHANGES.md` summary.

Exit codes: 0 approve, 1 plan-loop cap, 2 fix-loop cap, 3 sub-CLI failure. Full spec: [`docs/superpowers/specs/2026-05-15-auto-review-loop-design.md`](docs/superpowers/specs/2026-05-15-auto-review-loop-design.md).

## License and credit

This project is part of a Bachelor thesis at the German University in Cairo, supervised by Dr. Shereen Moataz Afifi. NICE clinical guideline content is used under fair-use academic terms. Synthea is open-source under the Apache 2.0 license. All other code in this repository is released under the same license.

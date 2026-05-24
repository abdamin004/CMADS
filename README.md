# CMADS — Clinical Multi-Agent Decisioning System

A seven-agent LangGraph system that turns synthetic patient records into a ranked differential diagnosis, a NICE-guideline-grounded treatment plan, and a doctor-facing review dashboard. Built as a Bachelor thesis at the German University in Cairo (Faculty of Media Engineering and Technology).

The system is designed to be **inspected**, not trusted blindly: every agent's output, every memory operation, and every retrieved guideline passage is exposed to a reviewing clinician through the React doctor console.

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

# 4 — open the doctor console (FastAPI on :8010, React on :5173)
make doctor-console-api      # in one terminal
make doctor-console-web      # in another, then open http://127.0.0.1:5173
                              # Pick Doctor (runtime) or Researcher (statistics)
                              # from the splash. Both live in the same app.
```

Pre-shipped Gold patient cases live in `data/gold/patient_cases/` and pre-computed run artefacts live in `data/gold/mas_results*/`, so both dashboards display real outputs immediately — no fresh pipeline run required. Qdrant credentials are only needed if you want guideline retrieval and case-based memory at run time; the dashboards work read-only without them.

---

## The doctor console

The React app at `:5173` opens on a splash that lets the user pick between
two workspaces. The choice is reflected in the URL (`?mode=`), and a topbar
chip lets you switch back at any time.

### Doctor mode (runtime)

The clinician's surface. One screen, one patient, one run at a time.

- **Hero** — enter a Gold patient UUID, pick a model preset / top-K / accuracy mode.
- **Running view** — live agent flow streams via SSE; the chart the agents are reading is shown alongside, so the clinician sees the evidence at the same time as the conclusion.
- **Result view** — five tabs: Patient data · ranked Differential (with supporting / refuting evidence per dx) · NICE-grounded Treatment plan · Similar past cases · Agent reasoning trace.
- Live runs write to a separate `mas_results_runtime/` cohort so they never enter research statistics.

### Researcher mode (statistics)

The research surface. Cohort-wide statistics + a per-patient drill-down.

- **Overview** — KPI tiles (DIRECT rate, found rate, runtime), per-disease rank distribution.
- **Memory A/B** — exact McNemar paired test (single-level vs. multi-level memory) with the 95 % CI band.
- **Model comparison** — head-to-head GPT-OSS-120B vs. Med42-70B (Batch 4 controlled subset).
- **MAS vs. single-LLM baseline** — paired-160 comparison.
- **Patient explorer** — faceted browse of any saved cohort; click in to the same five-tab review the doctor sees.
- **My test patients** — build a patient from scratch, clone a cohort patient, edit demographics / conditions / medications / labs with autocomplete, **Smart import** a lab slip (paste text · drop a PDF / FHIR JSON · upload a photo), then run the seven-agent pipeline against it. Past runs land in their own list with **View** (re-opens the result inline) and **Re-run** (opens a model-preset config modal, then hands off to the Doctor runtime view).

### Smart import (lab slips)

Inside the Recent labs section of the patient editor, **Smart import** routes any of:

- a chart-note or lab text snippet,
- a PDF or FHIR JSON file,
- a photo of a lab slip,

through the appropriate backend (pdfplumber / structural FHIR parse / Gemini 2.5 Flash for images), then surfaces an editable preview. The doctor can adjust any extracted value, snap free-text labels to cohort canonical names, and selectively merge into the patient under construction.

### Boot

```bash
make doctor-console        # boots both backend (:8010) and frontend (:5173)
```

Or in two terminals:

```bash
make doctor-console-api    # FastAPI backend on :8010
make doctor-console-web    # React frontend on :5173
```

The frontend is a Vite dev server that proxies `/api/*` to the FastAPI backend, so the backend must always be running. If you see `http proxy error … ECONNREFUSED 127.0.0.1:8010` in the Vite console, start the backend.

> The earlier Streamlit dashboard has been fully replaced by the React console. `make dashboard-legacy` retains the Streamlit view at `:8503` for thesis-defence fallback only.

---

## Architecture

```
Synthea (synthetic patients)
    → Bronze (Parquet) → Silver (OMOP CDM v5.4) → Silver+ (derived features) → Gold (case JSON)
    → LLM Detectability Verifier (data-quality gate)
    → Multi-Agent Pipeline (7 agents, 6 LangGraph stages, 4-tier shared memory)
    → Ranked Differential + NICE-Guideline Treatment Plan
    → React doctor console (Doctor + Researcher modes)
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
| Vector memory | **Qdrant** + `sentence-transformers` + **BioLORD-2023** | Tier-4 case store, NICE guideline retrieval |
| Data lake | **dbt-core** + **DuckDB** + **PyArrow** | Bronze → Silver (OMOP CDM v5.4) → Silver⁺ → Gold |
| Data source | **Synthea** (Java) | Synthetic FHIR-R4 patient generator |
| Frontend | **React + Vite + TypeScript** | Doctor console at `:5173` |
| Backend | **FastAPI + uvicorn** | Doctor console API at `:8010` |
| Document store | **MongoDB** (optional) | Hot store for patient cases + agent runs |
| Smart-import OCR | **pdfplumber** + **Gemini 2.5 Flash** | PDF parse / image lab-slip extraction |
| Legacy frontend | **Streamlit** | Fallback dashboard at `:8503` (defence only) |
| Logging | **structlog** | JSON-lines structured logs |
| Tests | **pytest** + **ruff** | Unit tests + lint/format |

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
├── doctor_console/             # React + FastAPI clinician console
│   ├── backend/                #   FastAPI app
│   └── frontend/               #   Vite + TypeScript React app
├── portal/                     # Legacy Streamlit dashboard (defence fallback)
├── config/                     # Pipeline configs + NICE guideline JSON
├── tests/                      # pytest test suites
├── thesis/                     # Compiled thesis PDF (source kept private)
├── docs/                       # System docs, evaluation methodology, decisions
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

Example — switch to OpenAI for everything:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_EVALUATOR_PROVIDER=openai
LLM_EVALUATOR_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

---

## Storage

CMADS uses two persistence layers:

| Layer | Where | What |
|---|---|---|
| **Cold (immutable inputs)** | DuckDB at `data/clinical.duckdb`, Synthea FHIR JSON at `data/bronze/`, Qdrant volumes | OMOP CDM Silver tables, raw FHIR bundles, BioLORD embeddings, NICE guideline vectors |
| **Hot (run outputs)** | MongoDB (`docker compose up -d mongo`) — collections `patient_cases`, `agent_runs`, `semantic_memory`, `derived_artefacts` | Gold patient cases, per-agent run outputs, execution traces, evaluation verdicts, derived artefacts |

The `USE_MONGO=true` flag (in `.env`) gates the runtime read/write path. With it off, the system reads/writes the on-disk `data/gold/mas_results*/` tree directly.

---

## Make commands

| Command | What it does |
|---|---|
| `make install` | Install Python dependencies |
| `make run-patient UUID=…` | Run the 7-agent pipeline on one patient (CLI) |
| `make run-batch BATCH=… [MAX=n]` | Run the pipeline on a cohort batch |
| `make doctor-console` | Boots both backend (:8010) and frontend (:5173) |
| `make doctor-console-api` | FastAPI doctor-console backend at `:8010` |
| `make doctor-console-web` | React doctor-console frontend at `:5173` (Doctor + Researcher modes) |
| `make dashboard-legacy` | Streamlit dashboard at `:8503` — defence fallback only |
| `make evaluate` | Re-run LLM-as-judge on saved results |
| `make setup-qdrant` | Populate Qdrant with NICE guidelines (one-time) |
| `make test` | Run all tests |
| `make test-mas` | MAS pipeline tests only |
| `make test-data` | Data pipeline tests only |
| `make lint` / `make format` | Lint and auto-format with ruff |
| `make thesis` | Build the thesis PDF locally (source kept private; only the compiled PDF is published in `thesis/main.pdf`) |
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

All of the above are browsable in Researcher mode of the React console — pick any cohort and drill down per-disease, per-agent, or per-patient.

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

## License and credit

This project is part of a Bachelor thesis at the German University in Cairo, supervised by Dr. Shereen Moataz Afifi. NICE clinical guideline content is used under fair-use academic terms. Synthea is open-source under the Apache 2.0 license. All other code in this repository is released under the same license.

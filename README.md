# CMADS — Clinical Multi-Agent Decisioning System

A multi-agent AI system that processes synthetic patient data through a clinical decision pipeline to generate diagnoses and evidence-based treatment plans.

Built as a Bachelor thesis project demonstrating how coordinated AI agents can replicate clinical reasoning when given structured EHR and laboratory data.

## Architecture

```
Synthea (synthetic patients)
    → Bronze (Parquet) → Silver (OMOP CDM) → Silver+ (derived features) → Gold (case JSON)
    → Multi-Agent Pipeline (7 agents, LangGraph)
    → Clinical Decision Report + Treatment Plan
```

### Agent Pipeline (6 stages)

| Stage | Agent | Role |
|-------|-------|------|
| 1 (parallel) | **EHR Analyst** | Extract structured clinical summary from patient EHR |
| 1 (parallel) | **Lab Interpreter** | Classify labs, interpret trends, rank by severity |
| 2 | **Diagnostic Reasoning** | Generate ranked differential diagnosis (adaptive loop, max 3 rounds) |
| 3 | **Clinical Reviewer** | Adversarial verification — independent second opinion |
| 4 | **Diagnostic Refiner** | Merge diagnostic + reviewer into final differential |
| 5 | **LLM Evaluator** | Compare diagnosis against Synthea ground truth (DIRECT/INDIRECT/MISS) |
| 6 | **Treatment Planning** | NICE guideline-based treatment via Qdrant vector search (DIRECT matches only) |

The pipeline diagram is available at [`docs/mas_pipeline.html`](docs/mas_pipeline.html).

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Orchestration | LangGraph (StateGraph) |
| Agent Runtime | LangChain (LCEL) |
| LLM | GPT-oss 120B via Groq API |
| Shared Memory | LangGraph State (TypedDict) |
| Output Schemas | Pydantic v2 |
| Vector DB | Qdrant Cloud + BioLORD-2023 embeddings |
| Data Pipeline | DuckDB + dbt-core + PyArrow |
| Portal | Streamlit |
| Logging | structlog |
| Data Source | Synthea (synthetic patient generator) |

## Project Structure

```
├── src/                    # Agent pipeline (core)
│   ├── orchestrator/       #   LangGraph graph + state
│   ├── agents/             #   7 agent implementations
│   ├── schemas/            #   Pydantic output schemas
│   ├── llm/                #   LLM adapter (Groq/Ollama)
│   ├── evaluation/         #   LLM-as-judge evaluation
│   └── vectordb/           #   Qdrant setup + query
├── pipeline/               # Data pipeline (Bronze → Gold)
├── portal/                 # Streamlit evaluation dashboard
├── config/                 # Pipeline configs + NICE guidelines
├── tests/                  # pytest test suites
├── docs/                   # System docs (SRD, SDD, decisions)
├── diagrams/               # Architecture SVG diagrams
├── notebooks/              # Exploration scripts
└── data/
    └── gold/               # 270 verified patients (tracked)
        ├── patient_cases/  #   ehr_case + lab_case + ground_truth per patient
        ├── mas_results/    #   Agent outputs for processed patients
        └── batches/        #   Cohort batch definitions (6 batches)
```

## Setup

```bash
# Clone and install
git clone https://github.com/abdamin004/CMADS.git
cd CMADS
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment (copy template, then edit .env)
cp .env.example .env
# Edit .env — set your API keys and choose your LLM provider/model

# Populate the Qdrant vector database with NICE guidelines (one-time)
make setup-qdrant
```

### LLM Configuration

All LLM settings are in `.env` — no code changes needed to switch providers or models:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `groq` | `groq`, `openai`, `anthropic`, `gemini`, or `ollama` |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Model name for the chosen provider |
| `LLM_EVALUATOR_MODEL` | `qwen/qwen3-32b` | Separate model for the LLM-as-Judge evaluator |
| `LLM_EVALUATOR_PROVIDER` | *(same as LLM_PROVIDER)* | Optional: use a different provider for evaluator |

**Provider API keys** (set the one matching your provider):

| Provider | Key Variable | Install |
|----------|-------------|---------|
| Groq | `GROQ_API_KEY` | `pip install langchain-groq` |
| OpenAI | `OPENAI_API_KEY` | `pip install langchain-openai` |
| Anthropic | `ANTHROPIC_API_KEY` | `pip install langchain-anthropic` |
| Gemini | `GOOGLE_API_KEY` | `pip install langchain-google-genai` |
| Ollama | *(none — local)* | `pip install langchain-ollama` |

**Examples:**

```env
# OpenAI GPT-4o
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_EVALUATOR_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Google Gemini
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
LLM_EVALUATOR_MODEL=gemini-2.0-flash
GOOGLE_API_KEY=AI...

# Anthropic Claude
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
LLM_EVALUATOR_MODEL=claude-haiku-4-20250414
ANTHROPIC_API_KEY=sk-ant-...

# Local Ollama (free)
LLM_PROVIDER=ollama
LLM_MODEL=llama3:70b
LLM_EVALUATOR_MODEL=llama3:70b
```

## Quick Start (run without rebuilding data)

The repo includes Gold-layer data for 270 verified patients across 8 diseases. You can run the MAS pipeline directly using `make` commands or Python:

```bash
# Install dependencies
make install

# Run on a single patient
make run-patient UUID=4b265e38-b837-001f-9059-5020ec1e3e26

# Run a full batch (50 patients)
make run-batch BATCH=data/gold/batches/batch_1.json

# Run first 5 only (for testing)
make run-batch BATCH=data/gold/batches/batch_1.json MAX=5

# Launch evaluation dashboard
make dashboard

# Run tests
make test
```

Results are saved to `data/gold/mas_results/{patient-uuid}/`.

### All available make commands

| Command | Description |
|---------|-------------|
| `make install` | Install Python dependencies |
| `make run-patient UUID=...` | Run MAS pipeline on one patient |
| `make run-batch BATCH=... [MAX=n]` | Run MAS pipeline on a batch |
| `make dashboard` | Launch Streamlit evaluation dashboard (port 8503) |
| `make setup-qdrant` | Populate Qdrant with NICE guidelines (one-time) |
| `make test` | Run all tests |
| `make test-mas` | Run MAS pipeline tests only |
| `make test-data` | Run data pipeline tests only |
| `make lint` | Check code quality with ruff |
| `make format` | Auto-format code with ruff |

## Data Pipeline (rebuild from scratch)

The data pipeline transforms Synthea output through four layers:

1. **Bronze** — Raw Synthea CSV → Parquet with schema enforcement
2. **Silver** — OMOP CDM v5.4 transformation via dbt + DuckDB
3. **Silver+** — Derived features (lab trends, risk scores, comorbidity matrix)
4. **Gold** — Point-in-time case assembly (hides target disease for fair evaluation)

To rebuild from scratch (requires Synthea + DuckDB):

```bash
# 1. Generate synthetic patients with Synthea
cd synthea && ./run_synthea -p 10000 && cd ..

# 2. Run data pipeline layers
python pipeline/bronze.py batch_10k
python pipeline/silver.py
python pipeline/silver_plus.py
python pipeline/gold.py

# 3. Verify patient data quality with LLM
python pipeline/lab_verifier_llm.py
```

See `pipeline/` for full implementation details.

## Evaluation Results

Evaluated end-to-end on **160 patients** drawn from the 270-patient
verified cohort, across 8 disease categories. The canonical aggregate
lives in [`docs/progress_presentation/aggregate_160.json`](docs/progress_presentation/aggregate_160.json) —
update README numbers from that file rather than from memory.

**Headline (n = 160)**

| Metric | Value |
|---|---:|
| **DIRECT match** | **118 / 160 · 74 %** |
| INDIRECT match | 22 / 160 · 14 % |
| MISS | 20 / 160 · 12 % |
| **Found rate (DIRECT + INDIRECT)** | **88 %** |
| Rank-1 when found | 60 % |
| Avg pipeline time / patient | ~192 s |

**Per-disease breakdown**

| Disease | n | DIRECT | INDIRECT | MISS | Found rate | DIRECT rate |
|---|--:|--:|--:|--:|--:|--:|
| End-stage renal disease | 51 | 41 | 9 | 1 | 98 % | 80 % |
| Metabolic syndrome X | 32 | 29 | 0 | 3 | 91 % | 91 % |
| Essential hypertension | 25 | 16 | 2 | 7 | 72 % | 64 % |
| Ischemic heart disease | 22 | 16 | 3 | 3 | 86 % | 73 % |
| CKD stage 3 | 14 | 8 | 5 | 1 | 93 % | 57 % |
| Diabetes mellitus type 2 | 8 | 4 | 1 | 3 | 63 % | 50 % |
| Chronic congestive heart failure | 5 | 3 | 0 | 2 | 60 % | 60 % |
| CKD stage 2 | 3 | 1 | 2 | 0 | 100 % | 33 % |
| **Total** | **160** | **118** | **22** | **20** | **88 %** | **74 %** |

> An earlier 50-patient checkpoint at
> [`docs/EXPERIMENT_RESULTS.md`](docs/EXPERIMENT_RESULTS.md) (March 2026,
> reporting 18 % DIRECT) is **superseded** by the 160-patient evaluation
> above and is preserved only for historical context.

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/SRD.md`](docs/SRD.md) | System Requirements (96 requirements) |
| [`docs/SDD.md`](docs/SDD.md) | System Design Document |
| [`docs/TECH_STACK.md`](docs/TECH_STACK.md) | Technology selections |
| [`docs/DATA_PIPELINE_DECISIONS.md`](docs/DATA_PIPELINE_DECISIONS.md) | Data pipeline design decisions |
| [`docs/DATA_QUALITY_ANALYSIS.md`](docs/DATA_QUALITY_ANALYSIS.md) | Synthea data quality analysis |
| [`docs/EVALUATION_METHODOLOGY.md`](docs/EVALUATION_METHODOLOGY.md) | LLM-as-judge methodology |
| [`docs/MAS_ARCHITECTURE_EVOLUTION.md`](docs/MAS_ARCHITECTURE_EVOLUTION.md) | Architecture iterations (v1→v4) |

## License

This project is part of a Bachelor thesis. All clinical guidelines are sourced from NICE (National Institute for Health and Care Excellence) and are used for academic purposes.

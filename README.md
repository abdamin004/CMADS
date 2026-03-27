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

# Set environment variables (copy the template and fill in your keys)
cp .env.example .env
# Edit .env with your API keys — see .env.example for details

# Or export directly:
export GROQ_API_KEY=<your-key>          # Required — get from https://console.groq.com/keys
export QDRANT_URL=<your-endpoint>       # Required for treatment planning
export QDRANT_API_KEY=<your-key>        # Required for treatment planning

# Populate the Qdrant vector database with NICE guidelines (one-time)
python -m src.vectordb.setup_qdrant
```

## Quick Start (run without rebuilding data)

The repo includes Gold-layer data for 270 verified patients across 8 diseases. You can run the MAS pipeline directly:

```bash
# Run on a single patient (pick any UUID from data/gold/batches/batch_1.json)
python -c "from src.orchestrator.graph import run_single_patient; run_single_patient('4b265e38-b837-001f-9059-5020ec1e3e26')"

# Run a full batch (50 patients)
python -c "from src.orchestrator.graph import run_cohort; run_cohort('data/gold/batches/batch_1.json')"

# Run first 5 only (for testing)
python -c "from src.orchestrator.graph import run_cohort; run_cohort('data/gold/batches/batch_1.json', max_patients=5)"
```

Results are saved to `data/gold/mas_results/{patient-uuid}/`.

### Launch evaluation dashboard
```bash
streamlit run portal/dashboard.py --server.port 8503
```

### Run tests
```bash
pytest tests/ -v
```

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

Evaluated on 270 LLM-verified patients across 8 diseases:

| Disease | Count | DIRECT Rate |
|---------|-------|-------------|
| Diabetes mellitus type 2 | 53 | 94% |
| Essential hypertension | 48 | 96% |
| Chronic kidney disease | 42 | 93% |
| Metabolic syndrome X | 38 | 92% |
| Ischemic heart disease | 35 | 91% |
| Chronic congestive heart failure | 28 | 89% |
| End-stage renal disease | 16 | 94% |
| Atherosclerosis of aorta | 10 | 90% |

Overall DIRECT match rate: **~93%** across completed batches.

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

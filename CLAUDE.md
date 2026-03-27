# CMADS — Clinical Multi-Agent Decisioning System

## Project Summary
Bachelor thesis project: end-to-end system that generates synthetic patient data (Synthea), processes it through a data pipeline (Bronze→Silver→Silver+→Gold), then runs a multi-agent AI pipeline to diagnose and produce treatment plans.

**Synthea** is the single source of truth for ALL patient data. It's a rule-based patient simulator (Java CLI) using state transition machines and Monte Carlo simulation informed by CDC/NIH statistics. No LLM-generated synthetic documents — agents work directly with Synthea's structured data.

## Architecture at a Glance
```
Synthea (Java CLI) → Bronze (Parquet) → Silver (OMOP CDM via dbt+DuckDB)
  → Silver+ (derived features) → Gold (ehr_case.json + lab_case.json)
  → Multi-Agent Pipeline (7 agents via LangGraph + LangChain + GPT-o3 120B on Ollama)
  → Clinical Decision Report
```

## Documentation (in docs/)
- **SRD.md** — System Requirements Document. Defines WHAT the system does. 96 requirements (MA-xxx, DP-xxx, IF-xxx, NF-xxx).
- **SDD.md** — System Design Document. Defines HOW. Architecture, shared memory, agent blueprints, execution sequence.
- **TECH_STACK.md** — Final technology selections for agent pipeline, evaluation, portal.

## Diagrams (in diagrams/)
- `architecture.svg` — Full system architecture (data pipeline + agent pipeline + shared memory)
- `shared_memory.svg` — Shared memory namespace design with R/W access patterns per agent
- `sequence.svg` — Agent execution sequence for a single patient case
- `agent_blueprint.svg` — Generic agent internal architecture (Input Gate → Prompt Assembler → LLM → Output Parser → Output Gate)
- `tech_stack.svg` — Technology stack layers

## Tech Stack (Agent Pipeline Only)
| Component | Technology |
|-----------|-----------|
| Orchestration | LangGraph (StateGraph) |
| Agent Runtime | LangChain (LCEL chains) |
| LLM | GPT-o3 120B via Ollama (local, localhost:11434) |
| LangChain Class | `ChatOllama` from `langchain-ollama` |
| Shared Memory | LangGraph State (TypedDict channels) |
| Checkpointing | LangGraph MemorySaver + custom FileCheckpointer |
| Output Schemas | Pydantic v2 |
| Config | YAML files |
| Evaluation | pandas, scikit-learn, matplotlib, Plotly |
| Portal | Streamlit + DuckDB (read) |
| Logging | structlog (JSON lines) |
| Testing | pytest + pytest-asyncio |
| Code Quality | ruff |

## Data Pipeline Stack (separate, already documented in Data Eng Spec v3.0)
| Component | Technology |
|-----------|-----------|
| Data Source | Synthea (Java CLI) |
| Bronze | Python + PyArrow → Parquet |
| Silver | dbt-core + DuckDB (OMOP CDM v5.4) |
| Silver+ | dbt-core + DuckDB (derived features) |
| Gold | Python assembler → JSON |
| Orchestration | Prefect (local) |
| Portal Data | DuckDB (clinical.duckdb) |

## Agent Pipeline — 7 Agents in 5 Stages

### Execution Graph (default: full_clinical)
```
Stage 1 (parallel): EHR Analyst + Lab Interpreter
    ↓
Stage 2: Diagnostic Reasoning
    ↓
Stage 3 (parallel): Treatment Planning + Radiology
    ↓
Stage 4: Clinical Reviewer
    ↓
Stage 5: Synthesis → Clinical Decision Report
```

### Agent Specifications

| Agent | Reads from Memory | Writes to Memory | Key Responsibility |
|-------|-------------------|------------------|--------------------|
| EHR Analyst | patient_context (ehr_case) | agent_outputs.ehr_analyst | Extract structured clinical summary from Synthea data |
| Lab Interpreter | patient_context (lab_case) | agent_outputs.lab_interpreter | Classify labs, interpret trends, rank by severity |
| Diagnostic Reasoning | ehr_analyst + lab_interpreter outputs, risk_scores, comorbidity_matrix | agent_outputs.diagnostic | Generate ranked differential diagnosis (≥3) with evidence |
| Treatment Planning | diagnostic output, medication_timeline, drug_condition_links | agent_outputs.treatment | Propose treatment plan, check interactions/contraindications |
| Radiology | diagnostic output, imaging_studies from Synthea | agent_outputs.radiology | Interpret imaging metadata, correlate with diagnoses |
| Clinical Reviewer | diagnostic + treatment + radiology outputs, critical_lab_flags | agent_outputs.reviewer | Adversarial review, consistency check, confidence score |
| Synthesis | ALL agent_outputs + conflicts + patient_context | agent_outputs.synthesis | Consolidate into final Clinical Decision Report |

### Shared Memory Namespaces
```
patient_context   — Gold-layer data (written by Orchestrator, read by all)
agent_outputs     — Per-agent output slots (write-own, read-downstream)
conflicts         — Contradiction records (written by Orchestrator diff engine)
scratchpad        — Per-agent ephemeral notes (private)
execution_trace   — Invocation logs (written by Orchestrator)
```

## Project Structure (target)
```
cmads/
├── config/
│   ├── pipelines/
│   │   ├── full_clinical.yaml
│   │   ├── diagnostic_only.yaml
│   │   └── no_radiology.yaml
│   ├── agents/
│   │   ├── ehr_analyst.yaml
│   │   ├── lab_interpreter.yaml
│   │   ├── diagnostic_reasoning.yaml
│   │   ├── treatment_planning.yaml
│   │   ├── clinical_reviewer.yaml
│   │   ├── radiology.yaml
│   │   └── synthesis.yaml
│   └── models/
│       └── ollama.yaml
├── prompts/
│   ├── ehr_analyst/v1.0.yaml
│   ├── lab_interpreter/v1.0.yaml
│   ├── diagnostic_reasoning/v1.0.yaml
│   ├── treatment_planning/v1.0.yaml
│   ├── clinical_reviewer/v1.0.yaml
│   ├── radiology/v1.0.yaml
│   └── synthesis/v1.0.yaml
├── schemas/
│   ├── ehr_analyst_output.json
│   ├── lab_interpreter_output.json
│   ├── diagnostic_output.json
│   ├── treatment_output.json
│   ├── radiology_output.json
│   ├── reviewer_output.json
│   └── synthesis_output.json
├── src/
│   ├── orchestrator/
│   │   ├── graph.py              # LangGraph StateGraph definition
│   │   ├── state.py              # PipelineState TypedDict
│   │   ├── conflict_detector.py  # Post-stage diff engine
│   │   └── checkpointer.py       # Custom FileCheckpointer
│   ├── memory/
│   │   └── shared_memory.py      # SharedMemory wrapper over LangGraph State
│   ├── agents/
│   │   ├── base.py               # Base agent class (Input Gate → Prompt → LLM → Parse → Output)
│   │   ├── ehr_analyst.py
│   │   ├── lab_interpreter.py
│   │   ├── diagnostic.py
│   │   ├── treatment.py
│   │   ├── radiology.py
│   │   ├── reviewer.py
│   │   └── synthesis.py
│   ├── llm/
│   │   ├── ollama_adapter.py     # ChatOllama setup + retry wrapper
│   │   └── callbacks.py          # AgentTracingCallback (structlog)
│   └── evaluation/
│       ├── metrics.py            # Diagnostic accuracy, differential recall, etc.
│       ├── run_evaluation.py     # CLI evaluation runner
│       └── compare.py            # A/B pipeline comparison
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/                 # Sample Gold JSON files for testing
├── data/
│   ├── gold/                     # ehr_case.json + lab_case.json per patient
│   └── clinical.duckdb
├── outputs/                      # Clinical reports, traces, eval results
├── logs/
├── checkpoints/
├── portal/
│   ├── app.py
│   └── pages/
├── requirements.txt
├── Makefile
└── README.md
```

## Key Implementation Notes

1. **LangGraph is the orchestrator** — don't build a custom one. Use `StateGraph`, `add_node`, `add_edge`, parallel fan-out/fan-in.

2. **Shared memory = LangGraph State** — the `PipelineState(TypedDict)` IS the shared memory. Each namespace is a key. Use `Annotated` types with reducer functions for append-only fields.

3. **ChatOllama, not ChatOpenAI** — all LLM calls go through `langchain_ollama.ChatOllama` pointing at localhost:11434. No API keys.

4. **Pydantic v2 for everything** — agent input/output schemas, config validation, structured LLM output via `.with_structured_output()`.

5. **Config-driven** — adding/removing/reconfiguring agents must be possible via YAML only (no code changes).

6. **Graceful degradation** — if an agent fails, the pipeline continues. Synthesis Agent handles partial results.

7. **Ground truth from Synthea** — evaluation compares agent output against Synthea's known conditions, meds, and labs. No LLM-generated ground truth.

## Implementation Priority
1. `src/orchestrator/state.py` — Define PipelineState
2. `src/llm/ollama_adapter.py` — ChatOllama wrapper
3. `src/agents/base.py` — Base agent class
4. `src/orchestrator/graph.py` — LangGraph StateGraph
5. One agent end-to-end (EHR Analyst) as proof of concept
6. Remaining 6 agents
7. Conflict detector
8. Evaluation framework
9. Streamlit portal

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: CMADS — Clinical Multi-Agent Decisioning System

Bachelor thesis project. A LangGraph-based pipeline of 7 clinical agents that ingests Synthea-generated synthetic patient data, produces a differential diagnosis, evaluates it against ground truth, and (on DIRECT matches only) generates a NICE-guideline-based treatment plan.

Synthea is the **single source of truth** for all patient data — no LLM-generated synthetic documents anywhere. Agents operate on structured Gold-layer JSON.

## Common Commands

All common workflows run through the Makefile:

```bash
make install                                       # pip install -r requirements.txt
make run-patient UUID=<patient-uuid>               # run MAS pipeline on one patient
make run-batch BATCH=data/gold/batches/batch_1.json [MAX=5]  # run on a cohort
make dashboard                                     # Streamlit eval dashboard (port 8503)
make setup-qdrant                                  # one-time: load NICE guidelines into Qdrant
make evaluate                                      # run LLM-as-judge evaluator
make test            # all tests
make test-mas        # MAS pipeline tests only
make test-data       # data pipeline tests only
make lint            # ruff check src/ pipeline/ portal/ tests/
make format          # ruff format
```

Run a single test: `python3 -m pytest tests/test_mas_pipeline.py::test_name -v`

Data pipeline rebuild (rarely needed — Gold data for 270 patients is checked in):
```bash
python pipeline/bronze.py batch_10k
python pipeline/silver.py
python pipeline/silver_plus.py
python pipeline/gold.py
```

## Configuration

All tuneables live in `.env` (loaded by `src/config.py`). **Never hardcode provider/model choices** — the adapter is provider-agnostic.

Key env vars:
- `LLM_PROVIDER` — `groq` (default), `openai`, `anthropic`, `gemini`, `ollama`
- `LLM_MODEL` — e.g. `openai/gpt-oss-120b` (default, via Groq)
- `LLM_EVALUATOR_MODEL` / `LLM_EVALUATOR_PROVIDER` — separate judge model
- `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` — whichever matches the provider
- `QDRANT_URL` / `QDRANT_API_KEY` — for treatment planning
- `DIAGNOSTIC_MAX_ROUNDS` (default 3), `DIAGNOSTIC_CONFIDENCE_THRESHOLD` (default 75)
- `AGENT_TIMEOUT` (seconds, default 300), `LLM_CALL_TIMEOUT`, `LLM_MAX_RETRY_WAIT`

Access from code via `from src.config import cfg` — do not read `os.environ` directly outside `config.py` and `llm/adapter.py`.

## Architecture

### Agent pipeline (6 stages, 7 agents)

```
Stage 1 (parallel): ehr_analyst + lab_interpreter
Stage 2: diagnostic_reasoning   (adaptive loop, max 3 rounds)
Stage 3: clinical_reviewer      (adversarial review)
Stage 4: final_diagnosis        (refiner — merges diagnostic + reviewer)
Stage 5: evaluation             (LLM-as-judge vs. Synthea ground truth → DIRECT/INDIRECT/MISS)
Stage 6: treatment_planning     (NICE guidelines via Qdrant; runs only on DIRECT matches)
```

The graph is built in `src/orchestrator/graph.py::compile_pipeline()`. Stage 1 fans out from `START` via `add_conditional_edges`; Stage 2 fans in once both Stage 1 agents have written their output.

### Shared memory = LangGraph State

`src/orchestrator/state.py` defines `PipelineState(TypedDict)`. **This IS the shared memory** — do not build a separate store. Namespaces:

| Key | Reducer | Purpose |
|-----|---------|---------|
| `patient_context` | overwrite | Gold data (set once by orchestrator) |
| `agent_outputs` | `_merge_agent_outputs` | Per-agent slot; each agent writes `{agent_id: output}` |
| `conflicts` | `add` (append) | Conflict records |
| `execution_trace` | `add` (append) | Per-agent invocation trace |
| `scratchpad` | overwrite | Ephemeral notes |

Because `agent_outputs` uses a merging reducer, parallel Stage 1 agents can write concurrently without overwriting each other.

### Agent blueprint (`src/agents/base.py`)

Every agent subclasses `BaseAgent` with:
- `agent_id: str` — also determines the prompt YAML path (`prompts/{agent_id}.yaml`)
- `output_schema: Type[BaseModel]` — Pydantic v2 schema from `src/schemas/`
- `build_user_prompt(state) -> str` — required override
- `run_reasoning(state, llm, json_llm) -> dict` — optional override for multi-call chain-of-thought (default is single-call)

`__call__(state)` implements the 5-component blueprint (Input Gate → Prompt → LLM → Parse → Output Gate), writes a trace entry, and returns `{"agent_outputs": {agent_id: ...}, "execution_trace": [...]}`.

Error handling is **graceful by design**:
- `SkipAgentException` → emit pre-built result, status `skipped`
- `ValidationError` → status `partial`, best-effort parse of error
- any other Exception → `output=None`, status `error`
- The pipeline never aborts on a single agent failure

The base class contains **heavy JSON repair** (`_extract_json_from_response`) — markdown fences, `<think>` tags, trailing commas, single quotes, unescaped newlines. Keep it; local LLMs produce malformed JSON constantly.

### LLM adapter (`src/llm/adapter.py`)

One factory (`get_llm`) handles all providers via a registry keyed by name. `invoke_with_retry` wraps calls with exponential backoff (capped at `LLM_MAX_RETRY_WAIT`) and a json-mode fallback: if `json_validate_failed` fires on the last attempt, it retries once without `json_mode`. Anthropic has no native json_mode — rely on base-class JSON repair.

LangSmith tracing auto-enables if `LANGSMITH_API_KEY` is set (EU endpoint, project `cmads-clinical-pipeline`).

### Prompts

Prompts live in `prompts/{agent_id}.yaml` (NOT in code). Structure:
```yaml
system: |
  <system prompt — overrides BaseAgent.system_prompt>
calls:
  analysis:   { system: ..., user: ... }
  structure:  { system: ..., user: ... }
  review:     { system: ..., user: ... }
```

Multi-call agents use `BaseAgent._run_analysis_structure_review` which expects the three `calls` blocks above. Variables like `{patient_data}`, `{analysis}`, `{output_schema}` are substituted via `str.format`.

### Data paths

Defaults (override in `.env`):
- `GOLD_DIR` = `data/gold/patient_cases` — one subdir per patient UUID with `ehr_case.json`, `lab_case.json`, `ground_truth.json`
- `MAS_RESULTS_DIR` = `data/gold/mas_results` — one subdir per patient with `{agent_id}.json` files + `execution_trace.json`
- `GUIDELINES_DIR` = `config/guidelines` — NICE guideline JSON per disease
- `DUCKDB_PATH` = `data/clinical.duckdb` — OMOP Silver layer, read by portal

Batches are at `data/gold/batches/batch_{1..6}.json` (lists of UUIDs).

## Project Layout

```
src/
  orchestrator/  graph.py (StateGraph), state.py (PipelineState)
  agents/        base.py + one module per agent:
                   ehr_analyst, lab_interpreter, diagnostic, reviewer,
                   refiner (→ final_diagnosis), evaluator, treatment
  schemas/       Pydantic output schemas per agent
  llm/           adapter.py (provider-agnostic get_llm + invoke_with_retry)
  evaluation/    llm_judge.py, judge_common.py
  vectordb/      setup_qdrant.py, query_guidelines.py
  config.py      central cfg object (all .env access)
pipeline/        Bronze → Silver → Silver+ → Gold (dbt + DuckDB + PyArrow)
prompts/         {agent_id}.yaml — single file per agent
config/guidelines/  NICE guideline JSON per disease
portal/          Streamlit dashboard (dashboard.py)
tests/           pytest; conftest.py loads cfg + cohort fixtures
docs/            SRD, SDD, TECH_STACK, evaluation methodology, etc.
data/gold/       patient_cases/, mas_results/, batches/
```

## Key Implementation Rules

1. **LangGraph is the orchestrator** — never build a custom one. Use `StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`.
2. **Shared memory = state** — agents read from and return partial `state` dicts; reducers handle merging.
3. **Config-driven agents** — adding/removing/reconfiguring an agent should mean a YAML prompt + a node added to the graph. Avoid embedding prompts in Python.
4. **Pydantic v2 only** — all agent outputs validate against a schema in `src/schemas/`.
5. **Ground truth comes from Synthea**, never from an LLM. The evaluator compares agent output against `ground_truth.json` written by the Gold assembler.
6. **Graceful degradation** — pipeline must continue even if one agent fails. Preserve the partial/error/skipped trace semantics in `base.py::__call__`.
7. **Provider-agnostic LLM calls** — always go through `get_llm()`; never import `ChatGroq` / `ChatOpenAI` / etc. directly from agent code.
8. **Commit discipline** — the Gold `mas_results/*.json` files churn on every run; stage them deliberately, don't blanket-add.

## Notes vault (`notes/`)
This repo contains an Obsidian vault at `notes/`. Conventions live in `notes/CLAUDE.md`. As part of your normal work in this project:

- **Decisions** — when a non-trivial decision is made (agent design, prompt change, schema change, evaluation methodology tweak, "let's do X instead of Y"), append one bullet to `notes/decisions.md` using the format in `notes/CLAUDE.md`. Do this **before** ending the turn.
- **Experiments** — when an experiment run produces a result worth remembering (new model, prompt variant, batch comparison), append one bullet to `notes/experiments.md` with DIRECT/INDIRECT/MISS counts and a link to the `mas_results/` path.
- **Bug investigations** — when you diagnose a non-trivial bug (anything that took more than one Read+Edit cycle), append a section to `notes/questions.md` with root cause + fix reference.
- **Skip** for routine edits, typos, one-line fixes, and routine pipeline reruns.
- **Never** put PHI, patient identifiers, secrets, or API keys in the vault.

If a note already exists on the topic, update it rather than creating a new one. Keep entries terse — one bullet, two sentences max — and link to commits / `file:line` for detail.

## Thesis (`thesis/`)
The Bachelor thesis LaTeX project lives at `thesis/`. **When working on thesis prose, open `thesis/CLAUDE.md` first** — it documents the chapter map, what's stub vs done, the citation conventions, and (critically) the on-disk locations of every empirical number that goes into the Results chapter, so claims trace back to artifacts in this repo rather than being invented.

- Build: `make thesis` (uses `tectonic` if present, else `pdflatex`).
- Clean: `make thesis-clean`.
- Watch + rebuild on save: `make thesis-watch` (needs `fswatch`).
- Build artifacts (`*.aux`, `*.bbl`, `main.pdf`) are gitignored — regenerate on demand.

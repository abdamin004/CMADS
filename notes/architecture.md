# Architecture

See [CLAUDE.md](../CLAUDE.md) for the canonical reference.

## Layers
- **Data pipeline**: Synthea → Bronze → Silver → Silver+ → Gold (DuckDB + dbt + PyArrow)
- **Orchestrator**: LangGraph `StateGraph` (`src/orchestrator/graph.py`)
- **Shared memory**: `PipelineState` TypedDict with merging reducers (`src/orchestrator/state.py`)
- **LLM adapter**: provider-agnostic `get_llm` + `invoke_with_retry` (`src/llm/adapter.py`)
- **Evaluation**: LLM-as-judge vs Synthea ground truth
- **Vector DB**: Qdrant for NICE guidelines (`src/vectordb/`)
- **Portal**: Streamlit dashboard

## Key files to bookmark
- `src/orchestrator/graph.py`, `src/orchestrator/state.py`
- `src/agents/base.py` (the 5-component blueprint)
- `src/config.py`
- `src/llm/adapter.py`
- `prompts/{agent_id}.yaml`
- `pipeline/bronze.py` · `pipeline/silver.py` · `pipeline/silver_plus.py` · `pipeline/gold.py`

## Implementation rules (recap)
1. LangGraph is the orchestrator
2. Shared memory = state
3. Config-driven agents (YAML prompts)
4. Pydantic v2 only
5. Synthea is ground truth (no LLM-generated patient data)
6. Graceful degradation
7. Provider-agnostic LLM calls via `get_llm()`
8. Don't blanket-commit `mas_results/*.json`

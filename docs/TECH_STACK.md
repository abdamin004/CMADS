**Final Technology Stack**

────────────────────────────────────────

**Agent Pipeline • Evaluation • Portal**

*LangChain + LangGraph + GPT-oss 120B (Groq API) + Streamlit*

  --------------------------- --------------------------------------------------------------------------
  **Document Title**          Final Technology Stack --- Agent Pipeline

  **Project**                 Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows

  **Version**                 2.0

  **Date**                    March 30, 2026

  **Author**                  Islam

  **Type**                    Bachelor Thesis

  **Companion To**            SRD v1.0 + Design Document v1.0 + Data Engineering Spec v3.0
  --------------------------- --------------------------------------------------------------------------

*This document specifies the definitive technology selections for the multi-agent pipeline, evaluation framework, and clinician portal. The data pipeline stack is documented separately in the Data Engineering Specification v3.0.*

**Table of Contents**

1. Stack Summary
2. LangGraph Orchestration
3. LLM Adapter
4. Agent Architecture
5. Evaluation
6. Treatment Planning
7. Portal
8. Configuration
9. Dependencies

---

**1. Stack Summary**

  ----------------------- ------------------------------ ---------------- -------------------------------------------------------------------------------
  **Layer**               **Technology**                 **Version**      **Purpose**

  **Orchestration**       LangGraph (StateGraph)         >=1.1            DAG-based multi-agent orchestration with state channels, fan-out/fan-in

  **Agent Runtime**       LangChain (LCEL)               >=1.2            Message construction, BaseChatModel interface, retry utilities

  **LLM (Agents)**        GPT-oss 120B                   Groq API         Primary reasoning model for all 7 agents, served via Groq cloud inference

  **LLM (Evaluator)**     Qwen3 32B                      Groq API         Separate model for LLM-as-Judge evaluation (independent from reasoning model)

  **LLM Serving**         Groq API (primary)             cloud            Cloud LLM inference; 5 providers supported via adapter (see section 3)

  **LLM SDK**             langchain-groq + langchain-ollama  latest       Primary + fallback provider packages; 3 more available (openai, anthropic, gemini)

  **Vector Database**     Qdrant Cloud                   latest           NICE clinical guidelines for semantic search (Treatment Planning agent)

  **Embeddings**          BioLORD-2023                   768-dim          Medical concept embeddings via sentence-transformers for guideline retrieval

  **Shared Memory**       LangGraph State (TypedDict)    built-in         5 namespaces with reducer annotations for safe concurrent writes

  **Checkpointing**       LangGraph MemorySaver          built-in         In-memory per-stage state serialisation (no custom FileCheckpointer)

  **Output Schemas**      Pydantic v2                    >=2.0            Agent output validation + JSON repair pipeline in BaseAgent

  **Prompt Management**   YAML files (prompts/)          ---              Per-agent prompt files loaded by BaseAgent._load_prompts()

  **Config**              python-dotenv + src/config.py  ---              Central Config class reads all settings from .env at access time

  **Logging**             structlog                      >=24.0           Structured JSON-lines logging with context binding

  **Observability**       LangSmith (optional)           >=0.1            Auto-enabled if LANGSMITH_API_KEY is set; EU endpoint by default

  **Portal**              Streamlit                      >=1.40           Single-file evaluation dashboard (portal/dashboard.py)

  **Portal Data**         DuckDB (read-only)             >=1.0            Direct SQL queries over Silver/Gold for portal

  **Visualisation**       Plotly                         >=6.0            Interactive charts in Streamlit dashboard

  **Testing**             pytest + pytest-asyncio        latest           Unit tests, integration tests, async agent tests

  **Code Quality**        ruff                           >=0.8            Linting and formatting
  ----------------------- ------------------------------ ---------------- -------------------------------------------------------------------------------

**1.1 Relationship to Data Pipeline Stack**

The data pipeline (documented in the Data Engineering Specification v3.0) ingests Synthea-generated patient data and produces Gold-layer JSON files (ehr_case.json, lab_case.json) that are the sole input to the agent pipeline. The two stacks share exactly one integration point:

-   **DuckDB:** The data pipeline writes Synthea-derived structured data to clinical.duckdb. The portal reads from it directly. The agent pipeline does not touch DuckDB --- it consumes Gold JSON files on disk.

---

**2. LangGraph Orchestration**

LangGraph is the orchestration backbone. The entire pipeline is defined as a single `StateGraph` in `src/orchestrator/graph.py`. It handles parallel execution, state management, and checkpointing natively.

**2.1 Pipeline: 6 Stages, 7 Agents**

The pipeline executes 7 agents across 6 sequential stages:

```
Stage 1 (parallel): EHR Analyst + Lab Interpreter
    |
Stage 2 (adaptive): Diagnostic Reasoning
    |
Stage 3: Clinical Reviewer
    |
Stage 4: Diagnostic Refiner
    |
Stage 5: LLM Evaluator
    |
Stage 6: Treatment Planning
    |
   END
```

There is no Radiology agent and no Synthesis agent. The pipeline ends with Treatment Planning, which only executes guideline retrieval when the Evaluator confirms a DIRECT match against ground truth.

**2.2 StateGraph Definition**

The shared memory is defined in `src/orchestrator/state.py` as a `PipelineState(TypedDict)` with reducer annotations:

```python
# src/orchestrator/state.py

def _merge_agent_outputs(existing: dict, new: dict) -> dict:
    """Reducer: merge new agent output slots into existing dict."""
    merged = copy.copy(existing) if existing else {}
    merged.update(new)
    return merged

class PipelineState(TypedDict, total=False):
    patient_context: dict                                 # Gold-layer data (set once)
    agent_outputs: Annotated[dict, _merge_agent_outputs]  # Per-agent slots (merge reducer)
    conflicts: Annotated[list, add]                       # Contradiction records (append-only)
    execution_trace: Annotated[list, add]                 # Invocation logs (append-only)
    scratchpad: dict                                      # Per-agent ephemeral notes
```

The `_merge_agent_outputs` reducer allows parallel agents (Stage 1) to write to their own key without overwriting each other. The `add` reducer (from `operator`) appends to lists.

**2.3 Graph Construction**

From `src/orchestrator/graph.py`:

```python
# src/orchestrator/graph.py

def _stage1_fanout(state: dict) -> list[str]:
    """Router: fan out to both Stage 1 agents in parallel."""
    return ["ehr_analyst", "lab_interpreter"]

def compile_pipeline():
    graph = StateGraph(PipelineState)

    # Stage 1 -- parallel: EHR Analyst + Lab Interpreter
    graph.add_node("ehr_analyst", ehr_analyst_agent)
    graph.add_node("lab_interpreter", lab_interpreter_agent)

    # Stage 2 -- Diagnostic Reasoning (depends on both Stage 1 agents)
    graph.add_node("diagnostic_reasoning", diagnostic_reasoning_agent)

    # Stage 3 -- Clinical Reviewer (verifies Stage 2 output)
    graph.add_node("clinical_reviewer", clinical_reviewer_agent)

    # Stage 4 -- Diagnostic Refiner (merges Diagnostic + Reviewer -> final differential)
    graph.add_node("final_diagnosis", diagnostic_refiner_agent)

    # Stage 5 -- LLM Evaluator (compares diagnosis against ground truth)
    graph.add_node("evaluation", evaluate_node)

    # Stage 6 -- Treatment Planning (NICE guidelines, only for DIRECT matches)
    graph.add_node("treatment_planning", treatment_planning_agent)

    # Fan-out from START to both Stage 1 agents (parallel)
    graph.add_conditional_edges(START, _stage1_fanout, ["ehr_analyst", "lab_interpreter"])

    # Stage 1 -> Stage 2 (fan-in: diagnostic waits for both)
    graph.add_edge("ehr_analyst", "diagnostic_reasoning")
    graph.add_edge("lab_interpreter", "diagnostic_reasoning")

    # Stage 2 -> Stage 3 -> Stage 4 -> Stage 5 -> Stage 6 -> END
    graph.add_edge("diagnostic_reasoning", "clinical_reviewer")
    graph.add_edge("clinical_reviewer", "final_diagnosis")
    graph.add_edge("final_diagnosis", "evaluation")
    graph.add_edge("evaluation", "treatment_planning")
    graph.add_edge("treatment_planning", END)

    # Compile with in-memory checkpointing
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
```

**2.4 Parallel Fan-Out / Fan-In**

LangGraph natively supports parallel execution via `add_conditional_edges` returning multiple node names. In Stage 1, `_stage1_fanout` returns `["ehr_analyst", "lab_interpreter"]`, causing both agents to execute concurrently. The `diagnostic_reasoning` node has edges from both, so it only fires once both have written their outputs to the state.

**2.5 Checkpointing**

The pipeline uses LangGraph's built-in `MemorySaver` for in-memory checkpointing. There is no custom `FileCheckpointer`. State is serialised after each node completes.

---

**3. LLM Adapter**

The LLM adapter (`src/llm/adapter.py`) is a provider-agnostic factory that supports 5 LLM providers. Switching providers requires only a `.env` change --- no code modifications.

**3.1 Provider Registry**

```python
# src/llm/adapter.py

PROVIDERS = {
    "groq":      ("langchain_groq",         "ChatGroq",                  _groq_kwargs),
    "openai":    ("langchain_openai",       "ChatOpenAI",                _openai_kwargs),
    "anthropic": ("langchain_anthropic",    "ChatAnthropic",             _anthropic_kwargs),
    "gemini":    ("langchain_google_genai", "ChatGoogleGenerativeAI",    _gemini_kwargs),
    "ollama":    ("langchain_ollama",       "ChatOllama",                _ollama_kwargs),
}
```

Each provider has a dedicated kwargs-builder function that handles provider-specific differences (e.g., `json_mode` is `response_format` for Groq/OpenAI, `response_mime_type` for Gemini, `format="json"` for Ollama). Provider packages are lazily imported --- only the active provider's package needs to be installed.

**3.2 get_llm() Factory**

```python
def get_llm(
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: str | None = None,
    provider: str | None = None,
    json_mode: bool = False,
) -> BaseChatModel:
```

Defaults are read from environment variables via `src/config.py`:
- `LLM_PROVIDER` (default: `groq`)
- `LLM_MODEL` (default: `openai/gpt-oss-120b`)

The function validates the API key before importing the provider package (fail-fast), then constructs the LangChain chat model with the appropriate kwargs.

**3.3 Evaluator LLM**

A separate `get_evaluator_llm()` function returns a different model for the LLM-as-Judge evaluator:

```python
def get_evaluator_llm(temperature: float = 0.0, max_tokens: int = 1024) -> BaseChatModel:
    return get_llm(
        temperature=temperature,
        max_tokens=max_tokens,
        model=cfg.LLM_EVALUATOR_MODEL,      # default: qwen/qwen3-32b
        provider=cfg.LLM_EVALUATOR_PROVIDER, # default: same as main provider
    )
```

This ensures the evaluator uses a different model (Qwen3 32B) from the reasoning agents (GPT-oss 120B), providing independence in the LLM-as-Judge evaluation.

**3.4 Retry with Exponential Backoff**

```python
def invoke_with_retry(
    llm: BaseChatModel,
    messages: list,
    max_retries: int = 3,
    agent_id: str = "unknown",
) -> Any:
```

Retry behaviour:
- Exponential backoff: `wait = min(2^attempt, LLM_MAX_RETRY_WAIT)` (default cap: 10s)
- Per-call timeout warning at `LLM_CALL_TIMEOUT` seconds (default: 120)
- Empty response detection (raises ValueError to trigger retry)
- JSON mode fallback: if the final attempt fails due to JSON validation, retries once without `json_mode=True`

**3.5 LangSmith Tracing**

LangSmith is auto-enabled when `LANGSMITH_API_KEY` is set in the environment. No custom callback handler is needed --- LangChain's native LangSmith integration handles tracing automatically:

```python
# src/llm/adapter.py (top-level, runs at import time)

if os.environ.get("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "cmads-clinical-pipeline")
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
```

---

**4. Agent Architecture**

Every agent extends `BaseAgent` (`src/agents/base.py`), which implements the 5-component blueprint from SDD Section 5.1: Input Gate, Prompt Assembler, LLM, Output Parser, Output Gate.

**4.1 BaseAgent Class**

```python
# src/agents/base.py

class BaseAgent:
    agent_id: str = "base"
    system_prompt: str = ""
    output_schema: Type[BaseModel] = BaseModel
    temperature: float = 0.2
    max_tokens: int = 4096
    max_agent_time: int = int(os.environ.get("AGENT_TIMEOUT", "300"))
```

Subclasses set `agent_id`, `system_prompt`, `output_schema`, and implement `build_user_prompt(state)`. Optionally, they override `run_reasoning()` for multi-call chain-of-thought patterns.

**4.2 YAML Prompt Loading**

Prompts are stored as flat YAML files in `prompts/` (one file per agent, e.g., `prompts/ehr_analyst.yaml`). There are no versioned subdirectories --- each agent has a single YAML file at the top level.

```python
def _load_prompts(self) -> dict:
    """Load prompts from YAML file (prompts/{agent_id}.yaml)."""
    yaml_path = PROMPTS_DIR / f"{self.agent_id}.yaml"
    if yaml_path.exists():
        self._prompts = yaml.safe_load(yaml_path.read_text())
        if "system" in self._prompts:
            self.system_prompt = self._prompts["system"].strip()
```

YAML files contain a top-level `system` prompt and a `calls` section for multi-call agents:

```yaml
# prompts/ehr_analyst.yaml

version: "1.0"
agent_id: ehr_analyst

system: |
  You are the EHR Analyst Agent in a multi-agent clinical decision pipeline.
  ...

calls:
  analysis:
    system: |
      You are a senior clinical analyst reviewing a patient's electronic health record.
      Perform a thorough analysis. Do NOT produce JSON yet.
    user: |
      {patient_data}
      Analyse this patient's record thoroughly:
      ...

  structure:
    system: "{system}"
    user: |
      # Your Previous Analysis
      {analysis}
      # Original Patient Data
      {patient_data}
      Now convert your analysis into the required JSON format.
      ...

  review:
    system: |
      You are a quality reviewer checking a clinical EHR summary.
    user: |
      # Original Patient Data
      {patient_data}
      # Produced Summary
      {output_json}
      Review this summary against the original data:
      ...
```

The `_get_call_prompt(call_name, key, fallback, **kwargs)` method retrieves prompts for specific calls and substitutes template variables (`{patient_data}`, `{analysis}`, `{output_json}`, etc.).

**4.3 Multi-Call Reasoning Pattern**

Most agents use `_run_analysis_structure_review()`, a three-call pattern:

1. **Analysis call** (free-text LLM, no JSON) --- deep clinical analysis
2. **Structure call** (JSON-mode LLM) --- convert analysis to validated Pydantic schema
3. **Review call** (JSON-mode LLM) --- self-critique and correct if needed; falls back to original if review output fails validation

```python
def _run_analysis_structure_review(self, state, llm, json_llm=None) -> dict:
    patient_data = self.build_user_prompt(state)

    # Call 1: Deep analysis (free text)
    analysis = self._call_llm(llm, system=..., user=...)

    # Call 2: Structured output (JSON mode)
    raw_json = self._call_llm(json_llm, system=..., user=...)
    output = self._parse_output(raw_json, json_llm, messages)

    # Call 3: Self-review (JSON mode, fallback to original on failure)
    review = self._call_llm(json_llm, system=..., user=...)
    try:
        return self._parse_output(review).model_dump()
    except (JSONDecodeError, ValidationError):
        return output.model_dump()  # Keep original if review fails
```

Each `_call_llm()` call checks the per-agent timeout (`AGENT_TIMEOUT`, default 300s) before invoking.

**4.4 JSON Repair Pipeline**

The system does NOT use `.with_structured_output()`. Instead, `_extract_json_from_response()` implements a multi-stage JSON repair pipeline:

1. Strip `<think>...</think>` tags (Qwen3 / reasoning models)
2. Extract from markdown code blocks (` ```json ... ``` `)
3. Regex extract first `{...}` block
4. Direct `json.loads()` attempt
5. Fix trailing commas before `}` or `]`
6. Fix missing commas between `}{` or `][`
7. Fix single quotes used as JSON delimiters (pattern-based)
8. Brute-force replace all single quotes with double quotes
9. Escape unescaped newlines

After extraction, Pydantic validates the result. If validation fails, a follow-up LLM call asks the model to fix its JSON.

**4.5 Per-Agent Timeout**

Each agent has a configurable timeout (default 300 seconds, set via `AGENT_TIMEOUT` env var). The `_check_timeout()` method is called before every LLM invocation within the agent:

```python
def _check_timeout(self):
    if hasattr(self, '_agent_start_time') and self._agent_start_time:
        elapsed = time.time() - self._agent_start_time
        if elapsed > self.max_agent_time:
            raise TimeoutError(f"Agent {self.agent_id} exceeded {self.max_agent_time}s timeout")
```

**4.6 LangGraph Node Function**

`BaseAgent.__call__()` is the LangGraph node function. It returns a dict that LangGraph merges into the `PipelineState`:

```python
return {
    "agent_outputs": {self.agent_id: output_dict},
    "execution_trace": [trace_entry],
}
```

Graceful degradation: if an agent raises any exception, it returns `agent_outputs: {agent_id: None}` with `status: "error"` in the trace. The pipeline continues.

---

**5. Evaluation (LLM-as-Judge)**

The evaluation system uses a separate LLM (Qwen3 32B) as a judge to compare agent diagnoses against Synthea ground truth. Shared logic lives in `src/evaluation/judge_common.py`.

**5.1 Judge Prompt**

The judge classifies each diagnosis as DIRECT, INDIRECT, or MISS:

```python
# src/evaluation/judge_common.py

JUDGE_PROMPT = """You are a clinical evaluator. Compare the system's diagnoses against the actual disease.

ACTUAL DISEASE: {target_disease}

SYSTEM'S TOP 5:
{differential}

Step 1: Check each diagnosis. Is it DIRECT, INDIRECT, or UNRELATED?

DIRECT = same disease, different name:
  "Coronary artery disease" = "Ischemic heart disease"
  "HFrEF" or "HFpEF" = "Congestive heart failure"
  ...

INDIRECT = cause, consequence, precursor, or subtype:
  "CKD stage 4" for ESRD = INDIRECT (precursor)
  "Diabetic nephropathy" for ESRD = INDIRECT (cause)
  ...

Step 2: Pick the BEST match (DIRECT > INDIRECT). Report its rank.

Respond with EXACTLY these 5 lines:
FOUND: YES or NO
MATCH_TYPE: DIRECT or INDIRECT or MISS
RANK: [1-5 or 0]
MATCHED_DIAGNOSIS: [name from list or NONE]
REASON: [one sentence]"""
```

**5.2 Response Parsing**

`parse_judge_response()` extracts the structured 5-line response:

```python
def parse_judge_response(text: str) -> dict:
    # Returns: {found, match_type, rank, matched_diagnosis, reason}
    # Handles inconsistencies (e.g., match_type=DIRECT but found=NO -> corrects to found=YES)
```

`strip_think_tags()` removes `<think>...</think>` blocks that Qwen3 produces in reasoning mode.

**5.3 Evaluation Flow**

The evaluator runs as Stage 5 in the pipeline (the `evaluate_node` in the graph). It:
1. Reads the refined differential from Stage 4 (Diagnostic Refiner)
2. Reads the target disease from ground truth (Synthea data)
3. Calls Qwen3 32B with the judge prompt
4. Parses the response into a structured evaluation result
5. Writes the result to `agent_outputs.evaluation`

The Treatment Planning agent (Stage 6) reads this evaluation to decide whether to proceed with guideline retrieval (only on DIRECT match).

---

**6. Treatment Planning (Qdrant + BioLORD-2023)**

The Treatment Planning agent uses semantic search over NICE clinical guidelines stored in Qdrant Cloud.

**6.1 Vector Database Setup**

From `src/vectordb/query_guidelines.py`:

```python
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from src.config import cfg

def search_guidelines(disease_name: str, top_k: int = 3) -> list[dict]:
    client = QdrantClient(url=cfg.QDRANT_URL, api_key=cfg.QDRANT_API_KEY)
    model = SentenceTransformer(cfg.EMBEDDING_MODEL)  # FremyCompany/BioLORD-2023

    embedding = model.encode(disease_name).tolist()

    results = client.query_points(
        collection_name=cfg.QDRANT_COLLECTION,  # "nice_guidelines"
        query=embedding,
        limit=top_k,
    )
```

Both the Qdrant client and the SentenceTransformer model are lazily initialised with thread-safe singletons.

**6.2 Configuration**

| Setting | Env Var | Default |
|---------|---------|---------|
| Qdrant endpoint | `QDRANT_URL` | (required) |
| Qdrant API key | `QDRANT_API_KEY` | (required) |
| Collection name | `QDRANT_COLLECTION` | `nice_guidelines` |
| Embedding model | `EMBEDDING_MODEL` | `FremyCompany/BioLORD-2023` |

**6.3 Return Format**

Each guideline result contains:
- `disease_name` --- matched disease from the collection
- `nice_guideline` --- NICE reference (e.g., "NG106")
- `nice_title` --- guideline title
- `source` --- source identifier
- `score` --- cosine similarity (0--1)
- `guideline` --- full parsed guideline JSON dict

---

**7. Portal**

The portal is a single Streamlit dashboard at `portal/dashboard.py`. There is no multi-page `pages/` directory.

**7.1 Dashboard**

```python
# portal/dashboard.py

st.set_page_config(
    page_title="CMADS Evaluation Dashboard",
    page_icon="...",
    layout="wide",
)
```

Launch command:

```
streamlit run portal/dashboard.py
```

The dashboard reads from:
- `GOLD_DIR` (default: `data/gold/patient_cases`) --- patient case JSON files
- `MAS_RESULTS_DIR` (default: `data/gold/mas_results`) --- agent pipeline output files
- `DUCKDB_PATH` (default: `data/clinical.duckdb`) --- Silver/Gold patient data
- `BATCH_DIR` (default: `data/gold/batches`) --- batch evaluation results

Visualisation uses Plotly (>=6.0) for interactive charts. Pandas provides the data manipulation layer.

---

**8. Configuration**

All configuration is centralised in `src/config.py`, which reads environment variables via `python-dotenv`.

**8.1 Central Config Class**

```python
# src/config.py

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

class Config:
    @property
    def LLM_PROVIDER(self) -> str:
        return _env("LLM_PROVIDER", "groq")

    @property
    def LLM_MODEL(self) -> str:
        return _env("LLM_MODEL", "openai/gpt-oss-120b")

    @property
    def LLM_EVALUATOR_MODEL(self) -> str:
        return _env("LLM_EVALUATOR_MODEL", "qwen/qwen3-32b")

    # ... (Ollama, Qdrant, agent tuning, data paths)

cfg = Config()
```

All properties read from `os.environ` at access time (not import time), making them overridable in tests.

**8.2 Environment Variables**

Complete list from `.env.example`:

| Category | Variable | Default | Description |
|----------|----------|---------|-------------|
| **LLM** | `LLM_PROVIDER` | `groq` | Provider: groq, openai, anthropic, gemini, ollama |
| | `LLM_MODEL` | `openai/gpt-oss-120b` | Model for all agents |
| | `LLM_EVALUATOR_MODEL` | `qwen/qwen3-32b` | Model for LLM-as-Judge evaluator |
| | `LLM_EVALUATOR_PROVIDER` | (same as LLM_PROVIDER) | Optional separate provider for evaluator |
| **API Keys** | `GROQ_API_KEY` | (required for groq) | Groq API key |
| | `OPENAI_API_KEY` | (required for openai) | OpenAI API key |
| | `OPENAI_BASE_URL` | (optional) | Custom base URL (Azure, OpenRouter, vLLM) |
| | `ANTHROPIC_API_KEY` | (required for anthropic) | Anthropic API key |
| | `GOOGLE_API_KEY` | (required for gemini) | Google Gemini API key |
| **Ollama** | `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| | `OLLAMA_CONTEXT_WINDOW` | `16384` | Context window for Ollama models |
| **Qdrant** | `QDRANT_URL` | (required) | Qdrant Cloud endpoint |
| | `QDRANT_API_KEY` | (required) | Qdrant API key |
| | `QDRANT_COLLECTION` | `nice_guidelines` | Collection name |
| | `EMBEDDING_MODEL` | `FremyCompany/BioLORD-2023` | Sentence-transformers model |
| **Agent Tuning** | `DIAGNOSTIC_MAX_ROUNDS` | `3` | Max self-critique rounds for diagnostic agent |
| | `DIAGNOSTIC_CONFIDENCE_THRESHOLD` | `75` | Stop when confidence >= this (0--100) |
| | `AGENT_TIMEOUT` | `300` | Max seconds per agent (default: 5 min) |
| | `LLM_CALL_TIMEOUT` | `120` | Warn if a single LLM call exceeds this |
| | `LLM_MAX_RETRY_WAIT` | `10` | Max seconds between retries (caps backoff) |
| **Data Paths** | `GOLD_DIR` | `data/gold/patient_cases` | Gold-layer patient case directory |
| | `MAS_RESULTS_DIR` | `data/gold/mas_results` | Agent pipeline results directory |
| | `GUIDELINES_DIR` | `config/guidelines` | NICE guidelines source directory |
| | `DUCKDB_PATH` | `data/clinical.duckdb` | DuckDB database path |
| **Observability** | `LANGSMITH_API_KEY` | (optional) | Enables LangSmith tracing when set |
| | `LANGSMITH_TRACING` | `true` | Auto-set when API key present |
| | `LANGSMITH_PROJECT` | `cmads-clinical-pipeline` | LangSmith project name |
| | `LANGSMITH_ENDPOINT` | `https://eu.api.smith.langchain.com` | LangSmith API endpoint |

---

**9. Dependencies**

From `requirements.txt` (single file for entire project):

```
# -- Core Agent Pipeline --
langchain>=1.2.0,<2.0.0
langchain-core>=1.2.0,<2.0.0
langchain-groq>=1.1.0,<2.0.0
langchain-ollama>=1.0.0,<2.0.0
langgraph>=1.1.0,<2.0.0
langgraph-checkpoint>=4.0.0,<5.0.0
pydantic>=2.0.0,<3.0.0
pyyaml>=6.0,<7.0

# -- LLM Providers --
groq>=0.37.0,<1.0.0

# -- Vector Database (Treatment Planning) --
qdrant-client>=1.12.0,<2.0.0
sentence-transformers>=3.0.0,<4.0.0
numpy<2

# -- Data Pipeline --
duckdb>=1.0.0,<2.0.0
pandas>=2.0.0,<3.0.0
pyarrow>=15.0.0,<18.0.0

# -- Portal (Streamlit) --
streamlit>=1.40.0,<2.0.0
plotly>=6.0.0,<7.0.0

# -- Environment & HTTP --
python-dotenv>=1.0.0,<2.0.0
requests>=2.31.0,<3.0.0

# -- Logging & Observability --
structlog>=24.0.0,<25.0.0
langsmith>=0.1.0,<1.0.0

# -- Testing --
pytest>=8.0.0,<9.0.0
pytest-asyncio>=0.24.0,<1.0.0

# -- Code Quality --
ruff>=0.8.0,<1.0.0
```

**9.1 Installation**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
```

Additional provider packages (install only if switching from Groq):
```bash
pip install langchain-openai       # for openai provider
pip install langchain-anthropic    # for anthropic provider
pip install langchain-google-genai # for gemini provider
```

---

*--- End of Document ---*

Final Technology Stack v2.0 • March 30, 2026 • CMADS Agent Pipeline

**Final Technology Stack**

────────────────────────────────────────

**Agent Pipeline • Evaluation • Portal**

*LangChain + LangGraph + GPT-o3 120B (Ollama) + Streamlit*

  --------------------------- --------------------------------------------------------------------------
  **Document Title**          Final Technology Stack --- Agent Pipeline

  **Project**                 Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows

  **Version**                 1.0

  **Date**                    March 22, 2026

  **Author**                  Islam

  **Type**                    Bachelor Thesis

  **Companion To**            SRD v1.0 + Design Document v1.0 + Data Engineering Spec v3.0
  --------------------------- --------------------------------------------------------------------------

*This document specifies the definitive technology selections for the multi-agent pipeline, evaluation framework, and clinician portal. The data pipeline stack is documented separately in the Data Engineering Specification v3.0.*

**Table of Contents**

**1. Technology Stack Overview**

This section presents the complete technology stack for the multi-agent pipeline subsystem of CMADS. The data pipeline stack (Synthea, PyArrow, dbt-core, DuckDB, Prefect) is fully documented in the Data Engineering Specification v3.0 and is not repeated here. This document covers the three remaining areas: agent pipeline execution, evaluation framework, and clinician portal. All patient data in CMADS originates from Synthea, an open-source patient simulator that uses rule-based state transition machines (Generic Module Framework) informed by CDC/NIH clinical statistics to generate realistic synthetic patient lifespans. Synthea is the single source of truth --- every downstream data layer and every agent input traces back to Synthea's output.

![](media/2be15837836089d1e11da3761953d4c1851f7993.png){width="6.458333333333333in" height="3.9895833333333335in"}

*Figure 1.1 --- Agent Pipeline Technology Stack Architecture*

**1.1 Stack Summary**

  ----------------------- ------------------------- ---------------- -------------------------------------------------------------------------------
  **Layer**               **Technology**            **Version**      **Purpose**

  **Orchestration**       LangGraph                 0.2.x            DAG-based multi-agent orchestration with state channels

  **Agent Runtime**       LangChain                 0.3.x            Prompt templates, LCEL chains, output parsers, callbacks

  **LLM (Agents)**        GPT-o3 120B               Ollama local     Primary reasoning model for all 7 agents, served locally via Ollama

  **LLM Serving**         Ollama                    latest           Local LLM server exposing OpenAI-compatible REST API at localhost:11434

  **LLM SDK**             langchain-ollama          latest           LangChain ChatOllama adapter --- native Ollama integration at localhost:11434

  **Shared Memory**       LangGraph State           built-in         TypedDict state channels with namespace isolation

  **Checkpointing**       LangGraph MemorySaver     built-in         Per-stage state serialisation to JSON

  **Output Schemas**      Pydantic v2               2.x              Agent input/output validation, structured LLM output

  **Config Format**       YAML + python-dotenv      ---              Pipeline, agent, and model configuration files

  **Schema Validation**   JSON Schema + Pydantic    ---              Inter-agent contract validation

  **Evaluation**          pandas + scikit-learn     latest           Metric computation and A/B comparison

  **Visualisation**       matplotlib + Plotly       latest           Evaluation charts, agent trace visualisation

  **Logging**             structlog                 latest           Structured JSON-lines logging with context binding

  **Portal**              Streamlit                 1.x              Clinician review UI, case viewer, agent output display

  **Portal Data**         DuckDB (read-only)        latest           Direct SQL queries over Silver/Gold for portal

  **Graph Rendering**     Graphviz + pyvis          latest           Agent execution graph and dependency visualisation

  **Testing**             pytest + pytest-asyncio   latest           Unit tests, integration tests, async agent tests

  **Code Quality**        ruff                      latest           Linting and formatting (replaces black + flake8)

  **Package Mgmt**        uv (or pip)               latest           Fast dependency resolution and virtual environments

  **Python**              Python                    3.11+            Runtime; required for LangGraph async support
  ----------------------- ------------------------- ---------------- -------------------------------------------------------------------------------

**1.2 Relationship to Data Pipeline Stack**

The data pipeline (documented in the Data Engineering Specification v3.0) ingests Synthea-generated patient data and produces Gold-layer JSON files (ehr_case.json, lab_case.json) that are the sole input to the agent pipeline. The two stacks share exactly one integration point:

-   **DuckDB:** The data pipeline writes Synthea-derived structured data to clinical.duckdb. The portal reads from it directly. The agent pipeline does not touch DuckDB --- it consumes Gold JSON files on disk.

**2. LangGraph Orchestration**

LangGraph is the orchestration backbone. It replaces the custom Python Orchestrator class referenced in earlier design iterations with a production-grade, graph-based execution engine that natively supports stateful multi-agent workflows.

**2.1 Why LangGraph**

  --------------------------------- ----------------------------------------- -----------------------------------------------------
  **Requirement**                   **LangGraph Feature**                     **Alternative (and why rejected)**

  **Declarative DAG (NF-033)**      StateGraph with add_node / add_edge       Custom Python DAG parser --- reinvents the wheel

  **Parallel execution (NF-023)**   Fan-out/fan-in with parallel branches     asyncio.gather --- manual, no state management

  **Shared memory (IF-001--005)**   State channels (TypedDict)                Redis / custom dict --- no native graph integration

  **Checkpointing (NF-043)**        Built-in MemorySaver + custom saver       Manual JSON snapshots --- error-prone

  **Conditional routing**           Conditional edges with router functions   if/else in Python --- not declarative

  **Error handling (NF-040)**       Retry policies + fallback nodes           try/except wrappers --- scattered logic

  **Visualisation**                 graph.get_graph().draw_mermaid_png()      Manual Graphviz --- extra effort
  --------------------------------- ----------------------------------------- -----------------------------------------------------

**2.2 StateGraph Definition**

The entire agent pipeline is defined as a single LangGraph StateGraph. The state object implements the shared memory design from the SDD, with each namespace as a typed channel.

> from langgraph.graph import StateGraph, END
>
> from typing import TypedDict, Annotated
>
> from operator import add
>
> class PipelineState(TypedDict):
>
> \# Namespace: patient_context (set once by orchestrator)
>
> patient_context: dict
>
> \# Namespace: agent_outputs (append-only, keyed by agent_id)
>
> agent_outputs: Annotated\[dict, merge_agent_outputs\]
>
> \# Namespace: conflicts (append-only list)
>
> conflicts: Annotated\[list, add\]
>
> \# Namespace: execution_trace (append-only list)
>
> execution_trace: Annotated\[list, add\]
>
> \# Namespace: scratchpad (per-agent, ephemeral)
>
> scratchpad: dict
>
> \# Build the graph
>
> graph = StateGraph(PipelineState)
>
> \# Stage 1 (parallel)
>
> graph.add_node(\"ehr_analyst\", ehr_analyst_node)
>
> graph.add_node(\"lab_interpreter\", lab_interpreter_node)
>
> \# Stage 2
>
> graph.add_node(\"diagnostic\", diagnostic_node)
>
> \# Stage 3 (parallel)
>
> graph.add_node(\"treatment\", treatment_node)
>
> graph.add_node(\"radiology\", radiology_node)
>
> \# Stage 4
>
> graph.add_node(\"reviewer\", reviewer_node)
>
> \# Stage 5
>
> graph.add_node(\"synthesis\", synthesis_node)
>
> \# Conflict detection nodes (after stages 2 and 4)
>
> graph.add_node(\"conflict_check_1\", conflict_detector)
>
> graph.add_node(\"conflict_check_2\", conflict_detector)
>
> \# Edges (define the DAG)
>
> graph.set_entry_point(\"ehr_analyst\") \# fan-out
>
> graph.add_edge(\"ehr_analyst\", \"diagnostic\")
>
> graph.add_edge(\"lab_interpreter\", \"diagnostic\")
>
> graph.add_edge(\"diagnostic\", \"conflict_check_1\")
>
> graph.add_edge(\"conflict_check_1\", \"treatment\")
>
> graph.add_edge(\"conflict_check_1\", \"radiology\")
>
> graph.add_edge(\"treatment\", \"reviewer\")
>
> graph.add_edge(\"radiology\", \"reviewer\")
>
> graph.add_edge(\"reviewer\", \"conflict_check_2\")
>
> graph.add_edge(\"conflict_check_2\", \"synthesis\")
>
> graph.add_edge(\"synthesis\", END)
>
> \# Compile with checkpointing
>
> from langgraph.checkpoint.memory import MemorySaver
>
> app = graph.compile(checkpointer=MemorySaver())

**2.3 Parallel Fan-Out / Fan-In**

LangGraph natively supports parallel execution when multiple edges lead from the same source node. In the graph above, the entry point fans out to both ehr_analyst and lab_interpreter. Both execute concurrently, and the diagnostic node only fires once both have written their outputs to the state.

Similarly, Stage 3 fans out from conflict_check_1 to both treatment and radiology, with reviewer as the fan-in point.

This eliminates the need for manual asyncio.gather() or ThreadPoolExecutor code --- LangGraph handles it internally.

**2.4 Checkpointing and Resume**

LangGraph's built-in MemorySaver stores the full PipelineState after each node completes. For persistent checkpoints (surviving process restarts), a custom FileCheckpointer writes state snapshots to disk:

> \# Custom file-based checkpointer
>
> class FileCheckpointer(BaseCheckpointSaver):
>
> def \_\_init\_\_(self, directory: str):
>
> self.dir = Path(directory)
>
> def put(self, config, checkpoint, metadata):
>
> path = self.dir / f\"{config\[\"thread_id\"\]}\_{metadata\[\"step\"\]}.json\"
>
> path.write_text(json.dumps(checkpoint, default=str))
>
> def get(self, config):
>
> \# Load latest checkpoint for thread_id
>
> \...

This implements NF-043 (checkpoint/resume) and NF-004 (post-hoc analysis). If the pipeline crashes at Stage 4, the developer reloads the Stage 3 checkpoint and resumes without re-incurring LLM costs for Stages 1--3.

**3. LangChain Agent Runtime**

Each agent node in the LangGraph graph is implemented as a LangChain chain using the LangChain Expression Language (LCEL). This section specifies how agents are constructed, how they interact with GPT-o3 120B served locally via Ollama, and how outputs are validated.

**3.1 Agent Chain Architecture**

Every agent follows the same LCEL pattern:

> from langchain_ollama import ChatOllama
>
> from langchain_core.prompts import ChatPromptTemplate
>
> from langchain_core.output_parsers import PydanticOutputParser
>
> \# 1. Model (Ollama local --- no API keys, no network required)
>
> llm = ChatOllama(
>
> model=\"gpt-o3-120b\",
>
> base_url=\"http://localhost:11434\",
>
> temperature=0.2,
>
> num_ctx=16384, \# context window in tokens
>
> timeout=120, \# local inference needs longer timeout
>
> )
>
> \# 2. Output parser (Pydantic schema)
>
> parser = PydanticOutputParser(pydantic_object=DiagnosticOutput)
>
> \# 3. Prompt template
>
> prompt = ChatPromptTemplate.from_messages(\[
>
> (\"system\", SYSTEM_PROMPT),
>
> (\"human\", \"{patient_context}\\n\\n{upstream_outputs}\\n\\n{format_instructions}\"),
>
> \])
>
> \# 4. LCEL chain: prompt \| model \| parser
>
> chain = prompt \| llm.with_structured_output(DiagnosticOutput)
>
> \# 5. Wrapped as a LangGraph node function
>
> def diagnostic_node(state: PipelineState) -\> dict:
>
> ehr_out = state\[\"agent_outputs\"\].get(\"ehr_analyst\", {})
>
> lab_out = state\[\"agent_outputs\"\].get(\"lab_interpreter\", {})
>
> result = chain.invoke({
>
> \"patient_context\": state\[\"patient_context\"\],
>
> \"upstream_outputs\": json.dumps({\"ehr\": ehr_out, \"lab\": lab_out}),
>
> \"format_instructions\": parser.get_format_instructions(),
>
> })
>
> return {\"agent_outputs\": {\"diagnostic\": result.model_dump()}}

**3.2 GPT-o3 120B via Ollama --- Configuration**

GPT-o3 120B is used as the reasoning backbone for all seven clinical agents. It runs locally on the development machine via Ollama, which serves the model at localhost:11434. LangChain's ChatOllama class provides native integration. No external API keys, cloud accounts, or network connectivity are required for inference.

  ------------------------- ---------------------------------------------------------------------------------------------------------
  **Model Identifier**      gpt-o3-120b (pulled via: ollama pull gpt-o3-120b)

  **Serving**               Ollama local server at http://localhost:11434

  **LangChain Class**       langchain_ollama.ChatOllama

  **Context Window**        Configurable via num_ctx parameter (default: 16384 tokens, adjustable based on available VRAM)

  **Structured Output**     .with_structured_output(PydanticSchema) for JSON conformance

  **Default Temperature**   0.2 for clinical reasoning agents; 0.0 for evaluation runs

  **Timeout**               120 seconds per agent invocation (local inference is slower than cloud APIs)

  **Retry Policy**          3 retries with exponential backoff (custom wrapper)

  **Fallback**              If GPT-o3 fails after retries (e.g., OOM, Ollama crash), agent returns status=error; pipeline continues

  **Cost**                  Zero marginal cost --- all inference runs on local GPU. No API billing.

  **Hardware**              Local GPU with sufficient VRAM for the 120B parameter model (quantised variants reduce requirement)
  ------------------------- ---------------------------------------------------------------------------------------------------------

**3.3 Pydantic Output Schemas**

Every agent's output is defined as a Pydantic v2 model. This serves three purposes: it constrains the LLM to produce valid JSON (via .with_structured_output()), it validates the output at parse time, and it generates JSON Schema for the inter-agent contracts specified in SRD Section 4.2.

> from pydantic import BaseModel, Field
>
> class Diagnosis(BaseModel):
>
> name: str = Field(description=\"Diagnosis name\")
>
> icd10: str = Field(description=\"ICD-10 code\")
>
> snomed: str = Field(description=\"SNOMED-CT code\")
>
> supporting_evidence: list\[str\]
>
> confidence: str = Field(pattern=\"\^(high\|moderate\|low)\$\")
>
> reasoning: str
>
> class DiagnosticOutput(BaseModel):
>
> differential: list\[Diagnosis\] = Field(min_length=3)
>
> unresolved_findings: list\[str\]
>
> primary_diagnosis: str = Field(description=\"Top-ranked diagnosis name\")

**3.4 Prompt Management**

Prompts are stored as versioned YAML files in the prompts/ directory. Each YAML file contains the system message, human message template, and optional few-shot examples. At runtime, LangChain's ChatPromptTemplate loads the YAML and injects variables.

The prompt directory structure mirrors the Design Document's specification:

> prompts/
>
> ehr_analyst/
>
> v1.0.yaml \# initial prompt
>
> v1.1.yaml \# refined after first evaluation
>
> lab_interpreter/
>
> v1.0.yaml
>
> diagnostic_reasoning/
>
> v1.0.yaml
>
> v1.1.yaml
>
> \... \# one directory per agent

The active prompt version for each agent is set in the agent's YAML config file (e.g., agents/diagnostic_reasoning.yaml: prompt_version: 1.1). This implements MA-083 (versioned prompts) and NF-001 (config in version control).

**3.5 LangChain Callbacks for Observability**

LangChain's callback system is used to implement NF-010 (LLM call logging) and NF-013 (inference tracking) without modifying agent code. Since inference runs locally via Ollama, there is no API cost --- but token counts and latency are still tracked for performance analysis:

> from langchain_core.callbacks import BaseCallbackHandler
>
> import structlog
>
> class AgentTracingCallback(BaseCallbackHandler):
>
> def on_llm_start(self, serialized, prompts, \*\*kwargs):
>
> structlog.get_logger().info(\'llm_call_start\',
>
> agent_id=self.agent_id, model=serialized.get(\'id\'))
>
> def on_llm_end(self, response, \*\*kwargs):
>
> usage = response.llm_output.get(\'token_usage\', {}) if response.llm_output else {}
>
> structlog.get_logger().info(\'llm_call_end\',
>
> agent_id=self.agent_id,
>
> prompt_tokens=usage.get(\'prompt_tokens\'),
>
> completion_tokens=usage.get(\'completion_tokens\'),
>
> duration_ms=self.\_elapsed_ms()) \# local inference: track time, not cost

**4. Evaluation Framework Stack**

The evaluation framework compares the multi-agent pipeline's clinical decision reports against ground truth labels. It uses standard Python data science tooling.

**4.1 Tool Responsibility Map**

  --------------------------------- --------------------------- -------------------------------------------------------------------------------------------------
  **Function**                      **Tool**                    **Details**

  **Metric computation**            pandas + scikit-learn       Diagnostic accuracy, differential recall, treatment relevance, F1, precision, recall per metric

  **Statistical comparison**        scipy.stats                 Wilcoxon signed-rank test for A/B pipeline config comparison; confidence intervals

  **LLM-as-Judge**                  GPT-o3 120B via LangChain   Automated qualitative scoring of clinical reasoning quality (rubric-based)

  **Cost analysis**                 pandas                      Per-case and aggregate token usage, cost per pipeline configuration

  **Visualisation (static)**        matplotlib + seaborn        Evaluation report charts: accuracy distributions, confusion matrices, cost breakdowns

  **Visualisation (interactive)**   Plotly                      Interactive evaluation dashboards embedded in Streamlit portal

  **Evaluation data store**         DuckDB                      Evaluation results stored as tables in clinical.duckdb for SQL querying

  **Report generation**             Jinja2 + Markdown           Per-run evaluation report in Markdown, convertible to PDF via pandoc

  **Experiment tracking**           JSON manifests              Run manifests with config hashes, model IDs, timestamps, metric summaries
  --------------------------------- --------------------------- -------------------------------------------------------------------------------------------------

**4.2 Evaluation Pipeline**

The evaluation runs as a post-pipeline step, invoked via:

> \# Run evaluation on the last pipeline run
>
> python -m evaluation.run_evaluation \--mode full \--n-cases 100
>
> \# A/B comparison between two configs
>
> python -m evaluation.compare \\
>
> \--run-a outputs/run_20260322_gpto3/ \\
>
> \--run-b outputs/run_20260322_claude/ \\
>
> \--output evaluation/comparison_report.md

**4.3 Metrics Implementation**

All metrics from SRD MA-091 are implemented:

-   **Diagnostic accuracy:** Exact match + SNOMED hierarchy distance (via OHDSI concept_ancestor table). Scored as 1.0 (exact), 0.5 (parent/child), 0.0 (unrelated).

-   **Differential recall:** \|ground_truth_conditions ∩ differential_list\| / \|ground_truth_conditions\|. Computed per-case.

-   **Treatment relevance:** Binary per-medication: is the proposed drug in the ground truth formulary for the condition? Aggregated as precision@k.

-   **Critical finding coverage:** For all severity ≥3 flags in the case, is each mentioned in the final report? Binary per-flag, aggregated as recall.

-   **LLM-as-Judge:** GPT-o3 scores the clinical reasoning on a 1--5 rubric across: evidence use, logical coherence, completeness, and clinical safety. Three independent scores are averaged.

**5. Clinician Portal Stack**

The portal is a Streamlit web application for reviewing agent pipeline outputs. It reads directly from DuckDB (for patient data) and from the outputs/ directory (for agent results).

**5.1 Portal Components**

  ------------------------------- ---------------------------------- --------------------------------------------------------------------------
  **Component**                   **Tool**                           **Description**

  **Web framework**               Streamlit 1.x                      Full-stack Python web app. No frontend code needed. Auto-reload on save.

  **Patient browser**             DuckDB SQL + st.dataframe          SQL queries over Silver tables displayed as interactive data frames

  **Case viewer**                 Streamlit tabs + st.json           Tabbed view of ehr_case.json and lab_case.json per patient

  **Agent output display**        st.expander + st.markdown          Expandable sections showing each agent's output with Markdown rendering

  **Clinical Decision Report**    st.markdown + st.download_button   Full rendered report with download option (JSON + Markdown)

  **Execution trace**             Plotly timeline                    Interactive Gantt chart of agent execution: timing, status, token usage

  **Agent graph visualisation**   Graphviz via st.graphviz_chart     Visual rendering of the LangGraph execution DAG with status overlays

  **Evaluation dashboard**        Plotly charts + st.metric          Aggregate metrics, per-case drill-down, A/B comparison side-by-side

  **DQ dashboard**                Great Expectations HTML            Embedded data quality report from the data pipeline
  ------------------------------- ---------------------------------- --------------------------------------------------------------------------

**5.2 Portal Architecture**

The portal is a single Streamlit application with a sidebar navigation:

> portal/
>
> app.py \# Main entry: st.set_page_config + sidebar nav
>
> pages/
>
> 01_patient_browser.py \# DuckDB queries over Silver tables
>
> 02_case_viewer.py \# Gold JSON viewer per patient
>
> 03_agent_outputs.py \# Per-agent expandable output display
>
> 04_decision_report.py \# Full clinical decision report
>
> 05_execution_trace.py \# Plotly timeline of agent execution
>
> 06_evaluation.py \# Metrics dashboard + A/B comparison
>
> 07_dq_report.py \# Embedded Great Expectations report
>
> \# Launch: streamlit run portal/app.py
>
> \# Available at: http://localhost:8501

**6. Dependency Manifest**

The complete Python dependency list for the agent pipeline, evaluation, and portal. Data pipeline dependencies (dbt-core, prefect, pyarrow, great-expectations) are managed in a separate requirements file as documented in the Data Engineering Spec v3.0.

> \# requirements-agents.txt
>
> \# ── Orchestration + Agent Framework ──
>
> langchain\>=0.3.0
>
> langchain-ollama\>=0.2.0
>
> \# ── LLM Serving ──
>
> \# Ollama installed separately: https://ollama.com/download
>
> \# Then: ollama pull gpt-o3-120b
>
> langgraph\>=0.2.0
>
> \# ── LLM SDKs ──
>
> \# ── Schema Validation ──
>
> pydantic\>=2.5.0
>
> jsonschema\>=4.20.0
>
> \# ── Configuration ──
>
> pyyaml\>=6.0
>
> python-dotenv\>=1.0.0
>
> \# ── Logging ──
>
> structlog\>=24.0.0
>
> \# ── Evaluation ──
>
> pandas\>=2.2.0
>
> scikit-learn\>=1.4.0
>
> scipy\>=1.12.0
>
> matplotlib\>=3.8.0
>
> seaborn\>=0.13.0
>
> plotly\>=5.18.0
>
> \# ── Portal ──
>
> streamlit\>=1.30.0
>
> duckdb\>=1.0.0
>
> graphviz\>=0.20.0
>
> pyvis\>=0.3.0
>
> \# ── Testing ──
>
> pytest\>=8.0.0
>
> pytest-asyncio\>=0.23.0
>
> \# ── Code Quality ──
>
> ruff\>=0.3.0

**6.1 Installation**

> \# Using uv (recommended for speed)
>
> uv venv && source .venv/bin/activate
>
> uv pip install -r requirements-agents.txt
>
> \# Or using pip
>
> python -m venv .venv && source .venv/bin/activate
>
> pip install -r requirements-agents.txt
>
> \# Environment variables (.env file)
>
> OLLAMA_HOST=http://localhost:11434 \# Ollama server URL
>
> OLLAMA_MODEL=gpt-o3-120b \# Default model for all agents
>
> LOG_LEVEL=INFO \# DEBUG for full prompt logging
>
> CHECKPOINT_DIR=./checkpoints \# LangGraph checkpoint directory

*--- End of Document ---*

Final Technology Stack v1.0 • March 22, 2026 • CMADS Agent Pipeline

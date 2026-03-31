**System Design Document**

────────────────────────────────────────

**Multi-Agent Systems for AI Clinical Decisioning**

**via Automation Workflows**

*The How --- Architecture, Patterns, and Implementation Design*

  ----------------------- --------------------------------------------------------------------------
  **Document Title**      System Design Document

  **Project**             Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows

  **Version**             1.0

  **Date**                March 22, 2026

  **Author**              Islam

  **Type**                Bachelor Thesis

  **Companion To**        System Requirements Document (SRD) v1.0
  ----------------------- --------------------------------------------------------------------------

*This document specifies how the system defined in the SRD shall be realised. It is the architectural and implementation companion to the requirements baseline.*

**Table of Contents**

**1. Introduction**

**1.1 Purpose and Scope**

This System Design Document (SDD) specifies how the Clinical Multi-Agent Decisioning System (CMADS) shall be architecturally structured and implemented. Where the companion SRD defines what the system must do, this document defines the patterns, components, data structures, communication protocols, and implementation decisions that realise those requirements.

The primary focus is on the multi-agent pipeline architecture: the orchestration pattern, the shared memory mechanism, the internal agent structure, and the inter-agent communication design. The data pipeline design is covered at a summary level since its architecture follows standard medallion (Bronze/Silver/Gold) patterns.

**1.2 Design Philosophy**

The architecture is guided by four principles, ordered by priority:

-   **Shared Memory over Message Passing:** Agents communicate through a structured, namespace-isolated shared memory store rather than direct point-to-point messages. This decouples agents from each other, simplifies the Orchestrator's routing logic, and makes the full system state inspectable at any point during execution. Each agent reads what it needs and writes what it produces --- the Orchestrator never shuttles payloads between agents.

-   **Configuration over Code:** The execution graph, agent prompts, model assignments, and pipeline variants are all declared in configuration files (YAML). Adding, removing, or reconfiguring agents requires zero code changes. This directly supports the thesis's experimental methodology: different pipeline topologies are compared by swapping config files, not by rewriting orchestration logic.

-   **Graceful Degradation:** Every agent is treated as potentially fallible. Timeouts, malformed LLM responses, and Ollama server errors are expected conditions, not exceptions. The pipeline continues with partial results, logging what was lost, so the Diagnostic Refiner and downstream agents always have something to work with.

-   **Observability by Default:** Every LLM call, memory read/write, schema validation, and state transition is logged with structured metadata. The execution trace is a first-class output --- as important as the clinical decision itself for thesis analysis.

**1.3 Relationship to SRD**

This document implements all 96 requirements defined in the SRD v1.0. The following mapping applies:

-   SRD Section 3.1 (Multi-Agent Pipeline) → SDD Sections 2--6 (architecture, orchestration, memory, agents)

-   SRD Section 3.2 (Data Pipeline) → SDD Section 7 (data pipeline design)

-   SRD Section 4 (Interfaces) → SDD Section 4 (shared memory contracts) + Section 5 (agent internals)

-   SRD Section 5 (Non-Functional) → SDD Sections 6 and 8 (error handling, config, logging)

**2. High-Level Architecture**

**2.1 System Overview**

CMADS is decomposed into two subsystems connected by a well-defined data interface (the Gold-layer JSON files). The data pipeline subsystem ingests Synthea-generated synthetic patient data --- the single source of truth for all patient data in the system --- and transforms it through Bronze, Silver, Silver+, and Gold layers into structured case files. Synthea is an open-source patient simulator that uses rule-based state transition machines and Monte Carlo simulation (informed by CDC/NIH clinical statistics) to produce realistic patient lifespans. The multi-agent pipeline subsystem consumes the resulting case files through a six-stage orchestrated workflow.

The following diagram shows the complete system architecture, including the data pipeline layers, the staged agent pipeline, the shared memory store, and the evaluation engine.

![](media/adb7c082faea6dd7a2f2d3a7e84a59d8de10bd23.png){width="6.458333333333333in" height="3.9895833333333335in"}

*Figure 2.1 --- CMADS High-Level System Architecture*

**2.2 Architectural Pattern: Orchestrator with Shared Memory**

The multi-agent pipeline uses a centralised Orchestrator pattern augmented with a shared memory store. This is a deliberate departure from the two most common multi-agent patterns:

-   **Pure message-passing (rejected):** In frameworks like AutoGen, agents pass messages directly to each other. This creates tight coupling: every agent must know who to send to, the Orchestrator must route every payload, and inspecting intermediate state requires intercepting messages. For a thesis prototype where we need full observability and easy reconfiguration, this is too rigid.

-   **Pure blackboard/shared-state (modified):** A classic blackboard architecture lets any agent read and write freely. While we adopt the shared-state concept, we add namespace isolation and access policies to prevent agents from overwriting each other's outputs. The Orchestrator retains control over execution sequencing.

The chosen hybrid combines the best of both:

-   The Orchestrator controls when each agent runs (sequencing) and detects conflicts (diff engine).

-   The Shared Memory Store holds all patient context, agent outputs, conflicts, scratchpad notes, and execution traces in namespaced slots.

-   Agents read from memory (pulling what they need) and write to memory (pushing their results). They never communicate directly with each other.

**2.3 Component Inventory**

The following table lists every major component in the system, its type, and the SRD requirements it implements.

  -------------------------------- ------------ -------------------------- ---------------------------
  **Component**                    **Type**     **SRD Reqs**               **Design Section**

  **Orchestrator**                 Controller   MA-001--007                §3.1

  **Shared Memory Store**          Data Store   IF-001--005, MA-005        §4

  **EHR Analyst Agent**            AI Agent     MA-010--013                §5.2

  **Lab Interpreter Agent**        AI Agent     MA-020--024                §5.3

  **Diagnostic Reasoning Agent**   AI Agent     MA-030--034                §5.4

  **Treatment Planning Agent**     AI Agent     MA-040--044                §5.5

  **Clinical Reviewer Agent**      AI Agent     MA-050--054                §5.6

  **Diagnostic Refiner Agent**     AI Agent     MA-060--063                §5.7

  **LLM Evaluator**                Pipeline     MA-070--074                §5.8

  **LLM Adapter**                  Adapter      IF-020--024                §5.1

  **Agent Config Registry**        Config       NF-030--034, MA-083--084   §6

  **Evaluation Engine**            Evaluator    MA-090--094                §8

  **Data Pipeline**                ETL          DP-001--022                §7
  -------------------------------- ------------ -------------------------- ---------------------------

**3. Orchestrator Design**

**3.1 Responsibilities**

The Orchestrator is the only component that knows the full execution graph. It has five responsibilities executed in strict order for each patient case:

-   **1. Initialise:** Load the Gold-layer case files (ehr_case.json, lab_case.json), hydrate the patient_context namespace in shared memory, and initialise the execution trace.

-   **2. Dispatch:** Walk the execution graph stage by stage. For each stage, invoke the assigned agent(s). Agents at the same stage have no mutual dependency and may be dispatched in parallel.

-   **3. Conflict Detection:** After each stage completes, run a lightweight diff engine over the agent_outputs namespace to detect contradictory claims (e.g., two agents proposing incompatible primary diagnoses). Write findings to the conflicts namespace.

-   **4. Trace Logging:** After each agent returns, append to the execution_trace namespace: agent_id, status, duration, token usage, and output hash.

-   **5. Finalise:** After the Treatment Planning Agent completes (or after the LLM Evaluator if treatment is skipped), extract the final outputs from shared memory, seal the execution trace, and write output files.

**3.2 Execution Graph**

The execution graph is declared in a YAML configuration file. The Orchestrator parses this at startup and builds an internal directed acyclic graph (DAG). The default graph has six stages:

> \# pipeline_config.yaml
>
> pipeline: full_clinical
>
> stages:
>
> \- stage: 1
>
> agents: \[ehr_analyst, lab_interpreter\]
>
> parallel: true
>
> \- stage: 2
>
> agents: \[diagnostic_reasoning\]
>
> depends_on: \[ehr_analyst, lab_interpreter\]
>
> adaptive: true \# uses self-consistency if confidence < threshold
>
> \- stage: 3
>
> agents: \[clinical_reviewer\]
>
> depends_on: \[diagnostic_reasoning\]
>
> \- stage: 4
>
> agents: \[final_diagnosis\]
>
> depends_on: \[diagnostic_reasoning, clinical_reviewer\]
>
> \- stage: 5
>
> agents: \[evaluation\]
>
> depends_on: \[final_diagnosis\]
>
> \- stage: 6
>
> agents: \[treatment_planning\]
>
> depends_on: \[evaluation\]
>
> condition: evaluation.match_type == "DIRECT"

Alternative pipeline configurations (e.g., diagnostic_only) are defined in separate YAML files and selected at runtime via a command-line argument or environment variable, fulfilling NF-034.

**3.3 Conflict Detection Engine**

After stages 2 and 4, the Orchestrator runs a conflict detection pass. The engine operates by comparing structured fields across agent outputs:

-   **Diagnosis conflicts:** If the Diagnostic Reasoning Agent's primary diagnosis differs from conditions flagged by the EHR Analyst or Lab Interpreter, a conflict record is created.

-   **Treatment--condition conflicts:** If the Treatment Planning Agent proposes a medication that the Clinical Reviewer flags as contraindicated, a conflict record is created.

-   **Confidence disagreements:** If the Reviewer's confidence score is more than 30 points below the Diagnostic Agent's confidence, this is flagged as a significant disagreement.

Conflict records are written to the conflicts namespace in shared memory and are a required input for the Diagnostic Refiner Agent. This implements SRD requirements MA-005 and MA-072.

**3.4 Timeout and Failure Handling**

Each agent invocation has a configurable timeout (default: 60 seconds, per NF-022). The Orchestrator handles failures as follows:

-   **Timeout:** The agent is terminated. Status is set to 'error' with error_code TIMEOUT. The Orchestrator continues to the next stage.

-   **Ollama server error:** The LLM Adapter retries (up to 3 times with exponential backoff). If all retries fail, the agent returns status 'error'.

-   **Schema validation failure:** The Output Parser extracts whatever valid fields it can. Status is set to 'partial'. Valid fields are written to shared memory; invalid fields are logged.

In all failure cases, the pipeline continues. Downstream agents are informed of which agents succeeded, failed, or returned partial results, and adjust their outputs accordingly. This implements NF-040 and NF-042.

**4. Shared Memory Architecture**

**4.1 Design Rationale**

Traditional multi-agent systems pass data between agents via the orchestrator (the Orchestrator-as-postman pattern). This creates a bottleneck: the Orchestrator must understand every agent's output format to route it correctly, and adding a new agent requires modifying routing logic.

CMADS instead introduces a shared memory store that acts as a structured blackboard with namespace isolation. The key advantages are:

-   **Decoupled agents:** Each agent reads from and writes to well-known namespaces. Agents are unaware of each other's existence --- they only know their own input/output namespaces.

-   **Full state visibility:** At any point during execution, the shared memory contains the complete system state: patient context, all agent outputs produced so far, conflicts detected, and the execution trace. This is invaluable for debugging and thesis analysis.

-   **Easy extensibility:** Adding a new agent means defining its read/write namespaces in config. No other agent is modified. No Orchestrator routing code changes.

-   **Built-in reproducibility:** The shared memory snapshot after each stage is a complete record of the pipeline state, enabling checkpoint/resume (NF-043) and post-hoc analysis (NF-004).

**4.2 Namespace Design**

The shared memory is organised into five namespaces, each with defined access policies. The following diagram details the namespace structure and agent access patterns.

![](media/db3a380953d6dc1f6aca21dda9794b8024a8b382.png){width="6.458333333333333in" height="3.2291666666666665in"}

*Figure 4.1 --- Shared Memory Namespace Architecture*

  --------------------- ----------------------------------------------------------------------------------------------------------------------- ---------------------------- -------------------
  **Namespace**         **Contents**                                                                                                            **Write Access**             **Read Access**

  **patient_context**   Gold-layer data: demographics, conditions, medications, allergies, risk scores, comorbidity matrix, encounter summary   Orchestrator                 All agents

  **agent_outputs**     Per-agent output slots: agent_outputs.{agent_id} → structured JSON payload                                              Each agent (own slot)        Downstream agents

  **conflicts**         Conflict records: contradictory diagnoses, treatment--condition flags, confidence disagreements                         Orchestrator (diff engine)   Diagnostic Refiner

  **scratchpad**        Per-agent ephemeral working notes: intermediate reasoning, chain-of-thought traces                                      Each agent (own slot)        Same agent only

  **execution_trace**   Per-agent invocation logs: timestamps, status, token usage, output hash, error details                                  Orchestrator                 Evaluation Engine
  --------------------- ----------------------------------------------------------------------------------------------------------------------- ---------------------------- -------------------

**4.3 Access Control Policy**

The access model follows a write-own, read-downstream pattern:

-   **Write isolation:** An agent can only write to its own slot within agent_outputs (e.g., the EHR Analyst writes to agent_outputs.ehr_analyst). No agent can overwrite another agent's output. This prevents race conditions and ensures auditability.

-   **Read-downstream:** An agent can read any namespace and any agent_outputs slot for agents that have already completed (i.e., upstream agents). The Orchestrator enforces this by only dispatching an agent after its dependencies have written their outputs.

-   **Orchestrator is admin:** The Orchestrator has full read/write access to all namespaces. It is the only component that writes to patient_context, conflicts, and execution_trace.

-   **Scratchpad is private:** Each agent's scratchpad slot is readable only by that agent. It is used for chain-of-thought traces or intermediate notes that should not influence other agents.

**4.4 Implementation Strategy**

For the thesis prototype (single-user, single-patient-at-a-time), the shared memory store is implemented as an in-memory Python dictionary with namespace keys. No external database is required.

> class SharedMemory:
>
> def \_\_init\_\_(self):
>
> self.\_store: dict\[str, dict\[str, Any\]\] = {
>
> \"patient_context\": {},
>
> \"agent_outputs\": {},
>
> \"conflicts\": \[\],
>
> \"scratchpad\": {},
>
> \"execution_trace\": \[\],
>
> }
>
> def read(self, namespace: str, key: str = None) -\> Any:
>
> \"\"\"Read from namespace. Returns full namespace or specific key.\"\"\"
>
> def write(self, namespace: str, key: str, value: Any,
>
> writer_id: str) -\> None:
>
> \"\"\"Write to namespace. Enforces access policy.\"\"\"
>
> def snapshot(self) -\> dict:
>
> \"\"\"Return deep copy of full state for checkpointing.\"\"\"

The snapshot() method enables checkpoint/resume (NF-043) by serialising the entire memory state to a JSON file after each stage. If the pipeline crashes, it can be resumed from the last checkpoint by reloading the snapshot.

**4.5 Memory Lifecycle for a Single Patient Case**

The shared memory goes through a defined lifecycle for each patient:

-   **1. Initialise:** Orchestrator creates a fresh SharedMemory instance and writes Gold-layer data to patient_context.

-   **2. Populate:** As each agent completes, its output is written to agent_outputs.{agent_id}. After conflict-prone stages, the Orchestrator writes to conflicts.

-   **3. Refine:** The Diagnostic Refiner reads the Diagnostic Reasoning and Clinical Reviewer outputs to produce the final differential diagnosis. The output is written to agent_outputs.final_diagnosis.

-   **4. Evaluate and Treat:** The LLM Evaluator compares the final diagnosis against Synthea ground truth and writes to agent_outputs.evaluation. If the match is DIRECT, the Treatment Planning Agent runs next. The Orchestrator then finalises the execution_trace and calls snapshot() to produce a JSON dump for analysis.

-   **5. Reset:** The SharedMemory instance is discarded. A new instance is created for the next patient.

**5. Agent Design**

This section specifies the internal architecture common to all agents (the Agent Blueprint), followed by the specific design of each agent in the pipeline.

**5.1 Agent Blueprint**

Every agent in CMADS is built from the same five-component blueprint. This standardised structure ensures consistency, testability, and swappability across all agents.

![](media/658bde75839cfe507619436354cc1a2eae44c22d.png){width="6.458333333333333in" height="2.8229166666666665in"}

*Figure 5.1 --- Generic Agent Internal Architecture*

The five components execute in sequence for every agent invocation:

-   **Input Gate:** Reads required data from shared memory using the agent's declared input namespaces. Validates the input against the agent's input JSON Schema. If required fields are missing (e.g., the Lab Interpreter was skipped), it logs a warning and proceeds with available data.

-   **Prompt Assembler:** Loads the agent's versioned system prompt template (Jinja2 or YAML), injects the patient context and upstream agent outputs, appends the output JSON Schema as instructions, and optionally adds few-shot examples. The assembled prompt is the exact string sent to the LLM.

-   **LLM Adapter:** A wrapper that sends the assembled prompt to GPT-o3 120B hosted locally via Ollama at localhost:11434. Uses LangChain's ChatOllama class for native Ollama integration. Handles retry logic with exponential backoff for local failures (server restarts, OOM). Records token usage and latency. The adapter is shared across all agents and configured per-agent via YAML. No external API keys or network connectivity required.

-   **Output Parser:** Extracts structured JSON from the LLM's raw response. Validates against the agent's output JSON Schema. If parsing fails, retries once with a stricter prompt. If validation fails, extracts valid fields, sets missing fields to null, and marks status as 'partial'.

-   **Output Gate:** Assembles the Agent Response object (status, output_payload, confidence_score, token_usage, execution_ms) and writes the output_payload to shared memory at agent_outputs.{agent_id}.

**5.1.1 Prompt Template Structure**

Every agent prompt follows a four-part structure:

> \# Template: prompts/{agent_id}/v{version}.yaml
>
> system: \|
>
> You are the {role_name}. Your expertise is {domain}.
>
> You are part of a multi-agent clinical decision pipeline.
>
> \## Your Task
>
> {task_description}
>
> \## Input Data
>
> You will receive: {input_description}
>
> \## Output Format
>
> Respond ONLY with valid JSON matching this schema:
>
> {output_schema_json}
>
> \## Reasoning Instructions
>
> {reasoning_guidelines}
>
> \## Few-Shot Examples (optional)
>
> {examples}

**5.2 EHR Analyst Agent**

The EHR Analyst is the primary intake agent. It is the first agent to execute (Stage 1, parallel with Lab Interpreter) and has no upstream agent dependencies.

  ----------------------- ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            ehr_analyst

  **Stage**               1 (parallel with lab_interpreter)

  **Reads from Memory**   patient_context (full Gold-layer ehr_case data)

  **Writes to Memory**    agent_outputs.ehr_analyst

  **Input**               Structured patient data from ehr_case.json: demographics, condition history (SNOMED-CT coded), medication list (RxNorm), allergies, observations, risk scores, encounter summaries

  **Output**              Structured clinical summary: chief_complaint, hpi, pmh, active_medications, allergies, active_problems (SNOMED-CT + onset), data_quality_flags

  **Model Config**        temperature: 0.1 \| max_tokens: 3000 \| json_mode: true

  **Key Reasoning**       Extract and structure --- does not diagnose. Identifies missing fields. Maps conditions to SNOMED-CT codes from source data.
  ----------------------- ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**5.3 Lab Interpreter Agent**

  ----------------------- --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            lab_interpreter

  **Stage**               1 (parallel with ehr_analyst)

  **Reads from Memory**   patient_context (lab_case data: measurements, lab_trends, critical_lab_flags, lab_panel_summary)

  **Writes to Memory**    agent_outputs.lab_interpreter

  **Input**               Raw lab measurements with reference ranges, pre-computed regression slopes (lab_trends), critical_lab_flags (severity 1--5), lab panel correlations

  **Output**              Prioritised findings list: each finding with {test, value, ref_range, classification, trend, severity, clinical_note, panel_context}

  **Model Config**        temperature: 0.1 \| max_tokens: 3000 \| json_mode: true

  **Key Reasoning**       Classify results against ranges. Interpret trends (e.g., declining eGFR = worsening renal function). Correlate panels (e.g., elevated BUN + creatinine = renal pattern). Rank by severity score.
  ----------------------- --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**5.4 Diagnostic Reasoning Agent**

  ----------------------- -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            diagnostic_reasoning

  **Stage**               2

  **Reads from Memory**   agent_outputs.ehr_analyst, agent_outputs.lab_interpreter, patient_context (risk_scores, comorbidity_matrix)

  **Writes to Memory**    agent_outputs.diagnostic_reasoning

  **Input**               Clinical summary + prioritised lab findings + risk scores + comorbidity matrix

  **Output**              Ranked differential: \[{diagnosis, icd10, snomed, supporting_evidence\[\], confidence, reasoning}\], plus unresolved_findings\[\]

  **Model Config**        temperature: 0.3 \| max_tokens: 4096 \| json_mode: true

  **Key Reasoning**       Synthesise clinical picture with lab evidence. Generate ≥3 differential diagnoses. Map evidence to specific findings. Use risk scores (CKD stage, Framingham, SOFA) as diagnostic context. Flag unexplained findings.
  ----------------------- -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**5.5 Treatment Planning Agent**

  ----------------------- -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            treatment_planning

  **Stage**               6 (only runs on DIRECT evaluation matches)

  **Reads from Memory**   agent_outputs.final_diagnosis, agent_outputs.evaluation, patient_context (medications, conditions, allergies), NICE clinical guideline JSON (retrieved via Qdrant vector search)

  **Writes to Memory**    agent_outputs.treatment_planning

  **Input**               Final differential diagnosis + evaluation result (must be DIRECT match) + patient medications/conditions/allergies + NICE guideline document for the matched disease

  **Output**              Treatment plan: {primary_dx_treatment: {medications\[\], non_pharm\[\], monitoring\[\], followup}, interactions_checked\[\], contraindications\[\], alternatives\[\]}

  **Model Config**        temperature: 0.2 \| max_tokens: 8192 \| json_mode: true

  **Key Reasoning**       Only runs when the LLM Evaluator confirms a DIRECT match against ground truth. Retrieves the relevant NICE clinical guideline via Qdrant vector search. Proposes evidence-based treatment grounded in guideline recommendations. Cross-checks proposed medications against current drugs and conditions. Skips entirely (with logged reason) if evaluation match type is not DIRECT.
  ----------------------- -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**5.6 Clinical Reviewer Agent**

  ----------------------- --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            clinical_reviewer

  **Stage**               3

  **Reads from Memory**   agent_outputs.diagnostic_reasoning, agent_outputs.ehr_analyst, agent_outputs.lab_interpreter, patient_context (critical_lab_flags)

  **Writes to Memory**    agent_outputs.clinical_reviewer

  **Input**               Diagnostic output + EHR summary + lab findings + critical lab flags

  **Output**              {consistency_assessment, critical_findings_coverage (severity ≥3), confidence_score (0--100), concerns\[\], omissions\[\], recommendations\[\]}

  **Model Config**        temperature: 0.2 \| max_tokens: 3000 \| json_mode: true

  **Key Reasoning**       Adversarial review: actively look for inconsistencies in the diagnostic reasoning. Verify every critical lab finding is addressed. Score confidence holistically. Produce actionable concern list for the Diagnostic Refiner.
  ----------------------- --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**5.7 Diagnostic Refiner Agent**

  ----------------------- -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            final_diagnosis

  **Stage**               4

  **Reads from Memory**   agent_outputs.diagnostic_reasoning, agent_outputs.clinical_reviewer, agent_outputs.ehr_analyst, agent_outputs.lab_interpreter

  **Writes to Memory**    agent_outputs.final_diagnosis

  **Input**               Initial diagnostic differential + Reviewer concerns/recommendations + EHR summary + lab findings

  **Output**              Refined DiagnosticOutput: ranked differential with updated confidence scores, evidence, and reasoning that incorporates the Reviewer's feedback

  **Model Config**        temperature: 0.2 \| max_tokens: 8192 \| json_mode: true

  **Key Reasoning**       Merges the initial diagnostic reasoning with the Clinical Reviewer's adversarial feedback to produce the FINAL differential diagnosis. Adjusts confidence scores, addresses concerns raised by the Reviewer, and resolves any identified inconsistencies. This is the definitive diagnostic output consumed by downstream stages.
  ----------------------- -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

*Note: Radiology is handled as a separate data enrichment step in the data pipeline (see pipeline/radiology/), not as an agent in the multi-agent pipeline. Synthea radiology reports are pre-processed and stored in Gold-layer data, available via patient_context.*

**5.8 LLM Evaluator (LLM-as-Judge)**

  ----------------------- ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Agent ID**            evaluation

  **Stage**               5

  **Reads from Memory**   agent_outputs.final_diagnosis, patient_context (for Synthea ground truth lookup)

  **Writes to Memory**    agent_outputs.evaluation

  **Input**               Final differential diagnosis + Synthea ground truth conditions for the patient

  **Output**              Evaluation result: {match_type (DIRECT/PARTIAL/NONE), matched_condition, confidence, reasoning, ground_truth_conditions}

  **Model Config**        Uses a separate evaluator model (configurable via LLM_EVALUATOR_MODEL env var, default: qwen/qwen3-32b)

  **Key Reasoning**       Compares the agent pipeline's final differential diagnosis against Synthea's known ground truth conditions. Classifies the match as DIRECT (primary diagnosis matches), PARTIAL (appears in differential but not primary), or NONE (not found). This is an in-pipeline evaluation stage, not a post-processing step. The match_type output controls whether Treatment Planning runs (DIRECT matches only).
  ----------------------- ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**6. Execution Sequence**

**6.1 Single Patient Case Flow**

The following sequence diagram shows the complete execution flow for a single patient case, illustrating the interaction between the Orchestrator, Shared Memory, and all six stages. Key elements include the parallel dispatch of Stage 1 agents, the adaptive Diagnostic Reasoning in Stage 2, the review-then-refine loop (Stages 3--4), and the conditional Treatment Planning in Stage 6.

![](media/03380da3b8a17e9e8bb4ae74bca1defebf974c03.png){width="6.458333333333333in" height="3.6354166666666665in"}

*Figure 6.1 --- Agent Execution Sequence for a Single Patient Case*

**6.2 Parallel Execution Model**

Stage 1 is the only parallel stage in the current pipeline. Stages 2--6 execute sequentially because each depends on the output of the previous stage:

-   **Stage 1 (parallel):** EHR Analyst and Lab Interpreter both read from patient_context (Gold-layer data) and write to separate agent_outputs slots. They never read each other's output.

-   **Stages 2--6 (sequential):** Diagnostic Reasoning depends on Stage 1 outputs. Clinical Reviewer depends on Diagnostic Reasoning. The Refiner depends on both. The Evaluator depends on the Refiner. Treatment Planning depends on the Evaluator's match type.

Parallelism in Stage 1 is implemented via LangGraph's conditional fan-out/fan-in edges. The Orchestrator waits for all agents in a parallel stage to complete (or timeout) before advancing to the next stage.

**6.3 Checkpointing**

After each stage completes, the Orchestrator calls SharedMemory.snapshot() to serialise the full memory state. Checkpoints are written to disk as:

> checkpoints/
>
> {patient_case_id}/
>
> stage_1_complete.json
>
> stage_2_complete.json
>
> stage_3_complete.json
>
> stage_4_complete.json
>
> stage_5_complete.json
>
> final.json

To resume from a checkpoint, the Orchestrator loads the snapshot, determines which stage to resume from, and continues the pipeline. This enables efficient debugging: if Stage 5 fails, the developer can fix the issue and resume from the Stage 4 checkpoint without re-running Stages 1--4 (saving significant local inference time).

**7. Data Pipeline Design (Summary)**

The data pipeline is supporting infrastructure. Its architecture follows the standard medallion pattern and is summarised here for completeness.

**7.1 Layer Architecture**

-   **Bronze:** Raw ingestion of Synthea-generated CSV and FHIR R4 JSON into append-only Parquet files. Synthea (a Java CLI tool using rule-based state transition machines) is the single source of all patient data. Each record is stamped with batch_id and load_ts. No transformations applied. Implemented as a simple file-copy + Parquet writer using pandas or pyarrow.

-   **Silver:** OMOP CDM v5.4 mapping. Synthea codes (SNOMED, LOINC, RxNorm) are mapped to OMOP concept_ids via vocabulary lookup tables. Six canonical tables are produced: person, visit_occurrence, condition_occurrence, measurement, drug_exposure, observation. Implemented as SQL-like transformations using pandas or DuckDB.

-   **Silver+:** Derived feature engineering. Nine tables are computed from Silver data: lab_trends (OLS regression slopes per lab test per patient), critical_lab_flags (rule-based severity scoring), patient_risk_scores (CKD staging, HbA1c banding, Framingham, SOFA, polypharmacy index), comorbidity_matrix (co-occurrence counts), medication_timeline, encounter_summary, drug_condition_links, lab_panel_summary, data_quality_report.

-   **Gold:** Assembly of per-patient case files. Two JSON files per patient: ehr_case.json (demographics, conditions, medications, observations, allergies, risk scores, comorbidities, encounters, drug-condition links) and lab_case.json (measurements, trends, flags, panel summaries, reference ranges). These are the sole input to the agent pipeline. All data traces back to Synthea.

**7.2 Technology Choices**

  ------------------------ -------------------------------- ---------------------------------------------------------------------------
  **Component**            **Technology**                   **Rationale**

  **File Format**          Apache Parquet                   Columnar, efficient for analytical queries, native pandas/pyarrow support

  **Transformation**       pandas + DuckDB                  pandas for row-level ops, DuckDB for SQL-like aggregations over Parquet

  **Vocabulary Mapping**   OMOP vocab CSV + dict lookups    Lightweight; full OMOP Athena DB is overkill for synthetic data

  **Orchestration**        Python scripts (Makefile)        Simple; no need for Airflow/Prefect for a single-user pipeline

  **Output**               JSON files on local filesystem   Consumed directly by agent pipeline; no database needed
  ------------------------ -------------------------------- ---------------------------------------------------------------------------

**8. Configuration, Logging, and Evaluation**

**8.1 Configuration Architecture**

All system configuration is stored in YAML files organised by concern:

> config/
>
> pipelines/
>
> full_clinical.yaml \# default 6-stage pipeline
>
> diagnostic_only.yaml \# stages 1-4 only (no evaluator/treatment)
>
> agents/
>
> ehr_analyst.yaml \# model, temperature, timeout, schemas
>
> lab_interpreter.yaml
>
> diagnostic_reasoning.yaml
>
> clinical_reviewer.yaml
>
> final_diagnosis.yaml
>
> evaluation.yaml
>
> treatment_planning.yaml
>
> models/
>
> ollama.yaml \# Ollama base URL (localhost:11434), default model, timeout
>
> google.yaml
>
> prompts/
>
> ehr_analyst/v1.0.yaml \# versioned prompt templates
>
> ehr_analyst/v1.1.yaml
>
> \...
>
> schemas/
>
> ehr_analyst_input.json \# JSON Schema for validation
>
> ehr_analyst_output.json
>
> \...

This structure means: to change which model the Diagnostic Agent uses, edit one line in agents/diagnostic_reasoning.yaml. To try a new prompt, create a new versioned file in prompts/ and update the agent config. To run the pipeline in diagnostic-only mode (skipping evaluation and treatment), pass \--pipeline diagnostic_only at the command line. Zero code changes required for any of these operations (NF-030--034).

**8.2 Logging Architecture**

Logging uses Python's structlog library to produce structured JSON lines. Every log entry includes:

-   timestamp (ISO 8601)

-   level (DEBUG/INFO/WARN/ERROR)

-   component (orchestrator, shared_memory, agent:{id}, llm_adapter, evaluator)

-   event (agent_invoked, memory_write, llm_call, schema_validation, conflict_detected, etc.)

-   context (patient_case_id, stage, agent_id where applicable)

Log verbosity is controlled via the LOG_LEVEL environment variable (NF-014). In DEBUG mode, full LLM prompts and responses are logged. In INFO mode, only summaries and token counts are recorded.

Logs are written to:

> logs/
>
> pipeline_run\_{timestamp}.jsonl \# full structured log
>
> cost_report\_{timestamp}.json \# token usage + estimated cost

**8.3 Evaluation Design**

The evaluation engine operates in two modes: (1) the in-pipeline LLM Evaluator (Stage 5), which uses an LLM-as-Judge to compare the Diagnostic Refiner's final differential against Synthea ground truth in real time, and (2) a post-pipeline batch evaluation that computes aggregate metrics across the patient cohort.

Metrics computed per patient case:

-   **Diagnostic accuracy:** Does the primary diagnosis match the ground truth primary condition? (Exact match and semantic similarity via SNOMED hierarchy distance.)

-   **Differential recall:** What fraction of ground-truth conditions appear in the differential diagnosis list?

-   **Treatment relevance:** Are the recommended medications appropriate for the ground-truth condition? (Scored against a reference formulary.)

-   **Critical finding coverage:** Were all severity ≥3 lab findings addressed in the report?

-   **Conflict resolution:** Were all detected conflicts acknowledged or resolved in the final report?

Aggregate metrics (mean, median, std dev) are computed across the patient cohort. Results support A/B comparison: different pipeline configs (e.g., different Ollama-hosted models, 6-stage vs. 4-stage, different prompt versions) on the same cohort produce comparable metric sets (NF-093, NF-094).

**9. Project Structure**

The repository follows a clear separation of concerns, with each top-level directory mapping to a distinct architectural component:

> cmads/
>
> ├── config/ \# All YAML configs (pipelines, agents, models)
>
> ├── prompts/ \# Versioned prompt templates per agent
>
> ├── schemas/ \# JSON Schemas for input/output validation
>
> ├── src/
>
> │ ├── orchestrator/ \# Orchestrator, execution graph parser, conflict engine
>
> │ ├── memory/ \# SharedMemory class, namespace access control
>
> │ ├── agents/ \# Agent base class + 6 agent implementations (+ evaluator node)
>
> │ ├── llm_adapter/ \# Provider-agnostic LLM adapter + retry logic
>
> │ ├── evaluation/ \# Evaluation engine, metrics, A/B comparison
>
> │ └── data_pipeline/ \# Bronze/Silver/Silver+/Gold ETL
>
> ├── tests/
>
> │ ├── unit/ \# Per-agent unit tests with fixed inputs
>
> │ ├── integration/ \# Full pipeline tests with mock LLM
>
> │ └── fixtures/ \# Test case files (Gold-layer JSON samples)
>
> ├── data/ \# Synthea outputs, Parquet layers, Gold JSON
>
> ├── outputs/ \# Clinical reports, traces, evaluation results
>
> ├── logs/ \# Structured JSONL logs
>
> ├── checkpoints/ \# Per-stage memory snapshots
>
> ├── Makefile \# Pipeline commands (make data, make run, make eval)
>
> └── README.md

**9.1 Key Design Decisions Summary**

  --------------------------------- ------------------------------------------------------ ---------------------------------------------------------
  **Decision**                      **Choice**                                             **Alternative Considered**

  **Inter-agent communication**     Shared Memory (blackboard with namespaces)             Direct message passing (AutoGen style) --- too coupled

  **Orchestration pattern**         Centralised Orchestrator with DAG                      Decentralised (agent-to-agent) --- no central control

  **Execution graph definition**    Declarative YAML                                       Hard-coded Python --- inflexible for experiments

  **LLM integration**               Ollama local serving + LangChain ChatOllama (native)   Cloud API --- requires network, API keys, incurs cost

  **Prompt management**             Versioned YAML templates + Jinja2                      Inline strings --- not reproducible

  **State persistence**             In-memory dict + JSON checkpoints                      Redis/database --- overkill for single-user

  **Conflict detection**            Post-stage diff engine in Orchestrator                 Real-time agent debate --- complex, costly

  **Evaluation approach**           Post-pipeline ground truth comparison                  Real-time clinician scoring --- not feasible for thesis

  **Data pipeline orchestration**   Makefile + Python scripts                              Airflow/Prefect --- unnecessary complexity
  --------------------------------- ------------------------------------------------------ ---------------------------------------------------------

*--- End of Document ---*

System Design Document v1.0 • March 22, 2026 • CMADS

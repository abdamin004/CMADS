# Agentic Design Patterns

## CMADS — Design Patterns in the Multi-Agent Clinical Pipeline

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | Documents the 10 agentic design patterns used across the CMADS pipeline: agent blueprints, reasoning strategies, fault tolerance, and retrieval-augmented treatment planning |

---

## 1. Five-Component Agent Blueprint

### What

Every agent in CMADS follows an identical five-stage internal architecture:

```
Input Gate --> Prompt Assembler --> LLM --> Output Parser --> Output Gate
```

The Input Gate reads from shared memory, the Prompt Assembler constructs messages, the LLM generates a response, the Output Parser validates against a Pydantic schema, and the Output Gate writes validated output back to shared memory.

### Why

A uniform internal structure means every agent is independently testable (SDD requirement MA-085) and swappable. New agents are created by subclassing and overriding two methods, not by reimplementing pipeline plumbing. The blueprint also enforces schema validation on every output, which prevents malformed data from propagating downstream and corrupting later agents.

### How

The `BaseAgent` class in `src/agents/base.py` implements the full blueprint in its `__call__` method (line 170). The five components map directly to code:

1. **Input Gate** -- the `__call__` method receives the LangGraph `state` dict, which is the shared memory. Each subclass's `build_user_prompt(state)` reads only the namespaces it needs.

2. **Prompt Assembler** -- `build_user_prompt()` constructs the user message. The system prompt is a class attribute. Together they become a `[SystemMessage, HumanMessage]` pair.

3. **LLM** -- `run_reasoning()` calls `invoke_with_retry()` (from `src/llm/adapter.py`) which wraps the LangChain chat model.

4. **Output Parser** -- `_parse_output()` extracts JSON from the response text, runs it through `_extract_json_from_response()` for repair, then validates against `self.output_schema` (a Pydantic v2 model) via `model_validate()`.

5. **Output Gate** -- `__call__` writes the validated dict to `agent_outputs.{agent_id}` in the state and appends an execution trace entry.

Subclasses only need to set four class attributes (`agent_id`, `system_prompt`, `output_schema`, `temperature`) and implement `build_user_prompt()`. Multi-call agents additionally override `run_reasoning()`.

---

## 2. Multi-Call Chain of Thought

### What

Instead of asking the LLM to analyse data and produce structured JSON in a single call, agents split the work across multiple sequential LLM calls. The minimum pattern is two calls: a free-text analysis call followed by a structured output call. More complex agents (Diagnostic Reasoning) use five or more calls.

### Why

A single LLM call that must simultaneously understand clinical data, reason about it, and format JSON reliably does none of these well. This was demonstrated empirically during development (documented in `docs/MAS_ARCHITECTURE_EVOLUTION.md`): the v1 single-call architecture anchored on the most obvious finding and missed the broader clinical picture, achieving 0% target disease detection in test cases.

Splitting calls gives the LLM dedicated cognitive space for each task:
- **Analysis calls** explore the data without the cognitive overhead of JSON formatting.
- **Structure calls** receive pre-digested reasoning and only need to format it.

### How

The `run_reasoning()` method in `BaseAgent` (line 147) provides the single-call default. Agents that need multi-call reasoning override it. The pattern across all multi-call agents is:

- **Call 1** uses `self._call_llm(llm, ...)` with `json_mode=False` -- free-text reasoning.
- **Final call** uses `self._call_llm(json_llm, ...)` with `json_mode=True` -- structured JSON output.
- Intermediate calls build on previous outputs, passing them as context.

The Treatment Planning Agent (`src/agents/treatment.py`, line 93) uses two calls: analysis against NICE guidelines, then JSON structuring. The Clinical Reviewer (`src/agents/reviewer.py`, line 65) uses three calls: independent re-analysis, per-diagnosis verification, then JSON output. The Diagnostic Agent (`src/agents/diagnostic.py`, line 70) uses five or more calls with an adaptive loop in between.

---

## 3. Adaptive Reasoning Loop

### What

The Diagnostic Reasoning Agent does not use a fixed number of LLM calls. After its three fixed calls (evidence synthesis, hypothesis generation, initial ranking), it enters an adaptive critique-and-refine loop that repeats until either the confidence threshold is met or the maximum round limit is reached.

The loop parameters are:
- `CONFIDENCE_THRESHOLD = 75` (out of 100)
- `MAX_REASONING_ROUNDS = 3`

### Why

Not all patients are equally complex. A patient with a clear-cut condition (e.g., well-controlled diabetes with textbook labs) does not need the same depth of analysis as a patient with ambiguous multi-system disease. Fixed-call architectures either waste time on easy cases or under-analyse hard cases. The adaptive loop allocates reasoning effort proportionally to diagnostic difficulty.

This was the v3-to-v4 evolution documented in `docs/MAS_ARCHITECTURE_EVOLUTION.md`: v3 used a fixed 5-call chain that spent the same time on every patient, while v4 added the confidence-gated loop to stop early when the differential is solid.

### How

In `src/agents/diagnostic.py`, the `run_reasoning()` method (line 70) implements this as a `while` loop (line 157):

**Critique step** (line 163): An LLM call with a "senior attending physician" persona reviews the current differential for anchoring bias, missed diagnoses, and probability errors. It outputs a confidence score (0-100) and either approves the differential or requests changes.

**Confidence extraction** (line 199-214): The agent parses the confidence score from the critique text using multiple regex patterns to handle format variation (`"confidence: 85"`, `"85/100"`, `"confidence score of 85"`, etc.).

**Exit conditions** (line 220): The loop stops if:
- The critique contains an adequacy phrase (e.g., "differential is adequate", "no major omissions"), OR
- The extracted confidence score meets or exceeds `CONFIDENCE_THRESHOLD` (75), OR
- `round_num` reaches `MAX_REASONING_ROUNDS` (3).

**Refine step** (line 237): If not confident enough, a new LLM call addresses every gap from the critique, adds missing diagnoses, recalibrates probabilities, and produces an updated differential. The loop then returns to the critique step.

After the loop exits, a final call with `json_llm` (json_mode=True) converts the refined free-text differential into validated structured JSON.

---

## 4. Adversarial Review Pattern

### What

The Clinical Reviewer Agent does not simply check the Diagnostic Agent's output against the evidence. It first performs an independent re-analysis of the raw evidence -- forming its own clinical impression before ever seeing the diagnostic conclusions. Only then does it compare its independent findings against the Diagnostic Agent's differential.

### Why

If the reviewer sees the diagnostic output first, it is susceptible to anchoring bias -- it will subconsciously look for evidence that confirms the proposed diagnoses rather than objectively evaluating the data. By forming an independent opinion first, the reviewer can identify diagnoses that the Diagnostic Agent missed entirely, which a confirmation-biased review would never catch.

This mirrors the clinical practice of seeking a "second opinion" from a physician who examines the patient independently rather than simply reviewing another doctor's notes.

### How

In `src/agents/reviewer.py`, `run_reasoning()` (line 65) implements three calls:

**Call 1 -- Independent Evidence Re-analysis** (line 74): The system prompt explicitly says "Ignore the diagnostic conclusions -- look at the raw data with fresh eyes." The user prompt asks the reviewer to identify the top 5 most significant findings, the clinical patterns it sees, and the diagnoses it would consider "based purely on the evidence." At this point, the diagnostic differential is present in the full prompt data but the system instruction directs the LLM to focus on the raw EHR and lab outputs first.

**Call 2 -- Per-Diagnosis Verification** (line 93): Now the reviewer receives both its own independent analysis and the Diagnostic Agent's differential. For each proposed diagnosis, it checks whether the evidence actually supports it, whether the probability is reasonable, assigns its own confidence score (0-100), and renders a verdict: "supported", "plausible", "questionable", or "unsupported". It also checks whether all critical lab findings (severity >= 3) are explained and whether the Diagnostic Agent missed conditions the reviewer identified independently.

**Call 3 -- Structured JSON** (line 117): Both the independent analysis and the verification are fed to `json_llm` to produce the final `ReviewerOutput` schema with per-diagnosis adjusted probabilities and an overall confidence score.

---

## 5. Dual LLM Mode

### What

Every multi-call agent instantiates two LLM instances: one with `json_mode=False` for free-text reasoning and one with `json_mode=True` for structured JSON output. The `__call__` method in `BaseAgent` creates both (line 186-187) and passes them to `run_reasoning()`.

### Why

Free-text mode and JSON mode serve different purposes and have different failure characteristics:

- **Free-text mode** (`json_mode=False`) produces richer, more exploratory reasoning. The LLM is not constrained by output format and can think through clinical patterns, express uncertainty, and build reasoning chains naturally.

- **JSON mode** (`json_mode=True`) constrains the LLM to produce valid JSON, which improves parse reliability but can degrade reasoning quality. The model sometimes omits nuance or truncates analysis to fit the JSON structure.

Using both modes in sequence gives the best of each: unconstrained reasoning followed by reliable structuring.

### How

In `src/llm/adapter.py`, `get_llm()` (line 38) accepts a `json_mode` parameter. For the Groq provider, it sets `response_format: {"type": "json_object"}` in model kwargs (line 63). For Ollama, the parameter is available but handled differently by the model runtime.

In `src/agents/base.py`, the `__call__` method (line 186-188) creates both variants:

```python
llm = self._get_llm(json_mode=False)
json_llm = self._get_llm(json_mode=True)
output_dict = self.run_reasoning(state, llm, json_llm)
```

Multi-call agents use `llm` for analysis/critique calls and `json_llm` for the final structuring call. For example, the Diagnostic Agent (line 91-151) uses `llm` for evidence synthesis, hypothesis generation, ranking, and critique, then switches to `jllm` (line 255-257) for the final JSON output. The default `run_reasoning()` in `BaseAgent` falls back to `json_llm` for single-call agents (line 160: `use_llm = json_llm or llm`).

---

## 6. JSON Repair Pipeline

### What

The `_extract_json_from_response()` function in `src/agents/base.py` (line 24) implements a multi-stage repair pipeline that progressively attempts to fix malformed JSON from LLM responses before giving up.

### Why

Local LLMs (and even cloud models) frequently produce JSON with minor formatting errors: think tags wrapping the response, markdown code blocks, trailing commas, missing commas between objects, and single quotes instead of double quotes. These are all syntactically invalid JSON but carry perfectly valid content. Rejecting the entire response and re-calling the LLM is expensive (30-60 seconds per call). The repair pipeline salvages most responses without an additional LLM round-trip.

### How

The repair pipeline in `_extract_json_from_response()` applies six stages in order, stopping at the first successful parse:

1. **Think tag removal** (line 27): Strips `<think>...</think>` tags that some models (especially reasoning models) wrap around their internal chain-of-thought.

2. **Code block extraction** (line 28-30): Extracts content from `` ```json ... ``` `` or `` ``` ... ``` `` markdown fences.

3. **JSON object extraction** (line 31-32): Uses regex to find the outermost `{...}` in the text, discarding any preamble or postamble.

4. **Trailing comma fix** (line 44): Removes commas before `}` or `]` (`",}"` becomes `"}"`) and adds missing commas between adjacent `}{` or `][`.

5. **Single-to-double quote conversion** (line 55-66): Applies targeted regex replacements for single-quoted JSON keys and values. This is a common error with local models that have seen Python dict syntax in training data.

6. **Brute-force quote replacement** (line 70-71): If targeted replacement fails, replaces all single quotes with double quotes. This is risky (it breaks apostrophes in values like "patient's") but is a last resort.

7. **Unescaped newline fix** (line 78): Escapes literal newlines inside string values.

If all stages fail, the function raises `json.JSONDecodeError`, which triggers the retry mechanism in `_parse_output()` (line 125) -- a follow-up LLM call that asks the model to fix its own JSON.

---

## 7. Retry with Exponential Backoff

### What

Every LLM call goes through `invoke_with_retry()` in `src/llm/adapter.py` (line 85), which retries failed calls with exponential backoff and includes a special fallback for `json_mode` validation failures.

### Why

LLM calls can fail for multiple reasons: network timeouts, rate limits, empty responses, or (specific to Groq with `json_mode=True`) server-side JSON validation rejections. A single failure should not crash the agent. Exponential backoff prevents hammering a recovering service while still retrying quickly on transient errors.

The `json_mode` fallback addresses a specific failure mode: Groq's API sometimes rejects responses that fail its internal JSON validation even though the content would be parseable by the client-side repair pipeline. In this case, retrying with `json_mode=False` and relying on the JSON repair pipeline is more reliable than retrying the same failing constraint.

### How

`invoke_with_retry()` (line 85-146) works as follows:

- **Retry loop**: Attempts up to `max_retries` (default 3) calls. On failure, waits `2^attempt` seconds (2s, 4s, 8s).

- **Empty response check** (line 105-106): Even successful API calls can return empty content (observed with Groq `json_mode`). These are treated as failures and retried.

- **JSON mode fallback** (line 124-141): On the final retry, if the error contains `"json_validate_failed"` or `"Failed to validate JSON"`, the function creates a new LLM instance with `json_mode=False` and tries once more. The response then goes through the client-side JSON repair pipeline in `_extract_json_from_response()` instead of relying on server-side validation.

- **Structured logging**: Every attempt logs the agent ID, attempt number, error type, and wait time via `structlog`, enabling post-hoc analysis of LLM reliability.

---

## 8. Parallel Fan-Out / Fan-In

### What

Stage 1 of the pipeline runs two agents -- EHR Analyst and Lab Interpreter -- in parallel. Both read from `patient_context` (which neither modifies) and write to separate keys in `agent_outputs`. Stage 2 (Diagnostic Reasoning) waits for both to complete before executing.

### Why

The EHR Analyst and Lab Interpreter are independent: they read different parts of the patient data (clinical record vs. lab results), they do not depend on each other's output, and they write to different memory slots. Running them sequentially would double the wall-clock time for Stage 1 with no benefit. Parallel execution is a direct latency optimisation.

### How

In `src/orchestrator/graph.py`, the `compile_pipeline()` function (line 39) uses LangGraph's `add_conditional_edges` to implement fan-out:

```python
graph.add_conditional_edges(START, _stage1_fanout, ["ehr_analyst", "lab_interpreter"])
```

The `_stage1_fanout` function (line 34) returns both node names, causing LangGraph to execute them concurrently. Fan-in is implicit: both Stage 1 nodes have edges to `diagnostic_reasoning` (lines 72-73):

```python
graph.add_edge("ehr_analyst", "diagnostic_reasoning")
graph.add_edge("lab_interpreter", "diagnostic_reasoning")
```

LangGraph's `StateGraph` only executes a node once all its incoming edges are satisfied. The `PipelineState` uses a dict-merge reducer for `agent_outputs`, so both agents' results are merged into the same state dict without conflicts.

The full execution graph is:

```
START --> [EHR Analyst | Lab Interpreter] --> Diagnostic Reasoning
      --> Clinical Reviewer --> Diagnostic Refiner --> Evaluation
      --> Treatment Planning --> END
```

---

## 9. Graceful Degradation

### What

When an agent fails -- whether from an LLM timeout, a schema validation error, or an unhandled exception -- the pipeline does not abort. The failed agent's output slot is filled with either partial data or `None`, an error is logged to the execution trace, and downstream agents proceed with whatever data is available.

### Why

In a multi-agent pipeline with 7 agents and potentially 10+ LLM calls per patient, the probability of at least one failure across a cohort run is significant. Aborting the entire pipeline on any single agent failure would make cohort-scale evaluation impractical. Graceful degradation ensures that even partially successful runs produce analysable output.

This is a core design principle (SDD section 1.2): "Every agent is treated as potentially fallible. Timeouts, malformed LLM responses, and Ollama server errors are expected conditions, not exceptions."

### How

The `__call__` method in `BaseAgent` (line 170-227) implements three tiers of failure handling:

**Tier 1 -- Success** (line 197): The agent produces a validated output dict, writes it to `agent_outputs.{agent_id}`, and logs `status: "success"`.

**Tier 2 -- Partial result** (line 202-216): A `ValidationError` is caught. The agent attempts to extract whatever JSON it can from the error context and writes it as a partial result with `status: "partial"`. Downstream agents receive incomplete but potentially useful data.

**Tier 3 -- Total failure** (line 218-227): Any other exception is caught. The agent writes `None` to its output slot with `status: "error"` and logs the full error. Downstream agents see `None` for this agent's output and must handle the absence.

Downstream agents are written to handle missing upstream data. For example, in `src/agents/diagnostic.py`, `build_user_prompt()` (line 287-405) checks each upstream output:

```python
if ehr_out:
    # ... use EHR data
else:
    sections.append("*EHR Analyst output not available (agent failed)*\n")
```

This allows the Diagnostic Agent to reason with lab data alone if the EHR Analyst failed, or vice versa. The quality degrades, but the pipeline completes.

---

## 10. RAG for Treatment Planning

### What

The Treatment Planning Agent uses Retrieval-Augmented Generation (RAG) to ground its treatment recommendations in NICE (National Institute for Health and Care Excellence) clinical guidelines. Before generating a treatment plan, it queries a Qdrant vector database to find the top 3 guidelines most semantically similar to the diagnosed disease, then feeds those guidelines as context to the LLM.

### Why

Treatment recommendations must be evidence-based, not hallucinated. Without external grounding, LLMs produce plausible-sounding but potentially incorrect drug names, doses, and interaction warnings. NICE guidelines provide authoritative, peer-reviewed treatment protocols for specific diseases. Using semantic search rather than exact matching handles the naming variation problem (e.g., "Atherosclerotic CAD" should match the "Chronic coronary syndromes" guideline).

### How

The RAG pipeline has three components:

**1. Vector Database** (`src/vectordb/query_guidelines.py`): Qdrant Cloud stores NICE guideline documents as vectors. Each document contains the guideline reference (e.g., "NG106"), title, disease name, and the full guideline JSON (drug recommendations, contraindications, monitoring plans). The embedding model is `FremyCompany/BioLORD-2023`, a biomedical sentence transformer chosen for its domain-specific vocabulary coverage.

**2. Retrieval** (`search_guidelines()`, line 39): The diagnosed disease name is embedded using BioLORD-2023, then a vector similarity search returns the top `k` (default 3) matching guidelines with similarity scores. Using top-3 rather than top-1 provides fallback context when the best match is not exact.

**3. Augmented Generation** (`src/agents/treatment.py`, `build_user_prompt()` line 171): The retrieved guidelines are formatted into the prompt with their full JSON content, similarity scores, and source references. The Treatment Agent's two-call reasoning then analyses the patient's medications and conditions against the guideline's recommendations (Call 1, free text), then structures the treatment plan as JSON (Call 2, json_mode). The contraindicated drugs list from all matched guidelines is explicitly extracted and passed to the analysis call (line 105-114) with instructions to check every drug against the patient's current medications and conditions.

The Treatment Agent also integrates with the evaluation system (line 181-193): it only generates treatment plans for patients whose diagnostic evaluation returned a "DIRECT" match, skipping patients where the diagnosis was uncertain.

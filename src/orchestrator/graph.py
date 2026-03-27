"""LangGraph StateGraph — CMADS Agent Pipeline Orchestrator.

Defines the execution graph for the multi-agent clinical decision pipeline.
Currently implements Stage 1 (EHR Analyst + Lab Interpreter in parallel).

Implements: SDD §3, TECH_STACK §2.2
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.agents.ehr_analyst import ehr_analyst_agent
from src.agents.lab_interpreter import lab_interpreter_agent
from src.agents.diagnostic import diagnostic_reasoning_agent
from src.agents.reviewer import clinical_reviewer_agent
from src.agents.refiner import diagnostic_refiner_agent
from src.agents.evaluator import evaluate_node
from src.agents.treatment import treatment_planning_agent


# ── State Definition (shared memory) ──────────────────────────────────

from src.orchestrator.state import PipelineState


# ── Graph Construction ─────────────────────────────────────────────────

def _stage1_fanout(state: dict) -> list[str]:
    """Router: fan out to both Stage 1 agents in parallel."""
    return ["ehr_analyst", "lab_interpreter"]


def compile_pipeline() -> Any:
    """Build and compile the LangGraph StateGraph.

    Returns a compiled graph that can be invoked with:
        result = pipeline.invoke(initial_state, config={"configurable": {"thread_id": "..."}})
    """
    from langgraph.graph import START

    graph = StateGraph(PipelineState)

    # Stage 1 — parallel: EHR Analyst + Lab Interpreter
    graph.add_node("ehr_analyst", ehr_analyst_agent)
    graph.add_node("lab_interpreter", lab_interpreter_agent)

    # Stage 2 — Diagnostic Reasoning (depends on both Stage 1 agents)
    graph.add_node("diagnostic_reasoning", diagnostic_reasoning_agent)

    # Stage 3 — Clinical Reviewer (verifies Stage 2 output)
    graph.add_node("clinical_reviewer", clinical_reviewer_agent)

    # Stage 4 — Diagnostic Refiner (merges Diagnostic + Reviewer → final differential)
    graph.add_node("final_diagnosis", diagnostic_refiner_agent)

    # Stage 5 — LLM Evaluator (compares diagnosis against ground truth)
    graph.add_node("evaluation", evaluate_node)

    # Stage 6 — Treatment Planning (applies NICE guidelines, only for DIRECT matches)
    graph.add_node("treatment_planning", treatment_planning_agent)

    # Fan-out from START to both Stage 1 agents (parallel)
    graph.add_conditional_edges(START, _stage1_fanout, ["ehr_analyst", "lab_interpreter"])

    # Stage 1 → Stage 2 (fan-in: diagnostic waits for both)
    graph.add_edge("ehr_analyst", "diagnostic_reasoning")
    graph.add_edge("lab_interpreter", "diagnostic_reasoning")

    # Stage 2 → Stage 3
    graph.add_edge("diagnostic_reasoning", "clinical_reviewer")

    # Stage 3 → Stage 4 (Refiner produces final differential)
    graph.add_edge("clinical_reviewer", "final_diagnosis")

    # Stage 4 → Stage 5 (Evaluation)
    graph.add_edge("final_diagnosis", "evaluation")

    # Stage 5 → Stage 6 (Treatment — reads evaluation.json to check DIRECT match)
    graph.add_edge("evaluation", "treatment_planning")

    # Stage 6 → END
    graph.add_edge("treatment_planning", END)

    # Compile with in-memory checkpointing
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# ── Pipeline Runner ────────────────────────────────────────────────────

GOLD_DIR = Path("data/gold/patient_cases")
MAS_RESULTS_DIR = Path("data/gold/mas_results")


def load_patient_case(patient_uuid: str) -> dict:
    """Load Gold-layer case files for a patient."""
    patient_dir = GOLD_DIR / patient_uuid

    ehr_case = json.loads((patient_dir / "ehr_case.json").read_text())
    lab_case = json.loads((patient_dir / "lab_case.json").read_text())

    return {
        "ehr_case": ehr_case,
        "lab_case": lab_case,
    }


def save_patient_results(patient_uuid: str, result: dict, duration_s: float):
    """Save all agent outputs and execution trace for a patient."""
    patient_dir = MAS_RESULTS_DIR / patient_uuid
    patient_dir.mkdir(parents=True, exist_ok=True)

    outputs = result.get("agent_outputs", {})
    trace = result.get("execution_trace", [])

    # Save each agent's output
    agent_files = {
        "ehr_analyst": "ehr_analyst.json",
        "lab_interpreter": "lab_interpreter.json",
        "diagnostic_reasoning": "diagnostic_reasoning.json",
        "clinical_reviewer": "clinical_reviewer.json",
        "final_diagnosis": "final_diagnosis.json",
        "evaluation": "evaluation.json",
        "treatment_planning": "treatment_planning.json",
    }

    for agent_id, filename in agent_files.items():
        agent_output = outputs.get(agent_id)
        if agent_output:
            (patient_dir / filename).write_text(
                json.dumps(agent_output, indent=2, default=str)
            )

    # Save execution trace
    (patient_dir / "execution_trace.json").write_text(
        json.dumps({
            "patient_uuid": patient_uuid,
            "duration_s": duration_s,
            "agents": [
                {
                    "agent_id": t.get("agent_id"),
                    "status": t.get("status"),
                    "execution_ms": t.get("execution_ms"),
                    "error": t.get("error"),
                }
                for t in trace
            ],
        }, indent=2, default=str)
    )


def run_single_patient(patient_uuid: str, pipeline=None, save=True) -> dict:
    """Run the pipeline for a single patient.

    Args:
        patient_uuid: Patient UUID from cohort.
        pipeline: Compiled LangGraph pipeline (created if None).
        save: If True, save results to data/gold/mas_results/.

    Returns:
        Final pipeline state dict.
    """
    if pipeline is None:
        pipeline = compile_pipeline()

    # Load Gold data
    case = load_patient_case(patient_uuid)

    # Build initial state (Orchestrator initialises shared memory — SDD §4.5)
    initial_state = {
        "patient_context": case,
        "agent_outputs": {},
        "conflicts": [],
        "execution_trace": [],
        "scratchpad": {},
    }

    # Invoke the graph
    start = time.time()
    result = pipeline.invoke(
        initial_state,
        config={"configurable": {"thread_id": f"patient_{patient_uuid}"}},
    )
    duration = time.time() - start

    # Save results
    if save:
        save_patient_results(patient_uuid, result, duration)

    return result


def run_cohort(cohort_file: str, max_patients: int | None = None,
               save: bool = True) -> list[dict]:
    """Run the pipeline for a cohort of patients.

    Args:
        cohort_file: Path to JSON file with patient UUIDs.
        max_patients: Limit number of patients (for testing).
        save: If True, save all results to disk.

    Returns:
        List of result dicts, one per patient.
    """
    with open(cohort_file) as f:
        uuids = json.load(f)

    if max_patients:
        uuids = uuids[:max_patients]

    pipeline = compile_pipeline()
    results = []
    pipeline_start = time.time()

    for i, uuid in enumerate(uuids):
        print(f"[{i+1}/{len(uuids)}] Patient: {uuid[:12]}...", end=" ", flush=True)
        start = time.time()
        try:
            result = run_single_patient(uuid, pipeline, save=save)
            duration = time.time() - start

            # Check agent status
            trace = result.get("execution_trace", [])
            statuses = {t["agent_id"]: t["status"] for t in trace}
            print(f"done ({duration:.1f}s) — {statuses}")

            results.append({
                "patient_uuid": uuid,
                "status": "success",
                "result": result,
                "duration_s": round(duration, 1),
            })
        except Exception as e:
            duration = time.time() - start
            print(f"ERROR ({duration:.1f}s) — {e}")
            results.append({
                "patient_uuid": uuid,
                "status": "error",
                "error": str(e),
                "duration_s": round(duration, 1),
            })

    total_time = time.time() - pipeline_start

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    print(f"\nComplete: {success}/{len(results)} patients succeeded")
    print(f"Time: {total_time:.0f}s ({total_time/max(len(results),1):.1f}s/patient)")

    if save:
        print(f"Results: {MAS_RESULTS_DIR}/")

        # Save run summary
        run_summary = {
            "cohort_file": cohort_file,
            "total_patients": len(results),
            "succeeded": success,
            "failed": len(results) - success,
            "total_time_s": round(total_time, 1),
            "avg_time_per_patient_s": round(total_time / max(len(results), 1), 1),
            "patients": [
                {
                    "uuid": r["patient_uuid"],
                    "status": r["status"],
                    "duration_s": r["duration_s"],
                    "error": r.get("error"),
                }
                for r in results
            ],
        }
        MAS_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (MAS_RESULTS_DIR / "run_summary.json").write_text(
            json.dumps(run_summary, indent=2, default=str)
        )

    return results

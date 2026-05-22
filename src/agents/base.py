"""Base Agent — 5-component blueprint from SDD §5.1.

Every agent follows: Input Gate → Prompt Assembler → LLM → Output Parser → Output Gate

Implements: MA-085 (independently testable), NF-061 (unit testable)
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Type

import yaml
import structlog
from pydantic import BaseModel, ValidationError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langchain_core.language_models import BaseChatModel

from src.llm.adapter import get_llm, invoke_with_retry
from src.memory import EpisodicMemory, MemoryManager

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

logger = structlog.get_logger()


class SkipAgentException(Exception):
    """Raised when an agent should be skipped (returns a pre-built result dict)."""

    def __init__(self, result: dict):
        self.result = result
        super().__init__("Agent skipped")


def _extract_json_from_response(text: str) -> dict:
    """Extract JSON from LLM response, handling think tags, code blocks, and minor errors."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Common LLM JSON errors — attempt repair
    repaired = text
    # Fix trailing commas before } or ]
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    # Fix missing commas between } { or ] [
    repaired = re.sub(r"(\})\s*(\{)", r"\1,\2", repaired)
    repaired = re.sub(r"(\])\s*(\[)", r"\1,\2", repaired)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Fix single quotes to double quotes (very common with local LLMs)
    # Strategy: replace single quotes used as JSON delimiters
    sq_repaired = repaired
    # Replace 'key': with "key":
    sq_repaired = re.sub(r"'([^']*?)'(\s*:)", r'"\1"\2', sq_repaired)
    # Replace : 'value' with : "value"
    sq_repaired = re.sub(r"(:\s*)'([^']*?)'(\s*[,}\]])", r'\1"\2"\3', sq_repaired)
    # Replace ['value' with ["value"
    sq_repaired = re.sub(r"(\[\s*)'([^']*?)'", r'\1"\2"', sq_repaired)
    # Replace 'value'] with "value"]
    sq_repaired = re.sub(r"'([^']*?)'(\s*\])", r'"\1"\2', sq_repaired)
    try:
        return json.loads(sq_repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: brute-force replace all single quotes with double quotes
    # (risky with apostrophes but better than failing)
    brute = repaired.replace("'", '"')
    try:
        return json.loads(brute)
    except json.JSONDecodeError:
        pass

    # Final: fix unescaped newlines
    brute = re.sub(r'(?<!\\)\n', r'\\n', brute)
    return json.loads(brute)


class BaseAgent:
    """Base class for all CMADS agents.

    Subclasses must set:
        agent_id: str
        system_prompt: str
        output_schema: Type[BaseModel]
        temperature: float

    And implement:
        build_user_prompt(state: dict) -> str

    Optionally override:
        run_reasoning(state, llm) -> dict
            For multi-call chain-of-thought reasoning.
    """

    agent_id: str = "base"
    system_prompt: str = ""
    output_schema: Type[BaseModel] = BaseModel
    temperature: float = 0.2
    max_tokens: int = 16384
    max_agent_time: int = int(os.environ.get("AGENT_TIMEOUT", "300"))  # configurable via .env
    _prompts: dict | None = None  # Cached YAML prompts

    def __init__(self):
        # Per-instance episodic-memory buffer. __call__ resets this each
        # invocation; subclasses append to it during run_reasoning.
        self._pending_memory_events: list[dict] = []

    def _load_prompts(self) -> dict:
        """Load prompts from YAML file (prompts/{agent_id}.yaml).

        Returns the parsed YAML dict. Caches after first load.
        Falls back to inline system_prompt if no YAML file exists.
        """
        if self._prompts is not None:
            return self._prompts

        yaml_path = PROMPTS_DIR / f"{self.agent_id}.yaml"
        if yaml_path.exists():
            self._prompts = yaml.safe_load(yaml_path.read_text())
            # Override inline system_prompt with YAML version
            if "system" in self._prompts:
                self.system_prompt = self._prompts["system"].strip()
            logger.info("prompts_loaded", agent_id=self.agent_id, source=str(yaml_path))
        else:
            self._prompts = {}
            logger.info("prompts_inline", agent_id=self.agent_id,
                        msg="No YAML file found, using inline prompts")
        return self._prompts

    def _get_call_prompt(self, call_name: str, key: str, fallback: str = "",
                         **kwargs) -> str:
        """Get a prompt for a specific call from YAML, with variable substitution.

        Args:
            call_name: Name of the call (e.g., "analysis", "structure", "review")
            key: "system" or "user"
            fallback: Default text if call not found in YAML
            **kwargs: Variables to substitute in the template (e.g., patient_data=..., analysis=...)

        Returns:
            The prompt string with {placeholders} replaced by kwargs values.
        """
        prompts = self._load_prompts()
        calls = prompts.get("calls", {})
        call = calls.get(call_name, {})
        template = call.get(key, fallback)

        # Replace {system} with the main system prompt
        if "{system}" in template:
            kwargs["system"] = self.system_prompt

        # Substitute variables — use safe formatting that ignores missing keys
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    def _get_llm(self, json_mode: bool = False) -> BaseChatModel:
        return get_llm(temperature=self.temperature, max_tokens=self.max_tokens,
                       json_mode=json_mode)

    def memory(self, state: dict) -> MemoryManager:
        """Return a MemoryManager scoped to this agent and the given state.

        Convenience helper — agents should prefer this over instantiating
        MemoryManager directly so wiring lives in one place.
        """
        return MemoryManager.from_state(state, agent_id=self.agent_id)

    @staticmethod
    def _memory_enabled() -> bool:
        """Master switch — agents skip memory work when disabled."""
        from src.config import cfg
        return cfg.MEMORY_ENABLED

    def _check_timeout(self):
        """Raise TimeoutError if agent has exceeded max_agent_time."""
        if hasattr(self, '_agent_start_time') and self._agent_start_time:
            elapsed = time.time() - self._agent_start_time
            if elapsed > self.max_agent_time:
                raise TimeoutError(
                    f"Agent {self.agent_id} exceeded {self.max_agent_time}s timeout "
                    f"(elapsed: {elapsed:.0f}s)")

    def _call_llm(self, llm: BaseChatModel, system: str, user: str, agent_id: str = None) -> str:
        """Single LLM call — returns raw text. Used by multi-call agents."""
        self._check_timeout()
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = invoke_with_retry(
            llm, messages, max_retries=3, agent_id=agent_id or self.agent_id
        )
        return response.content

    def _call_llm_conversation(self, llm: BaseChatModel, messages: list, agent_id: str = None) -> str:
        """LLM call with full message history — for follow-up calls."""
        response = invoke_with_retry(
            llm, messages, max_retries=3, agent_id=agent_id or self.agent_id
        )
        return response.content

    def _parse_output(self, raw_text: str, llm: BaseChatModel | None = None, messages: list = None) -> Any:
        """Parse and validate LLM output against schema, with JSON repair + retry."""
        try:
            parsed = _extract_json_from_response(raw_text)
            return self.output_schema.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as parse_err:
            logger.warning("agent_parse_retry",
                           agent_id=self.agent_id, error=str(parse_err)[:100])
            if llm and messages:
                fix_msg = HumanMessage(
                    content=f"Your previous response had invalid JSON. Error: {str(parse_err)[:200]}\n\n"
                            f"Please output ONLY valid JSON matching the schema. "
                            f"No markdown, no explanation, just the JSON object."
                )
                response = invoke_with_retry(
                    llm, messages + [AIMessage(content=raw_text), fix_msg],
                    max_retries=2, agent_id=self.agent_id
                )
                parsed = _extract_json_from_response(response.content)
                return self.output_schema.model_validate(parsed)
            raise

    def run_reasoning(self, state: dict, llm: BaseChatModel, json_llm: BaseChatModel | None = None) -> dict:
        """Run the agent's reasoning. Override for multi-call agents.

        Default: single-call (build prompt → call LLM → parse).
        Multi-call agents override this to do chain-of-thought.

        Args:
            llm: LLM for free-text calls (analysis, critique).
            json_llm: LLM with json_mode=True for structured output calls.
                      Falls back to llm if None.

        Returns: validated output dict.
        """
        use_llm = json_llm or llm
        user_prompt = self.build_user_prompt(state)
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = invoke_with_retry(use_llm, messages, max_retries=3, agent_id=self.agent_id)
        output = self._parse_output(response.content, use_llm, messages)
        return output.model_dump()

    def _run_analysis_structure_review(self, state: dict, llm, json_llm=None) -> dict:
        """Three-call reasoning: analysis -> structure -> review.

        Standard pattern for agents that:
        1. Analyse data (free text, no JSON)
        2. Convert analysis to structured JSON
        3. Self-review and correct if needed

        Requires YAML calls: analysis, structure, review.
        """
        patient_data = self.build_user_prompt(state)

        # ── Call 1: Deep analysis ──
        logger.info("agent_step", agent_id=self.agent_id, step="analysis")
        analysis = self._call_llm(llm,
            system=self._get_call_prompt("analysis", "system",
                fallback="You are a senior clinician. Perform a thorough analysis. "
                         "Do NOT produce JSON yet."),
            user=self._get_call_prompt("analysis", "user",
                fallback=patient_data, patient_data=patient_data),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="analysis",
                     length=len(analysis))

        # ── Call 2: Structured output ──
        logger.info("agent_step", agent_id=self.agent_id, step="structure")
        jllm = json_llm or llm
        output_schema = json.dumps(self.output_schema.model_json_schema(), indent=2)
        raw_json = self._call_llm(jllm,
            system=self._get_call_prompt("structure", "system",
                fallback=self.system_prompt),
            user=self._get_call_prompt("structure", "user",
                fallback=f"{analysis}\n{patient_data}",
                analysis=analysis, patient_data=patient_data,
                output_schema=output_schema),
        )
        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Convert to JSON"),
        ])
        output_dict = output.model_dump()

        # ── Call 3: Self-review ──
        logger.info("agent_step", agent_id=self.agent_id, step="review")
        output_json = json.dumps(output_dict, indent=2, default=str)
        review = self._call_llm(jllm,
            system=self._get_call_prompt("review", "system",
                fallback="You are a quality reviewer checking a clinical analysis."),
            user=self._get_call_prompt("review", "user",
                fallback=f"{patient_data}\n{output_json}",
                patient_data=patient_data, output_json=output_json),
        )
        try:
            reviewed = self._parse_output(review)
            logger.info("agent_step_done", agent_id=self.agent_id, step="review",
                         result="updated")
            return reviewed.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            logger.info("agent_step_done", agent_id=self.agent_id, step="review",
                         result="kept_original", reason=str(e)[:100])
            return output_dict

    def __call__(self, state: dict) -> dict:
        """LangGraph node function — the full 5-component pipeline."""
        self._load_prompts()  # Load YAML prompts on first call
        start = time.time()
        self._agent_start_time = start  # For timeout checks in _call_llm
        trace_entry = {
            "agent_id": self.agent_id,
            "status": "error",
            "execution_ms": 0,
            "llm_calls": 0,
            "error": None,
        }

        memory_events: list[dict] = []
        memory_summary: dict[str, str] = {}
        memory_on = self._memory_enabled()
        # Reset agent-buffered events from any prior invocation. Subclasses
        # can append episodic events to self._pending_memory_events during
        # run_reasoning; we drain the buffer below.
        self._pending_memory_events = []

        try:
            # 1. Input Gate
            logger.info("agent_start", agent_id=self.agent_id)
            if memory_on:
                memory_events.append(EpisodicMemory.write(
                    event_type="agent_start",
                    agent_id=self.agent_id,
                    summary=f"Started {self.agent_id}",
                    tags=["lifecycle"],
                ))

            # 2-4. Prompt → LLM → Parse (single or multi-call via run_reasoning)
            llm = self._get_llm(json_mode=False)
            json_llm = self._get_llm(json_mode=True)
            output_dict = self.run_reasoning(state, llm, json_llm)

            # Drain any episodic events the agent buffered during reasoning.
            if memory_on and self._pending_memory_events:
                memory_events.extend(self._pending_memory_events)
            self._pending_memory_events = []

            # 5. Output Gate
            duration_ms = int((time.time() - start) * 1000)
            trace_entry["status"] = "success"
            trace_entry["execution_ms"] = duration_ms
            logger.info("agent_success",
                        agent_id=self.agent_id, duration_ms=duration_ms)

            if memory_on:
                memory_events.append(EpisodicMemory.write(
                    event_type="agent_complete",
                    agent_id=self.agent_id,
                    summary=f"Completed {self.agent_id} in {duration_ms}ms",
                    tags=["lifecycle"],
                ))
                memory_summary[self.agent_id] = (
                    f"completed ({duration_ms}ms)"
                )

            update = {
                "agent_outputs": {self.agent_id: output_dict},
                "execution_trace": [trace_entry],
            }
            if memory_events:
                update["session_memory"] = memory_events
            if memory_summary:
                update["session_summary"] = memory_summary

            # Mongo write path (additive — state write above is unchanged)
            from src.config import cfg
            if cfg.USE_MONGO:
                import asyncio as _asyncio
                _patient_uuid = (
                    (state.get("patient_context") or {})
                    .get("ehr_case", {})
                    .get("patient_uuid", "unknown")
                )
                _envelope = {
                    "status": trace_entry["status"],
                    "output": output_dict,
                    "duration_ms": trace_entry["execution_ms"],
                }
                _asyncio.run(write_agent_envelope_to_mongo(
                    result_set=cfg.MAS_RESULTS_DIR.name,
                    patient_uuid=_patient_uuid,
                    agent_id=self.agent_id,
                    envelope=_envelope,
                ))

            return update

        except SkipAgentException as e:
            duration_ms = int((time.time() - start) * 1000)
            trace_entry["status"] = "skipped"
            trace_entry["execution_ms"] = duration_ms
            trace_entry["error"] = None
            logger.info("agent_skipped", agent_id=self.agent_id,
                        duration_ms=duration_ms)
            return {
                "agent_outputs": {self.agent_id: e.result},
                "execution_trace": [trace_entry],
            }

        except ValidationError as e:
            duration_ms = int((time.time() - start) * 1000)
            trace_entry["status"] = "partial"
            trace_entry["execution_ms"] = duration_ms
            trace_entry["error"] = f"Schema validation: {e.error_count()} errors"
            logger.warning("agent_partial",
                           agent_id=self.agent_id, errors=e.error_count())
            try:
                partial = _extract_json_from_response(str(e))
            except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
                logger.debug("agent_partial_parse_failed",
                             agent_id=self.agent_id, error=str(parse_err)[:100])
                partial = {}
            return {
                "agent_outputs": {self.agent_id: partial},
                "execution_trace": [trace_entry],
            }

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            trace_entry["execution_ms"] = duration_ms
            trace_entry["error"] = str(e)
            logger.error("agent_failed",
                         agent_id=self.agent_id, error=str(e))
            return {
                "agent_outputs": {self.agent_id: None},
                "execution_trace": [trace_entry],
            }

    def build_user_prompt(self, state: dict) -> str:
        """Build the user prompt from pipeline state. Override in subclass."""
        raise NotImplementedError

    @staticmethod
    def _autofill_primary_diagnosis(result: dict) -> dict:
        """Fill primary_diagnosis from differential[0] if the LLM left it empty."""
        if not result.get("primary_diagnosis") and result.get("differential"):
            top = result["differential"][0]
            result["primary_diagnosis"] = top.get("name", "")
            result["primary_probability"] = top.get("probability", 0.0)
        return result


async def write_agent_envelope_to_mongo(
    *,
    result_set: str,
    patient_uuid: str,
    agent_id: str,
    envelope: dict,
) -> None:
    """Atomic per-agent upsert into AgentRun. Called from BaseAgent.__call__
    after the agent emits its envelope, when USE_MONGO is set."""
    from datetime import datetime
    from src.db.mongo import init_db
    from src.db.documents import AgentRun

    await init_db()
    await AgentRun.find_one(
        AgentRun.result_set == result_set, AgentRun.patient_uuid == patient_uuid,
    ).upsert(
        {"$set": {f"agents.{agent_id}": envelope}},
        on_insert=AgentRun(
            result_set=result_set, patient_uuid=patient_uuid,
            started_at=datetime.utcnow(),
            agents={agent_id: envelope},
        ),
    )

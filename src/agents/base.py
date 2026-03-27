"""Base Agent — 5-component blueprint from SDD §5.1.

Every agent follows: Input Gate → Prompt Assembler → LLM → Output Parser → Output Gate

Implements: MA-085 (independently testable), NF-061 (unit testable)
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Type

import structlog
from pydantic import BaseModel, ValidationError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.llm.adapter import get_llm, invoke_with_retry

logger = structlog.get_logger()


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
    max_tokens: int = 4096
    max_agent_time: int = 300  # 5 minute hard cap per agent

    def _get_llm(self, json_mode: bool = False):
        return get_llm(temperature=self.temperature, max_tokens=self.max_tokens,
                       json_mode=json_mode)

    def _call_llm(self, llm, system: str, user: str, agent_id: str = None) -> str:
        """Single LLM call — returns raw text. Used by multi-call agents."""
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = invoke_with_retry(
            llm, messages, max_retries=3, agent_id=agent_id or self.agent_id
        )
        return response.content

    def _call_llm_conversation(self, llm, messages: list, agent_id: str = None) -> str:
        """LLM call with full message history — for follow-up calls."""
        response = invoke_with_retry(
            llm, messages, max_retries=3, agent_id=agent_id or self.agent_id
        )
        return response.content

    def _parse_output(self, raw_text: str, llm=None, messages: list = None) -> Any:
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

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
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

    def __call__(self, state: dict) -> dict:
        """LangGraph node function — the full 5-component pipeline."""
        start = time.time()
        trace_entry = {
            "agent_id": self.agent_id,
            "status": "error",
            "execution_ms": 0,
            "llm_calls": 0,
            "error": None,
        }

        try:
            # 1. Input Gate
            logger.info("agent_start", agent_id=self.agent_id)

            # 2-4. Prompt → LLM → Parse (single or multi-call via run_reasoning)
            llm = self._get_llm(json_mode=False)
            json_llm = self._get_llm(json_mode=True)
            output_dict = self.run_reasoning(state, llm, json_llm)

            # 5. Output Gate
            duration_ms = int((time.time() - start) * 1000)
            trace_entry["status"] = "success"
            trace_entry["execution_ms"] = duration_ms
            logger.info("agent_success",
                        agent_id=self.agent_id, duration_ms=duration_ms)

            return {
                "agent_outputs": {self.agent_id: output_dict},
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
            except Exception:
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

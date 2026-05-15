"""Orchestrator for the CC <-> Codex auto-review loop.

See docs/superpowers/specs/2026-05-15-auto-review-loop-design.md.
"""
from __future__ import annotations

import re

VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVE|REJECT)", re.IGNORECASE)


def parse_verdict(text: str) -> str:
    """Return 'APPROVE' or 'REJECT' from the last VERDICT: line.

    Missing or malformed => 'REJECT' (fail-safe).
    """
    matches = VERDICT_RE.findall(text or "")
    if not matches:
        return "REJECT"
    return matches[-1].upper()


from pathlib import Path


def render_prompt(template_path: Path, variables: dict[str, str]) -> str:
    """Read template_path and substitute {var} placeholders."""
    return Path(template_path).read_text(encoding="utf-8").format(**variables)

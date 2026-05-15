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

import subprocess
from datetime import datetime


def _log(log_file, message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")


def _invoke(cmd: list, cwd, output_file, log_file) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _log(log_file, f"RUN cwd={cwd} cmd={cmd[:2]}... -> {output_file.name}")
    with output_file.open("w", encoding="utf-8") as out, \
         log_file.open("a", encoding="utf-8") as err:
        result = subprocess.run(cmd, cwd=cwd, stdout=out, stderr=err,
                                check=False, text=True)
    _log(log_file, f"EXIT rc={result.returncode} bytes={output_file.stat().st_size}")
    return result.returncode


def run_claude(prompt: str, cwd, output_file, log_file) -> int:
    """Invoke `claude -p` headless. Stdout -> output_file."""
    cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits"]
    return _invoke(cmd, cwd, output_file, log_file)


def run_codex(prompt: str, cwd, output_file, log_file) -> int:
    """Invoke `codex exec` headless. Stdout -> output_file."""
    cmd = ["codex", "exec", prompt]
    return _invoke(cmd, cwd, output_file, log_file)

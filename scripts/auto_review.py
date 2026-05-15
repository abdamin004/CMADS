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


def create_run_dir(base: Path) -> Path:
    """Create `<base>/<ISO-timestamp>/` and return it."""
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    run = Path(base) / stamp
    run.mkdir(parents=True, exist_ok=False)
    return run


def plan_iter_dir(run_dir: Path, n: int) -> Path:
    return run_dir / f"iter_{n:02d}"


def fix_iter_dir(run_dir: Path, n: int) -> Path:
    return run_dir / f"fix_iter_{n:02d}"


import shutil
import difflib

THESIS_IGNORE_PATTERNS = ("*.aux", "*.log", "*.bbl", "*.blg", "*.out",
                          "*.toc", "*.lof", "*.lot", "*.fls", "*.fdb_latexmk",
                          "*.synctex.gz", "*.pdf", "__pycache__")


def snapshot_thesis(thesis_dir: Path, dest: Path) -> None:
    """Copy thesis_dir -> dest, skipping LaTeX build artifacts."""
    shutil.copytree(
        thesis_dir, dest,
        ignore=shutil.ignore_patterns(*THESIS_IGNORE_PATTERNS),
    )


def _flat_name(rel: Path) -> str:
    return "__".join(rel.parts) + ".diff"


def _list_files(root: Path) -> dict[str, Path]:
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            out[str(p.relative_to(root))] = p
    return out


def diff_thesis(before: Path, after: Path, diffs_dir: Path) -> list[dict]:
    """Write per-file unified diffs and return summary entries.

    Each entry: {"path": str, "added": int, "removed": int, "diff_file": str}.
    """
    diffs_dir.mkdir(parents=True, exist_ok=True)
    before_files = _list_files(before)
    after_files = _list_files(after)
    all_rel = sorted(set(before_files) | set(after_files))
    summary: list[dict] = []
    for rel in all_rel:
        b_lines = before_files[rel].read_text(encoding="utf-8").splitlines(keepends=True) \
            if rel in before_files else []
        a_lines = after_files[rel].read_text(encoding="utf-8").splitlines(keepends=True) \
            if rel in after_files else []
        if b_lines == a_lines:
            continue
        diff = list(difflib.unified_diff(
            b_lines, a_lines,
            fromfile=f"before/{rel}", tofile=f"after/{rel}",
        ))
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
        flat = _flat_name(Path(rel))
        (diffs_dir / flat).write_text("".join(diff), encoding="utf-8")
        summary.append({
            "path": rel, "added": added, "removed": removed, "diff_file": flat,
        })
    return summary

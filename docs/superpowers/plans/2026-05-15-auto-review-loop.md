# Auto-Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-command orchestrator that drives the manual Claude Code ↔ Codex CLI thesis-review + fix loop end to end, with thesis snapshots/diffs per run and bounded retries.

**Architecture:** A single Python orchestrator (`scripts/auto_review.py`) shells out to `claude -p` and `codex exec` headless modes via `subprocess`, exchanging Markdown artifacts on disk under `.review-cycle/<timestamp>/`. Each run snapshots `thesis/` before any work and after each fix iteration; `difflib.unified_diff` produces per-file `.diff` outputs and a `CHANGES.md` summary. Prompts live in versioned templates; loops cap at 3 iterations; Codex emits a final-line `VERDICT: APPROVE|REJECT` token the orchestrator greps deterministically. A thin Claude Code slash command wraps the script.

**Tech Stack:** Python 3.11 stdlib only (`subprocess`, `pathlib`, `argparse`, `datetime`, `re`, `shutil`, `difflib`), pytest, Claude Code CLI, Codex CLI.

**Spec reference:** `docs/superpowers/specs/2026-05-15-auto-review-loop-design.md`

---

## File Structure

**New:**
- `scripts/auto_review.py` — orchestrator (~500 lines, single module)
- `scripts/auto_review_prompts/{01..06}_*.txt` — 8 prompt templates
- `.claude/commands/auto-review.md` — slash command
- `tests/test_auto_review.py` — unit + mocked-state-machine tests

**Modified:**
- `.gitignore` — add `.review-cycle/`
- `README.md` — short usage section

All orchestrator logic stays in one file: the script is small, components are tightly coupled (state machine + IO + parsing + snapshots), and splitting forces test-import gymnastics with no isolation benefit. Prompts are external because they evolve independently of code.

---

## Task 1: Gitignore + CLI sanity

**Files:** `.gitignore`

- [ ] **Step 1: Verify both CLIs present**

Run:
```bash
which claude codex
claude -p --help 2>&1 | grep -iE 'permission|print' | head -5
codex --help 2>&1 | grep -E 'exec' | head -3
```
Expected: both binaries resolve; `claude -p` shows `--permission-mode` with `acceptEdits` (or note the current flag name for Task 4); `codex` shows an `exec` subcommand.

- [ ] **Step 2: Add `.review-cycle/` to `.gitignore`**

Append after the `# ── Data` block:

```
# ── Auto-review loop artifacts (regenerated per run) ────
.review-cycle/
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .review-cycle/ auto-review artifacts"
```

---

## Task 2: Verdict parser (TDD)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Create test file with header**

Create `tests/test_auto_review.py`:

```python
"""Tests for scripts/auto_review.py orchestrator."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import auto_review  # noqa: E402
```

- [ ] **Step 2: Write failing tests for `parse_verdict`**

Append to `tests/test_auto_review.py`:

```python
class TestParseVerdict:
    def test_approve(self):
        assert auto_review.parse_verdict("ok\nVERDICT: APPROVE\n") == "APPROVE"

    def test_reject(self):
        assert auto_review.parse_verdict("issues\nVERDICT: REJECT") == "REJECT"

    def test_trailing_whitespace(self):
        assert auto_review.parse_verdict("VERDICT: APPROVE   \n\n") == "APPROVE"

    def test_case_insensitive(self):
        assert auto_review.parse_verdict("verdict: approve") == "APPROVE"

    def test_missing_returns_reject(self):
        assert auto_review.parse_verdict("no verdict line") == "REJECT"

    def test_empty_returns_reject(self):
        assert auto_review.parse_verdict("") == "REJECT"

    def test_takes_last_match(self):
        text = "VERDICT: APPROVE\nthen\nVERDICT: REJECT\n"
        assert auto_review.parse_verdict(text) == "REJECT"
```

- [ ] **Step 3: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py -v
```
Expected: import or attribute errors.

- [ ] **Step 4: Implement `parse_verdict`**

Create `scripts/auto_review.py`:

```python
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
```

- [ ] **Step 5: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestParseVerdict -v
```
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): verdict parser"
```

---

## Task 3: Prompt renderer (TDD)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auto_review.py`:

```python
class TestRenderPrompt:
    def test_substitutes(self, tmp_path):
        t = tmp_path / "p.txt"
        t.write_text("Review {target} for {audience}.")
        assert auto_review.render_prompt(t, {"target": "thesis", "audience": "examiner"}) == "Review thesis for examiner."

    def test_missing_raises(self, tmp_path):
        t = tmp_path / "p.txt"
        t.write_text("Hello {name}")
        with pytest.raises(KeyError):
            auto_review.render_prompt(t, {})

    def test_no_placeholders(self, tmp_path):
        t = tmp_path / "p.txt"
        t.write_text("static")
        assert auto_review.render_prompt(t, {}) == "static"

    def test_literal_braces(self, tmp_path):
        t = tmp_path / "p.txt"
        t.write_text("use {{literal}} and {var}")
        assert auto_review.render_prompt(t, {"var": "X"}) == "use {literal} and X"
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py::TestRenderPrompt -v
```

- [ ] **Step 3: Implement**

Append to `scripts/auto_review.py`:

```python
from pathlib import Path


def render_prompt(template_path: Path, variables: dict[str, str]) -> str:
    """Read template_path and substitute {var} placeholders."""
    return Path(template_path).read_text(encoding="utf-8").format(**variables)
```

- [ ] **Step 4: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestRenderPrompt -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): prompt template renderer"
```

---

## Task 4: CLI wrappers (TDD with mocked subprocess)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auto_review.py`:

```python
class TestCliWrappers:
    def test_run_claude_invokes_claude_p(self, tmp_path, monkeypatch):
        seen = {}

        def fake_run(cmd, cwd, stdout, stderr, check, text):
            seen["cmd"] = cmd
            seen["cwd"] = cwd
            stdout.write("claude out\n")
            return type("R", (), {"returncode": 0})()

        monkeypatch.setattr(auto_review.subprocess, "run", fake_run)
        out = tmp_path / "o.md"
        rc = auto_review.run_claude(prompt="do", cwd=tmp_path,
                                    output_file=out, log_file=tmp_path / "t.log")
        assert rc == 0
        assert seen["cmd"][:2] == ["claude", "-p"]
        assert "do" in seen["cmd"]
        assert out.read_text() == "claude out\n"

    def test_run_codex_invokes_codex_exec(self, tmp_path, monkeypatch):
        seen = {}

        def fake_run(cmd, cwd, stdout, stderr, check, text):
            seen["cmd"] = cmd
            stdout.write("ok\nVERDICT: APPROVE\n")
            return type("R", (), {"returncode": 0})()

        monkeypatch.setattr(auto_review.subprocess, "run", fake_run)
        out = tmp_path / "v.md"
        rc = auto_review.run_codex(prompt="verify", cwd=tmp_path,
                                   output_file=out, log_file=tmp_path / "t.log")
        assert rc == 0
        assert seen["cmd"][:2] == ["codex", "exec"]
        assert "VERDICT: APPROVE" in out.read_text()

    def test_run_claude_propagates_nonzero(self, tmp_path, monkeypatch):
        def fake_run(cmd, cwd, stdout, stderr, check, text):
            stdout.write("")
            return type("R", (), {"returncode": 2})()

        monkeypatch.setattr(auto_review.subprocess, "run", fake_run)
        rc = auto_review.run_claude(prompt="x", cwd=tmp_path,
                                    output_file=tmp_path / "o.md",
                                    log_file=tmp_path / "t.log")
        assert rc == 2
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py::TestCliWrappers -v
```

- [ ] **Step 3: Implement wrappers**

Append to `scripts/auto_review.py`:

```python
import subprocess
from datetime import datetime


def _log(log_file: Path, message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")


def _invoke(cmd: list[str], cwd: Path, output_file: Path, log_file: Path) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _log(log_file, f"RUN cwd={cwd} cmd={cmd[:2]}... -> {output_file.name}")
    with output_file.open("w", encoding="utf-8") as out, \
         log_file.open("a", encoding="utf-8") as err:
        result = subprocess.run(cmd, cwd=cwd, stdout=out, stderr=err,
                                check=False, text=True)
    _log(log_file, f"EXIT rc={result.returncode} bytes={output_file.stat().st_size}")
    return result.returncode


def run_claude(prompt: str, cwd: Path, output_file: Path, log_file: Path) -> int:
    """Invoke `claude -p` headless. Stdout -> output_file."""
    cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits"]
    return _invoke(cmd, cwd, output_file, log_file)


def run_codex(prompt: str, cwd: Path, output_file: Path, log_file: Path) -> int:
    """Invoke `codex exec` headless. Stdout -> output_file."""
    cmd = ["codex", "exec", prompt]
    return _invoke(cmd, cwd, output_file, log_file)
```

- [ ] **Step 4: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestCliWrappers -v
```
Expected: 3 passed.

- [ ] **Step 5: Verify `--permission-mode acceptEdits` flag is current**

Run:
```bash
claude -p --help 2>&1 | grep -i permission
```
If the flag differs, update `run_claude` and its test, then re-run pytest.

- [ ] **Step 6: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): subprocess wrappers for claude and codex"
```

---

## Task 5: Run directory + iter path helpers (TDD)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auto_review.py`:

```python
class TestRunPaths:
    def test_create_run_dir(self, tmp_path):
        run = auto_review.create_run_dir(tmp_path)
        assert run.exists() and run.parent == tmp_path
        assert run.name.count("-") >= 4  # ISO-ish

    def test_iter_dirs(self, tmp_path):
        run = auto_review.create_run_dir(tmp_path)
        assert auto_review.plan_iter_dir(run, 1).name == "iter_01"
        assert auto_review.plan_iter_dir(run, 12).name == "iter_12"
        assert auto_review.fix_iter_dir(run, 1).name == "fix_iter_01"
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py::TestRunPaths -v
```

- [ ] **Step 3: Implement**

Append to `scripts/auto_review.py`:

```python
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
```

- [ ] **Step 4: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestRunPaths -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): run directory and iter path helpers"
```

---

## Task 6: Thesis snapshot + diff (TDD)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auto_review.py`:

```python
class TestThesisVersioning:
    def _make_thesis(self, root, files: dict[str, str]):
        thesis = root / "thesis"
        thesis.mkdir(parents=True, exist_ok=True)
        for rel, body in files.items():
            p = thesis / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        return thesis

    def test_snapshot_copies_tex_skips_build_artifacts(self, tmp_path):
        thesis = self._make_thesis(tmp_path, {
            "main.tex": "hello",
            "chapters/intro.tex": "intro",
            "main.aux": "build",
            "main.pdf": "binary",
            "main.synctex.gz": "build",
        })
        dest = tmp_path / "snap"
        auto_review.snapshot_thesis(thesis, dest)
        assert (dest / "main.tex").read_text() == "hello"
        assert (dest / "chapters" / "intro.tex").read_text() == "intro"
        assert not (dest / "main.aux").exists()
        assert not (dest / "main.pdf").exists()
        assert not (dest / "main.synctex.gz").exists()

    def test_diff_detects_changes(self, tmp_path):
        before = tmp_path / "before"
        after = tmp_path / "after"
        before.mkdir()
        after.mkdir()
        (before / "a.tex").write_text("line1\nline2\nline3\n")
        (after / "a.tex").write_text("line1\nlineTWO\nline3\nline4\n")
        (before / "removed.tex").write_text("gone\n")
        (after / "added.tex").write_text("new\n")

        diffs_dir = tmp_path / "diffs"
        summary = auto_review.diff_thesis(before, after, diffs_dir)

        assert (diffs_dir / "a.tex.diff").exists()
        assert "lineTWO" in (diffs_dir / "a.tex.diff").read_text()
        # summary contains all three files
        paths = {entry["path"] for entry in summary}
        assert paths == {"a.tex", "removed.tex", "added.tex"}
        a_entry = next(e for e in summary if e["path"] == "a.tex")
        assert a_entry["added"] == 2  # lineTWO + line4
        assert a_entry["removed"] == 1  # line2

    def test_diff_empty_when_unchanged(self, tmp_path):
        before = tmp_path / "before"
        after = tmp_path / "after"
        before.mkdir()
        after.mkdir()
        (before / "a.tex").write_text("same\n")
        (after / "a.tex").write_text("same\n")
        summary = auto_review.diff_thesis(before, after, tmp_path / "diffs")
        assert summary == []

    def test_flat_diff_name_for_nested_path(self, tmp_path):
        before = tmp_path / "before"
        after = tmp_path / "after"
        (before / "chapters").mkdir(parents=True)
        (after / "chapters").mkdir(parents=True)
        (before / "chapters" / "m.tex").write_text("a\n")
        (after / "chapters" / "m.tex").write_text("b\n")
        diffs = tmp_path / "diffs"
        auto_review.diff_thesis(before, after, diffs)
        assert (diffs / "chapters__m.tex.diff").exists()
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py::TestThesisVersioning -v
```

- [ ] **Step 3: Implement snapshot + diff**

Append to `scripts/auto_review.py`:

```python
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
```

- [ ] **Step 4: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestThesisVersioning -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): thesis snapshot and per-file diff"
```

---

## Task 7: Prompt templates

**Files:** `scripts/auto_review_prompts/*.txt` (8 files)

- [ ] **Step 1: Create `01_thesis_review.txt`**

```
You are reviewing a bachelor thesis written in LaTeX. The thesis sources are in the current working directory (thesis/). Read thesis/CLAUDE.md FIRST for context.

Produce a Markdown review with these sections:

# Thesis Review v1

## Critical Issues
Issues that would cause a major mark deduction. Each item: file:line, what is wrong, why it matters.

## Substantive Issues
Issues with argument, evidence, or structure. Same format.

## Prose & Style
Clarity, tone, repetition, awkward phrasing. Reference exact passages.

## Citations & Figures
Missing/broken refs, uncited claims, figures not referenced in text.

## Cross-chapter Consistency
Numbers, definitions, terminology that disagree across chapters.

## Out of Scope (do not fix)
Anything noticed but explicitly deferred this pass.

Be specific. No platitudes. Cite source files by path and line numbers.
```

- [ ] **Step 2: Create `02_codex_second_opinion.txt`**

```
You are giving a SECOND OPINION on a thesis review.

First review:  {review_v1_path}
Thesis sources: ./thesis/  (read thesis/CLAUDE.md for context)

Your job:
1. Read the existing review.
2. Spot-check the thesis to verify the issues raised are real.
3. Add anything the first reviewer missed.
4. Remove anything you disagree with (one-line justification).
5. Merge into a single FINAL review with the same section headings, plus a new section "## Reviewer Adjustments" listing what you added/removed/changed.

Output ONLY the merged final review in Markdown. No preamble.
```

- [ ] **Step 3: Create `03_plan.txt`**

```
You have a finalized thesis review at: {review_final_path}

Produce a numbered fix plan in Markdown. For each item:

  N. **[file:line]** -- concrete action (rewrite sentence to..., add citation for..., move figure X to..., etc.)

Group by file. Cover EVERY issue except "Out of Scope". End with:

## Coverage Map
Table mapping each review issue ID to the plan item(s) addressing it. Anything intentionally deferred goes here with a one-line reason.

Output ONLY the plan.
```

- [ ] **Step 4: Create `03_plan_followup.txt`**

```
Your previous plan was rejected.

Verdict:        {plan_verdict_path}
Review to cover: {review_final_path}
Your prior plan: {prev_plan_path}

Revise the plan to address every gap. Keep items the verdict approved. Output the COMPLETE revised plan (not a diff), same format as before.
```

- [ ] **Step 5: Create `04_plan_verify.txt`**

```
Verify a fix plan for completeness.

Plan:   {plan_path}
Review: {review_final_path}

For each issue in the review (skip "Out of Scope"), decide if the plan addresses it:

# Plan Verdict

## Covered
- Review issue -> plan item(s)

## Gaps
- Review issue -> why no plan item addresses it (or "addressed too weakly: <reason>")

## Notes
Anything else the executor should know.

End your output with EXACTLY ONE of these as the LAST line:

VERDICT: APPROVE
VERDICT: REJECT

APPROVE only if Gaps is empty.
```

- [ ] **Step 6: Create `05_execute.txt`**

```
Execute the fix plan at: {plan_path}
Originating review:      {review_final_path}

Apply every item in the plan. You may edit files directly. Your stdout becomes the execution log.

Output format:

# Execution Log

## Applied
- Plan item N -> files changed, brief description

## Skipped or Blocked
- Plan item N -> reason

## Notes
Anything reviewer should know before final verification.
```

- [ ] **Step 7: Create `05_execute_followup.txt`**

```
Your previous execution was rejected at final verification.

Residuals: {final_verdict_path}
Plan:      {plan_path}

Address every residual. You may make additional edits beyond the plan if the verdict identifies issues the plan missed. Output the updated execution log in the same format, with a "## Residuals Addressed" section mapping verdict residuals to your fixes.
```

- [ ] **Step 8: Create `06_final_verify.txt`**

```
Verify that the executed fixes actually resolved the review issues.

Plan:           {plan_path}
Review:         {review_final_path}
Execution log:  {execution_log_path}

For each non-deferred issue in the review, inspect the current state of the relevant files and decide:
- RESOLVED   -- fix in place and correct
- PARTIAL    -- attempted but incomplete
- UNRESOLVED -- no change or wrong change

Output:

# Final Verdict

## Resolved
- Issue -> file:line evidence

## Partial / Unresolved
- Issue -> what is still wrong, what would fix it

## Notes
Anything else the next iteration should know.

End your output with EXACTLY ONE of these as the LAST line:

VERDICT: APPROVE
VERDICT: REJECT

APPROVE only if Partial/Unresolved is empty.
```

- [ ] **Step 9: Commit**

```bash
git add scripts/auto_review_prompts/
git commit -m "feat(auto-review): 6-step prompt templates"
```

---

## Task 8: Main pipeline state machine (TDD)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Write failing tests covering happy path + both caps + CLI failure**

Append to `tests/test_auto_review.py`:

```python
class TestPipeline:
    def _setup_repo(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "thesis").mkdir(parents=True)
        (repo / "thesis" / "main.tex").write_text("v1")
        prompts = repo / "scripts" / "auto_review_prompts"
        prompts.mkdir(parents=True)
        for name in [
            "01_thesis_review.txt", "02_codex_second_opinion.txt",
            "03_plan.txt", "03_plan_followup.txt", "04_plan_verify.txt",
            "05_execute.txt", "05_execute_followup.txt", "06_final_verify.txt",
        ]:
            (prompts / name).write_text("static prompt body")
        return repo

    def test_happy_path_first_try(self, tmp_path, monkeypatch):
        repo = self._setup_repo(tmp_path)
        names = []

        def fake_claude(prompt, cwd, output_file, log_file):
            names.append(output_file.name)
            output_file.write_text("ok\n")
            return 0

        def fake_codex(prompt, cwd, output_file, log_file):
            names.append(output_file.name)
            output_file.write_text("ok\nVERDICT: APPROVE\n")
            return 0

        monkeypatch.setattr(auto_review, "run_claude", fake_claude)
        monkeypatch.setattr(auto_review, "run_codex", fake_codex)

        rc = auto_review.run_pipeline(repo_root=repo, max_plan_iters=3, max_fix_iters=3)
        assert rc == 0
        assert names == ["review_v1.md", "review_final.md",
                         "fix_plan.md", "plan_verdict.md",
                         "execution_log.md", "final_verdict.md"]

        runs = list((repo / ".review-cycle").iterdir())
        assert len(runs) == 1
        run = runs[0]
        assert (run / "thesis_before" / "main.tex").exists()
        assert (run / "fix_iter_01" / "thesis_after" / "main.tex").exists()
        assert (run / "CHANGES.md").exists()

    def test_plan_loop_caps(self, tmp_path, monkeypatch):
        repo = self._setup_repo(tmp_path)

        def fake_claude(prompt, cwd, output_file, log_file):
            output_file.write_text("ok\n")
            return 0

        def fake_codex(prompt, cwd, output_file, log_file):
            if output_file.name == "plan_verdict.md":
                output_file.write_text("gaps\nVERDICT: REJECT\n")
            else:
                output_file.write_text("VERDICT: APPROVE\n")
            return 0

        monkeypatch.setattr(auto_review, "run_claude", fake_claude)
        monkeypatch.setattr(auto_review, "run_codex", fake_codex)
        rc = auto_review.run_pipeline(repo_root=repo, max_plan_iters=2, max_fix_iters=3)
        assert rc == 1

    def test_fix_loop_caps(self, tmp_path, monkeypatch):
        repo = self._setup_repo(tmp_path)

        def fake_claude(prompt, cwd, output_file, log_file):
            output_file.write_text("ok\n")
            return 0

        def fake_codex(prompt, cwd, output_file, log_file):
            if output_file.name == "final_verdict.md":
                output_file.write_text("VERDICT: REJECT\n")
            else:
                output_file.write_text("VERDICT: APPROVE\n")
            return 0

        monkeypatch.setattr(auto_review, "run_claude", fake_claude)
        monkeypatch.setattr(auto_review, "run_codex", fake_codex)
        rc = auto_review.run_pipeline(repo_root=repo, max_plan_iters=3, max_fix_iters=2)
        assert rc == 2

    def test_cli_failure_returns_3(self, tmp_path, monkeypatch):
        repo = self._setup_repo(tmp_path)

        def fake_claude(prompt, cwd, output_file, log_file):
            output_file.write_text("")
            return 5

        def fake_codex(prompt, cwd, output_file, log_file):
            output_file.write_text("VERDICT: APPROVE\n")
            return 0

        monkeypatch.setattr(auto_review, "run_claude", fake_claude)
        monkeypatch.setattr(auto_review, "run_codex", fake_codex)
        rc = auto_review.run_pipeline(repo_root=repo, max_plan_iters=3, max_fix_iters=3)
        assert rc == 3

    def test_changes_md_records_iteration_summary(self, tmp_path, monkeypatch):
        repo = self._setup_repo(tmp_path)

        def fake_claude(prompt, cwd, output_file, log_file):
            # On execution step, also mutate the thesis so diffs are non-empty
            if output_file.name == "execution_log.md":
                (repo / "thesis" / "main.tex").write_text("v2 updated")
            output_file.write_text("ok\n")
            return 0

        def fake_codex(prompt, cwd, output_file, log_file):
            output_file.write_text("VERDICT: APPROVE\n")
            return 0

        monkeypatch.setattr(auto_review, "run_claude", fake_claude)
        monkeypatch.setattr(auto_review, "run_codex", fake_codex)
        rc = auto_review.run_pipeline(repo_root=repo, max_plan_iters=3, max_fix_iters=3)
        assert rc == 0
        run = next((repo / ".review-cycle").iterdir())
        changes = (run / "CHANGES.md").read_text()
        assert "main.tex" in changes
        assert "fix_iter_01" in changes
        # per-iter diff present
        assert (run / "fix_iter_01" / "diffs" / "main.tex.diff").exists()
        assert (run / "fix_iter_01" / "thesis_changes.md").exists()
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py::TestPipeline -v
```

- [ ] **Step 3: Implement `run_pipeline` and helpers**

Append to `scripts/auto_review.py`:

```python
PROMPTS_REL = "scripts/auto_review_prompts"


def _prompts(repo_root: Path) -> Path:
    return Path(repo_root) / PROMPTS_REL


def _log_path(run_dir: Path) -> Path:
    return run_dir / "transcript.log"


class CliFailure(RuntimeError):
    pass


def _write_iter_changes(iter_dir: Path, summary: list[dict]) -> None:
    """Write per-iteration thesis_changes.md."""
    lines = ["# Thesis changes (this iteration)", ""]
    if not summary:
        lines.append("_No changes to thesis/_")
    else:
        lines.append("| File | +added | -removed | Diff |")
        lines.append("|------|-------:|---------:|------|")
        for e in summary:
            lines.append(f"| `{e['path']}` | {e['added']} | {e['removed']} | "
                         f"[diff](diffs/{e['diff_file']}) |")
    (iter_dir / "thesis_changes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_run_changes(run_dir: Path, iter_summaries: list[tuple[str, list[dict]]],
                       final_verdict: str) -> None:
    """Write run-level CHANGES.md."""
    lines = [
        f"# Auto-review run {run_dir.name}",
        "",
        f"**Final verdict:** {final_verdict}",
        "",
        "## Per-iteration changes",
    ]
    for iter_name, summary in iter_summaries:
        lines.append(f"\n### {iter_name}")
        if not summary:
            lines.append("- _no thesis changes_")
            continue
        for e in summary:
            lines.append(f"- `{e['path']}` (+{e['added']} -{e['removed']}) "
                         f"-> [{iter_name}/diffs/{e['diff_file']}]"
                         f"({iter_name}/diffs/{e['diff_file']})")
    (run_dir / "CHANGES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(repo_root: Path, max_plan_iters: int = 3,
                 max_fix_iters: int = 3) -> int:
    """Drive the full state machine.

    Exit codes: 0 APPROVE, 1 plan-cap, 2 fix-cap, 3 sub-CLI failure.
    """
    repo_root = Path(repo_root)
    base = repo_root / ".review-cycle"
    base.mkdir(exist_ok=True)
    run_dir = create_run_dir(base)
    log = _log_path(run_dir)
    _log(log, f"START run={run_dir.name}")

    # Snapshot thesis/ before any work
    snapshot_thesis(repo_root / "thesis", run_dir / "thesis_before")

    def _claude(prompt, cwd, out):
        rc = run_claude(prompt=prompt, cwd=cwd, output_file=out, log_file=log)
        if rc != 0:
            raise CliFailure(f"claude rc={rc} on {out.name}")

    def _codex(prompt, cwd, out):
        rc = run_codex(prompt=prompt, cwd=cwd, output_file=out, log_file=log)
        if rc != 0:
            raise CliFailure(f"codex rc={rc} on {out.name}")

    iter_summaries: list[tuple[str, list[dict]]] = []

    try:
        # Step 1
        p = render_prompt(_prompts(repo_root) / "01_thesis_review.txt", {})
        review_v1 = run_dir / "review_v1.md"
        _claude(p, repo_root / "thesis", review_v1)

        # Step 2
        p = render_prompt(_prompts(repo_root) / "02_codex_second_opinion.txt",
                          {"review_v1_path": str(review_v1)})
        review_final = run_dir / "review_final.md"
        _codex(p, repo_root, review_final)

        # Plan loop
        plan_path: Path | None = None
        prev_verdict: Path | None = None
        approved = False
        for n in range(1, max_plan_iters + 1):
            iter_dir = plan_iter_dir(run_dir, n)
            iter_dir.mkdir(parents=True, exist_ok=True)
            if prev_verdict is None:
                p = render_prompt(_prompts(repo_root) / "03_plan.txt",
                                  {"review_final_path": str(review_final)})
            else:
                p = render_prompt(_prompts(repo_root) / "03_plan_followup.txt", {
                    "plan_verdict_path": str(prev_verdict),
                    "review_final_path": str(review_final),
                    "prev_plan_path": str(plan_path),
                })
            plan_path = iter_dir / "fix_plan.md"
            _claude(p, repo_root, plan_path)

            p = render_prompt(_prompts(repo_root) / "04_plan_verify.txt", {
                "plan_path": str(plan_path),
                "review_final_path": str(review_final),
            })
            verdict_path = iter_dir / "plan_verdict.md"
            _codex(p, repo_root, verdict_path)
            verdict = parse_verdict(verdict_path.read_text(encoding="utf-8"))
            _log(log, f"plan iter {n}: {verdict}")
            if verdict == "APPROVE":
                approved = True
                break
            prev_verdict = verdict_path
        if not approved:
            _log(log, "plan loop CAP HIT")
            _write_run_changes(run_dir, iter_summaries, "PLAN_CAP")
            return 1

        # Fix loop
        prev_final: Path | None = None
        for n in range(1, max_fix_iters + 1):
            iter_dir = fix_iter_dir(run_dir, n)
            iter_dir.mkdir(parents=True, exist_ok=True)
            if prev_final is None:
                p = render_prompt(_prompts(repo_root) / "05_execute.txt", {
                    "plan_path": str(plan_path),
                    "review_final_path": str(review_final),
                })
            else:
                p = render_prompt(_prompts(repo_root) / "05_execute_followup.txt", {
                    "final_verdict_path": str(prev_final),
                    "plan_path": str(plan_path),
                })
            exec_log = iter_dir / "execution_log.md"
            _claude(p, repo_root, exec_log)

            # Snapshot + diff after execution
            after_dir = iter_dir / "thesis_after"
            snapshot_thesis(repo_root / "thesis", after_dir)
            summary = diff_thesis(run_dir / "thesis_before", after_dir,
                                  iter_dir / "diffs")
            _write_iter_changes(iter_dir, summary)
            iter_summaries.append((iter_dir.name, summary))

            p = render_prompt(_prompts(repo_root) / "06_final_verify.txt", {
                "plan_path": str(plan_path),
                "review_final_path": str(review_final),
                "execution_log_path": str(exec_log),
            })
            final_verdict = iter_dir / "final_verdict.md"
            _codex(p, repo_root, final_verdict)
            verdict = parse_verdict(final_verdict.read_text(encoding="utf-8"))
            _log(log, f"fix iter {n}: {verdict}")
            if verdict == "APPROVE":
                _log(log, "DONE APPROVE")
                _write_run_changes(run_dir, iter_summaries, "APPROVE")
                return 0
            prev_final = final_verdict

        _log(log, "fix loop CAP HIT")
        _write_run_changes(run_dir, iter_summaries, "FIX_CAP")
        return 2

    except CliFailure as exc:
        _log(log, f"FAILURE {exc}")
        _write_run_changes(run_dir, iter_summaries, "CLI_FAILURE")
        return 3
```

- [ ] **Step 4: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestPipeline -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): main pipeline with snapshots, diffs, and CHANGES.md"
```

---

## Task 9: CLI entry point (--dry-run, --list-runs)

**Files:** `scripts/auto_review.py`, `tests/test_auto_review.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auto_review.py`:

```python
class TestEntryPoint:
    def test_dry_run_no_subprocess(self, tmp_path, monkeypatch, capsys):
        repo = tmp_path / "repo"
        (repo / "scripts" / "auto_review_prompts").mkdir(parents=True)
        (repo / "thesis").mkdir()

        def boom(*a, **kw):
            raise AssertionError("should not invoke subprocess in --dry-run")

        monkeypatch.setattr(auto_review.subprocess, "run", boom)
        rc = auto_review.main(["--repo-root", str(repo), "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out.lower()
        assert "step 1" in out and "step 6" in out

    def test_default_iters(self, monkeypatch):
        seen = {}

        def fake(repo_root, max_plan_iters, max_fix_iters):
            seen.update(plan=max_plan_iters, fix=max_fix_iters)
            return 0

        monkeypatch.setattr(auto_review, "run_pipeline", fake)
        rc = auto_review.main(["--repo-root", "/tmp/x"])
        assert rc == 0 and seen == {"plan": 3, "fix": 3}

    def test_list_runs(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        base = repo / ".review-cycle"
        run1 = base / "2026-05-15T10-00-00"
        run1.mkdir(parents=True)
        (run1 / "CHANGES.md").write_text("**Final verdict:** APPROVE\n")
        run2 = base / "2026-05-15T11-00-00"
        run2.mkdir(parents=True)
        # no CHANGES.md => incomplete
        rc = auto_review.main(["--repo-root", str(repo), "--list-runs"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "2026-05-15T10-00-00" in out and "APPROVE" in out
        assert "2026-05-15T11-00-00" in out and "incomplete" in out.lower()
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_auto_review.py::TestEntryPoint -v
```

- [ ] **Step 3: Implement `main` + `__main__`**

Append to `scripts/auto_review.py`:

```python
import argparse
import sys


def _list_runs(repo_root: Path) -> int:
    base = Path(repo_root) / ".review-cycle"
    if not base.exists():
        print(f"No runs at {base}")
        return 0
    rows = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        changes = d / "CHANGES.md"
        verdict = "incomplete"
        if changes.exists():
            for line in changes.read_text(encoding="utf-8").splitlines():
                if line.startswith("**Final verdict:**"):
                    verdict = line.split("**", 2)[2].strip().lstrip(":").strip()
                    break
        rows.append((d.name, verdict))
    for name, verdict in rows:
        print(f"{name}  {verdict}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CC <-> Codex auto-review loop")
    parser.add_argument("--repo-root", default=".", help="Project root (default: cwd)")
    parser.add_argument("--max-plan-iters", type=int, default=3)
    parser.add_argument("--max-fix-iters", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned steps; no CLI calls")
    parser.add_argument("--list-runs", action="store_true",
                        help="List all .review-cycle/ runs and verdicts")
    args = parser.parse_args(argv)

    repo = Path(args.repo_root).resolve()

    if args.list_runs:
        return _list_runs(repo)

    if args.dry_run:
        print("Auto-review plan (dry run):")
        print("  step 0: snapshot thesis/                     -> thesis_before/")
        print("  step 1: claude -p   thesis review            -> review_v1.md")
        print("  step 2: codex exec  second opinion           -> review_final.md")
        print(f"  step 3: claude -p   plan       (<= {args.max_plan_iters} iters) -> fix_plan.md")
        print("  step 4: codex exec  plan verdict             -> plan_verdict.md")
        print(f"  step 5: claude -p   execute    (<= {args.max_fix_iters} iters) -> execution_log.md")
        print("          + snapshot thesis/ + write diffs")
        print("  step 6: codex exec  final verdict            -> final_verdict.md")
        return 0

    return run_pipeline(
        repo_root=repo,
        max_plan_iters=args.max_plan_iters,
        max_fix_iters=args.max_fix_iters,
    )


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run, expect pass**

```bash
python -m pytest tests/test_auto_review.py::TestEntryPoint -v
```

- [ ] **Step 5: Run full file**

```bash
python -m pytest tests/test_auto_review.py -v
```
Expected: all tests pass (~24 total).

- [ ] **Step 6: Live `--dry-run` smoke**

```bash
python scripts/auto_review.py --dry-run
```
Expected: 7 lines printed (step 0 + steps 1-6), exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/auto_review.py tests/test_auto_review.py
git commit -m "feat(auto-review): argparse entry with --dry-run and --list-runs"
```

---

## Task 10: Slash command wrapper

**Files:** `.claude/commands/auto-review.md`

- [ ] **Step 1: Create slash command**

Create `.claude/commands/auto-review.md`:

```markdown
---
description: Run the auto-review loop (Claude Code <-> Codex CLI) on the thesis
---

Run the orchestrator with any user-supplied flags:

```bash
python scripts/auto_review.py $ARGUMENTS
```

When it finishes, report:
- Exit code meaning (0 APPROVE / 1 plan-cap / 2 fix-cap / 3 CLI failure)
- Path to the run directory under `.review-cycle/`
- Contents of `CHANGES.md` summary at the run root
- For non-zero exits: also print the last 40 lines of the latest verdict file so the user can decide whether to retry or adjust prompts
```

- [ ] **Step 2: Verify**

```bash
ls -la .claude/commands/auto-review.md
```

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/auto-review.md
git commit -m "feat(auto-review): /auto-review slash command"
```

---

## Task 11: README usage section

**Files:** `README.md`

- [ ] **Step 1: Append usage section**

Append to `README.md` (or insert in an existing tooling section if present):

```markdown
## Auto-review loop

Automates the manual Claude Code <-> Codex CLI back-and-forth that produces a vetted thesis review and verified fix execution. Each run snapshots `thesis/` and writes per-file diffs so you can see exactly what changed.

```bash
# from inside Claude Code
/auto-review

# direct
python scripts/auto_review.py
python scripts/auto_review.py --dry-run               # print planned steps, no LLM calls
python scripts/auto_review.py --max-plan-iters 5      # raise plan-loop cap
python scripts/auto_review.py --list-runs             # past runs + their verdicts
```

Artifacts land in `.review-cycle/<timestamp>/` (gitignored): full `thesis_before/` snapshot, per-iteration `thesis_after/`, per-file `diffs/*.diff`, and a top-level `CHANGES.md` summary.

Exit codes: 0 approve, 1 plan-loop cap, 2 fix-loop cap, 3 sub-CLI failure. Full spec: `docs/superpowers/specs/2026-05-15-auto-review-loop-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document auto-review loop in README"
```

---

## Task 12: Final integration sweep

- [ ] **Step 1: Full test suite**

```bash
make test 2>&1 | tail -30
```
Expected: green (or unchanged from pre-task baseline — capture that with `make test` once before starting Task 1).

- [ ] **Step 2: Lint**

```bash
make lint
```
Expected: clean. Fix any ruff complaints in `scripts/auto_review.py` or `tests/test_auto_review.py`, then re-commit.

- [ ] **Step 3: Notes decision entry**

Append to `notes/decisions.md`:

```markdown
- 2026-05-15 -- Added `scripts/auto_review.py` + `/auto-review` slash command: shells out to `claude -p` and `codex exec` to fully automate the thesis-review -> fix -> verify loop with bounded retries (3 plan iters, 3 fix iters). Each run snapshots `thesis/` and writes per-file diffs so changes are auditable across runs. Verdict protocol: last-line `VERDICT: APPROVE|REJECT`. Spec: `docs/superpowers/specs/2026-05-15-auto-review-loop-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add notes/decisions.md
git commit -m "notes: record auto-review loop decision"
```

---

## Intentionally out of scope

- `--resume DIR` flag — detecting last-completed step from disk artifacts. Useful but not blocking; add later if needed.
- Live LLM integration tests in CI — non-deterministic, expensive.
- Parallel step execution — steps are serial by design.
- Git-based versioning (tags or branch per run) — file snapshots already give you full history without touching git.

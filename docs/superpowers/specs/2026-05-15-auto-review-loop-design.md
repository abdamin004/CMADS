# Auto-Review Loop: Claude Code ↔ Codex CLI

**Date:** 2026-05-15
**Status:** Design — awaiting approval
**Owner:** islam.amin099@gmail.com

## Goal

Automate the manual back-and-forth between Claude Code (CC) and Codex CLI that currently produces a polished pass over the bachelor thesis plus a verified code/fix cycle on the main project. The user kicks off one command and walks away; the loop self-terminates on Codex approval or iteration cap.

## Non-goals

- Replacing either CLI with API calls — both tools stay as they are.
- Editing thesis prose directly in step 1; that stage produces a review document, not edits.
- Sharing model state across runs — each run is a clean state machine on disk.

## Workflow (state machine)

```
[1] CC(cwd=thesis/)   reads thesis sources           → review_v1.md
[2] Codex             reads review_v1 + thesis       → review_final.md
[3] CC(cwd=repo root) reads review_final             → fix_plan.md          ┐
[4] Codex             reads fix_plan + review_final  → plan_verdict.md     │ plan loop
        REJECT → loop to [3] with plan_verdict.md feedback (≤ MAX_PLAN_ITERS) ┘
        APPROVE → continue
[5] CC(cwd=repo root) executes fix_plan.md           → execution_log.md    ┐
[6] Codex             reads plan + diff + thesis     → final_verdict.md    │ fix loop
        REJECT → loop to [5] with final_verdict.md residuals (≤ MAX_FIX_ITERS) ┘
        APPROVE → done
```

**Loop caps (defaults):**
- `MAX_PLAN_ITERS = 3` — plan refinement converges fast; if not, prompts need work.
- `MAX_FIX_ITERS = 3` — execution residuals; if not, the plan was wrong.

On cap-hit: orchestrator exits non-zero, prints the latest verdict path, and leaves all artifacts on disk for manual continuation.

## Components

### 1. Orchestrator — `scripts/auto_review.py`

Python 3 script, no new deps (uses `subprocess`, `pathlib`, `argparse`, `datetime`). Responsibilities:

- Create a per-run working directory: `.review-cycle/<ISO-timestamp>/`
- Render prompts from templates in `scripts/auto_review_prompts/` with `{placeholder}` substitution
- Shell out to `claude -p` and `codex exec`, redirecting stdout to artifact files
- Parse the last line of every Codex verdict file for `VERDICT: APPROVE` or `VERDICT: REJECT`
- Drive the two loops with explicit `while` blocks and caps
- Maintain a single `transcript.log` with timestamps, command lines, exit codes, and artifact paths

Public surface:

```
python scripts/auto_review.py [--max-plan-iters N] [--max-fix-iters N] [--dry-run] [--resume DIR]
```

Exit codes:
- `0` — final Codex verdict APPROVE
- `1` — plan loop hit cap
- `2` — fix loop hit cap
- `3` — sub-CLI returned non-zero / parse failure

### 2. Prompt templates — `scripts/auto_review_prompts/`

One file per step, plain text with `{var}` placeholders:

- `01_thesis_review.txt` — instructs CC to review every chapter in `thesis/`, output a structured review with sections for issues, suggested rewrites, citations, figures, and consistency.
- `02_codex_second_opinion.txt` — feeds Codex `review_v1.md` and the thesis dir, asks it to merge/refine, flag anything missed, and emit a single `review_final.md`.
- `03_plan.txt` — feeds CC `review_final.md`, asks for a numbered fix plan with file paths and concrete actions.
- `04_plan_verify.txt` — Codex checks plan covers every issue in `review_final.md`; emits notes + `VERDICT:` line.
- `04_plan_verify_followup.txt` — same as above but appended with prior `plan_verdict.md` so CC sees what to address.
- `05_execute.txt` — CC reads `fix_plan.md` and applies changes; emits `execution_log.md` summarizing what was modified.
- `06_final_verify.txt` — Codex compares state against `review_final.md` issue-by-issue; emits `final_verdict.md` with residuals and `VERDICT:` line.
- `06_final_verify_followup.txt` — appended with prior `final_verdict.md` for the residual-fix round.

Keeping prompts in files (not embedded in Python) lets you iterate on tone/coverage without touching the orchestrator.

### 3. Slash-command wrapper — `.claude/commands/auto-review.md`

A Claude Code custom command so the user can trigger from inside CC:

```
---
description: Run the full thesis review + fix automation loop (CC ↔ Codex)
---
Run `python scripts/auto_review.py "$ARGUMENTS"` and report the result. Surface the final verdict path and key residuals if rejected.
```

The command itself is trivial — it just shells out. The orchestrator does the work.

### 4. Verdict protocol

Codex steps MUST end their output with one line:

```
VERDICT: APPROVE
```
or
```
VERDICT: REJECT
```

Orchestrator greps the **last non-empty line** of the verdict file. If neither token is found, treat as REJECT and log a parse warning. Prompts include this contract explicitly to make compliance reliable.

## CLI invocation details

**Claude Code headless:**
```
claude -p "$(cat prompt_file)" --permission-mode acceptEdits
```
- `-p` runs in non-interactive print mode
- `--permission-mode acceptEdits` allows step 5 to actually modify files without per-tool prompts
- `cwd` is set per step (`thesis/` for step 1, repo root otherwise)

**Codex headless:**
```
codex exec "$(cat prompt_file)"
```
- `exec` is Codex's non-interactive mode
- `cwd` always repo root so Codex can read both `thesis/` and source code

Both invocations capture stdout to the artifact path; stderr is teed into `transcript.log`.

## Artifact layout

```
.review-cycle/2026-05-15T14-32-00/
  transcript.log
  CHANGES.md                 # cross-iteration summary written at end of run
  thesis_before/             # full snapshot of thesis/ taken before step 1
    ...
  review_v1.md
  review_final.md
  iter_01/
    fix_plan.md
    plan_verdict.md          # REJECT — residual #3,#7
  iter_02/
    fix_plan.md
    plan_verdict.md          # APPROVE
  fix_iter_01/
    execution_log.md
    thesis_after/            # snapshot taken after step 5 of this iter
    diffs/                   # one .diff file per changed thesis file
      methodology.tex.diff
      results.tex.diff
    thesis_changes.md        # per-iter summary: "M file (+x -y)" + diff links
    final_verdict.md         # REJECT — issue #5 unresolved
  fix_iter_02/
    execution_log.md
    thesis_after/
    diffs/
    thesis_changes.md
    final_verdict.md         # APPROVE
```

`.review-cycle/` is added to `.gitignore`.

## Thesis versioning

Each run preserves a full snapshot of `thesis/` and a per-iteration diff so the user can audit what each run changed.

- **Before step 1:** `shutil.copytree(repo/thesis, run_dir/thesis_before)` (excludes `__pycache__`, `*.aux`, `*.log`, `*.bbl`, `*.pdf`, `*.synctex.gz` — build artifacts).
- **After step 5, each fix iteration:** `shutil.copytree(repo/thesis, run_dir/fix_iter_NN/thesis_after)`, then walk both trees and for every changed file write `diffs/<flattened-path>.diff` using `difflib.unified_diff`. Path flattening: `thesis/chapters/methodology.tex` → `chapters__methodology.tex.diff` (avoids nested mkdir).
- **At end of run:** write `CHANGES.md` listing run timestamp, final verdict, and per-iteration summary table: file path + `+added/-removed` line counts + relative link to the `.diff`.
- **`--list-runs` flag:** prints all `.review-cycle/*` directories with their final verdict (read the last line of the latest `final_verdict.md` if present, else "incomplete").

Versioning is stdlib-only (`shutil`, `difflib`, `pathlib`). It does NOT touch git. In-progress unstaged edits on `thesis/` are preserved untouched — snapshots are independent copies.

## Error handling

- **CLI non-zero exit:** orchestrator exits with code 3 immediately, logging which step failed.
- **Empty or malformed artifact:** treated as REJECT for verdict files; hard failure for any other step.
- **Loop cap hit:** non-zero exit with caps' code; artifacts preserved for manual continuation.
- **Interrupted run (Ctrl-C):** transcript captures partial state; `--resume DIR` allows restart from the last completed step by inspecting which artifact files exist.

## Testing

- **Unit:** verdict parser (`APPROVE` / `REJECT` / missing / mixed-case / extra whitespace).
- **Integration (mocked):** monkeypatch `subprocess.run` to return canned outputs; verify state-machine transitions and artifact paths.
- **Smoke:** `--dry-run` mode prints the planned command sequence without invoking CLIs.

No live LLM tests in CI — they're non-deterministic and expensive.

## What's deliberately out of scope

- Cross-run learning. Each run is independent.
- Parallelism. Steps are inherently sequential; no benefit.
- Web UI / dashboard. Transcript file is enough.
- Auto-commit of thesis edits. Step 5 modifies files; the user reviews and commits manually.

## Open questions

None — all decisions captured above. Loop caps and slash wrapper confirmed by user 2026-05-15.

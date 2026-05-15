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

"""Tests for scripts/auto_review.py orchestrator."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import auto_review  # noqa: E402


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
        assert (run / "fix_iter_01" / "diffs" / "main.tex.diff").exists()
        assert (run / "fix_iter_01" / "thesis_changes.md").exists()


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

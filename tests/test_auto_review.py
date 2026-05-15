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

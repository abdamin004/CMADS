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

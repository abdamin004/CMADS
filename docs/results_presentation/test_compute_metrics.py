"""Tests for compute_metrics — the deck's source of numbers.

We anchor on the numbers from notes/experiments.md so a future cohort
recompute that drifts will fail loudly here before the deck is rebuilt.
"""

from __future__ import annotations

from pathlib import Path

from compute_metrics import compute

REPO = Path(__file__).resolve().parents[2]


def test_paired_160_strict_judge():
    """The paired 160 cohort uses the strict (original) judge across
    both arms. Memory shows no measurable effect on DIRECT but does
    catch slightly more in the wider differential (+1.9 pp Found,
    -1.9 pp MISS on the same UUIDs)."""
    m = compute(REPO)
    s = m["cohorts"]["paired_single_level_160"]
    ml = m["cohorts"]["paired_multi_level_160"]
    b = m["cohorts"]["single_level_baseline"]

    # Headline baseline preserved at strict-judge values
    assert b["n"] == 160
    assert b["DIRECT_pct"] == 73.1, b["DIRECT_pct"]

    # Paired arms at strict judge
    assert s["n"] == 160
    assert ml["n"] == 160
    assert 51 <= s["DIRECT_pct"] <= 55, s["DIRECT_pct"]   # 53.1
    assert 50 <= ml["DIRECT_pct"] <= 54, ml["DIRECT_pct"] # 52.5
    # Memory's measurable effect is on Found, not DIRECT
    assert ml["found_pct"] > s["found_pct"], "Multi-level should beat single-level on Found"


def test_single_level_baseline():
    """The single-level baseline aggregates every evaluated patient in
    data/gold/mas_results/ (no memory subsystem). Current on-disk count
    is 160 patients; anchor on that. If the directory grows or shrinks,
    update this test (and the slide copy) together."""
    m = compute(REPO)
    b = m["cohorts"]["single_level_baseline"]
    assert b["n"] == 160
    assert b["DIRECT"] == 117
    assert b["INDIRECT"] == 23
    assert b["MISS"] == 20
    assert b["DIRECT_pct"] == 73.1
    assert b["found_pct"] == 87.5


def test_paired_mcnemar_block():
    m = compute(REPO)
    p = m["paired_mcnemar"]
    assert p["n_paired"] == 20
    assert p["off_direct_rate"] == 0.40
    assert p["on_direct_rate"] == 0.45
    cont = p["contingency"]
    assert cont["both_DIRECT"] == 6
    assert cont["only_OFF_DIRECT"] == 2
    assert cont["only_ON_DIRECT"] == 3
    assert cont["neither_DIRECT"] == 9
    assert p["mcnemar_p_two_sided"] == 1.0


def test_baseline_strict_judge_preserved():
    """The thesis's Section 4.1 headline of 73.1% DIRECT / 87.5% Found
    must remain reproducible from data/gold/mas_results/. The directory
    is now permanently at the strict-judge state (evaluation_strict.json
    was copied back over evaluation.json after the relaxed-judge re-run)."""
    m = compute(REPO)
    b = m["cohorts"]["single_level_baseline"]
    assert b["DIRECT"] == 117, b["DIRECT"]
    assert b["INDIRECT"] == 23, b["INDIRECT"]
    assert b["MISS"] == 20, b["MISS"]
    assert b["found"] == 140, b["found"]
    assert b["found_pct"] == 87.5, b["found_pct"]

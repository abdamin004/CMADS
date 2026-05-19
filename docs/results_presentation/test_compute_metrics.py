"""Tests for compute_metrics — the deck's source of numbers.

We anchor on the numbers from notes/experiments.md so a future cohort
recompute that drifts will fail loudly here before the deck is rebuilt.
"""

from __future__ import annotations

from pathlib import Path

from compute_metrics import compute

REPO = Path(__file__).resolve().parents[2]


def test_combined_100_patient_numbers():
    m = compute(REPO)

    cold = m["cohorts"]["batch_3_cold_start"]
    assert cold["n"] == 50
    assert cold["DIRECT"] == 23
    assert cold["INDIRECT"] == 23
    assert cold["MISS"] == 4
    assert cold["found"] == 46
    assert cold["DIRECT_pct"] == 46.0
    assert cold["found_pct"] == 92.0

    warm = m["cohorts"]["batch_4_warmed"]
    assert warm["n"] == 50
    assert warm["DIRECT"] == 26
    assert warm["found"] == 49
    assert warm["DIRECT_pct"] == 52.0
    assert warm["found_pct"] == 98.0

    combined = m["cohorts"]["combined_100"]
    assert combined["n"] == 100
    assert combined["DIRECT"] == 49
    assert combined["INDIRECT"] == 46
    assert combined["MISS"] == 5
    assert combined["DIRECT_pct"] == 49.0
    assert combined["found_pct"] == 95.0


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


def test_rank1_in_found_per_cohort():
    """Rank-1-in-found is computed per cohort by reading each patient's
    evaluation.json directly. The older 37%/27% numbers in
    notes/experiments.md were from a different computation path; the
    on-disk truth — and what the deck must show — is 70% / 61% / 65%
    (cold / warmed / combined)."""

    m = compute(REPO)
    cold = m["cohorts"]["batch_3_cold_start"]
    warm = m["cohorts"]["batch_4_warmed"]
    combined = m["cohorts"]["combined_100"]

    assert 67 <= cold["rank1_in_found_pct"] <= 72, cold["rank1_in_found_pct"]
    assert 59 <= warm["rank1_in_found_pct"] <= 64, warm["rank1_in_found_pct"]
    assert 63 <= combined["rank1_in_found_pct"] <= 68, combined["rank1_in_found_pct"]

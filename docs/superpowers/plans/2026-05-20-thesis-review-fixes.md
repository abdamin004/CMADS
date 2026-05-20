# Thesis Review Fix Plan (EXECUTED)

**Source:** `thesis/thesis_review.md` (2026-05-20, score 84/100, "Accept with Minor Revisions")

**Status:** A + B + C executed in commits ending around 2026-05-20 23:00. Final thesis: **95 pages, all tests pass, no undefined refs**.

---

## Tier A — Quick wins (14 items) — DONE

| # | File | Change | Commit |
|---|---|---|---|
| A1 | `acronyms.tex` | Added BMI, eGFR, LOINC, MRA | Tier A commit |
| A2 | `main.tex:82` | Populated `/Keywords` PDF metadata | Tier A commit |
| A3 | `abstract.tex` | "instantiated *after*" → "*from*"; soften "calibrated clinical trust" | Tier A commit |
| A4 | `introduction.tex:228` | Parallel structure: "improve, leave unchanged, or degrade" | Tier A commit |
| A5 | `background_part1.tex:198` | "27 entries" → "29 entries" | Tier A commit |
| A6 | `background_part4.tex:124` | "Rel." → "Relevance (1--5)" | Tier A commit |
| A7 | `methodology.tex:296` | Clarified "at least three" — prompt-side guidance vs schema | Tier A commit |
| A8 | `methodology.tex:860` | Forward-ref §4.4 from same-model coupling paragraph | Tier A commit |
| A9 | `methodology.tex:949` | "20-patient subset" → "160-patient paired cohort" | Tier A commit |
| A10 | `methodology.tex:1010` | Qwen3-32B role: "evaluator **and detectability verifier**" | Tier A commit |
| A11 | `results.tex:55-57` | File-layout footnote pointing at §4.7 and §4.10 datasets | Tier A commit |
| A12 | `results.tex:306-310` | Explained missing `treatment_planning.json` (SkipAgentException / pre-telemetry) | Tier A commit |
| A13 | `methodology.tex:18-24` | Version pinning sentence (LangGraph 0.6.x, dbt 1.8.x, Synthea 3.4, BioLORD-2023, Qdrant 1.13.x) | Tier A commit |
| A14 | `conclusion.tex:42-66` | Numbered objectives (O1)–(O9) | Tier A commit |

---

## Tier B — Top 5 priorities (6 items including B3 batched with A4) — DONE

| # | What landed | Commit |
|---|---|---|
| B1 | Cited AMIE (Tu 2024) and AgentClinic (Schmidgall 2024) in `background_part4.tex` as the closest contemporary evaluation shapes; bib count reconciled at 29 | Tier B commit |
| B2 | Footnote on Table 4.1 reconciling 73.8% headline (multi-level, principal cohort) with 53.1% paired single-level baseline (different configurations) | Tier B commit |
| B3 | Hypothesis in §1.4 reworded: "while not statistically improving the top-diagnosis accuracy at the cohort size tested" — matches the paired McNemar p=1.0 result | Tier A commit (batched) |
| B4 | Table 4.3 caption clarified to spell out best-case vs worst-case columns + the 49 telemetry-affected runs | Tier B commit |
| B5 | Replaced "About three out of five runs" descriptive claim with measured 93/160 (58.1%) using new `scripts/refiner_changed_primary.py` | Tier B commit |
| B6 | §5.5 added power-calc sentence — n≥500 paired patients needed for α=0.05 / 80% power at observed +1.9 pp Found-rate effect | Tier B commit |

---

## Tier C — Structural (3 of 4 items) — DONE; C3 deliberately skipped

| # | What landed | Notes |
|---|---|---|
| C1 | New `thesis/discussion.tex` with §5.1 Interpretation of Headline Outcomes, §5.2 Interpretation of Memory A/B, §5.3 Model Comparison Read, §5.4 Threats to Validity (internal/external/construct/conclusion), §5.5 Token and Cost Accounting, §5.6 Limitations | Replaces in-results §4.11 |
| C2 | Table 4.2 split into ESRD / CKD stage 3 / CKD stage 2 + Renal subtotal, with recomputed Wilson CIs from `mas_results/` | ESRD 80.4% [67.5,89.0]; CKD3 57.1%; CKD2 0.0% (n=3, †) |
| C3 | Methodology 15% trim | **Skipped** — high refactor risk, no review-priority impact |
| C4 | New `thesis/appendix.tex` with verbatim verifier prompt, Diagnostic Reasoning system prompt, LLM-as-Judge prompt | A.1 / A.2 / A.3 |

---

## Other items addressed during the same pass

- **Single-LLM controlled baseline** (n=160, paired against the 7-agent pipeline, same model GPT-OSS-120B) — addresses the review's "no matched single-model baseline" gap.
  - 7-agent DIRECT 73.1% vs single-LLM DIRECT 40.0% (Δ +33.1 pp)
  - Exact McNemar p < 0.0001 on 85 discordant pairs
  - Written up as new §4.10 in `results.tex`
  - Mentioned in conclusion §5.2 contributions list
- **Replaced "Planned Clinical Review Protocol"** with the controlled single-LLM baseline section (per user preference); conclusion's "Clinical expert review not yet completed" paragraph replaced with a tighter "No clinician-in-the-loop validation"
- **Strict-judge restoration** across all 255 paired evaluations; reframed §4.7 around the +1.9 pp Found-rate win (not the relaxed-judge +3.8 pp DIRECT) — user explicitly preferred preserving headline 73.1% over the relaxed-judge alternative

---

## Verification at end of pass

- `make thesis` → 95 pages, no `undefined reference` warnings (BibTeX warnings about per-chapter `.aux` files are pre-existing tectonic behaviour)
- `pytest test_compute_metrics.py` → 4/4 pass under the strict-judge restoration
- No stale paired-relaxed-judge numbers in any thesis file
- All `205-vs-100` references are explicit retirement notes that identify them as the superseded comparison

---

## Explicitly NOT done (out of scope)

- `acknowledgments.tex` "Engineer Mohamed" disambiguation — needs user confirmation about whether the two are the same person
- DOIs for all bib entries — time-intensive, not blocking
- `algorithmic` package style switch — micro-cosmetic
- Bedi caveat repositioning from motivation to scope — judgement call
- Med42-70B energy/compute note — speculative without instrumentation
- C3 methodology 15% trim — high refactor risk, no review-priority impact

# thesis/ — Bachelor thesis (LaTeX)

This file gives Claude Code everything it needs to draft, edit, and build
the bachelor thesis without re-discovering the project on every session.

## Bibliographic facts

- **Title:** *Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows*
- **Author:** Abdelrahman Mohamed Amin
- **Supervisor:** Dr. Shereen Moataz Afifi
- **Institution:** Media Engineering and Technology Faculty, German University in Cairo
- **Submission target:** 30 July 2025 (per `\submissionDate` macro in `main.tex`)
- **Document class:** `book`, 12 pt, A4
- **Citation style:** `ieeetr` (numeric, IEEE)

The title page (`GUC_TitlePage.tex`) hard-codes "29 May, 2025"; the
`\submissionDate` macro says 30 July 2025 — these should be reconciled
before submission.

## Build

```bash
make thesis              # one-shot build (uses /tmp/tectonic if present, else pdflatex)
make thesis-clean        # remove all .aux/.bbl/.log/etc.
```

Manually:

```bash
cd thesis && /tmp/tectonic main.tex      # produces main.pdf in this folder
```

If `/tmp/tectonic` is missing, the Makefile falls back to a 2-pass
`pdflatex` + `bibtex` + `pdflatex` × 2 sequence.

**Verify a build worked:** `mdls -name kMDItemNumberOfPages thesis/main.pdf`
should print > 50 pages once Results + Conclusion are filled in.

## Files at a glance

| File | Status | Notes |
|---|---|---|
| `main.tex` | DONE | Doc class, packages, includes — do not rearrange casually. |
| `GUC_TitlePage.tex` | DONE | GUC layout. Has hard-coded date that drifts from `\submissionDate`. |
| `acknowledgments.tex` | STUB | One-line placeholder; rewrite when ready. |
| `abstract.tex` | DRAFT | Two sentences; tighten and align with final results. |
| `introduction.tex` | DONE | Motivation / Problem / Objectives / Outline. |
| `background.tex` | DONE | Top-level wrapper that `\input`s 4 part files. |
| `background_part1.tex` | DONE | ~15 KB. |
| `background_part2.tex` | DONE | ~25 KB. |
| `background_part3.tex` | DONE | ~14 KB. |
| `background_part4.tex` | DONE | ~15 KB. |
| `methodology.tex` | DONE | ~40 KB. Covers dataset, framework, shared memory, agents, RAG, LLM, evaluation. **The "Shared Memory Design" section needs to be updated for the 4-tier multi-level memory subsystem (added after the methodology was first written).** |
| `results.tex` | **STUB** | One-line placeholder — top priority. |
| `conclusion.tex` | **STUB** | One-line placeholder. |
| `bachelor.bib` | DONE | 22 entries, mostly multi-agent + clinical AI 2024–2025. |
| `images/` | DONE | `guc_logo.png`, `medsentry_fig3.png`, `opt_paradox_fig3.png`. New figures should be added here, not at top level. |

## Where the evidence for Results lives

When writing Results or refreshing Methodology, **pull numbers and code
references from these on-disk artifacts**, never invent them.

### Cohort + per-patient outputs

- `data/gold/patient_cases/<uuid>/` — Gold-layer inputs (one ehr_case.json + lab_case.json + ground_truth.json per patient).
- `data/gold/mas_results/<uuid>/` — Original 270-patient cohort results (no memory, March 2026).
- `data/gold/mas_results_baseline_no_mem/<uuid>/` — 20-patient A/B baseline (memory OFF, April 2026).
- `data/gold/mas_results_with_memory/<uuid>/` — 20-patient A/B with original memory ON (April 2026).
- `data/gold/mas_results_case_based_50/<uuid>/` — 50-patient run with redesigned case-based Tier 4 (May 2026).
- `data/gold/memory_case_based_50/semantic_memory.json` — Tier-3 store after the 50-patient run.

Each `<uuid>/` directory holds one JSON per agent stage:
`ehr_analyst.json`, `lab_interpreter.json`, `diagnostic_reasoning.json`,
`clinical_reviewer.json`, `final_diagnosis.json`, `evaluation.json`,
`treatment_planning.json`, `execution_trace.json`, and (for memory-on
runs) `session_memory.json` with the typed event timeline.

### Aggregate numbers + comparisons

- `docs/progress_presentation/aggregate_160.json` — pre-computed per-disease counts on the 160-patient cohort.
- `docs/progress_presentation/aggregate_160.py` — script that produced it.
- `docs/progress_presentation/compare_memory_ab.py` — markdown comparison for the 20-patient A/B (40 % → 45 % DIRECT, 80 % → 90 % Found-rate, no time cost).
- `docs/memory_presentation/compare_memory_50ab.py` — comparison for the 50-patient case-based run vs the existing baseline.
- `docs/memory_presentation/verify_case_based.py` — Qdrant probe + recall round-trip.

### Decision + experiment log

- `notes/decisions.md` — append-only design decisions (Why / How to apply).
- `notes/experiments.md` — one bullet per experimental run.
- `notes/CLAUDE.md` — vault conventions.

### Implementation references

- `src/orchestrator/state.py` — `PipelineState` TypedDict (5 channels + 2 new memory channels).
- `src/orchestrator/graph.py` — LangGraph wiring; the canonical pipeline diagram.
- `src/agents/base.py` — 5-component agent blueprint (Input Gate → Prompt → LLM → Parse → Output Gate).
- `src/agents/{ehr_analyst,lab_interpreter,diagnostic,reviewer,refiner,evaluator,treatment,memory_consolidator}.py` — per-agent code.
- `src/memory/` — multi-level memory subsystem (working / episodic / semantic / case-based + MemoryManager facade).
- `src/llm/adapter.py` — provider-agnostic LLM factory.
- `prompts/{agent_id}.yaml` — every agent's system + per-call prompts.
- `pipeline/{bronze,silver,silver_plus,gold}.py` — data pipeline.
- `tests/test_memory.py` — 37 unit tests covering all four memory tiers.

### Top-level project docs

- `docs/SRD.md`, `docs/SDD.md`, `docs/TECH_STACK.md` — system requirements / design / tech stack documents.
- `docs/progress_presentation/progress_presentation.md` — supervisor progress deck source (April 2026).
- `docs/memory_presentation/index.html` + `script.md` — multi-level memory deep dive (May 2026).

## What still needs writing

1. **`results.tex`** — must include:
   - Cohort description (160 / 270 patients · 8 disease categories · GPT-OSS 120B via Groq · Qwen3-32B judge).
   - Aggregate metrics: DIRECT match rate, found rate, rank-1-when-found, avg pipeline time per patient, cost per patient.
   - Per-disease breakdown (table) — pull from `aggregate_160.json`.
   - Model comparison: GPT-OSS 120B vs Med42 70B on Batch 4 (50 % vs 25 % DIRECT; 8 vs 2 head-to-head wins; 13× wall-clock).
   - Multi-level memory A/B (20 patients): 40 % → 45 % DIRECT, 80 % → 90 % Found.
   - Honest caveats — n=20 binomial CI ±10 pp, 50-patient case-based result was ambiguous (DIRECT regressed slightly, rank-1-within-found improved).
2. **`conclusion.tex`** — should:
   - Summarise the contributions: data pipeline, 7-agent system, evaluation framework, multi-level memory.
   - State limitations honestly (anchoring bias risk, cold-start, vector ≠ clinical similarity, small N).
   - List future work (full 160-patient memory A/B, per-disease deltas, model × memory crossover, semantic-equivalence relaxation of DIRECT).
3. **Update Methodology · "Shared Memory Design"** — currently describes the original 5-channel state. The four-tier subsystem (Working / Episodic / Semantic / Case-based) is documented in `docs/memory_presentation/index.html`; bring that into the methodology chapter with a reference to `src/memory/`.
4. **Reconcile the title-page date** with `\submissionDate`.

## Style guide for thesis prose

- Match the existing chapter prose tone: descriptive, third person, technical but readable. No marketing language.
- Cite generously from `bachelor.bib` for related-work claims; if a claim has no citation, **do not invent one** — leave a `% TODO: cite` marker.
- For numbers, **always** trace back to a file in this repo. Acceptable forms: "DIRECT match was 74 % (118 / 160; see `data/gold/mas_results/`)" — not "74 % DIRECT (literature suggests …)".
- Tables and figures should reference the file or script that produced them in a comment above the LaTeX (so a future reader can re-derive the number).
- Do not pad. If a section is two paragraphs and complete, leave it.
- Keep the methodology and results consistent with the supervisor decks — if the deck claims a number, this thesis must trace it.

## Workflow tips for Claude

- Edit one chapter at a time; rebuild after each meaningful change to catch broken refs early.
- After adding figures, add `\label{}` immediately and reference with `\ref{}` from the prose.
- New `.bib` entries: prefer DOI-bearing sources; do not include unreviewed preprints unless you mark them `% PREPRINT` in the comment above.
- When citing the project's own measurements, the standard form is:
  `\cite{...}` for prior work + a footnote pointing at the file path for this project's empirical numbers (since they're not citable papers).
- Keep commits small: one chapter or one logical block. Suggested commit prefix: `thesis: `.

## Build pipeline summary

```
main.tex
 ├── GUC_TitlePage.tex
 ├── acknowledgments.tex
 ├── abstract.tex
 ├── introduction.tex
 ├── background.tex
 │     ├── background_part1.tex
 │     ├── background_part2.tex
 │     ├── background_part3.tex
 │     └── background_part4.tex
 ├── methodology.tex
 ├── results.tex          ← stub
 ├── conclusion.tex       ← stub
 └── bachelor.bib  (citation source · ieeetr style)
```

Tectonic resolves all of this in one pass and writes `main.pdf` next to
`main.tex`. Build artifacts (`*.aux`, `*.bbl`, etc.) are gitignored.

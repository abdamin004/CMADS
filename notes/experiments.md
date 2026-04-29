# Experiments

One bullet per run. Link to its `mas_results/` slice and any notebook. Tag `#experiment`.

- _example_ — 2026-04-26 — `gpt-oss-120b` vs `med42` on batch_1 (5 patients). Result: see [EXPERIMENT_RESULTS](../docs/EXPERIMENT_RESULTS.md). #experiment
- 2026-04-29 — **Multi-level memory A/B** on `batch_4_med42_20.json` (20 patients · GPT-OSS 120B · Qwen3 32B judge). **Memory OFF:** 8/20 DIRECT (40 %), 80 % found, 19 % rank-1-when-found, 113 s/patient. **Memory ON:** 9/20 DIRECT (45 %), 90 % found, 17 % rank-1-when-found, 114 s/patient. **Headline:** +5 pp DIRECT, +10 pp Found at no time cost; rank-1 within found stays flat → wiring helps detection more than ranking. **Refs:** [`mas_results_baseline_no_mem/`](../data/gold/mas_results_baseline_no_mem/), [`mas_results_with_memory/`](../data/gold/mas_results_with_memory/), [`compare_memory_ab.py`](../docs/progress_presentation/compare_memory_ab.py). #experiment #thesis

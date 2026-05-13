# CMADS — Notes Vault

Clinical Multi-Agent Decisioning System (bachelor thesis).

## Quick links
- [[architecture]]
- [[agents]]
- [[experiments]]
- [[decisions]]
- [[questions]]
- [[daily/]]

## Project docs (in repo)
- [CLAUDE.md](../CLAUDE.md) — codebase guide
- [README](../README.md)
- docs/
  - [SRD](../docs/SRD.md) · [SDD](../docs/SDD.md) · [TECH_STACK](../docs/TECH_STACK.md)
  - [AGENTIC_PATTERNS](../docs/AGENTIC_PATTERNS.md)
  - [MAS_ARCHITECTURE_EVOLUTION](../docs/MAS_ARCHITECTURE_EVOLUTION.md)
  - [MAS_OUTPUT_FORMAT](../docs/MAS_OUTPUT_FORMAT.md)
  - [DATA_GENERATION](../docs/DATA_GENERATION.md)
  - [DATA_PIPELINE_DECISIONS](../docs/DATA_PIPELINE_DECISIONS.md)
  - [DATA_QUALITY_ANALYSIS](../docs/DATA_QUALITY_ANALYSIS.md)
  - [DataPipelineLayers](../docs/DataPipelineLayers.md)
  - [EVALUATION_METHODOLOGY](../docs/EVALUATION_METHODOLOGY.md)
  - [EXPERIMENT_RESULTS](../docs/EXPERIMENT_RESULTS.md)
  - [MODEL_COMPARISON_GPT_OSS_vs_MED42](../docs/MODEL_COMPARISON_GPT_OSS_vs_MED42.md)
  - [TREATMENT_PLANNING](../docs/TREATMENT_PLANNING.md)
  - [RADIOLOGY_REPORT_GENERATION](../docs/RADIOLOGY_REPORT_GENERATION.md)
  - [E2E_Test_Documentation](../docs/E2E_Test_Documentation.md)
  - [multilevel_memory_plan](../docs/multilevel_memory_plan.md)

## Pipeline at a glance
1. Stage 1 (parallel): `ehr_analyst` + `lab_interpreter`
2. Stage 2: `diagnostic_reasoning` (max 3 rounds)
3. Stage 3: `clinical_reviewer`
4. Stage 4: `final_diagnosis`
5. Stage 5: `evaluation` → DIRECT / INDIRECT / MISS
6. Stage 6: `treatment_planning` (DIRECT only, NICE via Qdrant)

## Tags
Use `#decision`, `#experiment`, `#bug`, `#idea`, `#question`, `#followup`, `#thesis`.

# Agents

| Agent | Stage | Role |
|---|---|---|
| `ehr_analyst` | 1 | Extracts patient context from EHR JSON |
| `lab_interpreter` | 1 | Interprets lab panel JSON |
| `diagnostic_reasoning` | 2 | Adaptive loop, max 3 rounds, confidence threshold 75 |
| `clinical_reviewer` | 3 | Adversarial review |
| `final_diagnosis` (refiner) | 4 | Merges diagnostic + reviewer |
| `evaluation` | 5 | LLM-as-judge vs ground truth → DIRECT / INDIRECT / MISS |
| `treatment_planning` | 6 | NICE guidelines via Qdrant; DIRECT-only |

Prompts live in `prompts/{agent_id}.yaml`. Schemas in `src/schemas/`.

## Notes per agent
- [[agents/ehr_analyst]]
- [[agents/lab_interpreter]]
- [[agents/diagnostic_reasoning]]
- [[agents/clinical_reviewer]]
- [[agents/final_diagnosis]]
- [[agents/evaluation]]
- [[agents/treatment_planning]]

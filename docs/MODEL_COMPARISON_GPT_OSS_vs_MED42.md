# Model Comparison: GPT-OSS 120B vs Med42 70B

| | |
|---|---|
| **Author** | Abdelrahman |
| **Date** | April 2026 |
| **Evaluator** | Qwen3 32B (Groq) — same judge for both models |
| **Cohort** | 20 patients randomly sampled from Batch 4 (seed=42) |

---

## 1. Models

| | GPT-OSS 120B | Med42 70B |
|--|-------------|-----------|
| Model ID | `openai/gpt-oss-120b` | `thewindmom/llama3-med42-70b` |
| Parameters | 120B | 70B |
| Domain | General-purpose | Medical fine-tuned (Llama 3) |
| Inference | Groq API (cloud) | Ollama (local) |
| Cost/patient | ~$0.06 | $0.00 |
| Avg time/patient | ~2 min | ~27 min |
| Agent timeout | 300s | 900s |

---

## 2. Results

### 2.1 Overall Accuracy

| Metric | GPT-OSS 120B | Med42 70B |
|--------|:-----------:|:---------:|
| **DIRECT** | **10 (50%)** | 5 (25%) |
| **INDIRECT** | 6 (30%) | 10 (50%) |
| **MISS** | 4 (20%) | 5 (25%) |
| **Found rate (D+I)** | **80%** | 75% |
| **Head-to-head wins** | **8** | 2 (10 ties) |

### 2.2 Per-Disease

| Disease | N | GPT-OSS DIRECT | Med42 DIRECT | GPT-OSS MISS | Med42 MISS |
|---------|:-:|:-:|:-:|:-:|:-:|
| Metabolic syndrome X | 6 | **5 (83%)** | 1 (17%) | 1 | 2 |
| Ischemic heart disease | 4 | **3 (75%)** | 1 (25%) | 0 | 1 |
| Essential hypertension | 4 | 1 (25%) | **2 (50%)** | 3 | 1 |
| End-stage renal disease | 3 | **1 (33%)** | 0 (0%) | 0 | 0 |
| CKD stage 2/3 | 3 | 0 (0%) | 0 (0%) | 0 | 0 |

### 2.3 Patient-Level Detail

| # | Patient | Target | GPT-OSS | Med42 | Winner |
|:-:|---------|--------|---------|-------|--------|
| 1 | `00b9c124` | Essential hypertension | DIRECT (r2) | INDIRECT (r1) | GPT-OSS |
| 2 | `04ad2732` | Essential hypertension | MISS | DIRECT (r1) | **Med42** |
| 3 | `04d1f4cf` | Metabolic syndrome X | DIRECT (r1) | DIRECT (r4) | Tie |
| 4 | `220ee7db` | End-stage renal disease | DIRECT (r1) | INDIRECT (r1) | GPT-OSS |
| 5 | `287b245c` | CKD stage 2 | INDIRECT (r3) | INDIRECT (r3) | Tie |
| 6 | `4591f713` | CKD stage 2 | INDIRECT (r1) | INDIRECT (r1) | Tie |
| 7 | `475d513d` | Essential hypertension | MISS | DIRECT (r1) | **Med42** |
| 8 | `4c3fdc9d` | Metabolic syndrome X | MISS | MISS | Tie |
| 9 | `4e12da44` | Metabolic syndrome X | DIRECT (r1) | DIRECT (r1) | Tie |
| 10 | `5a55655e` | Ischemic heart disease | INDIRECT (r2) | MISS | GPT-OSS |
| 11 | `632cff94` | Ischemic heart disease | DIRECT (r2) | INDIRECT (r2) | GPT-OSS |
| 12 | `6fb486aa` | End-stage renal disease | INDIRECT (r1) | INDIRECT (r1) | Tie |
| 13 | `731b4e8a` | Essential hypertension | MISS | MISS | Tie |
| 14 | `887bfa15` | Ischemic heart disease | DIRECT (r1) | INDIRECT (r3) | GPT-OSS |
| 15 | `94f2b376` | Metabolic syndrome X | DIRECT (r2) | INDIRECT (r1) | GPT-OSS |
| 16 | `9703f5a7` | Metabolic syndrome X | DIRECT (r1) | MISS | GPT-OSS |
| 17 | `9bfe7b12` | Metabolic syndrome X | DIRECT (r3) | MISS | GPT-OSS |
| 18 | `a90e29ab` | Ischemic heart disease | DIRECT (r2) | DIRECT (r1) | Tie |
| 19 | `c2a09430` | CKD stage 3 | INDIRECT (r2) | INDIRECT (r2) | Tie |
| 20 | `f8e26d90` | End-stage renal disease | INDIRECT (r1) | INDIRECT (r1) | Tie |

---

## 3. Agent Reliability

| Agent | GPT-OSS | Med42 |
|-------|:-------:|:-----:|
| EHR Analyst | 100% | 65% (7 errors) |
| Lab Interpreter | 100% | 40% success + 20% partial |
| Diagnostic Reasoning | 100% | 70% (6 errors) |
| Clinical Reviewer | 100% | 85% (3 errors) |
| Final Diagnosis | 100% | 100% |
| Evaluation | 100% | 100% |

Med42 errors are primarily JSON schema validation failures and timeouts on Stage 1 agents, not clinical reasoning failures. The pipeline's graceful degradation allows downstream agents to work with partial results.

---

## 4. Key Findings

1. **GPT-OSS wins overall** — 50% vs 25% DIRECT rate, 8-2 head-to-head, with the same evaluator.

2. **GPT-OSS excels at composite diagnoses** — Metabolic syndrome requires unifying hypertension + dyslipidemia + obesity + glucose intolerance under one label. GPT-OSS does this in 5/6 cases; Med42 in 1/6.

3. **Med42 is better at hypertension** — 2/4 DIRECT vs 1/4, and only 1 MISS vs 3. The medical fine-tuning helps recognise straightforward clinical conditions from vital signs.

4. **Med42's self-evaluation was inflated** — when Med42 evaluated its own output, it scored 9 DIRECT (45%). Under the same Qwen3 judge, it dropped to 5 DIRECT (25%). This highlights why a fixed third-party evaluator is essential.

5. **Med42 is 13x slower** — ~27 min/patient (local 70B) vs ~2 min/patient (Groq cloud), but costs $0.

6. **Neither model handles CKD staging** — 0% DIRECT for both on CKD stage 2/3. Both identify CKD but miss the exact stage.

---

## 5. Configurations

**GPT-OSS:**
```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
LLM_EVALUATOR_MODEL=qwen/qwen3-32b
AGENT_TIMEOUT=300
```

**Med42:**
```env
LLM_PROVIDER=ollama
LLM_MODEL=thewindmom/llama3-med42-70b:latest
LLM_EVALUATOR_MODEL=qwen/qwen3-32b
LLM_EVALUATOR_PROVIDER=groq
OLLAMA_URL=http://localhost:11434
AGENT_TIMEOUT=900
MAS_RESULTS_DIR=data/gold/mas_results_med42
```

Batch file: `data/gold/batches/batch_4_med42_20.json`

---

*-- Model Comparison v2.0 -- April 2026 -- CMADS*

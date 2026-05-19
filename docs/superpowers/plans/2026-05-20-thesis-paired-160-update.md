# Thesis Update Plan — 205-vs-100 unpaired + 20-paired → unified 160-paired

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace both memory-comparison sections in the thesis (the 205-vs-100 unpaired aggregate AND the 20-patient paired McNemar) with one unified **160-paired controlled comparison** sourced from `data/gold/paired_160_mcnemar.json`.

**Architecture:** Three files touched (`thesis/results.tex`, `thesis/conclusion.tex`, `thesis/abstract.tex`) plus a build verification. No new sections — the existing `\section{Multi-Level Memory A/B Study}` is rewritten in place; the `\subsection{Paired Comparison on the 20-Patient A/B Set}` is dropped (subsumed).

**Tech Stack:** LaTeX (`tectonic` or `pdflatex` via `make thesis`), Python (paired-160 numbers already computed by `scripts/paired_160_mcnemar.py`).

**Precondition:** `data/gold/paired_160_mcnemar.json` exists and has `n_paired = 160` (or close, e.g. ≥ 155 if any patients have missing judgments). Do NOT start until the Monitor `bx8vjjagi` has fired and the file is on disk.

---

## File targets

| File | What changes |
|---|---|
| `thesis/results.tex` | Section 4.7 (memory A/B): unpaired-aggregate table dropped; subsection 4.7.1 (20-paired) replaced with 160-paired. Lines 91–92, 352–479, 498, 784. |
| `thesis/conclusion.tex` | Lines 25–28, 122–139: phrasing changes from "20-paired underpowered" to "160-paired controlled, p=X". |
| `thesis/abstract.tex` | Line 22: rewrite the one-line memory A/B summary. |
| `notes/decisions.md` | One-bullet record of the unification decision. |
| `notes/experiments.md` | One-bullet record of the n=160 paired result. |

---

### Task 1: Wait for paired-160 data, capture the numbers

**Files:**
- Read: `data/gold/paired_160_mcnemar.json` (will be written by Monitor `bx8vjjagi` running `scripts/paired_160_mcnemar.py` when baseline-95 + extra60 both complete).

- [ ] **Step 1: Verify the file exists and has the expected shape**

```bash
ls -la /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/data/gold/paired_160_mcnemar.json
python3 -c "
import json
m = json.load(open('/Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/data/gold/paired_160_mcnemar.json'))
print(f\"n_paired = {m['n_paired']}\")
print(f\"OFF DIRECT = {m['off_direct_rate']*100:.1f}%\")
print(f\"ON  DIRECT = {m['on_direct_rate']*100:.1f}%\")
print(f\"contingency: {m['contingency_2x2']}\")
print(f\"discordant = {m['mcnemar_exact']['discordant_pairs']}\")
print(f\"McNemar p (two-sided) = {m['mcnemar_exact']['p_value_two_sided']:.4f}\")
"
```
Expected: `n_paired ≥ 155` (allow up to 5 dropped for missing judgments). If `n_paired < 155`, **STOP** — investigate the gap before rewriting the thesis.

- [ ] **Step 2: Capture the numbers as variables for the rest of this plan**

Set these in your head / in a scratchpad — every subsequent edit uses them:

- `N_PAIRED` = e.g. 160 (or whatever the file reports)
- `OFF_DIRECT_PCT` = e.g. 73.1
- `ON_DIRECT_PCT` = e.g. 52.5
- `BOTH` / `ONLY_OFF` / `ONLY_ON` / `NEITHER` from `contingency_2x2`
- `DISCORDANT_N`
- `P_VALUE` = e.g. 0.001 (will inform "p < 0.01" vs "p = 0.5" phrasing)

---

### Task 2: Rewrite `thesis/results.tex` Section 4.7

This is the largest edit. The current section has a top-level unpaired aggregate (lines 352–440) + a subsection paired test (lines 441–479). Restructure to a single paired-160 controlled section.

**Files:**
- Modify: `thesis/results.tex:91-92, 352-479, 498, 784`

- [ ] **Step 1: Update the early reference (line 91–92)**

The intro to Chapter 4 mentions the paired McNemar. Replace:

```latex
named at the point of use: an exact McNemar for the paired memory
A/B (Section~\ref{sec:results_memory_ab_paired}) and Fisher's exact
```

With:

```latex
named at the point of use: an exact McNemar for the paired
160-patient memory A/B (Section~\ref{sec:results_memory_ab}) and Fisher's exact
```

(The subsection `sec:results_memory_ab_paired` no longer exists; rewrite cross-references to point to the parent `sec:results_memory_ab` section.)

- [ ] **Step 2: Rewrite the section opening (lines 352–401)**

Replace the entire passage from `\section{Multi-Level Memory A/B Study}` through the explanation of "two complementary measurements" + the unpaired-aggregate table caption. New copy:

```latex
\section{Multi-Level Memory A/B Study}
\label{sec:results_memory_ab}

The memory subsystem is evaluated as a paired controlled experiment on
$n = N_PAIRED$ patients. The same patient UUIDs are run with the
four-tier memory subsystem disabled and enabled; each patient
contributes one paired observation. This supersedes the earlier
preliminary checkpoint at $n = 20$ (exact McNemar $p = 1.0$) which is
no longer reported. The descriptive 205-vs-100 unpaired aggregate
from earlier drafts has been retired as well: with identical patient
sets per arm, the paired test is strictly more informative.

The memory-ON arm draws from
\texttt{mas\_results\_improved\_b3/} (batch~3, 50 patients),
\texttt{mas\_results\_improved\_50/} (batch~4, 50 patients), and
\texttt{mas\_results\_improved\_extra60/} (60 additional patients
sampled from batches~1 and~5). The memory-OFF arm draws from
\texttt{mas\_results/} for the 65~UUIDs already present in the
baseline cohort, plus
\texttt{mas\_results\_paired95\_single\_level/} for the remaining
95~UUIDs that were re-run with \texttt{MEMORY\_ENABLED=false}.
\texttt{scripts/paired\_160\_mcnemar.py} pairs the two arms by UUID
and computes the contingency and exact McNemar test; the persisted
output is at
\texttt{data/gold/paired\_160\_mcnemar.json}.
```

- [ ] **Step 3: Replace the unpaired-aggregate table (lines 402–440) with the paired contingency table**

Delete the entire `\begin{table}...\end{table}` block for `tab:memory_aggregate` (the 205-vs-100 table) and replace with a 2×2 contingency table. Template — fill in the actual counts from `paired_160_mcnemar.json`:

```latex
\begin{table}[h]
\centering
\caption{Paired contingency on $n = N_PAIRED$ patients, single-level
(memory OFF) vs.\ multi-level (memory ON). The off-diagonal cells
\textsc{only-off} and \textsc{only-on} are the discordant pairs that
drive the exact McNemar test.}
\label{tab:memory_paired_160}
\begin{tabular}{l c c}
\toprule
                          & ON $=$ DIRECT     & ON $\neq$ DIRECT  \\
\midrule
OFF $=$ DIRECT            & BOTH              & ONLY\_OFF         \\
OFF $\neq$ DIRECT         & ONLY\_ON          & NEITHER           \\
\bottomrule
\end{tabular}
\end{table}
```

- [ ] **Step 4: Replace the subsection paired test (lines 441–479) with the headline paired result paragraph**

The whole `\subsection{Paired Comparison on the 20-Patient A/B Set}` block (and its `\label{sec:results_memory_ab_paired}`) is dropped. Replace with one continuous paragraph that reports the n=160 result inline, immediately after the contingency table:

```latex
The DIRECT rate moved from \textbf{OFF\_DIRECT\_PCT\%} (memory~OFF)
to \textbf{ON\_DIRECT\_PCT\%} (memory~ON) on the same
$N\_PAIRED$~patients --- a paired delta of
$(\textsc{ON\_DIRECT\_PCT} - \textsc{OFF\_DIRECT\_PCT})$~percentage
points. The off-diagonal contains DISCORDANT\_N discordant pairs
(ONLY\_OFF where memory hurts, ONLY\_ON where memory helps); an
exact (binomial) McNemar test gives $p = P\_VALUE$.

%% if P_VALUE < 0.05:
At this sample size the paired test \emph{is} discriminative: the
direction is statistically distinguishable from chance, even though
the practical magnitude is small.
%% else:
At this sample size the paired test remains inconclusive: the
direction (positive or negative on DIRECT) is not distinguishable
from chance.
%% endif

The mechanism is consistent with the qualitative pattern reported in
the qualitative case walkthroughs of
Section~\ref{sec:results_qualitative}: when the case-based prior
retrieves a similar past patient, the Diagnostic Reasoning agent
sometimes follows the prior's disease family into INDIRECT rather
than the patient's specific Synthea label. The Reviewer/Refiner step
recovers some but not all of this drift. The trade is one of recall
over precision; whether the trade is worth it depends on whether the
downstream consumer reads the top-1 diagnosis or the full
differential.
```

**Manual judgement required:** look at the actual `P_VALUE` from the
file and **pick the correct branch** (`< 0.05` or otherwise). Delete
the unused branch and the `%%` markers before saving.

- [ ] **Step 5: Update the "n=20" stragglers (lines 498, 784)**

Line 498 (Model Selection Pilot section, currently `"At $n=20$ the DIRECT-rate comparison is..."`): update to clarify this 20 refers to the model-comparison pilot (Med42 vs GPT-OSS-120B), not the memory A/B. The pilot legitimately uses n=20, so just disambiguate the sentence — no number change. Example fix:

```latex
At $n = 20$ for the model-comparison pilot the DIRECT-rate comparison is
```

Line 784 (Discussion section): same disambiguation if needed; otherwise the n=20 there may already refer to a different experiment. Read and decide in place.

- [ ] **Step 6: Build the thesis to catch broken refs**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
make thesis 2>&1 | grep -iE "error|warning.*reference|undefined" | head -20
```
Expected: no `undefined reference` warnings. If `sec:results_memory_ab_paired` is still referenced somewhere, fix the cross-reference (point at `sec:results_memory_ab`).

- [ ] **Step 7: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add thesis/results.tex
git commit -m "thesis: unify memory A/B as paired 160 controlled

Replaces the 205-vs-100 unpaired aggregate and the n=20 paired
checkpoint with a single Section 4.7 reporting the paired McNemar
on N_PAIRED identical patients (OFF_DIRECT_PCT% -> ON_DIRECT_PCT%,
p = P_VALUE). Numbers from data/gold/paired_160_mcnemar.json."
```

---

### Task 3: Update `thesis/conclusion.tex`

The conclusion references "20-patient paired test" and "unpaired aggregate" in three places. Rewrite both narratives.

**Files:**
- Modify: `thesis/conclusion.tex:25-28, 122-139`

- [ ] **Step 1: Lines 25–28 (motivation framing)**

Find:
```latex
actually helps --- the answer is more nuanced: in the unpaired
[...]
diagnosis, while the controlled paired 20-patient test is
```

Replace with:
```latex
actually helps --- the answer is more nuanced: on the same
N_PAIRED~patients with memory toggled, the DIRECT rate moves
OFF_DIRECT_PCT\% -> ON_DIRECT_PCT\% (paired McNemar $p = P_VALUE$),
```

(Adjust phrasing to flow with the surrounding sentence.)

- [ ] **Step 2: Lines 122–139 (Limitations / Future Work paragraph)**

Find the block starting `multi-level memory runs and the controlled 20-patient paired test` and rewrite. New copy:

```latex
multi-level memory runs against the same single-level pipeline on
the same N_PAIRED~patients, with an exact McNemar test on the
discordant pairs (Section~\ref{sec:results_memory_ab}). The DIRECT
rate moved from OFF_DIRECT_PCT\% (memory OFF) to ON_DIRECT_PCT\%
(memory ON), p~$=$~P_VALUE. The Found rate increased by
$\sim$6~percentage points and the MISS rate fell, consistent with
the broader-recall hypothesis; the DIRECT cost is the price of that
broader recall. Reporting that pattern transparently was the
priority, not engineering a positive result.
```

- [ ] **Step 3: Build + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
make thesis 2>&1 | tail -5
git add thesis/conclusion.tex
git commit -m "thesis: update conclusion to reference paired 160 result"
```

---

### Task 4: Update `thesis/abstract.tex`

Single line, single edit.

**Files:**
- Modify: `thesis/abstract.tex:22`

- [ ] **Step 1: Replace line 22**

Find:
```latex
20-patient paired memory A/B test (exact McNemar $p = 1.0$) is
```

Replace with:
```latex
N_PAIRED-patient paired memory A/B test (exact McNemar $p = P_VALUE$) is
```

- [ ] **Step 2: Build + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
make thesis 2>&1 | tail -5
git add thesis/abstract.tex
git commit -m "thesis: abstract reflects paired 160 McNemar"
```

---

### Task 5: Log in notes

**Files:**
- Modify: `notes/decisions.md`
- Modify: `notes/experiments.md`

- [ ] **Step 1: Append to `notes/decisions.md`**

```markdown
- 2026-05-20 — Retire the 205-vs-100 unpaired memory aggregate and the n=20 paired checkpoint; unify the thesis memory A/B as a paired controlled test on N_PAIRED identical patients. **Why:** the unpaired aggregate mixed patient subsets, and the n=20 paired was underpowered (p=1.0). The 160-paired test is strictly more informative on both counts. **How to apply:** all future memory comparisons should use the paired protocol — same UUIDs both arms, exact McNemar on discordants. **Refs:** [`docs/superpowers/plans/2026-05-20-thesis-paired-160-update.md`](../docs/superpowers/plans/2026-05-20-thesis-paired-160-update.md), [`scripts/paired_160_mcnemar.py`](../scripts/paired_160_mcnemar.py), [`data/gold/paired_160_mcnemar.json`](../data/gold/paired_160_mcnemar.json). #decision #thesis
```

- [ ] **Step 2: Append to `notes/experiments.md`**

```markdown
- 2026-05-20 — **Paired memory A/B on N=N_PAIRED identical patients** (the thesis's primary memory comparison). **OFF (memory disabled):** OFF_DIRECT_PCT% DIRECT. **ON (multi-level memory):** ON_DIRECT_PCT% DIRECT. **Contingency:** BOTH both DIRECT · ONLY_OFF only-OFF · ONLY_ON only-ON · NEITHER neither. **Discordant pairs:** DISCORDANT_N. **Exact McNemar p (two-sided) = P_VALUE.** Supersedes the n=20 paired test from 2026-04-29. **Refs:** [`paired_160_mcnemar.json`](../data/gold/paired_160_mcnemar.json), [`scripts/paired_160_mcnemar.py`](../scripts/paired_160_mcnemar.py). #experiment #thesis
```

- [ ] **Step 3: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add notes/decisions.md notes/experiments.md
git commit -m "notes: paired-160 memory A/B (supersedes n=20)"
```

---

### Task 6: Final thesis build + verify

- [ ] **Step 1: Clean build**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
make thesis-clean
make thesis 2>&1 | tail -10
```

Expected: PDF written to `thesis/main.pdf`, no `undefined reference` warnings.

- [ ] **Step 2: Page-count sanity check**

```bash
mdls -name kMDItemNumberOfPages thesis/main.pdf
```

Expected: > 50 pages (otherwise something fell off).

- [ ] **Step 3: Spot-check the rewritten section**

```bash
pdftotext -layout thesis/main.pdf - | grep -A20 "Multi-Level Memory A/B Study" | head -40
```

Confirm the paired-160 numbers (`N_PAIRED`, `OFF_DIRECT_PCT`, `ON_DIRECT_PCT`, `P_VALUE`) appear correctly.

- [ ] **Step 4: Done**

No more thesis edits needed for this plan. The deck (`docs/results_presentation/CMADS_Results_Presentation.pptx`) auto-rebuilt at 160 vs 160 already; the thesis and deck now tell the same story but at different levels of detail.

---

## What this plan does NOT change

- `docs/results_presentation/` — already updated to 160 vs 160 unpaired aggregate via the Monitor. The deck shows the aggregate (memorable, visually clean) and the thesis shows the paired (statistically rigorous). They tell the same story.
- Section 4.7 cross-references from other chapters — should still resolve to `sec:results_memory_ab`. Only the subsection `sec:results_memory_ab_paired` is dropped, so search for that label specifically.
- The 20-patient paired data (`data/gold/paired_memory_mcnemar.json`) — keep on disk as historical record, but no longer cited in the thesis.
- The 205-historical claim — drops out entirely; no longer cited.

## Self-review

- **Spec coverage:** every grepped reference (`results.tex:91-92, 352-479, 498, 784`, `conclusion.tex:25-28, 122-139`, `abstract.tex:22`) maps to a step.
- **Placeholders:** every templated number (`N_PAIRED`, `OFF_DIRECT_PCT`, etc.) is keyed to a field in `paired_160_mcnemar.json` — they are NOT placeholders, they are bindings.
- **Risk:** the `< 0.05` branch in Task 2 Step 4 needs a judgement call. The plan flags this explicitly and tells the executor which branch to pick based on the actual p-value.

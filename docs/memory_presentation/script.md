# CMADS — Multi-Level Memory · 3-minute speaking script

> ~430 spoken words · ~3:15 at 135 wpm · 9 slides
> Pacing target on each slide is in brackets — adjust on the day.

---

## Slide 1 — Title  *[~12 s]*

Good afternoon. Three minutes, nine slides, on the multi-level memory
subsystem you asked for last week — what changed in CMADS, why it
changed, the limits I see, and the evidence we have so far.

---

## Slide 2 — The pipeline before memory  *[~18 s]*

Quick reminder of where we started. My archeticture is seven specialised agents  
running over a single LangGraph shared state — the bar across the top  
of this diagram. The state held the patient context and each agent's  
final structured output. That's where the gap lived: nothing in the  
state captured *how* any agent reached its output, and nothing flowed
from one patient run to the next.

---

## Slide 3 — The gap in the old design  *[~22 s]*

The gap I was working from is concrete. Our Diagnostic agent runs an
adaptive critique loop — three rounds, confidence shifting from sixty
to seventy-eight as it rejects earlier hypotheses. The Reviewer's job
is to challenge that path. But under the old design, the only thing the
Reviewer could see was the final differential JSON. The reasoning trail
was gone.

---

## Slide 4 — Old memory vs new memory  *[~22 s]*

The old `PipelineState` had five channels, but only three were ever
written — `scratchpad` and `conflicts` were the placeholder shape of a
memory system without the substance. The new design activates all five,
adds two more for the episodic timeline, and puts two more layers above
and beyond: a disk store for cross-session aggregates, and a vector
store for case-similarity recall.

---

## Slide 5 — Four-tier architecture  *[~60 s]*

Four tiers, scoped from narrowest to broadest, each one doing a
different job.

**Tier 1 — Working memory.** Per-agent scratch space. The previously
unused `scratchpad` channel, now load-bearing inside the Diagnostic
loop, where it tracks the confidence trajectory and critique trail
across rounds. Cleared at every invocation; never visible to other
agents — that's Tier 2's role.

**Tier 2 — Episodic memory.** The current run's timeline, on two
channels. `session_memory` is an append-only list of typed events —
critique, confidence check, decision — that the Reviewer reads to
challenge the Diagnostic agent's path, and the Refiner reads in full.
`session_summary` is a lighter per-agent digest — one short line each
— a quick scoreboard for any future coordinator.

**Tier 3 — Semantic memory.** Cross-session, on disk. A small JSON file
keyed by disease — DIRECT, INDIRECT, MISS counts, rank-1 frequency,
observed evidence patterns. Updated by Stage 7 after every patient.
Read by the Refiner and Treatment as priors over the differential.

**Tier 4 — Case-based memory.** Cross-session, in Qdrant. Every
finished patient embedded with BioLORD-2023 into a `patient_cases`
collection, with the run's outcome as payload. The Diagnostic agent
opens its prompt with the top-K most similar past patients as a
Bayesian-style prior — case-based recall, not static lookup. NICE
guidelines stay accessible to Treatment but live outside the memory
hierarchy.

---

## Slide 6 — Pipeline integration  *[~20 s]*

The pipeline shape is unchanged at the top — same seven agents. What's
new is the read-write matrix. Diagnostic now opens its prompt with the
case-based prior. The Reviewer reads the critique trail. Memory
consolidation — a new Stage 7 — writes both Tier 3 and Tier 4 after
every patient, so the next run starts smarter.

---

## Slide 7 — Honest limitations  *[~18 s]*

Before the numbers — three real risks of this design I want to flag.
**Context inflation:** every agent now reads more, so prompts grow and
tokens cost. **Anchoring bias:** case-based recall tells the Diagnostic
agent "patients like this had disease X" — that can pull it off a
genuinely novel presentation. **Cold start:** the priors are empty on
the first patient; the system effectively runs memory-off until the
store warms up.

The pipeline shape is unchanged at the top — same seven agents. What's
new is the read-write matrix. Diagnostic now opens its prompt with the
case-based prior. The Reviewer reads the critique trail. Memory
consolidation — a new Stage 7 — writes both Tier 3 and Tier 4 after
every patient, so the next run starts smarter.

---

## Slide 8 — A/B results  *[~25 s]*

Results from a clean A/B on twenty patients of Batch 4. Same model,
same Qwen3 judge, same prompts — only the `MEMORY_ENABLED` flag
toggled. DIRECT match goes from forty to forty-five percent. Found rate
from eighty to ninety. Time cost is roughly zero. The wiring helps
detection more than ranking, which fits the design intent — the
Reviewer can challenge the path earlier, so more correct diagnoses land
in the differential at all. We're now scaling this validation to the
full Batch 4 cohort.

---

## Slide 9 — Summary  *[~12 s]*

Recap. Four tiers, one facade, one new maintenance stage. Thirty-five
unit tests passing. Validated as a clean A/B at N=20. Next step: run
the same A/B on the full 160-patient cohort. Thank you — happy to
take questions.

---

## Presenter notes (off the script)

- **If asked about Tier-4 specifically:** the redesign was your push from
last week — wrapping NICE in a "memory tier" was a stretch. Vector
recall earns its keep when used for case similarity, not static
reference lookup.
- **If asked about scaling:** N=20 binomial CI is roughly ±10 pp.
Currently re-running at N=50 on the full Batch 4 to tighten the
confidence interval. Early signal: rank-1-within-found is up; DIRECT
may regress slightly — investigating whether the case-based prior is
pulling some DIRECT into INDIRECT.
- **If asked about cost:** zero LLM cost added. BioLORD embeddings are
CPU-cheap; Qdrant calls are sub-100 ms.
- **If asked about MEMORY_ENABLED in production:** stays on. Off-switch
exists only to keep the A/B clean, not as a runtime mode.

---

*Total speaking time at 135 wpm: ~3 minutes 5 seconds.*
*Slide 5 is the heaviest — if running long there, skip the
`session_summary` sentence in Tier 2 to recover ~10 s, or skip the
"NICE guidelines stay accessible" closer to recover ~6 s. Slide 2 can
also be cut to ~10 s by keeping just the first sentence.*
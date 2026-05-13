# notes/ — Obsidian vault conventions

This folder is an Obsidian vault. Follow these conventions when creating or editing notes here.

## Layout
- `index.md` — vault entry point; keep links here current
- `architecture.md` — system overview, links to key files
- `agents.md` — per-agent index, links into `agents/`
- `agents/` — one note per agent (`ehr_analyst.md`, `diagnostic_reasoning.md`, etc.)
- `experiments.md` — experiment log (one bullet per run)
- `decisions.md` — append-only decision log
- `questions.md` — open questions and followups
- `daily/` — daily notes (`YYYY-MM-DD.md`); user-written, do not auto-create
- `attachments/` — binary attachments (created on demand by Obsidian)

## Link style
- Use Obsidian wiki-links: `[[note-name]]`, not `[note-name](note-name.md)`.
- Use **relative** paths to reach files outside the vault (e.g. `[SDD](../docs/SDD.md)`).
- When referencing an agent's prompt or schema, link the source: `[prompts/diagnostic_reasoning.yaml](../prompts/diagnostic_reasoning.yaml)`.

## Tags
Use these tags consistently (no others without asking):
- `#decision` — a decision was made
- `#experiment` — an experiment run / result
- `#bug` — a bug was investigated or fixed
- `#idea` — speculative; not yet decided
- `#question` — open question
- `#followup` — needs revisit later
- `#thesis` — relevant for the bachelor thesis writeup

## Decision entries (decisions.md)
Append one bullet to `decisions.md`. Format:

```
- YYYY-MM-DD — <one-line summary>. **Why:** <reason>. **Refs:** <commit | file:line | issue>. #decision
```

If it needs more than two sentences, create `decisions/YYYY-MM-DD-slug.md` and link to it.

## Experiment entries (experiments.md)
One bullet per run:

```
- YYYY-MM-DD — <model/config> on <batch/cohort>. **Result:** <DIRECT %, INDIRECT %, MISS %>. **Refs:** <mas_results path>. #experiment
```

## Bug investigations
For non-trivial bugs, append to `questions.md`:

```
## YYYY-MM-DD — <symptom>
- **Root cause:** ...
- **Fix:** <commit | file:line>
- **Why it bit us:** ...
#bug
```

Skip trivial typos / one-line fixes.

## What NOT to log here
- Routine code edits (git history covers it)
- Step-by-step task progress (use TaskCreate)
- Patient data, PHI, or any synthetic patient that could be confused for real data
- Secrets, API keys
- Bulk `mas_results/*.json` content — link to the path instead

## Editing rules
- Never rewrite existing decision/experiment entries — append a superseding one and link back.
- When you add a top-level note, link it from `index.md`.
- Don't touch `.obsidian/workspace*` (local UI state).

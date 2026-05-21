# Doctor-runtime advanced-settings dropdown

**Status:** Approved 2026-05-21 · Implementation in progress.

## Problem

The doctor-runtime entry surface (`RuntimeHero`) currently exposes three
controls top-to-bottom: top-K precision picker, UUID input, model grid.
That ordering buries the primary action (type UUID, run) below two
secondary controls. The doctor's mental model is "this patient, now" —
the UUID input should be the first interactive element.

We also lack a way to opt out of the principal configuration
(multi-level memory + terminal-renal canonicalizer) for runtime
comparisons; the only way today is editing `.env`.

## Goal

Reorder the entry form so UUID + Run is the only thing visible by
default, and consolidate the model picker, precision picker, and a new
"system accuracy mode" preset under a single collapsible **Advanced
settings** disclosure.

## Default view (collapsed)

```
┌─────────────────────────────────────────────────────────────────┐
│  🩺 Let's look at a patient                                      │
│                                                                  │
│  Let's look at this patient together.                            │
│  Pull up the patient and I'll walk through their chart…          │
│                                                                  │
│  Patient UUID                                                    │
│  ┌─────────────────────────────────────────┐ ┌────────────────┐ │
│  │ e.g.  4b265e38-b837-001f-9059-…         │ │ ▶ Run pipeline │ │
│  └─────────────────────────────────────────┘ └────────────────┘ │
│                                                                  │
│  ▾ Advanced settings · GPT-OSS-120B · Top 3 · Multi-level memory │
└─────────────────────────────────────────────────────────────────┘
```

## Advanced panel (expanded)

Three controls, top-to-bottom:

1. **System accuracy mode** — two preset cards:
   - **Recommended** — Multi-level memory + terminal-renal
     canonicalizer (the principal headline configuration; 76.9 % DIRECT
     on the paired-160 cohort).
   - **Fast baseline** — Single-level memory, no canonicalizer (~30 s
     faster per run; 53.8 % DIRECT on the same cohort).

2. **Top-K precision picker** — existing four chips (Top 1 / 2 / 3 / 5).
   The trust-signal percentage (`X % of past 160 patients had the
   target in top K`) is shown directly under the chips, not above the
   form.

3. **Model** — existing model preset grid in a tighter 2-column layout
   (1-column on narrow viewports).

## Backend contract

Extend `RunRequest` (Pydantic) with one new field:

```python
accuracy_mode: Literal["recommended", "fast"] = "recommended"
```

The run worker maps the value to environment variable overrides applied
in the worker subprocess, the same way provider/model overrides work:

| accuracy_mode | MEMORY_ENABLED | CANONICALIZER_ENABLED |
|---------------|----------------|------------------------|
| recommended   | true           | true                   |
| fast          | false          | false                  |

`accuracy_mode` is persisted on the `RunTask` model and surfaced back to
the front-end so the run-results view can show which mode produced the
output.

## Frontend changes

- `RuntimeHero.tsx` — reorder; wrap the three advanced controls inside
  a native `<details>` element; render the current selections as the
  `<summary>` text (e.g. `▾ Advanced settings · GPT-OSS-120B · Top 3 ·
  Multi-level memory`).
- `styles.css` — `.runtime-solo__advanced` block with `<summary>`
  styling, accuracy-mode chip styles, tighter model grid.
- `types.ts` — `AccuracyMode = "recommended" | "fast"`.
- `api.ts` — `startRun(uuid, preset, topK, accuracyMode)`.
- `RuntimeMode.tsx` — accept `accuracyMode` from `RuntimeHero.onRun`
  and forward to `startRun`.

## Out of scope

- No dropdown library; native `<details>` + custom chips.
- No persisting the doctor's last-selected configuration across browser
  sessions (could add via `localStorage` later).
- No telemetry on mode usage.

## Tests / verification

- Smoke test: open Doctor runtime, type a UUID, click Run with both
  default and Fast baseline modes; confirm the backend received the
  intended `accuracy_mode` value (visible in `RunTask.modelOverride`).
- Confirm the collapsed summary string updates as the doctor changes
  controls inside Advanced.
- Confirm hot reload still works.

## References

- `doctor_console/frontend/src/components/RuntimeHero.tsx`
- `doctor_console/backend/app.py` — `RunRequest`, `start_run`,
  `_run_worker`
- `src/config.py` — `MEMORY_ENABLED`, `CANONICALIZER_ENABLED`
- `notes/experiments.md` 2026-05-21 entry — paired-160 v2 headline

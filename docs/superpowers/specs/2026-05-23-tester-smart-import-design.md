# Tester — Smart Import (paste / file / image → structured patient)

**Date:** 2026-05-23
**Status:** Approved (user instructed "build it" after the pre-brainstorm scope decisions). Ready for direct implementation.
**Scope:** A new entry point on the Tester splash that takes free-text, a PDF/FHIR-JSON file, or a lab-slip image and extracts demographics, active conditions, and recent labs into a `TestPatientPayload`-shaped object. The clinician reviews each extracted field via a preview modal and accepts or rejects per row before merging into the editor.

---

## 1. Motivation

Building a synthetic patient from scratch is friction — typing in age, gender, 6 conditions, 5 medications, 12 labs is a lot of clicks when the clinician already has the data in a chart note, PDF lab report, or photo of a lab slip. Smart Import bridges the gap: paste the source material, let an LLM extract structured fields, review what landed before merging.

## 2. Pre-decided in the chat (no further brainstorming)

| Question | Decision |
|---|---|
| Input formats | Text + PDF + FHIR JSON + image (full matrix) |
| Rollout | Three phases (text → file → image), but spec covers all three |
| Auto-merge or preview? | Preview-with-checkboxes — never auto-merge |
| Conflict resolution | Extracted value overwrites existing per-field, unless user unchecks |
| LLM | Existing Groq provider adapter; `gpt-oss-120b` for text, vision-capable preset for image |
| New endpoint | `POST /api/tests/extract` with `{kind: "text"|"file"|"image", content}` |
| Frontend surface | New third card on the Tester splash; 3-tab input modal; preview modal |
| Schema | Reuse `TestPatientPayload` Pydantic model |
| Snap-to-vocabulary | Best-effort fuzzy match against the existing vocabulary cache, suggest closest cohort term as a chip alongside the extracted free text |
| Audit | Save raw input to Mongo `extraction_log` collection (one doc per extract call, ttl 90 days) |
| Length cap | 32 kB text / 5 MB file / 10 MB image — over → 413 with friendly message |
| Multi-language | English primary; the LLM handles other languages best-effort, no special path |

## 3. Architecture

```
                 Tester splash (Build / clone tab → Start from scratch)
                 ┌───────────────────────────────────────────────────────┐
                 │  ✎  Open blank editor   |  📋  Smart import  ← new    │
                 └───────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                 ┌───────────────────────────────────────────────────────┐
                 │  SmartImportModal                                     │
                 │  ┌──────────────────────────────────────────────────┐ │
                 │  │ [Paste text] [Upload file] [Image]               │ │
                 │  │                                                  │ │
                 │  │  ← input surface per tab →                       │ │
                 │  │                                                  │ │
                 │  │  [ Extract → ]                                   │ │
                 │  └──────────────────────────────────────────────────┘ │
                 └───────────────────────────────────────────────────────┘
                                                  │
                                  POST /api/tests/extract
                                                  ▼
                 ┌───────────────────────────────────────────────────────┐
                 │  Backend extraction pipeline                          │
                 │  ┌─────────────────────────────────────────────────┐  │
                 │  │ kind=text   →  Groq text LLM (json_mode)         │  │
                 │  │ kind=file   →  detect mime:                      │  │
                 │  │                 .pdf  → pdfplumber → text → LLM  │  │
                 │  │                 .json → FHIR structural parse     │  │
                 │  │ kind=image  →  Groq vision (one shot)            │  │
                 │  └─────────────────────────────────────────────────┘  │
                 │  Validate JSON with TestPatientPayload (Pydantic)     │
                 │  Snap each extracted free-text term to vocabulary     │
                 │  Log raw input + extracted payload to Mongo           │
                 └───────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                 ┌───────────────────────────────────────────────────────┐
                 │  PreviewMergeModal                                    │
                 │  ✔ Demographics                                       │
                 │     ✔ age = 71   ✔ gender = F                         │
                 │  ✔ Active conditions (3)                              │
                 │     ✔ Type 2 diabetes mellitus  ◀ snap to vocab       │
                 │  ✔ Recent labs (5)                                    │
                 │     ✔ HbA1c = 8.2 % ◀ extracted from "A1c 8.2%"       │
                 │  [Reject all] [Accept all]   [Cancel] [Merge →]       │
                 └───────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                 PatientBuilderEditor  ← payload pre-populated with accepted fields
```

## 4. Backend

### 4.1 New endpoint

```
POST /api/tests/extract
Content-Type: multipart/form-data
Fields:
  kind:    "text" | "file" | "image"
  text:    string           (when kind=text)
  file:    UploadFile       (when kind=file)
  image:   UploadFile       (when kind=image)

Returns:
  {
    "extracted": TestPatientPayload-shape  (the structured guess),
    "warnings": list[str],
    "snap_suggestions": {
      "conditions": [{from: "T2DM", to: "Diabetes mellitus type 2 (disorder)", score: 0.94}, ...],
      "medications": [...],
      "labs":        [...]
    }
  }

4xx errors:
  413 if input exceeds size cap
  415 if file mime unsupported
  422 if extraction returned malformed JSON after retry
  503 if Groq is unreachable / rate-limited
```

### 4.2 Files touched

- `doctor_console/backend/app.py` — new endpoint + a small dispatch function `_extract_dispatch(kind, content) -> dict`
- `prompts/extract_patient.yaml` (new) — system prompt + user template with the JSON-schema example
- `src/extraction/__init__.py` (new) — `extract_text(...)`, `extract_pdf(...)`, `extract_fhir(...)`, `extract_image(...)` — one function per modality, each returning the same dict shape
- `src/extraction/vocabulary_snap.py` (new) — fuzzy-match extracted free-text strings to the cohort vocabulary cache using `difflib.SequenceMatcher` (no new dep) with a threshold of 0.7
- `requirements.txt` — add `pdfplumber>=0.10.0,<1.0.0`

### 4.3 Prompt strategy

Single system prompt requesting strict JSON matching the `TestPatientPayload` JSON-schema (serialized into the prompt). Use `json_mode=True` on the Groq adapter. On parse failure, retry once with a stricter "respond with ONLY the JSON, no markdown" follow-up. On second failure, return 422 with the raw model output in the response body for the user to fall back to manual entry.

Temperature `0.1`. Max tokens `2048`. Stop sequences none.

The prompt explicitly tells the LLM:
- Only emit fields it sees explicitly mentioned in the source — never fabricate
- For each field, attach a `_confidence` score 0-1 (the LLM judges its own confidence)
- Output the cohort's preferred condition name when obvious (e.g. "diabetes" → "Diabetes mellitus type 2"), but quote the raw text in a `_source` field if the term is unclear
- Reject inputs that aren't clinical text (e.g. random web pages, source code) with `{"_rejected": true, "_reason": "..."}`

### 4.4 FHIR parsing (deterministic — no LLM)

Walk the FHIR Bundle / entry list:
- `Patient` resource → demographics (age computed from `birthDate`)
- `Observation` resource (category = laboratory) → labs
- `Condition` resource (clinicalStatus = active) → conditions
- `MedicationRequest` resource (status = active) → medications

R4 and R5 both accepted (the field shapes overlap enough that one parser handles both).

### 4.5 Image / OCR

Groq vision in **one shot**: send the image as a base64 data URL with the same extraction prompt. The vision model returns structured JSON directly. No separate OCR step. Trades a small accuracy hit for far less complexity than chained OCR + extract.

Vision-capable preset: detect the first available vision-capable Groq model from `discover_model_presets()`; if none configured, return 503 with a clear message ("Image extraction not configured — paste the text instead").

### 4.6 Audit log

Mongo collection `extraction_log`:
```python
{
  "_id":              uuid4,
  "created_at":       datetime,
  "kind":             "text" | "file" | "image",
  "raw_input":        str | None,        # text content (truncated to 8 kB for logging)
  "file_name":        str | None,
  "file_mime":        str | None,
  "extracted":        dict,                # the validated TestPatientPayload-shape
  "warnings":         list[str],
  "snap_suggestions": dict,
  "model_used":       str,
  "duration_ms":      int,
  "expires_at":       datetime,            # ttl 90 days for clean-up
}
```

A Mongo TTL index on `expires_at` deletes old logs automatically.

## 5. Frontend

### 5.1 New third splash card

`TesterJourney.tsx`: the splash currently has two cards (cohort, scratch). Adds a third — **Smart import** — with the existing `tester-splash__card` styling and a `📋` icon eyebrow. Eyebrow: "PASTE OR UPLOAD". Headline: "Smart import." Body: "Paste a chart note, drop a PDF, or snap a photo of a lab slip — I'll extract the patient for you." CTA: "Try it →".

### 5.2 `SmartImportModal.tsx` (new)

Three-tab modal (using the same `.segmented` / `.segmented__btn` family from earlier polish):

| Tab | Surface |
|---|---|
| **Paste text** | `<textarea>` 600px tall, monospace font, char counter, 32 kB cap |
| **Upload file** | Drag-and-drop zone + file picker; accepts `.pdf` `.json`; shows filename + size after selection |
| **Image** | Drag-and-drop zone + file picker; accepts `image/png` `image/jpeg` `image/webp`; shows thumbnail preview |

Primary action button at the bottom: "Extract →". Disabled until the active tab has content. Shows a spinner + "Extracting…" while the request is in flight. On 4xx/5xx errors, shows a small inline error card with the message and a "Try again" button.

### 5.3 `PreviewMergeModal.tsx` (new)

Renders the extracted payload as a tree of accordions, one per top-level section (Demographics, Active conditions, Active medications, Recent labs). Each leaf has:
- A checkbox (default checked unless `_confidence < 0.4`)
- The extracted value
- If the field already has a value in the editor: small "was: <old>" pill in slate-500
- If snap-to-vocabulary returned a suggestion: a "snap to <cohort term>" link that swaps the value to the canonical form

Bottom bar: `[Reject all]` `[Accept all]` on the left; `[Cancel]` `[Merge →]` on the right. "Merge →" overlays the accepted fields onto the current `payload` state in `TesterJourney`, then closes both modals and routes the user into the editor.

### 5.4 API client

Add to `doctor_console/frontend/src/api.ts`:
```typescript
export function extractText(text: string): Promise<ExtractResponse>;
export function extractFile(file: File): Promise<ExtractResponse>;
export function extractImage(image: File): Promise<ExtractResponse>;
```

All three POST to `/api/tests/extract` with the appropriate body shape.

## 6. Phasing

| Phase | Ships | Scope |
|---|---|---|
| **1 (priority)** | Free-text paste + extract + preview + merge | The full UX skeleton end-to-end. ~1 backend day + 1 frontend day. |
| **2** | PDF + FHIR JSON upload | Same endpoint extended. Adds `pdfplumber` dep. ~½ backend day + ~½ frontend day. |
| **3** | Image / vision-capable Groq path | Same endpoint extended. ~½ day total if the vision preset is already configured. |

Each phase is a separate commit (or commit group) so partial value lands incrementally.

## 7. Error handling + edge cases

| Case | Behaviour |
|---|---|
| LLM returns malformed JSON twice in a row | 422 with the raw text in the response; frontend shows "Couldn't make sense of that — try editing manually" + a button to drop into the blank editor |
| Input exceeds size cap | 413 with the specific cap in the message |
| File MIME unsupported | 415 with "Try .pdf / .json / .png / .jpeg" |
| Groq unreachable | 503 with retry-after; frontend offers manual fallback |
| FHIR bundle has no Patient resource | Return what we found (Conditions, Observations); warn that demographics are missing |
| LLM hallucinates a field (e.g. age=200) | Pydantic validation rejects → backend either retries once or returns a warning ("Skipped 'age=200' — invalid") |
| User has unsaved edits in the editor | Preview modal shows side-by-side; conflict resolution per-row |
| LLM says `{"_rejected": true}` | Show "This doesn't look like clinical content — try a different file or paste the relevant section" |

## 8. Testing

| Layer | Tests |
|---|---|
| `src/extraction/extract_text.py` | Unit tests with hand-crafted prompts/responses (mock Groq); verify JSON validation, retry logic, confidence pass-through |
| `src/extraction/vocabulary_snap.py` | Unit tests with fixed cohort vocab; check fuzzy threshold + ranking |
| `src/extraction/extract_fhir.py` | Unit tests with sample FHIR R4 + R5 bundles; verify all four resource types parsed |
| `tests/integration/test_extract_api.py` | Integration: `POST /api/tests/extract` with each kind; happy path + 413 + 415 + 422 |
| Frontend | Manual smoke through the UI — no Vitest setup (consistent with existing scope) |

## 9. Acceptance criteria

1. Open `Build / clone tab → Start from scratch` — three cards appear (existing two + Smart import).
2. Click Smart import → modal opens with three tabs, "Paste text" focused by default.
3. Paste a chart note (e.g. "70 y/o F with T2DM on metformin, HbA1c 8.2%, recent eGFR 42") → Extract → preview shows demographics (age=70, gender=F), 1 condition (T2DM), 1 medication (metformin), 2 labs (HbA1c, eGFR).
4. Uncheck eGFR → Merge → editor opens pre-populated with the other fields but without eGFR.
5. Upload `data/gold/patient_cases/<uuid>/ehr_case.json` (a FHIR-ish JSON) → Extract → preview populated by the deterministic parser (no Groq call).
6. (Phase 3) Snap a photo of the screenshot in your screenshots dir → Extract → preview populated. (Will demo on a real lab slip when available.)
7. Researcher Overview headline numbers (78.1% / 95.0% / contingency 70-16-53-21) unchanged after using Smart import — proves the audit log is namespace-isolated.

## 10. Out of scope

- Real-time streaming of extraction output (one-shot only)
- Multi-document combine (one input at a time)
- Manual field-mapping UI (the LLM picks fields; user accepts/rejects, not remaps)
- Saving the original input as a permanent attachment to the TestPatient (just goes into `extraction_log` with TTL)
- HIPAA-grade audit logging (this is synthetic data; the audit log is for debugging, not compliance)
- Cost meter / per-user quota

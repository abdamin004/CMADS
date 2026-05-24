import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FlaskConical, Sparkles, Plus, Trash2 } from "lucide-react";
import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["labs"];
  onChange: (next: TestPatientPayload["labs"]) => void;
  /** Opens the Smart Import modal (paste / file / image → labs). Optional —
   *  when absent the button is hidden (e.g. in unit-test contexts). */
  onSmartImport?: () => void;
}

/**
 * Common clinical units the agents will recognise. Curated to the ones
 * actually used across the Synthea cohort's latest_labs entries;
 * "other…" falls through to free-text entry.
 */
const UNITS = [
  "mg/dL", "g/dL", "%", "mmol/L", "mEq/L",
  "IU/L", "U/L", "ng/mL", "pg/mL", "µg/dL",
  "mIU/L", "µIU/mL", "mL/min/1.73 m²", "mm Hg", "bpm",
  "x10^9/L", "x10^12/L", "K/µL", "M/µL", "fL", "pg",
];

/**
 * Lightweight lab knowledge base. Each entry pairs a test-name regex with a
 * canonical unit and a typical reference range. Two roles:
 *   1. When the user adds a known lab, we pre-fill the unit so they only
 *      enter a value.
 *   2. We surface a faded reference-range hint and a quick visual flag
 *      (↑ H / ↓ L) so the clinician gets sanity feedback while editing.
 *
 * The flag is *not* sent to the agent — the lab interpreter does its own
 * out-of-range logic. This is purely a UX aid.
 */
type LabSpec = {
  match: RegExp;
  unit:  string;
  low:   number;
  high:  number;
};
const LAB_KB: LabSpec[] = [
  { match: /\b(wbc|white\s*blood)/i,                unit: "x10^9/L",        low: 4.0,  high: 11.0 },
  { match: /\b(rbc|red\s*blood)/i,                  unit: "x10^12/L",       low: 4.2,  high: 5.9  },
  { match: /\b(h[ae]moglobin|hgb|\bhb\b)/i,         unit: "g/dL",           low: 12.0, high: 17.5 },
  { match: /\b(hematocrit|hct)\b/i,                 unit: "%",              low: 36,   high: 50   },
  { match: /\b(platelet|plt)\b/i,                   unit: "x10^9/L",        low: 150,  high: 400  },
  { match: /\b(glucose|fbg|fasting\s*glucose)/i,    unit: "mg/dL",          low: 70,   high: 110  },
  { match: /\b(hba1c|\ba1c\b|glycated)/i,           unit: "%",              low: 4.0,  high: 5.6  },
  { match: /\b(creatinine|\bcr\b)/i,                unit: "mg/dL",          low: 0.6,  high: 1.3  },
  { match: /\b(egfr|gfr)\b/i,                       unit: "mL/min/1.73 m²", low: 60,   high: 120  },
  { match: /\b(bun|urea)\b/i,                       unit: "mg/dL",          low: 7,    high: 20   },
  { match: /\b(sodium|na\+?)\b/i,                   unit: "mmol/L",         low: 135,  high: 145  },
  { match: /\b(potassium|k\+?)\b/i,                 unit: "mmol/L",         low: 3.5,  high: 5.0  },
  { match: /\b(chloride|\bcl\b)/i,                  unit: "mmol/L",         low: 98,   high: 107  },
  { match: /\b(co2|bicarb|hco3)/i,                  unit: "mmol/L",         low: 22,   high: 29   },
  { match: /\b(alt|sgpt)\b/i,                       unit: "U/L",            low: 7,    high: 56   },
  { match: /\b(ast|sgot)\b/i,                       unit: "U/L",            low: 10,   high: 40   },
  { match: /\b(ldl)\b/i,                            unit: "mg/dL",          low: 0,    high: 100  },
  { match: /\b(hdl)\b/i,                            unit: "mg/dL",          low: 40,   high: 200  },
  { match: /\b(triglyceride|\btg\b)/i,              unit: "mg/dL",          low: 0,    high: 150  },
  { match: /\b(tsh)\b/i,                            unit: "mIU/L",          low: 0.4,  high: 4.0  },
  { match: /\b(troponin)/i,                         unit: "ng/mL",          low: 0,    high: 0.04 },
  { match: /\b(crp|c-reactive)/i,                   unit: "mg/L",           low: 0,    high: 10   },
];

function specFor(name?: string): LabSpec | undefined {
  if (!name) return undefined;
  return LAB_KB.find((s) => s.match.test(name));
}

function flagFor(value: string | undefined, spec: LabSpec | undefined): "L" | "H" | null {
  if (!spec || value == null || value === "") return null;
  const n = parseFloat(value);
  if (Number.isNaN(n)) return null;
  if (n < spec.low)  return "L";
  if (n > spec.high) return "H";
  return null;
}

// Quick-add chips — high-yield labs across the cohort. Adding any of them
// auto-fills the canonical unit via the LAB_KB above.
const QUICK_ADD = [
  "Hemoglobin", "HbA1c", "Glucose", "Creatinine",
  "eGFR",        "Potassium", "Sodium",   "TSH",
];

export function LabsForm({ value, onChange, onSmartImport }: Props) {
  const rows = value?.latest_labs ?? [];
  const [unitMode, setUnitMode] = useState<Record<number, "select" | "free">>({});

  function setRow(i: number, patch: Partial<(typeof rows)[number]>) {
    onChange({ latest_labs: rows.map((r, j) => j === i ? { ...r, ...patch } : r) });
  }
  function add(item: VocabularyItem) {
    const spec = specFor(item.label);
    onChange({
      latest_labs: [
        ...rows,
        {
          test_name: item.label,
          value: "",
          unit: spec?.unit ?? "",
          reference_range: spec ? `${spec.low}–${spec.high} ${spec.unit}` : undefined,
        },
      ],
    });
  }
  function remove(i: number) {
    onChange({ latest_labs: rows.filter((_, j) => j !== i) });
    setUnitMode((m) => { const n = { ...m }; delete n[i]; return n; });
  }
  function clearAll() {
    onChange({ latest_labs: [] });
    setUnitMode({});
  }

  const usedNames = new Set(rows.map((r) => r.test_name.toLowerCase()));
  const suggestions = QUICK_ADD.filter(
    (label) => !usedNames.has(label.toLowerCase()),
  ).slice(0, 8);

  return (
    <div className="labs-form">
      {/* Search row — combobox + smart-import button.  Smart import is
          surfaced as the primary visual accent because it routes to OCR /
          PDF extraction, which is the fastest way to seed a row. */}
      <div className="labs-form__add">
        <div className="labs-form__add-search">
          <VocabularyCombobox
            kind="lab"
            placeholder="Add a lab by name (e.g. Hemoglobin, HbA1c)…"
            onPick={add}
          />
        </div>
        {onSmartImport && (
          <button
            type="button"
            onClick={onSmartImport}
            className="labs-form__smart"
            title="Paste a chart note, drop a PDF, or upload a photo of a lab slip"
          >
            <Sparkles size={13} strokeWidth={1.8} />
            Smart import
          </button>
        )}
      </div>

      {suggestions.length > 0 && (
        <div className="labs-form__suggest">
          <span className="labs-form__suggest-eyebrow">
            <Sparkles size={11} strokeWidth={1.8} />
            Common in this cohort
          </span>
          <div className="labs-form__suggest-row">
            {suggestions.map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => add({ label, code: null })}
                className="lab-suggest-chip"
              >
                <Plus size={11} strokeWidth={2.2} />
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <div className="labs-form__count-row">
          <span className="labs-form__count">
            <strong>{rows.length}</strong>
            {rows.length === 1 ? " lab" : " labs"}
          </span>
          <button type="button" onClick={clearAll} className="labs-form__clear">
            Clear all
          </button>
        </div>
      )}

      {rows.length === 0 && (
        <div className="labs-form__empty">
          <div className="labs-form__empty-mark" aria-hidden="true">
            <FlaskConical size={18} strokeWidth={1.4} />
          </div>
          <div>
            <div className="labs-form__empty-title">No labs on file yet</div>
            <div className="labs-form__empty-sub">
              Search above, tap a quick-add chip, or use <em>Smart import</em>
              to paste / drop / snap a lab slip. The lab interpreter agent
              reads each value with its unit and decides if it's out of range.
            </div>
          </div>
        </div>
      )}

      {/* Rows — dense worksheet.  Single-line per lab; reference range and
          flag live inline, so the user reads each record without scanning
          a stack of label/value columns. A 2-px left-edge accent tints
          the row red (H) or blue (L) when the value falls outside the
          known range — clinical-shorthand familiar from a CBC/BMP slip. */}
      <motion.ul className="lab-list" layout>
        <AnimatePresence initial={false} mode="popLayout">
          {rows.map((r, i) => {
            const spec = specFor(r.test_name);
            const flag = flagFor(r.value, spec);
            const useFreeUnit =
              unitMode[i] === "free" ||
              (r.unit !== "" && r.unit != null && !UNITS.includes(r.unit ?? ""));
            return (
              <motion.li
                key={`${r.test_name}-${i}`}
                layout
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.16, ease: [0.23, 1, 0.32, 1] }}
                className={`lab-row${flag === "H" ? " lab-row--high" : flag === "L" ? " lab-row--low" : ""}`}
              >
                <div className="lab-row__name">
                  <span className="lab-row__name-text">
                    {r.test_name || <span className="lab-row__name-empty">Unnamed lab</span>}
                  </span>
                  {spec && (
                    <span className="lab-row__range mono">
                      {spec.low}–{spec.high} {spec.unit}
                    </span>
                  )}
                </div>
                <input
                  type="text" inputMode="decimal"
                  className="lab-row__value mono"
                  placeholder="—"
                  value={r.value ?? ""}
                  onChange={(e) => setRow(i, { value: e.target.value })}
                  aria-label={`${r.test_name} value`}
                />
                {useFreeUnit ? (
                  <div className="lab-row__unit-free">
                    <input
                      type="text"
                      className="lab-row__unit-input"
                      placeholder="unit"
                      value={r.unit ?? ""}
                      onChange={(e) => setRow(i, { unit: e.target.value })}
                      aria-label={`${r.test_name} unit`}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setRow(i, { unit: "" });
                        setUnitMode((m) => ({ ...m, [i]: "select" }));
                      }}
                      className="lab-row__unit-toggle"
                    >
                      pick
                    </button>
                  </div>
                ) : (
                  <select
                    className="lab-row__unit"
                    value={r.unit ?? ""}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === "__other__") {
                        setUnitMode((m) => ({ ...m, [i]: "free" }));
                        setRow(i, { unit: "" });
                      } else {
                        setRow(i, { unit: v });
                      }
                    }}
                    aria-label={`${r.test_name} unit`}
                  >
                    <option value="">— unit —</option>
                    {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                    <option value="__other__">other…</option>
                  </select>
                )}
                <div className="lab-row__flag-slot" aria-hidden={!flag}>
                  {flag === "H" && (
                    <span className="lab-flag lab-flag--high" title={`above ${spec?.high} ${spec?.unit}`}>↑ H</span>
                  )}
                  {flag === "L" && (
                    <span className="lab-flag lab-flag--low" title={`below ${spec?.low} ${spec?.unit}`}>↓ L</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => remove(i)}
                  className="lab-row__remove"
                  aria-label={`Remove ${r.test_name}`}
                >
                  <Trash2 size={13} strokeWidth={1.7} />
                </button>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </motion.ul>

      {rows.length > 0 && (
        <p className="labs-form__hint">
          The agents read each value with its unit and decide if it's out
          of range. The ↑ H / ↓ L marks are just a quick visual sanity check.
        </p>
      )}
    </div>
  );
}

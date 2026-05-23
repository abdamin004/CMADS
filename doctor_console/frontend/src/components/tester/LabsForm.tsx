import { useState } from "react";
import { FlaskConical, Sparkles } from "lucide-react";
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
 * Common clinical units the agents will recognise.
 * Curated to the ones actually used across the Synthea cohort's
 * latest_labs entries; "Other…" falls through to free-text entry.
 * The agents interpret value + unit together — the clinician does not
 * need to mark high/low, the system decides from the reference range.
 */
const UNITS = [
  "mg/dL", "g/dL", "%", "mmol/L", "mEq/L",
  "IU/L", "U/L", "ng/mL", "pg/mL", "µg/dL",
  "mIU/L", "µIU/mL", "mL/min/1.73 m²", "mm Hg", "bpm",
  "K/µL", "M/µL", "fL", "pg",
];

export function LabsForm({ value, onChange, onSmartImport }: Props) {
  const rows = value?.latest_labs ?? [];
  const [unitMode, setUnitMode] = useState<Record<number, "select" | "free">>({});

  function setRow(i: number, patch: Partial<(typeof rows)[number]>) {
    onChange({ latest_labs: rows.map((r, j) => j === i ? { ...r, ...patch } : r) });
  }
  function add(item: VocabularyItem) {
    onChange({ latest_labs: [...rows, { test_name: item.label, value: "", unit: "" }] });
  }
  function remove(i: number) {
    onChange({ latest_labs: rows.filter((_, j) => j !== i) });
    setUnitMode((m) => { const n = { ...m }; delete n[i]; return n; });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <VocabularyCombobox kind="lab" placeholder="Add a lab test…" onPick={add} />
        </div>
        {onSmartImport && (
          <button
            type="button"
            onClick={onSmartImport}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-emerald-700/60 bg-emerald-900/20 px-3 py-2 text-xs font-medium text-emerald-300 hover:bg-emerald-800/30 hover:border-emerald-600 transition-colors"
            title="Paste a chart note, drop a PDF, or upload a photo of a lab slip"
          >
            <Sparkles size={14} strokeWidth={1.8} />
            Smart import
          </button>
        )}
      </div>
      {rows.length === 0 && (
        <div className="flex items-center gap-3 rounded-md border border-dashed border-slate-700 px-4 py-3 text-sm text-slate-500">
          <FlaskConical size={20} strokeWidth={1.4} className="shrink-0 text-slate-600" />
          <span>No labs added yet. Type above to add the first.</span>
        </div>
      )}
      <ul className="space-y-3">
        {rows.map((r, i) => {
          const useFreeUnit =
            unitMode[i] === "free" || (r.unit !== "" && r.unit != null && !UNITS.includes(r.unit ?? ""));
          return (
            <li key={i}
                className="rounded-md border border-slate-700 bg-slate-900 px-3 py-3 text-sm">
              {/* Heading row: test name + delete */}
              <div className="mb-2 flex items-start gap-2">
                <span className="flex-1 break-words text-slate-100">
                  {r.test_name || <span className="italic text-slate-500">Unnamed lab</span>}
                </span>
                <button onClick={() => remove(i)}
                  aria-label="Remove lab"
                  className="text-slate-500 hover:text-rose-400">×</button>
              </div>
              {/* Inputs row: value + unit */}
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2">
                  <span className="text-xs uppercase tracking-wide text-slate-500">value</span>
                  <input
                    type="text" inputMode="decimal"
                    className="w-32 rounded bg-slate-800 px-2 py-1 text-slate-100"
                    placeholder="e.g. 9.4"
                    value={r.value ?? ""}
                    onChange={(e) => setRow(i, { value: e.target.value })} />
                </label>
                <label className="flex items-center gap-2">
                  <span className="text-xs uppercase tracking-wide text-slate-500">unit</span>
                  {useFreeUnit ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        className="w-40 rounded bg-slate-800 px-2 py-1 text-slate-100"
                        placeholder="e.g. mg/dL"
                        value={r.unit ?? ""}
                        onChange={(e) => setRow(i, { unit: e.target.value })} />
                      <button type="button"
                        onClick={() => { setRow(i, { unit: "" });
                                         setUnitMode((m) => ({ ...m, [i]: "select" })); }}
                        className="text-xs text-slate-500 underline hover:text-slate-300">
                        pick from list
                      </button>
                    </div>
                  ) : (
                    <select
                      className="w-40 rounded bg-slate-800 px-2 py-1 text-slate-100"
                      value={r.unit ?? ""}
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === "__other__") {
                          setUnitMode((m) => ({ ...m, [i]: "free" }));
                          setRow(i, { unit: "" });
                        } else {
                          setRow(i, { unit: v });
                        }
                      }}>
                      <option value="">— pick a unit —</option>
                      {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                      <option value="__other__">Other (type your own)…</option>
                    </select>
                  )}
                </label>
              </div>
            </li>
          );
        })}
      </ul>
      {rows.length > 0 && (
        <p className="text-xs text-slate-500">
          The agents read each value together with its unit and decide if it's out
          of range. You don't need to flag high or low yourself.
        </p>
      )}
    </div>
  );
}

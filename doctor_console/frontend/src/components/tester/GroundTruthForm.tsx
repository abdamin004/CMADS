import { useState } from "react";
import type { TestPatientPayload } from "../../types";

const THESIS_DISEASES = [
  "Ischemic heart disease",
  "Chronic congestive heart failure",
  "Essential hypertension",
  "Diabetes mellitus type 2",
  "End-stage renal disease",
  "Chronic kidney disease stage 3",
  "Chronic kidney disease stage 2",
  "Metabolic syndrome X",
];

interface Props {
  value: TestPatientPayload["ground_truth"];
  onChange: (next: TestPatientPayload["ground_truth"]) => void;
}

const MODES = [
  { key: "dropdown" as const, label: "Thesis disease" },
  { key: "other"    as const, label: "Other (free text)" },
  { key: "blank"    as const, label: "Leave blank" },
];

export function GroundTruthForm({ value, onChange }: Props) {
  const name = value?.target_condition?.name ?? "";
  const isThesis = THESIS_DISEASES.includes(name);
  const [mode, setMode] = useState<"dropdown"|"other"|"blank">(
    !name ? "blank" : isThesis ? "dropdown" : "other"
  );

  function set(n: string) {
    if (!n) onChange({});
    else onChange({ target_condition: { name: n } });
  }

  return (
    <div className="space-y-4">
      {/* Segmented control — same visual family as doctor-tab__bar */}
      <div className="segmented" role="group" aria-label="Ground truth mode">
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            role="radio"
            aria-checked={mode === m.key}
            onClick={() => { setMode(m.key); if (m.key === "blank") set(""); }}
            className={`segmented__btn${mode === m.key ? " segmented__btn--active" : ""}`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "dropdown" && (
        <select
          className="block w-full rounded-md border border-slate-700 bg-transparent px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          value={isThesis ? name : ""}
          onChange={(e) => set(e.target.value)}
        >
          <option value="">— pick one —</option>
          {THESIS_DISEASES.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      )}
      {mode === "other" && (
        <input
          type="text"
          className="block w-full rounded-md border border-slate-700 bg-transparent px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          placeholder="Disease name (free text)"
          value={!isThesis ? name : ""}
          onChange={(e) => set(e.target.value)}
        />
      )}
      {mode === "blank" && (
        <p className="text-sm text-slate-400">
          Evaluator (Stage 5) will be skipped — pipeline still produces a ranked
          differential but there's no DIRECT/INDIRECT/MISS verdict.
        </p>
      )}
    </div>
  );
}

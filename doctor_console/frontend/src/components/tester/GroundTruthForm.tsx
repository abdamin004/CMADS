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
      <div className="flex gap-2">
        {(["dropdown","other","blank"] as const).map(m => (
          <button key={m}
            onClick={() => { setMode(m); if (m==="blank") set(""); }}
            className={`rounded-md px-3 py-1 text-xs uppercase tracking-wide
                       ${mode === m ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-300"}`}>
            {m === "dropdown" ? "Thesis disease" : m === "other" ? "Other (free text)" : "Leave blank"}
          </button>
        ))}
      </div>
      {mode === "dropdown" && (
        <select className="block w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          value={isThesis ? name : ""}
          onChange={(e) => set(e.target.value)}>
          <option value="">— pick one —</option>
          {THESIS_DISEASES.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      )}
      {mode === "other" && (
        <input type="text"
          className="block w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          placeholder="Disease name (free text)"
          value={!isThesis ? name : ""}
          onChange={(e) => set(e.target.value)} />
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

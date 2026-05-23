import { useEffect, useState } from "react";
import { browseCohort, getCohortTemplate } from "../api";
import type { CohortBrowseRow, TestPatientPayload } from "../types";

const DISEASES = [
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
  onTemplate: (payload: TestPatientPayload) => void;
}

export function PatientPicker({ onTemplate }: Props) {
  const [disease, setDisease] = useState<string>("");
  const [ageRange, setAgeRange] = useState<[number, number]>([0, 120]);
  const [gender, setGender] = useState<string>("");
  const [rows, setRows] = useState<CohortBrowseRow[]>([]);
  const [selected, setSelected] = useState<CohortBrowseRow | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    browseCohort({
      disease: disease || undefined,
      age_min: ageRange[0], age_max: ageRange[1],
      gender:  gender || undefined,
      limit:   50,
    }).then((r) => { setRows(r); setSelected(null); })
      .finally(() => setLoading(false));
  }, [disease, ageRange[0], ageRange[1], gender]);

  async function useTemplate() {
    if (!selected) return;
    const payload = await getCohortTemplate(selected.uuid);
    onTemplate(payload);
  }

  return (
    <div className="flex h-full gap-4 p-4">
      {/* LEFT: facets */}
      <aside className="w-60 shrink-0 space-y-5 border-r border-slate-800 pr-3 text-sm">
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Disease</div>
          {DISEASES.map(d => (
            <label key={d} className="mb-1 flex items-center gap-2">
              <input type="radio" name="disease" checked={disease === d}
                onChange={() => setDisease(d === disease ? "" : d)} />
              <span className="text-slate-300">{d}</span>
            </label>
          ))}
          {disease && (
            <button onClick={() => setDisease("")}
              className="mt-1 text-xs text-slate-500 underline">clear</button>
          )}
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Age</div>
          <div className="flex items-center gap-2 text-slate-300">
            <input type="number" min={0} max={120} value={ageRange[0]}
              onChange={(e) => setAgeRange([Number(e.target.value), ageRange[1]])}
              className="w-16 rounded bg-slate-800 px-2 py-1 text-center" />
            <span className="text-slate-500">–</span>
            <input type="number" min={0} max={120} value={ageRange[1]}
              onChange={(e) => setAgeRange([ageRange[0], Number(e.target.value)])}
              className="w-16 rounded bg-slate-800 px-2 py-1 text-center" />
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Gender</div>
          <div className="flex gap-2">
            {["", "M", "F", "Other"].map((g) => (
              <button key={g || "any"}
                onClick={() => setGender(g === gender ? "" : g)}
                className={`rounded-md px-3 py-1 text-xs
                           ${gender === g ? "bg-emerald-600 text-white"
                                          : "bg-slate-800 text-slate-300"}`}>
                {g || "Any"}
              </button>
            ))}
          </div>
        </div>
      </aside>
      {/* MIDDLE: list */}
      <section className="w-80 shrink-0 overflow-y-auto border-r border-slate-800 pr-2">
        <div className="mb-2 text-xs text-slate-400">
          {loading ? "Loading…" : `${rows.length} patient${rows.length === 1 ? "" : "s"}`}
        </div>
        <ul className="space-y-1">
          {rows.map(row => (
            <li key={row.uuid}>
              <button onClick={() => setSelected(row)}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm
                           ${selected?.uuid === row.uuid
                              ? "bg-emerald-600/20 text-emerald-200"
                              : "text-slate-300 hover:bg-slate-800"}`}>
                <div className="font-mono text-xs text-slate-500">{row.uuid.slice(0,11)}</div>
                <div>{row.age ?? "?"}{row.gender ?? "?"} · {row.disease ?? "—"}</div>
                <div className="mt-0.5 text-xs text-slate-500">{row.active_count} active conditions</div>
              </button>
            </li>
          ))}
        </ul>
      </section>
      {/* RIGHT: preview */}
      <section className="flex-1 overflow-y-auto pr-2">
        {!selected && (
          <div className="grid h-full place-items-center text-sm text-slate-500">
            Select a patient on the left to preview, then "Use as template" to start editing.
          </div>
        )}
        {selected && (
          <div className="space-y-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-400">Selected patient</div>
              <div className="font-mono text-sm text-slate-400">{selected.uuid}</div>
              <div className="mt-1 text-slate-100">
                {selected.age}{selected.gender} · {selected.disease}
              </div>
              <div className="mt-0.5 text-sm text-slate-500">
                {selected.active_count} active conditions
              </div>
            </div>
            <button onClick={useTemplate}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500">
              Use as template →
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

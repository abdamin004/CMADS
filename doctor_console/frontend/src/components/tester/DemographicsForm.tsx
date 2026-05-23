import type { TestPatientPayload } from "../../types";

interface Props {
  value: TestPatientPayload["demographics"];
  onChange: (next: TestPatientPayload["demographics"]) => void;
}

export function DemographicsForm({ value, onChange }: Props) {
  function set<K extends keyof typeof value>(k: K, v: (typeof value)[K]) {
    onChange({ ...value, [k]: v });
  }
  return (
    <div className="space-y-4">
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Age</span>
        <input type="number" min={0} max={120} value={value.age ?? ""}
          onChange={(e) => set("age", Number(e.target.value))}
          className="mt-1 block w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Gender</span>
        <div className="mt-1 flex gap-3">
          {(["M","F","Other"] as const).map(g => (
            <button key={g}
              onClick={() => set("gender", g)}
              className={`rounded-md px-3 py-1 text-sm
                         ${value.gender === g ? "bg-emerald-600 text-white"
                                              : "bg-slate-800 text-slate-300"}`}>
              {g}
            </button>
          ))}
        </div>
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Race (optional)</span>
        <input type="text" value={value.race ?? ""}
          onChange={(e) => set("race", e.target.value)}
          className="mt-1 block w-64 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">BMI (optional)</span>
        <input type="number" step="0.1" value={value.bmi ?? ""}
          onChange={(e) => set("bmi", Number(e.target.value))}
          className="mt-1 block w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
      </label>
    </div>
  );
}

import type { TestPatientPayload } from "../../types";

interface Props {
  value: TestPatientPayload["visits"];
  onChange: (next: TestPatientPayload["visits"]) => void;
}

export function VisitsForm({ value, onChange }: Props) {
  const v = (value as Record<string, number | undefined>) ?? {};
  function set(k: string, n: number) {
    onChange({ ...v, [k]: n });
  }
  const fields: Array<[string,string]> = [
    ["total","Total"], ["emergency","Emergency"], ["inpatient","Inpatient"],
    ["outpatient","Outpatient"], ["wellness","Wellness"],
  ];
  return (
    <div className="grid grid-cols-2 gap-4">
      {fields.map(([k, label]) => (
        <label key={k} className="block">
          <span className="text-xs uppercase tracking-wide text-slate-400">{label}</span>
          <input type="number" min={0} value={v[k] ?? ""}
            onChange={(e) => set(k, Number(e.target.value))}
            className="mt-1 block w-32 rounded-md border border-slate-700 bg-transparent px-3 py-2 text-sm text-slate-100" />
        </label>
      ))}
    </div>
  );
}

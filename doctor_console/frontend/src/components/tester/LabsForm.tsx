import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["labs"];
  onChange: (next: TestPatientPayload["labs"]) => void;
}

export function LabsForm({ value, onChange }: Props) {
  const rows = value?.latest_labs ?? [];
  function setRow(i: number, patch: Partial<(typeof rows)[number]>) {
    onChange({ latest_labs: rows.map((r, j) => j === i ? { ...r, ...patch } : r) });
  }
  function add(item: VocabularyItem) {
    onChange({ latest_labs: [...rows, { test_name: item.label, value: "", unit: "" }] });
  }
  function remove(i: number) {
    onChange({ latest_labs: rows.filter((_, j) => j !== i) });
  }
  return (
    <div className="space-y-4">
      <VocabularyCombobox kind="lab" placeholder="Add a lab test…" onPick={add} />
      <ul className="space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="flex gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm">
            <span className="flex-[2] text-slate-200">{r.test_name}</span>
            <input className="flex-1 rounded bg-slate-800 px-2 py-1 text-slate-100"
              placeholder="value" value={r.value ?? ""}
              onChange={(e) => setRow(i, { value: e.target.value })} />
            <input className="flex-1 rounded bg-slate-800 px-2 py-1 text-slate-100"
              placeholder="unit" value={r.unit ?? ""}
              onChange={(e) => setRow(i, { unit: e.target.value })} />
            <select className="rounded bg-slate-800 px-2 py-1 text-slate-100"
              value={r.flag ?? ""}
              onChange={(e) => setRow(i, { flag: e.target.value })}>
              <option value="">—</option>
              <option value="H">H (high)</option>
              <option value="L">L (low)</option>
              <option value="HH">HH</option>
              <option value="LL">LL</option>
            </select>
            <button onClick={() => remove(i)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

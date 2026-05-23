import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["medications"];
  onChange: (next: TestPatientPayload["medications"]) => void;
}

export function MedicationsForm({ value, onChange }: Props) {
  const active = value?.active ?? [];
  function add(item: VocabularyItem) {
    onChange({ active: [...active, { medication: item.label,
                                      rx_code: item.code ?? undefined }] });
  }
  function remove(idx: number) {
    onChange({ active: active.filter((_, i) => i !== idx) });
  }
  return (
    <div className="space-y-4">
      <VocabularyCombobox kind="medication" placeholder="Type a medication…" onPick={add} />
      <ul className="space-y-2">
        {active.map((m, i) => (
          <li key={i} className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm">
            <span className="flex-1">{m.medication}</span>
            {m.rx_code && <span className="text-xs text-slate-500">{m.rx_code}</span>}
            <button onClick={() => remove(i)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

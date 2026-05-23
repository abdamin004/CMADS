import { ListChecks } from "lucide-react";
import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["conditions"];
  onChange: (next: TestPatientPayload["conditions"]) => void;
}

export function ConditionsForm({ value, onChange }: Props) {
  const active = value?.active ?? [];
  function add(item: VocabularyItem) {
    onChange({ active: [...active, { condition: item.label,
                                      code: item.code ?? undefined }] });
  }
  function remove(idx: number) {
    onChange({ active: active.filter((_, i) => i !== idx) });
  }
  return (
    <div className="space-y-4">
      <VocabularyCombobox kind="condition" placeholder="Type a condition…" onPick={add} />
      {active.length === 0 ? (
        <div className="flex items-center gap-3 rounded-md border border-dashed border-slate-700 px-4 py-3 text-sm text-slate-500">
          <ListChecks size={20} strokeWidth={1.4} className="shrink-0 text-slate-600" />
          <span>No conditions added yet. Type above to add the first.</span>
        </div>
      ) : (
        <ul className="space-y-2">
          {active.map((c, i) => (
            <li key={i} className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm">
              <span className="flex-1">{c.condition}</span>
              {c.code && <span className="text-xs text-slate-500">{c.code}</span>}
              <button onClick={() => remove(i)}
                aria-label="Remove condition"
                className="text-slate-500 hover:text-rose-400 transition-colors">×</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

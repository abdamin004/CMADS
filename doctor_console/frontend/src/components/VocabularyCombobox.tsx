import { useEffect, useRef, useState } from "react";
import { getVocabulary } from "../api";
import type { VocabularyItem } from "../types";

interface Props {
  kind: "condition" | "medication" | "lab";
  placeholder?: string;
  onPick: (item: VocabularyItem) => void;
}

export function VocabularyCombobox({ kind, placeholder, onPick }: Props) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<VocabularyItem[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [loading, setLoading] = useState(false);
  const debounce = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!open) return;
    window.clearTimeout(debounce.current);
    setLoading(true);
    debounce.current = window.setTimeout(() => {
      getVocabulary(kind, q)
        .then(setItems)
        .catch(() => setItems([]))
        .finally(() => setLoading(false));
    }, 200);
    return () => {
      window.clearTimeout(debounce.current);
      setLoading(false);
    };
  }, [q, open, kind]);

  const exactMatch = items.some(
    (it) => it.label.toLowerCase() === q.toLowerCase(),
  );
  const showEmpty = !loading && q.length > 0 && items.length === 0;

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, items.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlight < items.length) {
        onPick(items[highlight]);
      } else if (q && !exactMatch) {
        onPick({ label: q, code: null });
      }
      setQ("");
      setOpen(false);
      setHighlight(0);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const dropdownVisible = open && (loading || q.length > 0 || items.length > 0);

  return (
    <div className="relative">
      <input
        className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm
                   text-slate-100 placeholder-slate-500 focus:border-emerald-500
                   focus:outline-none focus:ring-1 focus:ring-emerald-500"
        placeholder={placeholder || "Type to search…"}
        value={q}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 100)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setHighlight(0); }}
        onKeyDown={handleKey}
        aria-autocomplete="list"
        aria-expanded={dropdownVisible}
      />
      {dropdownVisible && (
        <ul
          role="listbox"
          className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-md
                     border border-slate-700 bg-slate-900 shadow-lg"
        >
          {/* Loading state */}
          {loading && items.length === 0 && (
            <li className="flex items-center gap-2 px-3 py-2 text-sm text-slate-500" aria-live="polite">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-slate-500" />
              Searching…
            </li>
          )}

          {/* Results */}
          {items.map((it, i) => (
            <li
              key={`${it.label}-${it.code ?? "-"}`}
              role="option"
              aria-selected={i === highlight}
              className={`cursor-pointer px-3 py-1.5 text-sm
                          ${i === highlight ? "bg-emerald-600/20 text-emerald-200"
                                            : "text-slate-200 hover:bg-slate-800"}`}
              onMouseDown={(e) => { e.preventDefault(); onPick(it);
                                    setQ(""); setOpen(false); setHighlight(0); }}
            >
              <span>{it.label}</span>
              {it.code && (
                <span className="ml-2 text-xs text-slate-500">{it.code}</span>
              )}
            </li>
          ))}

          {/* No matches hint — shown above the "Use anyway" footer */}
          {showEmpty && !exactMatch && (
            <li className="px-3 py-1.5 text-xs text-slate-500" aria-live="polite">
              (no matches in cohort vocabulary)
            </li>
          )}

          {/* "Use anyway" footer */}
          {q && !exactMatch && !loading && (
            <li
              role="option"
              aria-selected={highlight === items.length}
              className={`cursor-pointer border-t border-slate-700 px-3 py-1.5 text-sm
                          ${highlight === items.length ? "bg-amber-600/20 text-amber-200"
                                                       : "text-amber-300 hover:bg-slate-800"}`}
              onMouseDown={(e) => { e.preventDefault();
                                    onPick({ label: q, code: null });
                                    setQ(""); setOpen(false); setHighlight(0); }}
            >
              <span className="mr-2">⚠</span>Use anyway: <span className="italic">{q}</span>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

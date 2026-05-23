import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ArrowUpDown } from "lucide-react";
import type { PerDiseaseRow } from "../types";

type Props = {
  rows: PerDiseaseRow[];
  /** Whether the table body is expanded by default. */
  defaultOpen?: boolean;
};

type SortKey =
  | "disease" | "n" | "direct" | "indirect" | "miss" | "foundPct" | "avgRank";
type SortDir = "asc" | "desc";

// Default the table to "Found % descending" — the metric researchers reach for
// first ("which diseases is the system strongest / weakest on?"). Ranking
// alphabetically by disease name hides the answer behind a scroll.
const DEFAULT_SORT: SortKey = "foundPct";
const DEFAULT_DIR: SortDir = "desc";

// Numeric columns toggle desc-first; text column toggles asc-first.
function initialDirFor(key: SortKey): SortDir {
  return key === "disease" ? "asc" : "desc";
}

function compareRows(a: PerDiseaseRow, b: PerDiseaseRow, key: SortKey, dir: SortDir): number {
  let av: number | string;
  let bv: number | string;
  if (key === "disease") {
    av = a.disease.toLowerCase();
    bv = b.disease.toLowerCase();
  } else if (key === "avgRank") {
    // Null avg-rank sorts to the end regardless of direction so weak rows
    // don't masquerade as a perfect score.
    av = a.avgRank ?? Number.POSITIVE_INFINITY;
    bv = b.avgRank ?? Number.POSITIVE_INFINITY;
  } else {
    av = a[key];
    bv = b[key];
  }
  if (av < bv) return dir === "asc" ? -1 : 1;
  if (av > bv) return dir === "asc" ? 1 : -1;
  return 0;
}

type ColDef = { key: SortKey; label: string; numeric: boolean };
const COLUMNS: ColDef[] = [
  { key: "disease",  label: "Disease",   numeric: false },
  { key: "n",        label: "n",         numeric: true  },
  { key: "direct",   label: "DIRECT",    numeric: true  },
  { key: "indirect", label: "INDIRECT",  numeric: true  },
  { key: "miss",     label: "MISS",      numeric: true  },
  { key: "foundPct", label: "Found %",   numeric: true  },
  { key: "avgRank",  label: "Avg rank",  numeric: true  },
];

/**
 * Per-target-disease breakdown. Editorial table; right-aligned numerals in
 * JetBrains Mono so columns line up vertically; per-row tint by foundPct.
 * The header is a collapse toggle so the section folds shut on long pages.
 *
 * Columns are sortable — click any header to sort. Found % desc is the
 * default since "where am I strong/weak" is the question that brings
 * researchers here.
 */
export function PerDiseaseTable({ rows, defaultOpen = true }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [sortKey, setSortKey] = useState<SortKey>(DEFAULT_SORT);
  const [sortDir, setSortDir] = useState<SortDir>(DEFAULT_DIR);

  const sortedRows = useMemo(() => {
    const copy = rows.slice();
    copy.sort((a, b) => compareRows(a, b, sortKey, sortDir));
    return copy;
  }, [rows, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(initialDirFor(key));
    }
  };

  return (
    <section className={`panel per-disease${open ? "" : " is-collapsed"}`}>
      <button
        type="button"
        className="panel-heading panel-heading--toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div>
          <div className="eyebrow">Per ground-truth disease</div>
          <h3>Where the system is strong, and where it isn't</h3>
          {open ? (
            <p>
              Grouped by the patient's confirmed Synthea diagnosis. Found % is
              the share of patients in that group where the system surfaced the
              correct disease in its top-5 differential. Click any column to sort.
            </p>
          ) : (
            <p className="panel-heading__collapsed-hint">
              {rows.length} disease{rows.length === 1 ? "" : "s"} · click to expand
            </p>
          )}
        </div>
        <ChevronDown
          size={16}
          strokeWidth={2}
          className={`panel-heading__chevron${open ? " is-open" : ""}`}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="per-disease__scroll">
          <table className="per-disease__table">
            <thead>
              <tr>
                {COLUMNS.map((col) => {
                  const isActive = sortKey === col.key;
                  const ariaSort = isActive
                    ? (sortDir === "asc" ? "ascending" : "descending")
                    : "none";
                  return (
                    <th
                      key={col.key}
                      className={`${col.numeric ? "num " : ""}per-disease__th${isActive ? " is-sorted" : ""}`}
                      aria-sort={ariaSort}
                    >
                      <button
                        type="button"
                        className="per-disease__sort-btn"
                        onClick={() => handleSort(col.key)}
                        aria-label={
                          isActive
                            ? `Sorted by ${col.label} ${sortDir === "asc" ? "ascending" : "descending"}, click to reverse`
                            : `Sort by ${col.label}`
                        }
                      >
                        <span>{col.label}</span>
                        {isActive ? (
                          sortDir === "asc"
                            ? <ChevronUp size={12} strokeWidth={2.2} aria-hidden />
                            : <ChevronDown size={12} strokeWidth={2.2} aria-hidden />
                        ) : (
                          <ArrowUpDown
                            size={11}
                            strokeWidth={1.8}
                            aria-hidden
                            className="per-disease__sort-idle"
                          />
                        )}
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => {
                const tone = row.foundPct >= 90
                  ? "great" : row.foundPct >= 75
                  ? "good" : row.foundPct >= 50
                  ? "ok" : "weak";
                return (
                  <tr key={row.disease} className={`per-disease__row per-disease__row--${tone}`}>
                    <td>{row.disease}</td>
                    <td className="num mono">{row.n}</td>
                    <td className="num mono">{row.direct}</td>
                    <td className="num mono">{row.indirect}</td>
                    <td className="num mono">{row.miss}</td>
                    <td className="num mono"><strong>{row.foundPct.toFixed(0)}%</strong></td>
                    <td className="num mono">
                      {row.avgRank !== null && row.avgRank !== undefined
                        ? row.avgRank.toFixed(2) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

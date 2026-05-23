import { ExternalLink, Loader2 } from "lucide-react";
import type { CohortRow } from "../types";

type Props = {
  rows: CohortRow[];
  loading: boolean;
  activeCohortId?: string;
  onPick?: (id: string) => void;
  onOpenPatient?: (uuid: string) => void;
};

/**
 * Master cohort-comparison table. Replaces the Streamlit "Run cohort
 * comparison" view (portal/dashboard.py:344-379). Rows are sorted by
 * category then by patient count; clicking a row sets the active cohort
 * in the overview above.
 */
export function CohortCompareTable({ rows, loading, activeCohortId, onPick }: Props) {
  if (loading) {
    return (
      <div className="empty-state">
        <Loader2 size={16} className="spin" /> Loading cohort comparison…
      </div>
    );
  }
  if (!rows.length) {
    return <div className="empty-state">No research cohorts found on disk.</div>;
  }

  const sorted = [...rows].sort((a, b) => {
    if (a.category !== b.category) return a.category.localeCompare(b.category);
    return b.n - a.n;
  });

  return (
    <div className="cohort-compare__scroll">
      <table className="cohort-compare__table">
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Category</th>
            <th>Model</th>
            <th className="num">n</th>
            <th className="num">DIRECT %</th>
            <th className="num">Found %</th>
            <th className="num">Rank-1 / found</th>
            <th className="num">Median time</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={row.id}
              className={`cohort-compare__row${row.id === activeCohortId ? " is-active" : ""}`}
              onClick={() => onPick?.(row.id)}
            >
              <td className="cohort-compare__name">
                <strong>{row.label}</strong>
                <span className="mono cohort-compare__id">{row.id}</span>
              </td>
              <td>{row.category}</td>
              <td className="mono">{row.model}</td>
              <td className="num mono">{row.n}</td>
              <td className="num mono"><strong>{row.directPct.toFixed(1)}%</strong></td>
              <td className="num mono">{row.foundPct.toFixed(1)}%</td>
              <td className="num mono">{row.rank1PctOfFound.toFixed(0)}%</td>
              <td className="num mono">
                {row.medianTimeS ? `${Math.round(row.medianTimeS)}s` : "—"}
              </td>
              <td>
                {row.id === activeCohortId ? null : (
                  <button
                    type="button"
                    className="ghost-button"
                    style={{ minHeight: 30, fontSize: "0.78rem" }}
                    onClick={(e) => { e.stopPropagation(); onPick?.(row.id); }}
                  >
                    <ExternalLink size={13} /> View
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

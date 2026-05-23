import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { RankBucket } from "../types";

type Props = {
  buckets: RankBucket[];
  /** Whether the histogram body is expanded by default. */
  defaultOpen?: boolean;
};

/**
 * "Where was the target found?" histogram.
 *
 * Pure SVG bars (no chart-lib), tints by tone:
 * success for rank-1, accent for ranks 2-3, warning for 4-5, critical for miss.
 * The header is a collapse toggle — the whole section folds shut so screens
 * with many widgets don't get crowded.
 */
export function RankHistogram({ buckets, defaultOpen = true }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const tones = ["success", "accent", "accent", "warning", "critical"];
  const labels: Record<string, string> = {
    "1": "Rank 1", "2": "Rank 2", "3": "Rank 3", "4-5": "Rank 4–5", "miss": "Miss",
  };
  const total = buckets.reduce((acc, b) => acc + (b.count || 0), 0);

  // Build the "at a glance" summary line shown when collapsed. Pre-computes
  // the headline shares (rank-1, rank-2-3, miss) so the user can scan the
  // distribution shape without expanding the section.
  const summary = (() => {
    if (!total) return null;
    const at = (lbl: string) => buckets.find((b) => b.label === lbl)?.count ?? 0;
    const r1 = at("1");
    const r23 = at("2") + at("3");
    const miss = at("miss");
    const pct = (v: number) => `${Math.round((100 * v) / total)}%`;
    return { r1Pct: pct(r1), r23Pct: pct(r23), missPct: pct(miss) };
  })();

  return (
    <section className={`panel rank-histogram${open ? "" : " is-collapsed"}`}>
      <button
        type="button"
        className="panel-heading panel-heading--toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div>
          <div className="eyebrow">Where the target was found</div>
          <h3>Rank distribution</h3>
          {open ? (
            <p>
              The doctor wants the right answer at the top of the list. This breaks
              down, for every cohort, where the system placed the confirmed disease.
            </p>
          ) : summary ? (
            <p className="panel-heading__collapsed-hint rank-histogram__summary">
              <span className="mono"><strong>Rank-1</strong> {summary.r1Pct}</span>
              <span aria-hidden>·</span>
              <span className="mono"><strong>Rank 2–3</strong> {summary.r23Pct}</span>
              <span aria-hidden>·</span>
              <span className="mono"><strong>Miss</strong> {summary.missPct}</span>
              <span className="rank-histogram__summary-cta mono">click to expand</span>
            </p>
          ) : (
            <p className="panel-heading__collapsed-hint">
              {total} patients · click to expand
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
        <div className="rank-histogram__rows">
          {buckets.map((bucket, idx) => {
            const tone = tones[idx] ?? "accent";
            const pct = max ? Math.round((100 * bucket.count) / max) : 0;
            return (
              <div className={`rank-row rank-row--${tone}`} key={bucket.label}>
                <div className="rank-row__label">{labels[bucket.label] ?? bucket.label}</div>
                <div className="rank-row__bar">
                  <div className="rank-row__bar-fill" style={{ width: `${pct}%` }} />
                  <span className="rank-row__count mono">{bucket.count}</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

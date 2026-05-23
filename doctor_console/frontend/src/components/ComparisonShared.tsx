/**
 * Shared per-arm presentation primitives used by every comparison tab
 * (Memory A/B, Model comparison, MAS vs single-LLM). One source of truth so
 * the three tabs read consistently.
 */
import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { CohortAggregates, PerDiseaseRow, RankBucket } from "../types";
import { cascadeListContainer, cascadeRow } from "../lib/motion";
import { KpiTile } from "./KpiTile";
import { PerDiseaseTable } from "./PerDiseaseTable";
import { RankHistogram } from "./RankHistogram";

export function ArmSection({
  eyebrow, label, tone, agg, rankDist, perDisease,
}: {
  eyebrow: string;
  label: string;
  /** Visual emphasis. "primary" = the winning / principal configuration. */
  tone: "neutral" | "primary";
  agg?: CohortAggregates;
  rankDist?: RankBucket[];
  perDisease?: PerDiseaseRow[];
}) {
  // DIRECT and INDIRECT are intentionally NOT shown as standalone tiles —
  // they live in the comparison table below where the deltas are colour-coded.
  // The arm-level KPI strip keeps only the headline (Found), the quality
  // floor (MISS), and the precision-within-found number.
  const kpis = agg ? [
    { label: "Found",
      value: `${agg.foundPct.toFixed(1)}%`,
      tone: (tone === "primary" ? "success" : undefined) as "success" | undefined },
    { label: "MISS",
      value: `${agg.missPct.toFixed(1)}%`,
      tone: (agg.missPct > 10 ? "critical" : undefined) as "critical" | undefined },
    { label: "Rank-1-of-found",  value: `${agg.rank1PctOfFound.toFixed(1)}%` },
  ] : [];

  return (
    <section className={`memory-ab__arm memory-ab__arm--${tone}`}>
      <header className="memory-ab__arm-head">
        <div className="eyebrow">{eyebrow}</div>
        <h3>{label}</h3>
        {agg ? <span className="memory-ab__arm-n mono">n = {agg.n}</span> : null}
      </header>

      {agg ? (
        <motion.section
          className="kpi-grid"
          initial="hidden"
          animate="visible"
          variants={cascadeListContainer}
        >
          {kpis.map((kpi, idx) => (
            <motion.div key={kpi.label} variants={cascadeRow}>
              <KpiTile index={idx} {...kpi} />
            </motion.div>
          ))}
        </motion.section>
      ) : null}

      {(rankDist || perDisease) ? (
        <details className="arm-collapsible">
          <summary>
            <span>Breakdowns</span>
            <span className="arm-collapsible__hint mono">
              rank distribution &middot; per ground-truth disease
            </span>
            <span className="arm-collapsible__toggle" aria-hidden="true">▾</span>
          </summary>
          <div className="arm-collapsible__body arm-collapsible__stack">
            {rankDist ? (
              <div className="arm-collapsible__section">
                <div className="arm-collapsible__section-head">
                  <strong>Rank distribution</strong>
                  <span className="mono">where the target lands in the differential</span>
                </div>
                <RankHistogram buckets={rankDist} />
              </div>
            ) : null}
            {perDisease ? (
              <div className="arm-collapsible__section">
                <div className="arm-collapsible__section-head">
                  <strong>Per ground-truth disease</strong>
                  <span className="mono">accuracy broken down by target condition</span>
                </div>
                <PerDiseaseTable rows={perDisease} />
              </div>
            ) : null}
          </div>
        </details>
      ) : null}
    </section>
  );
}

export function ComparisonPanel({
  offAgg, onAgg, offLabel, onLabel, title = "Comparison",
}: {
  offAgg: CohortAggregates;
  onAgg: CohortAggregates;
  offLabel: string;
  onLabel: string;
  title?: string;
}) {
  // Row order is doctor-readable: the headline (Found) leads, then the
  // top-1 quality split (DIRECT/INDIRECT), then the rank-precision metrics
  // (Rank-1, Rank-2 within found), then the failure modes (MISS / runtime).
  // INDIRECT and MISS are "lower-is-better" — colour logic flips via
  // `goodIfUp`.
  const rows: Array<{ label: string; left: number; right: number; goodIfUp: boolean }> = [
    { label: "Found (D + I)",       left: offAgg.foundPct,         right: onAgg.foundPct,          goodIfUp: true  },
    { label: "DIRECT",              left: offAgg.directPct,        right: onAgg.directPct,         goodIfUp: true  },
    { label: "INDIRECT",            left: offAgg.indirectPct,      right: onAgg.indirectPct,       goodIfUp: false },
    { label: "Rank-1 within found", left: offAgg.rank1PctOfFound,  right: onAgg.rank1PctOfFound,   goodIfUp: true  },
    { label: "Rank-2 within found", left: offAgg.rank2PctOfFound ?? 0, right: onAgg.rank2PctOfFound ?? 0, goodIfUp: true  },
    { label: "MISS",                left: offAgg.missPct,          right: onAgg.missPct,           goodIfUp: false },
    { label: "Median runtime",      left: offAgg.medianTimeS,      right: onAgg.medianTimeS,       goodIfUp: false },
  ];

  return (
    <section className="panel memory-ab__compare">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">Side-by-side delta</div>
          <h3>{title}</h3>
          <p>
            Green = the principal configuration wins on this metric. Red = the
            baseline wins. The colour reflects clinical desirability, not just
            the sign of the delta (lower MISS, INDIRECT, runtime are good).
          </p>
        </div>
      </div>
      <table className="comparison-view__kpi-table">
        <thead>
          <tr>
            <th></th>
            <th className="num">{offLabel}</th>
            <th className="num">{onLabel}</th>
            <th className="num">Δ</th>
          </tr>
        </thead>
        <motion.tbody
          initial="hidden"
          animate="visible"
          variants={cascadeListContainer}
        >
          {rows.map((row) => {
            const delta = row.right - row.left;
            const isRuntime = row.label === "Median runtime";
            const threshold = isRuntime ? 0.5 : 0.5;
            const flat = Math.abs(delta) < threshold;
            const candidateBetter = (delta > 0) === row.goodIfUp;
            const tone = flat ? "flat" : candidateBetter ? "good" : "bad";
            const fmt = isRuntime
              ? (n: number) => `${Math.round(n)}s`
              : (n: number) => `${n.toFixed(1)}%`;
            const absFmt = isRuntime
              ? (n: number) => `${Math.round(n)}s`
              : (n: number) => `${n.toFixed(1)} pp`;
            return (
              <motion.tr
                key={row.label}
                variants={cascadeRow}
                className={`compare-row compare-row--${tone}`}
              >
                <td>{row.label}</td>
                <td className="num mono">{fmt(row.left)}</td>
                <td className="num mono">{fmt(row.right)}</td>
                <td className={`num mono delta delta--${tone}`}>
                  {flat ? <Minus size={13} />
                    : delta > 0 ? <ArrowUpRight size={13} />
                    : <ArrowDownRight size={13} />}
                  {absFmt(Math.abs(delta))}
                </td>
              </motion.tr>
            );
          })}
        </motion.tbody>
      </table>
    </section>
  );
}

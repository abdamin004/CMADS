import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Loader2, RotateCw } from "lucide-react";
import { getStatsOverview } from "../api";
import type { StatsOverview as StatsOverviewT } from "../types";
import { cascade, cascadeItem, cascadeListContainer, cascadeRow } from "../lib/motion";
import { KpiTile } from "./KpiTile";
import { PerDiseaseTable } from "./PerDiseaseTable";
import { PrecisionAtKCard } from "./PrecisionAtKCard";
import { RankHistogram } from "./RankHistogram";

type Props = {
  onOpenPatient?: (uuid: string) => void;
};

// Researcher overview is locked to the main thesis cohort. The other cohorts
// (memory A/B variants, model comparisons, baselines) live behind the
// dedicated comparison tabs — they aren't presented here as alternatives to
// the headline accuracy number. The "multi_level" virtual cohort unions the
// three multi-level memory source dirs and reads the latest evaluations
// (evaluation_canon.json where present, otherwise evaluation.json) — this
// is the principal headline configuration reported in the thesis.
const MAIN_COHORT = "multi_level";

/**
 * Researcher landing view — shows the headline system accuracy on the main
 * 160-patient cohort only. Five KPI tiles, the Precision @ K interactive
 * card, then the rank distribution and per-disease breakdown side by side.
 */
export function StatsOverview({ onOpenPatient: _onOpenPatient }: Props) {
  const [overview, setOverview] = useState<StatsOverviewT | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getStatsOverview(MAIN_COHORT));
    } catch (err) {
      setOverview(undefined);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const aggregates = overview?.aggregates;

  const kpis = useMemo(() => {
    if (!aggregates) return [];
    const directShare = aggregates.n ? (100 * aggregates.direct) / aggregates.n : 0;
    return [
      {
        label: "Patients reviewed",
        value: String(aggregates.n),
        secondary: `cohort · ${MAIN_COHORT}`,
      },
      {
        label: "System found rate",
        value: `${aggregates.foundPct.toFixed(1)}%`,
        tone: "success" as const,
        secondary: `direct ${directShare.toFixed(0)}%`,
      },
      {
        label: "Median runtime",
        value: aggregates.medianTimeS ? `${Math.round(aggregates.medianTimeS)}s` : "—",
        secondary: "per patient · end-to-end",
      },
    ];
  }, [aggregates]);

  return (
    <motion.div
      className="stats-overview"
      initial="hidden"
      animate="visible"
      variants={cascade}
    >
      <motion.section variants={cascadeItem} className="stats-overview__head panel">
        <div>
          <div className="eyebrow">Main system accuracy</div>
          <h2>{overview?.resultSet.label ?? "Loading…"}</h2>
          <p className="stats-overview__sub">
            {overview ? (
              <>
                Seven-agent pipeline · {overview.resultSet.model ?? "—"}
                {overview.aggregates?.n
                  ? ` · ${overview.aggregates.n} patients evaluated`
                  : ""}
              </>
            ) : "Aggregating per-agent outputs from the headline cohort."}
          </p>
        </div>
      </motion.section>

      {error ? (
        <motion.div
          variants={cascadeItem}
          className="alert alert--with-action"
          role="alert"
          aria-live="polite"
        >
          <AlertCircle size={16} aria-hidden />
          <span>{error}</span>
          <button
            type="button"
            className="alert__action"
            onClick={() => void load()}
            disabled={loading}
          >
            {loading
              ? <Loader2 size={13} strokeWidth={1.8} className="spin" aria-hidden />
              : <RotateCw size={13} strokeWidth={1.8} aria-hidden />}
            Retry
          </button>
        </motion.div>
      ) : null}

      {loading ? (
        <motion.div variants={cascadeItem} className="empty-state">
          <Loader2 size={16} className="spin" /> Computing aggregates…
        </motion.div>
      ) : null}

      {aggregates ? (
        // KPI grid uses cascadeListContainer — it rises as one beat of
        // the page cascade AND staggers its own children tightly so
        // the tiles read as one wave rather than a second separate one.
        <motion.section className="kpi-grid" variants={cascadeListContainer}>
          {kpis.map((kpi, idx) => (
            <motion.div key={kpi.label} variants={cascadeRow}>
              <KpiTile index={idx} {...kpi} />
            </motion.div>
          ))}
        </motion.section>
      ) : null}

      {overview ? (
        <motion.div variants={cascadeItem}>
          <PrecisionAtKCard
            cohortLabel={overview.resultSet.label}
            buckets={overview.rankDistribution}
            totalN={aggregates?.n ?? 0}
          />
        </motion.div>
      ) : null}

      {overview ? (
        <motion.div variants={cascadeItem}>
          <details className="arm-collapsible">
            <summary>
              <span>Breakdowns</span>
              <span className="arm-collapsible__hint mono">
                rank distribution &middot; per ground-truth disease
              </span>
              <span className="arm-collapsible__toggle" aria-hidden="true">▾</span>
            </summary>
            <div className="arm-collapsible__body arm-collapsible__stack">
              <div className="arm-collapsible__section">
                <div className="arm-collapsible__section-head">
                  <strong>Rank distribution</strong>
                  <span className="mono">where the target lands in the differential</span>
                </div>
                <RankHistogram buckets={overview.rankDistribution} />
              </div>
              <div className="arm-collapsible__section">
                <div className="arm-collapsible__section-head">
                  <strong>Per ground-truth disease</strong>
                  <span className="mono">accuracy broken down by target condition</span>
                </div>
                <PerDiseaseTable rows={overview.perDisease} />
              </div>
            </div>
          </details>
        </motion.div>
      ) : null}
    </motion.div>
  );
}

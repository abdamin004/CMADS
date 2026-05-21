import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Loader2 } from "lucide-react";
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
    return [
      {
        label: "Patients reviewed",
        value: String(aggregates.n),
      },
      {
        label: "System found rate",
        value: `${aggregates.foundPct.toFixed(1)}%`,
        tone: "success" as const,
      },
      {
        label: "Median runtime",
        value: aggregates.medianTimeS ? `${Math.round(aggregates.medianTimeS)}s` : "—",
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
        <motion.div variants={cascadeItem} className="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
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
        <motion.section
          variants={cascadeItem}
          className="stats-overview__grid"
        >
          <RankHistogram buckets={overview.rankDistribution} />
          <PerDiseaseTable rows={overview.perDisease} />
        </motion.section>
      ) : null}
    </motion.div>
  );
}

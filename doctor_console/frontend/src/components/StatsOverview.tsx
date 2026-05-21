import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Loader2 } from "lucide-react";
import { getStatsOverview } from "../api";
import type { StatsOverview as StatsOverviewT } from "../types";
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
    <div className="stats-overview">
      <section className="stats-overview__head panel">
        <div>
          <div className="eyebrow">Main system accuracy</div>
          <h2>{overview?.resultSet.label ?? "Loading…"}</h2>
          <p className="stats-overview__sub">
            {overview ? (
              <>
                Seven-agent LangGraph pipeline · {overview.resultSet.model ?? "—"} ·
                {" "}<code className="mono">{overview.resultSet.path}</code>
              </>
            ) : "Aggregating per-agent outputs from the 160-patient cohort."}
          </p>
        </div>
      </section>

      {error ? (
        <div className="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      {loading ? (
        <div className="empty-state">
          <Loader2 size={16} className="spin" /> Computing aggregates…
        </div>
      ) : null}

      {aggregates ? (
        <motion.section
          className="kpi-grid"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
          }}
        >
          {kpis.map((kpi, idx) => (
            <KpiTile key={kpi.label} index={idx} {...kpi} />
          ))}
        </motion.section>
      ) : null}

      {overview ? (
        <PrecisionAtKCard
          cohortLabel={overview.resultSet.label}
          buckets={overview.rankDistribution}
          totalN={aggregates?.n ?? 0}
        />
      ) : null}

      {overview ? (
        <section className="stats-overview__grid">
          <RankHistogram buckets={overview.rankDistribution} />
          <PerDiseaseTable rows={overview.perDisease} />
        </section>
      ) : null}
    </div>
  );
}

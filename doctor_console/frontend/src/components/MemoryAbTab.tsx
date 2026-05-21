import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, ArrowDownRight, ArrowUpRight, Layers, Loader2, Minus } from "lucide-react";
import { getMemoryAbComparison } from "../api";
import type { CohortAggregates, MemoryAbComparison, PerDiseaseRow, RankBucket } from "../types";
import { KpiTile } from "./KpiTile";
import { PerDiseaseTable } from "./PerDiseaseTable";
import { RankHistogram } from "./RankHistogram";
import { Disclosure } from "./Disclosure";

type Props = {
  onOpenPatient?: (uuid: string) => void;
};

/**
 * Memory A/B comparison tab — full per-arm presentation matched to the
 * StatsOverview layout. Reads single-level first (the baseline), then the
 * principal multi-level + canonicalizer configuration, then surfaces a
 * coloured delta panel.
 */
export function MemoryAbTab({ onOpenPatient }: Props) {
  const [data, setData] = useState<MemoryAbComparison | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getMemoryAbComparison());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return (
      <div className="empty-state">
        <Loader2 size={16} className="spin" /> Loading the memory comparison…
      </div>
    );
  }
  if (error) {
    return <div className="alert"><AlertCircle size={16} /> {error}</div>;
  }
  if (!data || !data.nPaired) {
    return (
      <div className="panel">
        <p>
          The paired-160 memory comparison hasn't been computed yet. Run
          {" "}<code className="mono">python scripts/canon_rejudge_paired160.py</code>.
        </p>
      </div>
    );
  }

  const offAgg = data.offAggregates;
  const onAgg  = data.onAggregates;
  const ct = data.contingency as Record<string, number>;

  return (
    <div className="stats-overview memory-ab">
      <section className="stats-overview__head panel">
        <div>
          <div className="eyebrow">Memory A/B — paired controlled comparison</div>
          <h2>Single-level baseline vs. multi-level memory + canonicalizer</h2>
          <p className="stats-overview__sub">
            Same {data.nPaired} patients run twice. Each arm's stats first,
            then a side-by-side delta. Click any patient in the discordant
            list to open their per-agent narrative.
          </p>
        </div>
      </section>

      {/* 1. Single-level (baseline) — important info first */}
      <ArmSection
        eyebrow="Baseline · arm 1"
        label={data.armA.label}
        tone="neutral"
        agg={offAgg}
        rankDist={data.offRankDistribution}
        perDisease={data.offPerDisease}
      />

      {/* 2. Multi-level + canonicalizer — the principal configuration */}
      <ArmSection
        eyebrow="Principal configuration · arm 2"
        label={data.armB.label}
        tone="primary"
        agg={onAgg}
        rankDist={data.onRankDistribution}
        perDisease={data.onPerDisease}
      />

      {/* 3. The comparison: coloured deltas */}
      {offAgg && onAgg ? (
        <ComparisonPanel offAgg={offAgg} onAgg={onAgg}
          offLabel={data.armA.label} onLabel={data.armB.label} />
      ) : null}

      {/* 4. 2 × 2 contingency on DIRECT */}
      <section className="panel mcnemar-contingency">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">2 × 2 contingency — DIRECT match</div>
            <h3>Where the two arms agreed and disagreed at rank 1</h3>
            <p>
              On the {data.nPaired} paired patients, the off-diagonal cells are the
              cases where one arm produced a DIRECT match and the other did not.
            </p>
          </div>
        </div>
        <table className="mcnemar-contingency__table">
          <thead>
            <tr>
              <th></th>
              <th>{data.armB.label} = DIRECT</th>
              <th>{data.armB.label} ≠ DIRECT</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th>{data.armA.label} = DIRECT</th>
              <td className="mono"><strong>{ct.both_DIRECT ?? 0}</strong></td>
              <td className="mono"><strong>{ct.only_OFF_DIRECT ?? 0}</strong></td>
            </tr>
            <tr>
              <th>{data.armA.label} ≠ DIRECT</th>
              <td className="mono mcnemar-contingency__winner">
                <strong>{ct.only_ON_DIRECT ?? 0}</strong>
              </td>
              <td className="mono"><strong>{ct.neither_DIRECT ?? 0}</strong></td>
            </tr>
          </tbody>
        </table>
      </section>

      {/* 5. Discordant patients */}
      {data.discordant.length ? (
        <Disclosure
          title={
            <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
              <Layers size={14} strokeWidth={1.7} />
              <span>Discordant patients</span>
              <span className="simple-run__dive-tag mono">{data.discordant.length} CASES</span>
            </span>
          }
          hint="The patients where exactly one arm got DIRECT. Click a row to open the per-agent narrative."
        >
          <section className="panel" style={{ marginTop: 12 }}>
            <div className="discordant-list">
              {data.discordant.map((row) => (
                <button
                  type="button"
                  key={row.patientUuid}
                  className="discordant-list__row"
                  onClick={() => onOpenPatient?.(row.patientUuid)}
                >
                  <span className="mono discordant-list__uuid">{row.patientUuid.slice(0, 12)}…</span>
                  <span className="discordant-list__target">{row.target}</span>
                  <span className="discordant-list__verdict mono">
                    {row.offDirect ? "DIRECT" : "MISS"}
                    <span className="discordant-list__arrow">→</span>
                    {row.onDirect ? "DIRECT" : "MISS"}
                  </span>
                </button>
              ))}
            </div>
          </section>
        </Disclosure>
      ) : null}
    </div>
  );
}

function ArmSection({
  eyebrow, label, tone, agg, rankDist, perDisease,
}: {
  eyebrow: string;
  label: string;
  tone: "neutral" | "primary";
  agg?: CohortAggregates;
  rankDist?: RankBucket[];
  perDisease?: PerDiseaseRow[];
}) {
  const kpis = agg ? [
    { label: "DIRECT",     value: `${agg.directPct.toFixed(1)}%`,    tone: (tone === "primary" ? "success" : undefined) as "success" | undefined },
    { label: "Found",      value: `${agg.foundPct.toFixed(1)}%` },
    { label: "INDIRECT",   value: `${agg.indirectPct.toFixed(1)}%` },
    { label: "MISS",       value: `${agg.missPct.toFixed(1)}%`,      tone: (agg.missPct > 10 ? "critical" : undefined) as "critical" | undefined },
    { label: "Rank-1-of-found", value: `${agg.rank1PctOfFound.toFixed(1)}%` },
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
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
          }}
        >
          {kpis.map((kpi, idx) => (
            <KpiTile key={kpi.label} index={idx} {...kpi} />
          ))}
        </motion.section>
      ) : null}

      {rankDist && perDisease ? (
        <section className="stats-overview__grid">
          <RankHistogram buckets={rankDist} />
          <PerDiseaseTable rows={perDisease} />
        </section>
      ) : null}
    </section>
  );
}

function ComparisonPanel({
  offAgg, onAgg, offLabel, onLabel,
}: {
  offAgg: CohortAggregates;
  onAgg: CohortAggregates;
  offLabel: string;
  onLabel: string;
}) {
  const rows: Array<{ label: string; left: number; right: number; goodIfUp: boolean }> = [
    { label: "DIRECT",            left: offAgg.directPct,        right: onAgg.directPct,        goodIfUp: true  },
    { label: "Found (D + I)",     left: offAgg.foundPct,         right: onAgg.foundPct,         goodIfUp: true  },
    { label: "Rank-1 within found", left: offAgg.rank1PctOfFound, right: onAgg.rank1PctOfFound, goodIfUp: true  },
    { label: "INDIRECT",          left: offAgg.indirectPct,      right: onAgg.indirectPct,      goodIfUp: false },
    { label: "MISS",              left: offAgg.missPct,          right: onAgg.missPct,          goodIfUp: false },
  ];

  return (
    <section className="panel memory-ab__compare">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">Side-by-side delta</div>
          <h3>Comparison</h3>
          <p>
            Green = the principal configuration wins on this metric. Red = the
            baseline wins. The colour reflects clinical desirability, not just
            the sign of the delta (e.g. lower MISS is good).
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
        <tbody>
          {rows.map((row) => {
            const delta = row.right - row.left;
            const flat = Math.abs(delta) < 0.5;
            const candidateBetter = (delta > 0) === row.goodIfUp;
            const tone = flat ? "flat" : candidateBetter ? "good" : "bad";
            return (
              <tr key={row.label} className={`compare-row compare-row--${tone}`}>
                <td>{row.label}</td>
                <td className="num mono">{row.left.toFixed(1)}%</td>
                <td className="num mono">{row.right.toFixed(1)}%</td>
                <td className={`num mono delta delta--${tone}`}>
                  {flat ? <Minus size={13} />
                    : delta > 0 ? <ArrowUpRight size={13} />
                    : <ArrowDownRight size={13} />}
                  {Math.abs(delta).toFixed(1)} pp
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

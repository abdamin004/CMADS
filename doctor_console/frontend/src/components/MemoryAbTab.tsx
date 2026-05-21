import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { getMemoryAbComparison } from "../api";
import type { MemoryAbComparison } from "../types";
import { ArmSection, ComparisonPanel } from "./ComparisonShared";

type Props = {
  /** Kept for API compatibility with the other comparison tabs; unused now
   *  that the discordant-patient list has been removed. */
  onOpenPatient?: (uuid: string) => void;
};

/**
 * Memory A/B comparison tab — full per-arm presentation matched to the
 * StatsOverview layout and the other comparison tabs (Model · MAS-vs-Single).
 * Reads single-level first (baseline), then the principal multi-level
 * configuration, then a coloured delta panel, then the 2×2 contingency.
 */
export function MemoryAbTab(_props: Props) {
  void _props;
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
          <h2>Single-level baseline vs. multi-level memory</h2>
          <p className="stats-overview__sub">
            Same {data.nPaired} patients run twice. Each arm's stats first,
            then a side-by-side delta.
          </p>
        </div>
      </section>

      {/* 1. Single-level baseline */}
      <ArmSection
        eyebrow="Baseline · arm 1"
        label={data.armA.label}
        tone="neutral"
        agg={offAgg}
        rankDist={data.offRankDistribution}
        perDisease={data.offPerDisease}
      />

      {/* 2. Principal configuration */}
      <ArmSection
        eyebrow="Principal configuration · arm 2"
        label={data.armB.label}
        tone="primary"
        agg={onAgg}
        rankDist={data.onRankDistribution}
        perDisease={data.onPerDisease}
      />

      {/* 3. Side-by-side coloured delta */}
      {offAgg && onAgg ? (
        <ComparisonPanel
          offAgg={offAgg}
          onAgg={onAgg}
          offLabel={data.armA.label}
          onLabel={data.armB.label}
        />
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
    </div>
  );
}

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Target } from "lucide-react";
import type { RankBucket } from "../types";
import { easeOut } from "../lib/motion";

type Props = {
  cohortLabel: string;
  buckets: RankBucket[];
  totalN: number;
};

const K_CHOICES = [1, 2, 3, 5] as const;
type KValue = typeof K_CHOICES[number];

/**
 * Wilson 95% confidence interval for a binomial proportion.
 * Stays well-calibrated near 0 and 1 where the Wald (normal-approximation)
 * interval falls apart. Returns percentages, not fractions.
 */
function wilson95(found: number, n: number): { lo: number; hi: number } {
  if (n <= 0) return { lo: 0, hi: 0 };
  const z = 1.96;
  const p = found / n;
  const denom = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / denom;
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom;
  return { lo: Math.max(0, (centre - half) * 100), hi: Math.min(100, (centre + half) * 100) };
}

/**
 * "Precision @ K" — how often the system landed the true diagnosis in the
 * top K suggestions. Derives entirely from the cohort's rank distribution
 * (rank buckets "1", "2", "3", "4-5", "miss"), so no extra request is
 * needed when the user changes K.
 *
 * For K=4 we can't distinguish from "4-5" with current bucketing, so the
 * picker is restricted to {1, 2, 3, 5}.
 */
export function PrecisionAtKCard({ cohortLabel, buckets, totalN }: Props) {
  const [k, setK] = useState<KValue>(5);

  const lookup = useMemo(() => {
    const out: Record<string, number> = {};
    buckets.forEach((b) => { out[b.label] = b.count; });
    return out;
  }, [buckets]);

  const countAtK = (kv: number) => {
    let sum = (lookup["1"] ?? 0);
    if (kv >= 2) sum += (lookup["2"] ?? 0);
    if (kv >= 3) sum += (lookup["3"] ?? 0);
    if (kv >= 5) sum += (lookup["4-5"] ?? 0);
    return sum;
  };

  const found = countAtK(k);
  const pct = totalN ? (100 * found) / totalN : 0;

  // Wilson 95% confidence interval for the proportion found / totalN.
  // More accurate than the normal-approximation Wald interval at small N or
  // when pct is near 0% / 100%. Stays simple — single hot rebuild per K.
  const wilson = wilson95(found, totalN);

  // Cumulative coverage for the stacked bar.
  const coverage = K_CHOICES.map((kv) => ({
    k: kv,
    found: countAtK(kv),
    pct: totalN ? (100 * countAtK(kv)) / totalN : 0,
  }));

  return (
    <section className="panel precision-card">
      <header className="panel-heading">
        <div>
          <div className="eyebrow">
            <Target size={11} strokeWidth={2} /> Precision @ K
          </div>
          <h3>How many suggestions does the doctor need to read?</h3>
          <p className="precision-card__hint">
            Share of <strong>{totalN}</strong> patients in the
            {" "}<em>{cohortLabel}</em> cohort whose confirmed diagnosis
            appeared in the system's top-K differential.
          </p>
        </div>
        <div className="precision-card__picker" role="radiogroup" aria-label="Top K">
          {K_CHOICES.map((kv) => (
            <button
              key={kv}
              type="button"
              role="radio"
              aria-checked={k === kv}
              className={`precision-card__chip${k === kv ? " is-active" : ""}`}
              onClick={() => setK(kv)}
            >
              <span className="mono precision-card__chip-label">Top</span>
              <span className="precision-card__chip-num">{kv}</span>
            </button>
          ))}
        </div>
      </header>

      <div className="precision-card__body">
        <motion.div
          key={k}
          className="precision-card__big"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, ease: easeOut }}
        >
          <div className="precision-card__big-eyebrow mono">
            Precision @ Top {k}
          </div>
          <div className="precision-card__big-value">{pct.toFixed(1)}%</div>
          <div className="precision-card__big-detail">
            <strong>{found}</strong> of <strong>{totalN}</strong> patients,
            the right diagnosis was in the top {k} suggestion{k === 1 ? "" : "s"}.
          </div>
          {totalN ? (
            <div className="precision-card__ci mono">
              n = {totalN} · Wilson 95% CI {wilson.lo.toFixed(1)}% – {wilson.hi.toFixed(1)}%
            </div>
          ) : null}
        </motion.div>

        <div className="precision-card__bar-wrap">
          <div className="precision-card__bar">
            {coverage.map((c, i) => {
              const prev = i === 0 ? 0 : coverage[i - 1].pct;
              const segment = c.pct - prev;
              return (
                <div
                  key={c.k}
                  className={`precision-card__bar-seg precision-card__bar-seg--k${c.k}${k === c.k ? " is-selected" : ""}`}
                  style={{ width: `${segment}%` }}
                  title={`Top ${c.k}: ${c.pct.toFixed(1)}% (+${segment.toFixed(1)} pp)`}
                />
              );
            })}
            <div
              className="precision-card__bar-miss"
              style={{ width: `${Math.max(0, 100 - (coverage[coverage.length - 1]?.pct ?? 0))}%` }}
              title="Miss"
            />
          </div>
          <div className="precision-card__bar-legend">
            {coverage.map((c) => (
              <button
                key={c.k}
                type="button"
                className={`precision-card__legend-item precision-card__legend-item--k${c.k}${k === c.k ? " is-selected" : ""}`}
                onClick={() => setK(c.k as KValue)}
                aria-pressed={k === c.k}
                aria-label={`Set Top K to ${c.k}; currently ${c.pct.toFixed(1)} percent of patients found`}
              >
                <span className="precision-card__legend-dot" aria-hidden />
                <span className="precision-card__legend-label">
                  Top {c.k} · <strong>{c.pct.toFixed(1)}%</strong>
                </span>
              </button>
            ))}
            <div
              className="precision-card__legend-item precision-card__legend-item--miss precision-card__legend-item--static"
              aria-hidden={false}
            >
              <span className="precision-card__legend-dot" aria-hidden />
              <span className="precision-card__legend-label">
                Miss · <strong>{(100 - (coverage[coverage.length - 1]?.pct ?? 0)).toFixed(1)}%</strong>
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

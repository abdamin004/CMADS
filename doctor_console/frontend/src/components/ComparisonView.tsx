import type { ComparisonResult } from "../types";
import { ArmSection, ComparisonPanel } from "./ComparisonShared";

type Props = {
  data: ComparisonResult;
  /** Plain-language headline shown above the side-by-side. */
  headline?: string;
  /** Researcher-grade detail line (n, methodology hint). */
  methodology?: string;
  /** Kept for API compatibility; the discordant-patient list has been
   *  removed for visual consistency with the Overview / Memory A/B tabs. */
  onOpenPatient?: (uuid: string) => void;
};

/**
 * Generic two-arm comparison view. Shares the same per-arm layout used by
 * StatsOverview and MemoryAbTab: baseline arm first, candidate arm second,
 * coloured delta panel last. Used by the Model and MAS-vs-Single-LLM tabs.
 */
export function ComparisonView({ data, headline, methodology }: Props) {
  const b = data.baseline;
  const c = data.candidate;

  return (
    <div className="stats-overview comparison-view">
      {headline ? (
        <section className="stats-overview__head panel">
          <div>
            <div className="eyebrow">Paired controlled comparison</div>
            <h2>{headline}</h2>
            {methodology ? <p className="stats-overview__sub">{methodology}</p> : null}
            <div className="comparison-view__meta mono">
              {data.restrictedToIntersection
                ? `Paired on n = ${data.pairedN} shared patients`
                : `Full cohorts (baseline n = ${b.aggregates.n}, candidate n = ${c.aggregates.n})`}
            </div>
          </div>
        </section>
      ) : null}

      <ArmSection
        eyebrow="Baseline · arm 1"
        label={b.label}
        tone="neutral"
        agg={b.aggregates}
        perDisease={b.perDisease}
      />

      <ArmSection
        eyebrow="Principal configuration · arm 2"
        label={c.label}
        tone="primary"
        agg={c.aggregates}
        perDisease={c.perDisease}
      />

      <ComparisonPanel
        offAgg={b.aggregates}
        onAgg={c.aggregates}
        offLabel={b.label}
        onLabel={c.label}
      />
    </div>
  );
}

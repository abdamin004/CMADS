import type { ReactNode } from "react";

type Variant = "default" | "result" | "memory" | "kpi";
type Tone = "default" | "success" | "warning" | "critical" | "accent";

type Props = {
  /** Eyebrow / metric label — mono uppercase. */
  label: ReactNode;
  /** Primary value — Fraunces serif numeral / phrase. */
  value: ReactNode;
  /** Optional single-line subtitle below the value. */
  hint?: ReactNode;
  /** Optional leading icon (lucide). Auto-tinted by variant. */
  icon?: ReactNode;
  /** Visual variant. Maps onto existing CSS:
   *   default  → editorial neutral tile
   *   result   → ResultsPanel pattern
   *   memory   → MemoryTimeline pattern
   *   kpi      → StatsOverview oversized KPI tile (defers to <KpiTile/>)
   */
  variant?: Variant;
  /** Color tone reinforcement for the value text. */
  tone?: Tone;
  /** Stable DOM attribute for E2E targeting. */
  demoAnchor?: string;
};

/**
 * Editorial metric tile — the shared underlying shape behind ResultsPanel's
 * `.result-card`, MemoryTimeline's `.memory-tile`, and a few one-off
 * label/value cards. Pre-Phase-2 these patterns were reinvented in three
 * places with overlapping CSS; this component lets new tiles consume the
 * existing CSS without copy-pasting the markup.
 *
 * KpiTile keeps its own (richer) implementation because it adds the
 * leading rule + index decoration + hover lift. Pass `variant="kpi"` here
 * only when you want the basic compositional shape without those details;
 * for canonical KPI tiles, keep using <KpiTile/>.
 */
export function MetricTile({
  label,
  value,
  hint,
  icon,
  variant = "default",
  tone = "default",
  demoAnchor,
}: Props) {
  const cls = variant === "memory" ? "memory-tile"
            : variant === "result" ? "result-card"
            : variant === "kpi"    ? "kpi-tile"
            :                        "result-card";
  const toneCls = tone === "default" ? "" : ` metric-tile--${tone}`;
  return (
    <div className={`${cls}${toneCls}`} data-demo-anchor={demoAnchor}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <p className="metric-tile__hint">{hint}</p> : null}
    </div>
  );
}

import { motion } from "framer-motion";
import { TrendingDown, TrendingUp } from "lucide-react";
import { easeOut } from "../lib/motion";

type Delta = {
  /** Numeric value of the comparison delta (e.g. +5.2 for +5.2pp). */
  value: number;
  /** Suffix appended to the magnitude (e.g. "pp" for percentage points). */
  unit?: string;
  /** What the delta is relative to ("vs single-LLM baseline", "vs Med42"). */
  vs: string;
};

type Props = {
  index?: number;
  label: string;
  value: string;
  hint?: string;
  /** Optional secondary metric line — e.g. "n = 160", "p95: 42s". */
  secondary?: string;
  /** Optional delta vs a comparison baseline. Drives the colored trend chip. */
  delta?: Delta;
  tone?: "default" | "success" | "warning" | "critical" | "accent";
};

/**
 * Editorial-style KPI tile. Oversized Fraunces numeral, mono uppercase label,
 * a single-line plain-language hint underneath. Lifts on hover, no shadow
 * trickery — typography carries the weight.
 */
export function KpiTile({
  index = 0, label, value, hint, secondary, delta, tone = "default",
}: Props) {
  const deltaSign = delta ? (delta.value > 0 ? "up" : delta.value < 0 ? "down" : "flat") : null;
  const deltaMag = delta ? `${delta.value > 0 ? "+" : ""}${delta.value.toFixed(1)}${delta.unit ?? ""}` : null;

  return (
    <motion.article
      className={`kpi-tile kpi-tile--${tone}`}
      variants={{
        hidden: { opacity: 0, y: 12 },
        visible: {
          opacity: 1, y: 0,
          transition: { duration: 0.45, ease: easeOut },
        },
      }}
      whileHover={{ y: -2 }}
    >
      <div className="kpi-tile__rule" aria-hidden />
      <div className="kpi-tile__label mono">{label}</div>
      <div className="kpi-tile__value">{value}</div>
      {secondary ? (
        <div className="kpi-tile__secondary mono">{secondary}</div>
      ) : null}
      {delta && deltaSign && deltaMag ? (
        <div
          className={`kpi-tile__delta kpi-tile__delta--${deltaSign}`}
          title={`${deltaMag} ${delta.vs}`}
        >
          {deltaSign === "up" ? <TrendingUp size={11} strokeWidth={2} aria-hidden />
            : deltaSign === "down" ? <TrendingDown size={11} strokeWidth={2} aria-hidden />
            : null}
          <span className="mono">{deltaMag}</span>
          <span className="kpi-tile__delta-vs">{delta.vs}</span>
        </div>
      ) : null}
      {hint ? <p className="kpi-tile__hint">{hint}</p> : null}
      <div className="kpi-tile__index mono" aria-hidden>{String(index + 1).padStart(2, "0")}</div>
    </motion.article>
  );
}

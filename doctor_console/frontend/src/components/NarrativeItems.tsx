import { type ReactNode, useState } from "react";
import { ChevronRight, AlertTriangle, Activity, Pill, ListChecks } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

/**
 * Smart renderer for AgentNarrative section items.
 *
 * The backend (doctor_console.backend.app._build_narrative_for) emits
 * each item as a single string. Most sections use a structured pipe
 * format the agents fall into naturally:
 *
 *   "Stage 2 hypertension | high | active"
 *   "Total cholesterol | 169.4 mg/dL | normal"
 *   "#1 | Essential hypertension | 48% | high | reasoning..."
 *   "Section name | inconsistent | rationale..."
 *
 * Plain prose paragraphs come through as a single item with no pipes.
 *
 * This component detects the pattern and renders rich rows (rank chips,
 * tone-tinted status pills, probability bars, medication doses) instead
 * of plain bullets. Falls back gracefully to <p>/<li> for unstructured
 * items.
 */

type Props = {
  items: string[];
  sectionTitle?: string;
};

export function NarrativeItems({ items, sectionTitle }: Props) {
  if (!items.length) return null;

  // Detect overall pattern. If at least one item has pipes, treat the
  // section as structured; otherwise render as readable prose.
  const structured = items.some((i) => i.includes("|"));

  if (!structured) {
    return (
      <div className="narrative-prose">
        {items.map((item, i) => (
          <p key={i}>{item}</p>
        ))}
      </div>
    );
  }

  return (
    <div className="narrative-rows">
      {items.map((item, i) => (
        <NarrativeRow key={i} raw={item} sectionTitle={sectionTitle} />
      ))}
    </div>
  );
}

function NarrativeRow({
  raw,
  sectionTitle,
}: {
  raw: string;
  sectionTitle?: string;
}) {
  const parts = raw.split("|").map((p) => p.trim()).filter(Boolean);

  // No pipes → render as a single readable line in the structured row
  // grid so it visually aligns with siblings.
  if (parts.length <= 1) {
    return <div className="narrative-row narrative-row--prose">{raw}</div>;
  }

  const variant = detectVariant(parts, sectionTitle);

  switch (variant) {
    case "ranked-differential":
      return <RankedDifferentialRow parts={parts} />;
    case "labs":
      return <LabRow parts={parts} />;
    case "problem":
      return <ProblemRow parts={parts} />;
    case "medication":
      return <MedicationRow parts={parts} />;
    case "check":
      return <CheckRow parts={parts} />;
    case "verification":
      return <VerificationRow parts={parts} />;
    case "kv":
      return <KvRow parts={parts} />;
    default:
      return <GenericRow parts={parts} />;
  }
}

type Variant =
  | "ranked-differential"
  | "labs"
  | "problem"
  | "medication"
  | "check"
  | "verification"
  | "kv"
  | "generic";

function detectVariant(parts: string[], sectionTitle = ""): Variant {
  const title = sectionTitle.toLowerCase();

  // Ranked differential: starts with "#1", "#2", etc. and has 4-5 cols
  if (/^#\d+$/.test(parts[0])) return "ranked-differential";

  if (title.includes("ranked") || title.includes("differential")) {
    return "ranked-differential";
  }

  // Lab row: middle column looks like a numeric value with units
  if (parts.length === 3 && /[\d.]+\s*(mg\/dL|mmHg|%|mEq|mmol|ng|pg|IU|U\/L|g\/dL|mL\/min)/i.test(parts[1])) {
    return "labs";
  }
  if (title.includes("findings") || title.includes("labs") || title.includes("vital")) {
    return "labs";
  }

  // Medication row: 3 cols + dose-looking middle column
  if (title.includes("medication") || title.includes("medic")) {
    return "medication";
  }
  if (parts.length === 3 && /\d.*\b(mg|mcg|g|mL|tablet|capsule|inhaler)\b/i.test(parts[1])) {
    return "medication";
  }

  // Consistency / coverage checks: status word in middle
  if (title.includes("consistency") || title.includes("check")) return "check";
  if (parts.length === 3 && /inconsistent|consistent|partial|complete/i.test(parts[1])) {
    return "check";
  }

  // Verification notes: plausibility + strength
  if (title.includes("verification")) return "verification";
  if (parts.length === 3 && /plausible|questionable|implausible/i.test(parts[1])) {
    return "verification";
  }

  // Problem row: 3 cols with status + severity
  if (title.includes("problem") || title.includes("condition") || title.includes("flag")) {
    return "problem";
  }
  if (parts.length === 3 && /\b(active|resolved|chronic|new|high|moderate|low|critical)\b/i.test(parts[1] + " " + parts[2])) {
    return "problem";
  }

  // Key-value: 2 cols (Target | X; Matched diagnosis | Y)
  if (parts.length === 2) return "kv";

  return "generic";
}

// ─── row variants ────────────────────────────────────────────────────

function RankedDifferentialRow({ parts }: { parts: string[] }) {
  // Either "#N | name | prob% | confidence | reasoning"
  // or just "name | prob% | confidence | reasoning"
  let rank = 0;
  let rest = parts;
  if (/^#\d+$/.test(parts[0])) {
    rank = Number(parts[0].slice(1));
    rest = parts.slice(1);
  }
  const [name, probStr, confidence, ...reasoningParts] = rest;
  const reasoning = reasoningParts.join(" | ");
  const probMatch = probStr?.match(/([\d.]+)\s*%/);
  const probPct = probMatch ? Number(probMatch[1]) : 0;

  const [open, setOpen] = useState(false);
  const hasReasoning = !!reasoning;

  return (
    <div
      className={`nrow nrow--dx ${open ? "nrow--open" : ""}`}
      data-rank={rank || undefined}
    >
      <button
        type="button"
        className="nrow__head"
        onClick={() => hasReasoning && setOpen((v) => !v)}
        aria-expanded={open}
        aria-disabled={!hasReasoning}
      >
        {rank ? (
          <span className={`nrow__rank nrow__rank--${rank <= 3 ? rank : "other"}`}>
            {String(rank).padStart(2, "0")}
          </span>
        ) : null}
        <span className="nrow__main">
          <span className="nrow__name">{name}</span>
        </span>
        {probPct > 0 ? (
          <span className="nrow__prob">
            <span className="nrow__prob-bar" aria-hidden>
              <span
                className="nrow__prob-fill"
                style={{ width: `${Math.min(100, Math.max(3, probPct))}%` }}
              />
            </span>
            <span className="nrow__prob-num">{probPct}%</span>
          </span>
        ) : null}
        {confidence ? <Pill_ className={toneClass(confidence)} label={confidence} /> : null}
        {hasReasoning ? (
          <span className="nrow__chevron" aria-hidden>
            <ChevronRight size={14} style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 200ms ease" }} />
          </span>
        ) : null}
      </button>
      <AnimatePresence initial={false}>
        {open && hasReasoning ? (
          <motion.div
            className="nrow__detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 0.65, 0.3, 0.96] }}
          >
            <p>{reasoning}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function LabRow({ parts }: { parts: string[] }) {
  const [name, value, flag = ""] = parts;
  return (
    <div className="nrow nrow--lab">
      <span className="nrow__icon"><Activity size={14} /></span>
      <span className="nrow__main">
        <span className="nrow__name">{name}</span>
      </span>
      <span className="nrow__value mono">{value}</span>
      {flag ? <Pill_ className={toneClass(flag)} label={flag} /> : null}
    </div>
  );
}

function MedicationRow({ parts }: { parts: string[] }) {
  const [name, dose = "", purpose = ""] = parts;
  return (
    <div className="nrow nrow--med">
      <span className="nrow__icon"><Pill size={14} /></span>
      <span className="nrow__main">
        <span className="nrow__name">{name}</span>
        {purpose ? <span className="nrow__sub">{purpose}</span> : null}
      </span>
      {dose ? <span className="nrow__value mono">{dose}</span> : null}
    </div>
  );
}

function ProblemRow({ parts }: { parts: string[] }) {
  const [name, severity = "", status = ""] = parts;
  return (
    <div className="nrow nrow--problem">
      <span className="nrow__icon"><ListChecks size={14} /></span>
      <span className="nrow__main">
        <span className="nrow__name">{name}</span>
      </span>
      {severity ? <Pill_ className={toneClass(severity)} label={severity} /> : null}
      {status ? <Pill_ className={toneClass(status)} label={status} /> : null}
    </div>
  );
}

function CheckRow({ parts }: { parts: string[] }) {
  const [name, status = "", rationale = ""] = parts;
  const [open, setOpen] = useState(false);
  const isInconsistent = /inconsistent|partial/i.test(status);
  return (
    <div className={`nrow nrow--check ${open ? "nrow--open" : ""}`}>
      <button
        type="button"
        className="nrow__head"
        onClick={() => rationale && setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="nrow__icon">
          {isInconsistent ? <AlertTriangle size={14} /> : <ListChecks size={14} />}
        </span>
        <span className="nrow__main">
          <span className="nrow__name">{name}</span>
        </span>
        <Pill_ className={toneClass(status)} label={status} />
        {rationale ? (
          <span className="nrow__chevron" aria-hidden>
            <ChevronRight size={14} style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 200ms ease" }} />
          </span>
        ) : null}
      </button>
      <AnimatePresence initial={false}>
        {open && rationale ? (
          <motion.div
            className="nrow__detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <p>{rationale}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function VerificationRow({ parts }: { parts: string[] }) {
  const [name, plausibility = "", strength = ""] = parts;
  return (
    <div className="nrow nrow--verify">
      <span className="nrow__main">
        <span className="nrow__name">{name}</span>
      </span>
      {plausibility ? <Pill_ className={toneClass(plausibility)} label={plausibility} /> : null}
      {strength ? <Pill_ className={`pill--strength ${toneClass(strength)}`} label={`evidence: ${strength}`} /> : null}
    </div>
  );
}

function KvRow({ parts }: { parts: string[] }) {
  const [key, value] = parts;
  return (
    <div className="nrow nrow--kv">
      <span className="nrow__key">{key}</span>
      <span className="nrow__value">{value}</span>
    </div>
  );
}

function GenericRow({ parts }: { parts: string[] }) {
  return (
    <div className="nrow nrow--generic">
      {parts.map((p, i) => (
        <span key={i} className={i === 0 ? "nrow__name" : "nrow__field"}>
          {p}
        </span>
      ))}
    </div>
  );
}

function Pill_({ label, className }: { label: string; className: string }) {
  return <span className={`pill ${className}`}>{label}</span>;
}

function toneClass(text: string): string {
  const t = text.toLowerCase();
  if (/(high|critical|inconsistent|abnormal|implausible|severe)/.test(t)) return "tone-bad";
  if (/(moderate|partial|questionable|borderline|elevated|low)/.test(t)) return "tone-warn";
  if (/(normal|consistent|plausible|stable|resolved|strong)/.test(t)) return "tone-good";
  if (/(active|chronic|new|ongoing)/.test(t)) return "tone-info";
  return "tone-neutral";
}

// Re-export for downstream consumers that want the ReactNode type.
export type { ReactNode };

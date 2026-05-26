import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle, ArrowRight, Check, Clock, Search, X,
} from "lucide-react";
import { getRuntimePastRuns } from "../api";
import { parseBackendDate, relativeBackend } from "../lib/datetime";
import { confClass, demoLine, initials, shortId } from "../lib/clinical";
import type {
  ModelPreset, RuntimePastRun, RuntimePastRunsResponse,
} from "../types";

/* ────────────────────────────────────────────────────────────────────────
   Past Patients dashboard.
   The clinician's landing surface for the runtime ribbon's "Past runs"
   link. Lists every patient they have already read through the
   multi-agent system as a clickable card; clicking a card opens the
   per-patient detail page (see RuntimePatientDetail).
   ──────────────────────────────────────────────────────────────────── */

interface Props {
  onOpenPatient: (uuid: string) => void;
  onRun:         (uuid: string, preset: ModelPreset, topK: number) => void;
  onBack:        () => void;
  defaultPreset?: ModelPreset;
  defaultTopK?:   number;
}

type FilterKey = "all" | "recent" | "flagged" | "disagreement";

const FILTER_LABELS: Record<FilterKey, string> = {
  all:          "All",
  recent:       "Last 4 days",
  flagged:      "Flagged",
  disagreement: "You disagreed",
};

export function RuntimePastRuns({
  onOpenPatient, onRun, onBack, defaultPreset, defaultTopK = 3,
}: Props) {
  void onBack; void onRun; void defaultPreset; void defaultTopK;
  const [data,   setData]   = useState<RuntimePastRunsResponse | null>(null);
  const [error,  setError]  = useState<string | null>(null);
  const [query,  setQuery]  = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [sort,   setSort]   = useState<"recent" | "runs" | "confidence">("recent");

  useEffect(() => {
    let cancelled = false;
    getRuntimePastRuns(80)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);

  const patients = data?.runs ?? [];

  /* ── Live filter + sort over the loaded list ──────────────────────── */
  const q = query.trim().toLowerCase();
  const filtered: RuntimePastRun[] = useMemo(() => {
    const rows = patients.filter((p) => {
      if (filter === "flagged"      && !p.flagged)                  return false;
      if (filter === "disagreement" && p.agreement !== "disagree")  return false;
      if (filter === "recent") {
        const d = parseBackendDate(p.ran_at);
        if (!d) return false;
        const days = (Date.now() - d.getTime()) / 86400000;
        if (days > 4) return false;
      }
      if (!q) return true;
      const hay = [
        p.patient_uuid,
        p.top_dx ?? "",
        p.ground_truth_disease ?? "",
        p.race ?? "",
        p.gender ?? "",
        String(p.age ?? ""),
      ].join(" ").toLowerCase();
      return hay.includes(q);
    });
    const cmp: Record<typeof sort, (a: RuntimePastRun, b: RuntimePastRun) => number> = {
      recent: (a, b) =>
        (parseBackendDate(b.ran_at)?.getTime() ?? 0) -
        (parseBackendDate(a.ran_at)?.getTime() ?? 0),
      runs:        (a, b) => (b.run_count   ?? 0) - (a.run_count   ?? 0),
      confidence:  (a, b) => (b.confidence  ?? 0) - (a.confidence  ?? 0),
    };
    return [...rows].sort(cmp[sort]);
  }, [patients, filter, q, sort]);

  /* ── Live counts for filter pills + stat strip ────────────────────── */
  const counts = useMemo(() => ({
    all:          patients.length,
    recent:       patients.filter((p) => {
      const d = parseBackendDate(p.ran_at);
      if (!d) return false;
      return (Date.now() - d.getTime()) / 86400000 <= 4;
    }).length,
    flagged:      patients.filter((p) => p.flagged).length,
    disagreement: patients.filter((p) => p.agreement === "disagree").length,
  }), [patients]);

  const stats = useMemo(() => ({
    patients:  patients.length,
    totalRuns: patients.reduce((a, p) => a + (p.run_count ?? 1), 0),
    agreed:    patients.filter((p) => p.agreement === "agree").length,
    flagged:   patients.filter((p) => p.flagged).length,
  }), [patients]);

  return (
    <motion.div
      className="pp-shell"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
    >
      {/* Page head ─────────────────────────────────────────────────── */}
      <header className="pp-head">
        <div className="pp-head__col">
          <p className="pp-eyebrow mono">Doctor console · review</p>
          <h1 className="pp-title">
            Your <em>past patients</em>
          </h1>
          <p className="pp-sub">
            Patients you have read through the multi-agent system. Click any
            row to see every prior run on that chart, inspect a specific read,
            or kick off a new one against the current model.
          </p>
        </div>
        <div className="pp-strip" aria-label="Cohort summary">
          <StripCell label="Patients"    value={stats.patients} />
          <StripCell label="Total runs"  value={stats.totalRuns} />
          <StripCell label="You agreed"  value={stats.agreed}  tone="success" />
          <StripCell label="Flagged"     value={stats.flagged} tone="warning" />
        </div>
      </header>

      {/* Toolbar ───────────────────────────────────────────────────── */}
      <div className="pp-toolbar">
        <div className="pp-search">
          <Search size={14} strokeWidth={1.8} className="pp-search__icon" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by patient ID, diagnosis, age…"
            className="pp-search__input"
          />
        </div>
        <div className="pp-pills" role="tablist">
          {(["all","recent","flagged","disagreement"] as FilterKey[]).map((id) => {
            const active = filter === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(id)}
                className={`pp-pill${active ? " is-active" : ""}`}
              >
                {FILTER_LABELS[id]}
                <span className="pp-pill__count mono">{counts[id]}</span>
              </button>
            );
          })}
        </div>
        <label className="pp-sort">
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
            className="pp-sort__select"
          >
            <option value="recent">Most recent</option>
            <option value="runs">Most runs</option>
            <option value="confidence">Highest confidence</option>
          </select>
        </label>
      </div>

      {/* Patient list ──────────────────────────────────────────────── */}
      {error && <div className="pp-error" role="alert">{error}</div>}

      {!data ? (
        <div className="pp-empty">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="pp-empty">
          No patients match that filter. Try clearing the search or switching
          back to <strong>All</strong>.
        </div>
      ) : (
        <ul className="pp-list">
          {filtered.map((p) => (
            <li key={p.patient_uuid}>
              <PatientCard p={p} onClick={() => onOpenPatient(p.patient_uuid)} />
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  );
}

/* ─── Sub-components ─────────────────────────────────────────────── */

function StripCell({ label, value, tone }: {
  label: string;
  value: number | string;
  tone?: "success" | "warning";
}) {
  return (
    <div className="pp-strip__cell">
      <div className={`pp-strip__value${tone ? ` is-${tone}` : ""}`}>{value}</div>
      <div className="pp-strip__label mono">{label}</div>
    </div>
  );
}

function PatientCard({ p, onClick }: { p: RuntimePastRun; onClick: () => void }) {
  const conf = p.confidence != null ? Math.round(p.confidence) : null;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`pp-card${p.flagged ? " is-flagged" : ""}`}
    >
      <div className="pp-card__avatar">
        {initials(p.patient_uuid)}
        {p.flagged && (
          <span className="pp-card__avatar-flag" title="Flagged for follow-up">
            <AlertTriangle size={8} strokeWidth={2.2} />
          </span>
        )}
      </div>

      <div className="pp-card__id">
        <div className="pp-card__demo">
          <span>{demoLine(p)}</span>
          <span className="pp-card__uuid mono">{shortId(p.patient_uuid)}…</span>
        </div>
        <div className="pp-card__meta mono">
          <span>
            {(p.conditions_count ?? 0)} condition{(p.conditions_count ?? 0) === 1 ? "" : "s"}
          </span>
          {p.cutoff_date && (
            <>
              <span className="pp-card__meta-dot" />
              <span>cutoff {p.cutoff_date}</span>
            </>
          )}
        </div>
      </div>

      <div className="pp-card__dx">
        <span className="pp-card__dx-label mono">Last read · top diagnosis</span>
        {p.top_dx ? (
          <span className="pp-card__dx-name">
            {p.top_dx}
            {conf != null && (
              <span className={`pp-card__dx-conf mono ${confClass(conf)}`}>
                {conf}%
              </span>
            )}
          </span>
        ) : (
          <span className="pp-card__dx-name pp-card__dx-name--empty">
            No diagnosis recorded on the last read.
          </span>
        )}
      </div>

      <div className="pp-card__right">
        <AgreementBadge agreement={p.agreement ?? null} />
        <div className="pp-card__when">
          <Clock size={11} strokeWidth={1.8} />
          <span>Read {relativeBackend(p.ran_at)}</span>
        </div>
        <div className="pp-card__runs">
          <strong>{p.run_count ?? 1}</strong>{" "}
          {(p.run_count ?? 1) === 1 ? "run" : "runs"} on chart
        </div>
        <span className="pp-card__open">
          Open <ArrowRight size={11} strokeWidth={2} />
        </span>
      </div>
    </button>
  );
}

function AgreementBadge({ agreement }: { agreement: RuntimePastRun["agreement"] | null }) {
  if (!agreement) return null;
  const { label, Icon: Glyph, tone } = {
    agree:     { label: "Agreed",    Icon: Check,           tone: "success"  },
    disagree:  { label: "Disagreed", Icon: X,               tone: "critical" },
    uncertain: { label: "Uncertain", Icon: AlertTriangle,   tone: "warning"  },
  }[agreement];
  return (
    <span className={`pp-agree pp-agree--${tone}`}>
      <Glyph size={9} strokeWidth={2.5} />
      {label}
    </span>
  );
}

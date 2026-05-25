import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, ChevronDown, Eye, FileText, Play, Search } from "lucide-react";
import { getRuntimePastRuns } from "../api";
import { PatientPreviewDrawer } from "./PatientPreviewDrawer";
import type {
  ModelPreset, RuntimePastRun, RuntimePastRunsResponse,
  RuntimePatientSuggestion,
} from "../types";

interface Props {
  /** Opens the saved result of a previous runtime run in place (no new
   *  pipeline call). The parent loads via getResult and switches phase. */
  onView:   (patientUuid: string) => void;
  /** Fires a new pipeline run against the given UUID with the parent's
   *  current default preset. The parent owns model-preset selection so
   *  this view stays clutter-free. */
  onRun:    (patientUuid: string, preset: ModelPreset, topK: number) => void;
  /** Back to the hero (clean slate). */
  onBack:   () => void;
  /** Default preset to use when the user clicks Run on a suggestion or
   *  re-runs a past row.  Passed in so the bottom-sheet model picker the
   *  hero offers stays the single source of truth for preset choice. */
  defaultPreset?: ModelPreset;
  defaultTopK?:   number;
}

function relative(iso?: string | null): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60)        return `${Math.round(s)}s ago`;
  if (s < 3600)      return `${Math.round(s / 60)}m ago`;
  if (s < 86400)     return `${Math.round(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)}d ago`;
  return `${Math.round(s / (86400 * 7))}w ago`;
}

function demoLine(p: { age: number | null; gender: string | null; race: string | null }): string {
  const parts: string[] = [];
  if (p.age != null) parts.push(`${p.age}${p.gender ?? ""}`);
  else if (p.gender) parts.push(p.gender);
  if (p.race)        parts.push(p.race);
  return parts.join(" · ") || "demographics not on file";
}

export function RuntimePastRuns({ onView, onRun, onBack, defaultPreset, defaultTopK = 3 }: Props) {
  const [data, setData]     = useState<RuntimePastRunsResponse | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [busy, setBusy]     = useState<string | null>(null);
  const [query, setQuery]   = useState("");
  // Per-row "show known diagnosis" toggles — known dx stays hidden by
  // default so the row stays clinically uncluttered; the doctor opts in.
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  function toggleRevealed(uuid: string) {
    setRevealed((m) => ({ ...m, [uuid]: !m[uuid] }));
  }
  // Patient-preview drawer state — null means closed; a uuid opens it.
  const [previewUuid, setPreviewUuid] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRuntimePastRuns(80)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);

  const q = query.trim().toLowerCase();
  const runs = useMemo<RuntimePastRun[]>(() => {
    if (!data) return [];
    if (!q)    return data.runs;
    return data.runs.filter((r) =>
      r.patient_uuid.toLowerCase().includes(q)
      || (r.top_dx ?? "").toLowerCase().includes(q)
      || (r.ground_truth_disease ?? "").toLowerCase().includes(q));
  }, [data, q]);
  const suggestions = useMemo<RuntimePatientSuggestion[]>(() => {
    if (!data) return [];
    if (!q)    return data.suggestions;
    return data.suggestions.filter((p) =>
      p.patient_uuid.toLowerCase().includes(q)
      || (p.ground_truth_disease ?? "").toLowerCase().includes(q));
  }, [data, q]);

  function fireRun(uuid: string) {
    if (!defaultPreset) {
      setError("Pick a model preset on the hero first, then come back to Run.");
      return;
    }
    setBusy(uuid);
    onRun(uuid, defaultPreset, defaultTopK);
  }

  return (
    <motion.div
      className="rt-past"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
    >
      <header className="rt-past__header">
        <div>
          <button type="button" onClick={onBack} className="rt-past__back">
            <ArrowLeft size={13} strokeWidth={1.8} />
            Back to hero
          </button>
          <h2 className="rt-past__title">Your patients</h2>
          <p className="rt-past__sub">
            Patients you have reviewed before stay here so you can re-open a
            read or run the pipeline again. The list below the runs has new
            patients waiting for a first review.
          </p>
        </div>
        <div className="rt-past__search">
          <Search size={12} strokeWidth={1.8} className="rt-past__search-icon" />
          <input
            type="text"
            placeholder="Search patient or diagnosis…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="rt-past__search-input"
          />
        </div>
      </header>

      {error && (
        <div className="rt-past__error" role="alert">{error}</div>
      )}

      <section className="rt-past__section">
        <header className="rt-past__section-head">
          <div className="rt-past__eyebrow mono">Reviewed</div>
          <h3 className="rt-past__section-title">Patients you have read</h3>
        </header>
        {!data ? (
          <div className="rt-past__empty">Loading…</div>
        ) : runs.length === 0 ? (
          <div className="rt-past__empty">
            {q ? "No past reads match that search." :
              "You haven't reviewed any patients yet. Start one from the hero or pick a new patient below."}
          </div>
        ) : (
          <ul className="rt-past__list">
            {runs.map((r) => {
              const showKnown = !!revealed[r.patient_uuid];
              return (
              <li key={r.patient_uuid} className="rt-past__card">
                <div className="rt-past__card-main">
                  <div className="rt-past__patient">
                    <span className="rt-past__patient-name">{demoLine(r)}</span>
                    <span className="rt-past__patient-id mono" title={r.patient_uuid}>
                      {r.patient_uuid.slice(0, 8)}…
                    </span>
                  </div>
                  {r.top_dx ? (
                    <div className="rt-past__dx">
                      <span className="rt-past__dx-label">Top diagnosis</span>
                      <span className="rt-past__dx-name">{r.top_dx}</span>
                      {r.confidence != null && (
                        <span className="rt-past__dx-conf">
                          {Math.round(r.confidence)}%
                        </span>
                      )}
                    </div>
                  ) : (
                    <div className="rt-past__dx rt-past__dx--empty">
                      No diagnosis recorded on the last read.
                    </div>
                  )}
                  <div className="rt-past__footline">
                    <span>Read {relative(r.ran_at)}</span>
                    {r.duration_s != null && (
                      <span className="rt-past__footline-sep">·</span>
                    )}
                    {r.duration_s != null && (
                      <span>took {Math.round(r.duration_s)}s</span>
                    )}
                    {r.ground_truth_disease && (
                      <>
                        <span className="rt-past__footline-sep">·</span>
                        <button
                          type="button"
                          onClick={() => toggleRevealed(r.patient_uuid)}
                          className="rt-past__reveal"
                          aria-expanded={showKnown}
                        >
                          {showKnown ? "Hide known diagnosis" : "Show known diagnosis"}
                          <ChevronDown size={10} strokeWidth={2}
                                       className={showKnown ? "rt-past__reveal-chev is-open" : "rt-past__reveal-chev"} />
                        </button>
                      </>
                    )}
                  </div>
                  {showKnown && r.ground_truth_disease && (
                    <div className="rt-past__known">
                      <span className="rt-past__known-label">Known diagnosis</span>
                      <span className="rt-past__known-name">{r.ground_truth_disease}</span>
                    </div>
                  )}
                </div>
                <div className="rt-past__card-actions">
                  <button
                    type="button"
                    onClick={() => onView(r.patient_uuid)}
                    className="rt-past__btn rt-past__btn--primary"
                    title="Open the previous read"
                  >
                    <Eye size={12} strokeWidth={1.8} />
                    Open read
                  </button>
                  <button
                    type="button"
                    onClick={() => fireRun(r.patient_uuid)}
                    disabled={busy === r.patient_uuid}
                    className="rt-past__btn rt-past__btn--ghost"
                    title="Run the pipeline again on this patient"
                  >
                    <Play size={11} strokeWidth={1.8} />
                    Re-run
                  </button>
                </div>
              </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rt-past__section">
        <header className="rt-past__section-head">
          <div className="rt-past__eyebrow mono">New</div>
          <h3 className="rt-past__section-title">Patients waiting for a first read</h3>
        </header>
        {!data ? (
          <div className="rt-past__empty">Loading…</div>
        ) : suggestions.length === 0 ? (
          <div className="rt-past__empty">
            {q ? "No new patients match that search."
               : "No new patients to review right now."}
          </div>
        ) : (
          <ul className="rt-past__list">
            {suggestions.map((p) => {
              const showKnown = !!revealed[p.patient_uuid];
              return (
              <li key={p.patient_uuid} className="rt-past__card">
                <div className="rt-past__card-main">
                  <div className="rt-past__patient">
                    <span className="rt-past__patient-name">{demoLine(p)}</span>
                    <span className="rt-past__patient-id mono" title={p.patient_uuid}>
                      {p.patient_uuid.slice(0, 8)}…
                    </span>
                  </div>
                  <div className="rt-past__footline">
                    <span>Not read yet</span>
                    {p.ground_truth_disease && (
                      <>
                        <span className="rt-past__footline-sep">·</span>
                        <button
                          type="button"
                          onClick={() => toggleRevealed(p.patient_uuid)}
                          className="rt-past__reveal"
                          aria-expanded={showKnown}
                        >
                          {showKnown ? "Hide known diagnosis" : "Show known diagnosis"}
                          <ChevronDown size={10} strokeWidth={2}
                                       className={showKnown ? "rt-past__reveal-chev is-open" : "rt-past__reveal-chev"} />
                        </button>
                      </>
                    )}
                  </div>
                  {showKnown && p.ground_truth_disease && (
                    <div className="rt-past__known">
                      <span className="rt-past__known-label">Known diagnosis</span>
                      <span className="rt-past__known-name">{p.ground_truth_disease}</span>
                    </div>
                  )}
                </div>
                <div className="rt-past__card-actions">
                  <button
                    type="button"
                    onClick={() => setPreviewUuid(p.patient_uuid)}
                    className="rt-past__btn rt-past__btn--ghost"
                    title="Inspect this patient's chart before running"
                  >
                    <FileText size={11} strokeWidth={1.8} />
                    Preview chart
                  </button>
                  <button
                    type="button"
                    onClick={() => fireRun(p.patient_uuid)}
                    disabled={busy === p.patient_uuid}
                    className="rt-past__btn rt-past__btn--primary"
                    title="Run the pipeline on this patient"
                  >
                    <Play size={11} strokeWidth={2} />
                    Run pipeline
                  </button>
                </div>
              </li>
              );
            })}
          </ul>
        )}
      </section>

      <PatientPreviewDrawer
        patientUuid={previewUuid}
        onClose={() => setPreviewUuid(null)}
      />
    </motion.div>
  );
}

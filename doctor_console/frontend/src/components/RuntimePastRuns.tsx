import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, Eye, Play, Search } from "lucide-react";
import { getRuntimePastRuns } from "../api";
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
            {runs.map((r) => (
              <li key={r.patient_uuid} className="rt-past__row">
                <div className="rt-past__row-meta">
                  <div className="rt-past__row-top">
                    <span className="rt-past__row-uuid mono">{r.patient_uuid.slice(0, 8)}…</span>
                    <span className="rt-past__row-demo">{demoLine(r)}</span>
                  </div>
                  <div className="rt-past__row-bottom">
                    {r.top_dx ? (
                      <>
                        <span className="rt-past__eyebrow mono">Top dx</span>
                        <span className="rt-past__row-dx">{r.top_dx}</span>
                        {r.confidence != null && (
                          <span className="rt-past__row-conf mono">
                            {Math.round(r.confidence)}%
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="rt-past__row-empty">no diagnosis on record</span>
                    )}
                  </div>
                  {r.ground_truth_disease && (
                    <div className="rt-past__row-gt mono">
                      known dx: {r.ground_truth_disease}
                    </div>
                  )}
                </div>
                <div className="rt-past__row-side">
                  <div className="rt-past__row-when mono">
                    {relative(r.ran_at)}
                    {r.duration_s != null && <> · {Math.round(r.duration_s)}s</>}
                  </div>
                  <div className="rt-past__row-actions">
                    <button
                      type="button"
                      onClick={() => onView(r.patient_uuid)}
                      className="rt-past__btn rt-past__btn--ghost"
                      title="Open the saved result"
                    >
                      <Eye size={11} strokeWidth={1.8} />
                      View
                    </button>
                    <button
                      type="button"
                      onClick={() => fireRun(r.patient_uuid)}
                      disabled={busy === r.patient_uuid}
                      className="rt-past__btn rt-past__btn--primary"
                      title="Run the pipeline again on this patient"
                    >
                      <Play size={11} strokeWidth={2} />
                      Re-run
                    </button>
                  </div>
                </div>
              </li>
            ))}
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
            {suggestions.map((p) => (
              <li key={p.patient_uuid} className="rt-past__row">
                <div className="rt-past__row-meta">
                  <div className="rt-past__row-top">
                    <span className="rt-past__row-uuid mono">{p.patient_uuid.slice(0, 8)}…</span>
                    <span className="rt-past__row-demo">{demoLine(p)}</span>
                  </div>
                  {p.ground_truth_disease && (
                    <div className="rt-past__row-bottom">
                      <span className="rt-past__eyebrow mono">known dx</span>
                      <span className="rt-past__row-dx">{p.ground_truth_disease}</span>
                    </div>
                  )}
                </div>
                <div className="rt-past__row-side">
                  <div className="rt-past__row-when mono">not read yet</div>
                  <div className="rt-past__row-actions">
                    <button
                      type="button"
                      onClick={() => fireRun(p.patient_uuid)}
                      disabled={busy === p.patient_uuid}
                      className="rt-past__btn rt-past__btn--primary"
                      title="Run the pipeline on this patient"
                    >
                      <Play size={11} strokeWidth={2} />
                      Run
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </motion.div>
  );
}

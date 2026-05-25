import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, ChevronDown, Clock, Eye, FileText, Play, Search } from "lucide-react";
import { getRunHistory, getRuntimePastRuns } from "../api";
import { parseBackendDate, relativeBackend, formatBackendDate } from "../lib/datetime";
import { PatientPreviewDrawer } from "./PatientPreviewDrawer";
import type {
  ModelPreset, RuntimePastRun, RuntimePastRunsResponse,
  RuntimePatientSuggestion, RuntimeRunHistoryEntry,
} from "../types";

interface Props {
  /** Opens a saved result of a previous runtime run in place (no new
   *  pipeline call). The parent loads via getResult / openRunArchive
   *  and switches phase. When archiveId is set, the parent loads that
   *  specific snapshot from <uuid>/_history/<archiveId>/ rather than
   *  the latest top-level read. */
  onView:   (patientUuid: string, archiveId?: string) => void;
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

// Local-clock-correct relative time. The shared parser appends Z to
// naïve backend ISO strings before parsing so the math doesn't drift
// by the user's UTC offset. Local-TZ absolute display goes through
// formatBackendDate from the same module when needed.
const relative = relativeBackend;

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
  // Per-row history-disclosure state. Each row opens its own list of
  // archived runs; history is fetched lazily the first time the
  // disclosure is opened and cached in `history[uuid]`.
  const [historyOpen,    setHistoryOpen]    = useState<Record<string, boolean>>({});
  const [history,        setHistory]        = useState<Record<string, RuntimeRunHistoryEntry[] | "loading" | "error">>({});
  async function toggleHistory(uuid: string) {
    const nowOpen = !historyOpen[uuid];
    setHistoryOpen((m) => ({ ...m, [uuid]: nowOpen }));
    if (nowOpen && !(uuid in history)) {
      setHistory((m) => ({ ...m, [uuid]: "loading" }));
      try {
        const resp = await getRunHistory(uuid);
        setHistory((m) => ({ ...m, [uuid]: resp.entries }));
      } catch {
        setHistory((m) => ({ ...m, [uuid]: "error" }));
      }
    }
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
                    <span className="rt-past__footline-sep">·</span>
                    <button
                      type="button"
                      onClick={() => toggleHistory(r.patient_uuid)}
                      className="rt-past__reveal"
                      aria-expanded={!!historyOpen[r.patient_uuid]}
                    >
                      <Clock size={10} strokeWidth={2} />
                      {historyOpen[r.patient_uuid] ? "Hide previous reads" : "Show previous reads"}
                      <ChevronDown size={10} strokeWidth={2}
                                   className={historyOpen[r.patient_uuid] ? "rt-past__reveal-chev is-open" : "rt-past__reveal-chev"} />
                    </button>
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
                  {historyOpen[r.patient_uuid] && (
                    <RowHistory
                      state={history[r.patient_uuid]}
                      onOpen={(archiveId) => onView(r.patient_uuid, archiveId)}
                    />
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

/* Inline "previous reads" list for a single past-runs row. The parent
 * lazily fetches /api/runtime/runs/<uuid>/history when the disclosure
 * first opens; this component just renders whatever state is in flight. */
function RowHistory({
  state, onOpen,
}: {
  state:  RuntimeRunHistoryEntry[] | "loading" | "error" | undefined;
  onOpen: (archiveId: string) => void;
}) {
  if (state === "loading" || state === undefined) {
    return <div className="rt-past__history rt-past__history--meta">Loading previous reads…</div>;
  }
  if (state === "error") {
    return <div className="rt-past__history rt-past__history--meta">Couldn't load the run history.</div>;
  }
  if (state.length === 0) {
    return (
      <div className="rt-past__history rt-past__history--meta">
        No previous reads on file — only the most recent is saved so far.
      </div>
    );
  }
  return (
    <ol className="rt-past__history">
      {state.map((entry) => (
        <li key={entry.archive_id} className="rt-past__history-item">
          <div className="rt-past__history-meta">
            <div className="rt-past__history-when">
              {entry.ran_at ? formatBackendDate(entry.ran_at) : "unknown time"}
              <span className="rt-past__history-rel mono">
                {entry.ran_at ? ` · ${relativeBackend(entry.ran_at)}` : ""}
                {entry.duration_s != null ? ` · ${Math.round(entry.duration_s)}s` : ""}
              </span>
            </div>
            {entry.top_dx ? (
              <div className="rt-past__history-dx">
                {entry.top_dx}
                {entry.confidence != null && (
                  <span className="rt-past__history-conf mono">
                    {Math.round(entry.confidence)}%
                  </span>
                )}
              </div>
            ) : (
              <div className="rt-past__history-dx rt-past__history-dx--empty">
                No diagnosis recorded for this read.
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => onOpen(entry.archive_id)}
            className="rt-past__btn rt-past__btn--ghost"
            title="Open this archived read"
          >
            <Eye size={11} strokeWidth={1.8} />
            Open
          </button>
        </li>
      ))}
    </ol>
  );
}

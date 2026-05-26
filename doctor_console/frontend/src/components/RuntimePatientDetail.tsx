import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Calendar, Cpu, Eye, FileText,
  ListChecks, Loader2, Play, RotateCw, Stethoscope, X,
} from "lucide-react";
import {
  getPatientCase, getResult, getRunTimeline, openRunArchive,
  type CaseBundle,
} from "../api";
import { formatBackendDate, relativeBackend } from "../lib/datetime";
import { confClass, demoLineLong, initials, shortId } from "../lib/clinical";
import type {
  ModelPreset, PatientResult, RuntimeRunTimelineResponse,
  RuntimeRunTimelineRead,
} from "../types";

interface Props {
  patientUuid:    string;
  onBack:         () => void;
  onRun:          (uuid: string, preset: ModelPreset, topK: number) => void;
  defaultPreset?: ModelPreset;
  defaultTopK?:   number;
}

/* ────────────────────────────────────────────────────────────────────
   Patient Detail — every prior read on this chart.
   Hero with demographics + Re-run CTA. Below: left timeline of reads
   (with confidence sparkline), right "Chart at a glance" sidebar.
   Click any timeline entry → opens an inspect drawer with the verdict,
   top-3 differential, agent timing, and treatment-plan callout.
   ──────────────────────────────────────────────────────────────────── */
export function RuntimePatientDetail({
  patientUuid, onBack, onRun, defaultPreset, defaultTopK = 3,
}: Props) {
  const [timeline, setTimeline] = useState<RuntimeRunTimelineResponse | null>(null);
  const [chart,    setChart]    = useState<CaseBundle | null>(null);
  const [error,    setError]    = useState<string | null>(null);
  // Drawer state — which read is being inspected.
  const [drawerArchiveId, setDrawerArchiveId] = useState<string | null | undefined>(undefined);
  // PatientResult for the drawer (loaded lazily when a read is opened).
  const [drawerResult, setDrawerResult] = useState<PatientResult | null>(null);
  const [drawerBusy,   setDrawerBusy]   = useState(false);

  useEffect(() => {
    let cancelled = false;
    setTimeline(null);
    setChart(null);
    setError(null);
    getRunTimeline(patientUuid)
      .then((d) => { if (!cancelled) setTimeline(d); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    getPatientCase(patientUuid)
      .then((c) => { if (!cancelled) setChart(c); })
      .catch(() => { /* chart sidebar degrades gracefully */ });
    return () => { cancelled = true; };
  }, [patientUuid]);

  function openInspect(read: RuntimeRunTimelineRead) {
    setDrawerArchiveId(read.archive_id);
    setDrawerResult(null);
    setDrawerBusy(true);
    const loader = read.archive_id
      ? openRunArchive(patientUuid, read.archive_id)
      : getResult("mas_results_runtime", patientUuid);
    loader
      .then((r) => setDrawerResult(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setDrawerBusy(false));
  }
  function closeDrawer() {
    setDrawerArchiveId(undefined);
    setDrawerResult(null);
  }

  function fireRun() {
    if (!defaultPreset) {
      setError("Pick a model preset on the hero first, then come back to Run.");
      return;
    }
    onRun(patientUuid, defaultPreset, defaultTopK);
  }

  const reads     = timeline?.reads ?? [];
  const patient   = timeline?.patient;
  const drawerRead = drawerArchiveId !== undefined
    ? reads.find((r) => r.archive_id === drawerArchiveId) ?? null
    : null;

  /* Sparkline points: confidence trend across reads, oldest → newest. */
  const sparkPoints = useMemo(() => {
    const sorted = [...reads].reverse();
    return sorted.map((r) => Math.max(0, Math.min(100, r.confidence ?? 0)));
  }, [reads]);

  return (
    <motion.div
      className="pd-shell"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
    >
      <button type="button" onClick={onBack} className="pd-back">
        <ArrowLeft size={13} strokeWidth={1.8} />
        Back to past patients
      </button>

      {/* Hero ──────────────────────────────────────────────────────── */}
      <section className="pd-hero">
        <div className="pd-hero__id">
          <div className="pd-hero__avatar">{initials(patientUuid)}</div>
          <div className="pd-hero__id-meta">
            <span className="pd-hero__uuid mono">
              {shortId(patientUuid)}… · patient record
            </span>
            <h2 className="pd-hero__name">
              {patient ? demoLineLong(patient) : "Loading patient…"}
            </h2>
          </div>
        </div>
        <div className="pd-hero__chips">
          {patient?.race === null && patient?.gender === null ? null : null}
          {chart?.patient?.cutoffDate && (
            <span className="pd-chip">
              <Calendar size={11} strokeWidth={1.8} /> Chart cutoff{" "}
              <strong>{chart.patient.cutoffDate}</strong>
            </span>
          )}
          {chart && (
            <span className="pd-chip">
              <ListChecks size={11} strokeWidth={1.8} />{" "}
              <strong>{((chart.ehrCase as Record<string, unknown>)?.conditions as Record<string, unknown>)?.["active"]
                ? ((((chart.ehrCase as Record<string, unknown>).conditions as Record<string, unknown>)["active"] as unknown[]).length)
                : 0}</strong>{" "}active conditions
            </span>
          )}
          <span className="pd-chip">
            <Stethoscope size={11} strokeWidth={1.8} />{" "}
            <strong>{reads.length}</strong> total{" "}
            {reads.length === 1 ? "run" : "runs"}
          </span>
          {patient?.ground_truth_disease && (
            <span className="pd-chip pd-chip--accent">
              known dx · {patient.ground_truth_disease}
            </span>
          )}
        </div>
        <div className="pd-hero__cta">
          <button
            type="button"
            className="pd-btn-primary"
            onClick={fireRun}
          >
            <Play size={13} strokeWidth={2.2} />
            {reads.length ? "Re-run analysis" : "Run analysis"}
          </button>
          <button
            type="button"
            className="pd-btn-ghost"
            onClick={() => openInspect(reads[0])}
            disabled={reads.length === 0}
            title="Inspect the most recent read in detail"
          >
            <FileText size={12} strokeWidth={1.8} />
            Open latest read
          </button>
          {defaultPreset && (
            <span className="pd-cta-meta mono">
              model · {defaultPreset.label ?? defaultPreset.id}
            </span>
          )}
        </div>
      </section>

      {error && <div className="pd-error" role="alert">{error}</div>}

      {/* Detail grid ─────────────────────────────────────────────── */}
      <div className="pd-grid">
        {/* Run history / timeline */}
        <section className="pd-panel">
          <header className="pd-panel__head">
            <h3 className="pd-panel__title">Run history</h3>
            <div className="pd-panel__sub mono">
              {reads.length} {reads.length === 1 ? "read" : "reads"}
              {reads.length > 0 && reads[reads.length - 1].ran_at && (
                <> · oldest {formatBackendDate(reads[reads.length - 1].ran_at)}</>
              )}
            </div>
          </header>

          {sparkPoints.length > 1 && <ConfidenceSpark points={sparkPoints} />}

          {!timeline ? (
            <div className="pd-loading">
              <Loader2 size={14} strokeWidth={1.7} className="pd-spin" />
              Loading reads…
            </div>
          ) : reads.length === 0 ? (
            <div className="pd-empty">
              This patient hasn't been read yet. Click <strong>Run analysis</strong> to
              create the first read.
            </div>
          ) : (
            <ol className="pd-timeline">
              {reads.map((r) => (
                <TimelineEntry
                  key={r.archive_id ?? "live"}
                  read={r}
                  selected={drawerArchiveId === r.archive_id}
                  onInspect={() => openInspect(r)}
                  onRerun={fireRun}
                />
              ))}
            </ol>
          )}
        </section>

        {/* Chart at a glance */}
        <ChartSidebar chart={chart} />
      </div>

      <InspectDrawer
        open={drawerArchiveId !== undefined}
        read={drawerRead}
        result={drawerResult}
        loading={drawerBusy}
        onClose={closeDrawer}
        onRerun={fireRun}
      />
    </motion.div>
  );
}

/* ─── Timeline entry ─────────────────────────────────────────────── */
function TimelineEntry({
  read, selected, onInspect, onRerun,
}: {
  read:      RuntimeRunTimelineRead;
  selected:  boolean;
  onInspect: () => void;
  onRerun:   () => void;
}) {
  const conf = read.confidence;
  return (
    <li>
      <article
        className={`pd-tl${selected ? " is-selected" : ""}`}
        role="button"
        tabIndex={0}
        onClick={onInspect}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault(); onInspect();
          }
        }}
      >
        <div className="pd-tl__when">
          <span className="pd-tl__date mono">{formatBackendDate(read.ran_at)}</span>
          <span className="pd-tl__rel">{relativeBackend(read.ran_at)}</span>
        </div>
        <div className="pd-tl__body">
          <div className="pd-tl__dx-row">
            <span className="pd-tl__dx">
              {read.top_dx ?? "No diagnosis recorded"}
            </span>
            {conf != null && (
              <span className={`pp-card__dx-conf mono ${confClass(conf)}`}>
                {Math.round(conf)}%
              </span>
            )}
            {read.match_type && (
              <span className={`pd-tl__match pd-tl__match--${read.match_type}`}>
                {read.match_type}
              </span>
            )}
          </div>
          <div className="pd-tl__sub mono">
            {read.model && (
              <>
                <span><Cpu size={10} strokeWidth={1.8} /> <strong>{read.model}</strong></span>
                <span className="pd-tl__sub-sep">·</span>
              </>
            )}
            {read.duration_s != null && (
              <span>{Math.round(read.duration_s)}s pipeline</span>
            )}
            {read.triggered_by && (
              <>
                <span className="pd-tl__sub-sep">·</span>
                <span>by {read.triggered_by}</span>
              </>
            )}
          </div>
          {read.note && <p className="pd-tl__note">{read.note}</p>}
          <div className="pd-tl__actions">
            <button
              type="button"
              className="pd-btn-mini"
              onClick={(e) => { e.stopPropagation(); onInspect(); }}
            >
              <Eye size={11} strokeWidth={1.8} />
              Inspect
            </button>
            <button
              type="button"
              className="pd-btn-mini"
              onClick={(e) => { e.stopPropagation(); onRerun(); }}
            >
              <RotateCw size={11} strokeWidth={1.8} />
              Re-run on this chart
            </button>
          </div>
        </div>
      </article>
    </li>
  );
}

/* ─── Confidence sparkline ───────────────────────────────────────── */
function ConfidenceSpark({ points }: { points: number[] }) {
  const w = 100, h = 100, padX = 4, padY = 8;
  if (!points.length) return null;
  const maxX = Math.max(1, points.length - 1);
  const xs = (i: number) => padX + (i / maxX) * (w - 2 * padX);
  const ys = (v: number) => h - padY - (Math.max(0, Math.min(100, v)) / 100) * (h - 2 * padY);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${xs(i).toFixed(1)},${ys(p).toFixed(1)}`).join(" ");
  const area = `${path} L${xs(maxX).toFixed(1)},${h - padY} L${xs(0).toFixed(1)},${h - padY} Z`;
  return (
    <div className="pd-spark" aria-label="Confidence trend across runs">
      <div className="pd-spark__head mono">
        <span>Top-1 confidence · oldest → newest</span>
        <span>{points[0]}% → {points[points.length - 1]}%</span>
      </div>
      <svg className="pd-spark__svg" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="pd-spark-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#pd-spark-fill)" />
        <path
          d={path}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        {points.map((p, i) => (
          <circle
            key={i}
            cx={xs(i)} cy={ys(p)} r="1.6"
            fill="var(--bg-elevated)" stroke="var(--accent)" strokeWidth="1.2"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
    </div>
  );
}

/* ─── Chart at a glance sidebar ──────────────────────────────────── */
function ChartSidebar({ chart }: { chart: CaseBundle | null }) {
  if (!chart) {
    return (
      <aside className="pd-panel">
        <header className="pd-panel__head">
          <h3 className="pd-panel__title">Chart at a glance</h3>
        </header>
        <div className="pd-loading">
          <Loader2 size={14} strokeWidth={1.7} className="pd-spin" />
          Loading chart…
        </div>
      </aside>
    );
  }
  const ehr = (chart.ehrCase ?? {}) as Record<string, any>;
  const lab = (chart.labCase ?? {}) as Record<string, any>;
  const conditions   = ((ehr.conditions  ?? {}).active  ?? []) as Array<Record<string, any>>;
  const medications  = ((ehr.medications ?? {}).active  ?? []) as Array<Record<string, any>>;
  const vitalsBlock  = (lab.recent_vitals ?? {}) as Record<string, any>;
  const labs         = (lab.latest_labs ?? []) as Array<Record<string, any>>;

  const bp = vitalsBlock.bp ??
    (vitalsBlock.bp_systolic && vitalsBlock.bp_diastolic
      ? `${vitalsBlock.bp_systolic}/${vitalsBlock.bp_diastolic}` : null);
  const hr   = vitalsBlock.hr ?? vitalsBlock.heart_rate ?? null;
  const spo2 = vitalsBlock.spo2 ?? vitalsBlock.oxygen_sat ?? null;
  const temp = vitalsBlock.temp_c ?? vitalsBlock.temperature_c ?? null;

  return (
    <aside className="pd-panel">
      <header className="pd-panel__head">
        <h3 className="pd-panel__title">Chart at a glance</h3>
        {chart.patient?.cutoffDate && (
          <div className="pd-panel__sub mono">cutoff {chart.patient.cutoffDate}</div>
        )}
      </header>

      {conditions.length > 0 && (
        <section className="pd-section">
          <h4 className="pd-section__head mono">Active conditions</h4>
          <ul className="pd-chart-list">
            {conditions.slice(0, 8).map((c, i) => (
              <li key={i}>{c.condition || c.name || "Condition"}</li>
            ))}
            {conditions.length > 8 && (
              <li className="pd-chart-list__more mono">+{conditions.length - 8} more</li>
            )}
          </ul>
        </section>
      )}

      {medications.length > 0 && (
        <section className="pd-section">
          <h4 className="pd-section__head mono">Active medications</h4>
          <ul className="pd-chart-list">
            {medications.slice(0, 8).map((m, i) => (
              <li key={i}>{m.medication || m.name || "Medication"}</li>
            ))}
            {medications.length > 8 && (
              <li className="pd-chart-list__more mono">+{medications.length - 8} more</li>
            )}
          </ul>
        </section>
      )}

      {(bp || hr || spo2 || temp) && (
        <section className="pd-section">
          <h4 className="pd-section__head mono">Vitals · most recent</h4>
          <div className="pd-vitals">
            <Vital label="BP"   value={bp} />
            <Vital label="HR"   value={hr != null ? `${hr}` : null} />
            <Vital label="SpO₂" value={spo2 != null ? `${spo2}%` : null} />
            <Vital label="Temp" value={temp != null ? `${temp}°C` : null} />
          </div>
        </section>
      )}

      {labs.length > 0 && (
        <section className="pd-section">
          <h4 className="pd-section__head mono">Labs · latest panel</h4>
          <div className="pd-labs">
            {labs.slice(0, 6).map((l, i) => (
              <div className="pd-lab" key={i}>
                <span className="pd-lab__name">{l.lab_name || l.test_name || "—"}</span>
                <span className="pd-lab__value mono">
                  {l.value ?? ""} {l.units ?? l.unit ?? ""}
                </span>
                <span className={`pd-lab__flag pd-lab__flag--${(l.flag ?? "").toLowerCase()}`}>
                  {l.flag || ""}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </aside>
  );
}

function Vital({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="pd-vital">
      <div className="pd-vital__label mono">{label}</div>
      <div className="pd-vital__value mono">{value ?? "—"}</div>
    </div>
  );
}

/* ─── Inspect drawer ─────────────────────────────────────────────── */
function InspectDrawer({
  open, read, result, loading, onClose, onRerun,
}: {
  open:    boolean;
  read:    RuntimeRunTimelineRead | null;
  result:  PatientResult | null;
  loading: boolean;
  onClose: () => void;
  onRerun: () => void;
}) {
  // Esc closes.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Top-3 differential extracted from the loaded result.
  const top3 = useMemo(() => {
    const fd = (result?.finalDiagnosis ?? {}) as Record<string, unknown>;
    const diff = Array.isArray(fd.differential)
      ? (fd.differential as Array<Record<string, unknown>>)
      : [];
    return diff.slice(0, 3).map((d) => {
      const name = String(d.name ?? d.diagnosis ?? "—");
      const raw  = typeof d.probability === "number" ? d.probability
                 : typeof d.confidence  === "number" ? d.confidence
                 : null;
      const conf = raw == null ? null : Math.round(raw > 1 ? raw : raw * 100);
      return { name, conf };
    });
  }, [result]);

  // Agent timing from result.agents[].executionMs (ms).
  const timing = useMemo(() => {
    const agents = result?.agents ?? [];
    return agents
      .filter((a) => a.id !== "evaluation" && typeof a.executionMs === "number")
      .map((a) => ({
        id: a.id, label: a.label, ms: a.executionMs as number,
      }));
  }, [result]);
  const totalMs = timing.reduce((sum, a) => sum + a.ms, 0);

  // Treatment summary one-liner from result.treatment.treatment_summary.
  const treatmentSummary = useMemo(() => {
    const t = result?.treatment as Record<string, unknown> | undefined;
    return typeof t?.treatment_summary === "string" ? t.treatment_summary : null;
  }, [result]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="pd-drawer-bd"
            className="pd-drawer-bd"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
          />
          <motion.aside
            key="pd-drawer"
            className="pd-drawer"
            role="dialog"
            aria-label="Inspect run"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.26, ease: [0.23, 1, 0.32, 1] }}
          >
            <header className="pd-drawer__head">
              <div className="pd-drawer__head-text">
                <h3 className="pd-drawer__title">
                  {read?.top_dx ?? "Loading read…"}
                </h3>
                <div className="pd-drawer__sub mono">
                  {read?.ran_at && <>{formatBackendDate(read.ran_at)}</>}
                  {read?.model && <> · {read.model}</>}
                  {read?.duration_s != null && <> · {Math.round(read.duration_s)}s</>}
                </div>
              </div>
              <button
                type="button"
                className="pd-drawer__close"
                onClick={onClose}
                aria-label="Close inspect drawer"
              >
                <X size={14} strokeWidth={1.8} />
              </button>
            </header>

            <div className="pd-drawer__body">
              {loading ? (
                <div className="pd-loading">
                  <Loader2 size={14} strokeWidth={1.7} className="pd-spin" />
                  Loading run…
                </div>
              ) : (
                <>
                  <section className="pd-drawer__section">
                    <h4 className="pd-drawer__section-title mono">Verdict</h4>
                    <div className="pd-callout">
                      {read?.match_type ? (
                        <>
                          Match against ground truth —{" "}
                          <strong className="mono">{read.match_type}</strong>.
                        </>
                      ) : (
                        <>Top diagnosis rendered by the multi-agent system.</>
                      )}
                      {read?.confidence != null && (
                        <>
                          {" "}Top diagnosis confidence{" "}
                          <strong>{Math.round(read.confidence)}%</strong>.
                        </>
                      )}
                      {read?.note && (
                        <> Reviewer note: <em>{read.note}</em></>
                      )}
                    </div>
                  </section>

                  {top3.length > 0 && (
                    <section className="pd-drawer__section">
                      <h4 className="pd-drawer__section-title mono">Differential — top 3</h4>
                      <ul className="pd-diff">
                        {top3.map((d, i) => (
                          <li key={`${d.name}-${i}`} className="pd-diff__row">
                            <span className="pd-diff__rank mono">{i + 1}</span>
                            <div className="pd-diff__main">
                              <div className="pd-diff__name">{d.name}</div>
                              <div className="pd-diff__bar">
                                <div
                                  className="pd-diff__bar-fill"
                                  style={{ width: `${d.conf ?? 0}%` }}
                                />
                              </div>
                            </div>
                            <span className={`pd-diff__conf mono ${confClass(d.conf)}`}>
                              {d.conf != null ? `${d.conf}%` : "—"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  {timing.length > 0 && (
                    <section className="pd-drawer__section">
                      <h4 className="pd-drawer__section-title mono">Agent timing</h4>
                      <div className="pd-agent-bars">
                        {timing.map((a) => (
                          <div className="pd-agent-bar" key={a.id}>
                            <span className="pd-agent-bar__name">{a.label}</span>
                            <div className="pd-agent-bar__track">
                              <div
                                className="pd-agent-bar__fill"
                                style={{ width: totalMs ? `${(a.ms / totalMs) * 100}%` : "0%" }}
                              />
                            </div>
                            <span className="pd-agent-bar__time mono">
                              {(a.ms / 1000).toFixed(1)}s
                            </span>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {treatmentSummary && (
                    <section className="pd-drawer__section">
                      <h4 className="pd-drawer__section-title mono">Treatment plan</h4>
                      <div className="pd-callout pd-callout--success">
                        {treatmentSummary}
                      </div>
                    </section>
                  )}

                  <section className="pd-drawer__section">
                    <h4 className="pd-drawer__section-title mono">Actions</h4>
                    <div className="pd-drawer__actions">
                      <button type="button" className="pd-btn-primary" onClick={onRerun}>
                        <RotateCw size={12} strokeWidth={1.8} />
                        Re-run with current model
                      </button>
                    </div>
                  </section>
                </>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}


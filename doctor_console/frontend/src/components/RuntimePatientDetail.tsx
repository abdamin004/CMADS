import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle, ArrowLeft, ArrowRight, Calendar, Check, Cpu,
  Eye, ListChecks, Loader2, Play, RotateCw, Stethoscope, X,
} from "lucide-react";
import {
  getPatientCase, getRunTimeline, setRunAgreement,
  type CaseBundle,
} from "../api";
import { formatBackendDate, relativeBackend } from "../lib/datetime";
import { confClass, demoLineLong, initials, shortId } from "../lib/clinical";
import { TestRunConfigModal } from "./TestRunConfigModal";
import type {
  ModelPreset, RuntimeRunTimelineResponse, RuntimeRunTimelineRead,
} from "../types";

interface Props {
  patientUuid:    string;
  onBack:         () => void;
  /** Open a specific read in the full RuntimeResultView (5-tab view).
   *  archiveId === null opens the most recent live read; a string
   *  opens the snapshot. */
  onInspectRead:  (uuid: string, archiveId: string | null) => void;
  /** Fire a new pipeline run with the doctor-chosen preset/top-K. */
  onRun:          (uuid: string, preset: ModelPreset, topK: number) => void;
  defaultPreset?: ModelPreset;
  defaultTopK?:   number;
}

type Agreement = "agree" | "disagree" | "uncertain" | null;

/* ────────────────────────────────────────────────────────────────────
   Patient Detail — every prior read on this chart.
   Hero: identity + chips + Re-run CTA. Inline grid: left timeline of
   reads (sparkline + per-entry agree/disagree pills + model badge +
   Inspect/Re-run actions), right "Chart at a glance" sidebar.
   Inspect (or clicking a timeline entry) now routes to the full
   RuntimeResultView instead of an inline drawer.
   ──────────────────────────────────────────────────────────────────── */
export function RuntimePatientDetail({
  patientUuid, onBack, onInspectRead, onRun, defaultPreset, defaultTopK = 3,
}: Props) {
  const [timeline, setTimeline] = useState<RuntimeRunTimelineResponse | null>(null);
  const [chart,    setChart]    = useState<CaseBundle | null>(null);
  const [error,    setError]    = useState<string | null>(null);
  // Run-config modal: the patient whose row triggered it (always our
  // own uuid here, but the modal type expects a TestPatientSummary-
  // shaped object — see below). null when closed.
  const [rerunOpen, setRerunOpen] = useState(false);
  // Optimistic per-read agreement state to keep clicks snappy. The
  // server is the source of truth; we mirror its writes back.
  const [agreements, setAgreements] = useState<Record<string, Agreement>>({});

  useEffect(() => {
    let cancelled = false;
    setTimeline(null);
    setChart(null);
    setError(null);
    setAgreements({});
    getRunTimeline(patientUuid)
      .then((d) => {
        if (cancelled) return;
        setTimeline(d);
        // Seed local agreement state from server values.
        const seed: Record<string, Agreement> = {};
        for (const r of d.reads) {
          const key = r.archive_id ?? "live";
          seed[key] = (r.agreement ?? null) as Agreement;
        }
        setAgreements(seed);
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    getPatientCase(patientUuid)
      .then((c) => { if (!cancelled) setChart(c); })
      .catch(() => { /* sidebar degrades gracefully */ });
    return () => { cancelled = true; };
  }, [patientUuid]);

  function setAgreementFor(archiveId: string | null, next: Agreement) {
    const key = archiveId ?? "live";
    const current = agreements[key] ?? null;
    const value: Agreement = current === next ? null : next;
    // Optimistic update + persist; revert on failure.
    setAgreements((m) => ({ ...m, [key]: value }));
    setRunAgreement(patientUuid, archiveId, value)
      .catch((e: Error) => {
        setError(e.message);
        setAgreements((m) => ({ ...m, [key]: current }));
      });
  }

  const reads     = timeline?.reads ?? [];
  const patient   = timeline?.patient;

  /* Sparkline points: confidence trend across reads, oldest → newest. */
  const sparkPoints = useMemo(() => {
    const sorted = [...reads].reverse();
    return sorted.map((r) => Math.max(0, Math.min(100, r.confidence ?? 0)));
  }, [reads]);

  // Synthesise a TestPatientSummary-shaped object for the
  // TestRunConfigModal. The modal only reads label + test_uuid +
  // last_run_at, so we map our patient fields accordingly.
  const rerunModalPatient = useMemo(() => ({
    test_uuid:   patientUuid,
    label:       patient ? demoLineLong(patient) : `Patient ${shortId(patientUuid)}…`,
    created_at:  "",
    run_count:   reads.length,
    last_run_at: reads[0]?.ran_at ?? null,
  }), [patientUuid, patient, reads]);

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

      {/* Hero ───────────────────────────────────────────────────── */}
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
            onClick={() => setRerunOpen(true)}
          >
            <Play size={13} strokeWidth={2.2} />
            {reads.length ? "Re-run analysis" : "Run analysis"}
          </button>
          <button
            type="button"
            className="pd-btn-ghost"
            onClick={() => onInspectRead(patientUuid, reads[0]?.archive_id ?? null)}
            disabled={reads.length === 0}
            title="Inspect the most recent read in detail"
          >
            <Eye size={12} strokeWidth={1.8} />
            Open latest read
            <ArrowRight size={11} strokeWidth={1.8} />
          </button>
          {defaultPreset && (
            <span className="pd-cta-meta mono">
              defaults to · {defaultPreset.label ?? defaultPreset.id}
            </span>
          )}
        </div>
      </section>

      {error && <div className="pd-error" role="alert">{error}</div>}

      {/* Detail grid ────────────────────────────────────────────── */}
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
              {reads.map((r) => {
                const key = r.archive_id ?? "live";
                const ag  = agreements[key] ?? null;
                return (
                  <TimelineEntry
                    key={key}
                    read={r}
                    agreement={ag}
                    onAgree={(v) => setAgreementFor(r.archive_id, v)}
                    onInspect={() => onInspectRead(patientUuid, r.archive_id)}
                    onRerun={() => setRerunOpen(true)}
                  />
                );
              })}
            </ol>
          )}
        </section>

        {/* Chart at a glance */}
        <ChartSidebar chart={chart} />
      </div>

      {rerunOpen && (
        <TestRunConfigModal
          patient={rerunModalPatient}
          onClose={() => setRerunOpen(false)}
          onStarted={() => setRerunOpen(false)}
          // The modal's onStarted only handles the task hand-off, but
          // re-run from this surface needs to fire the runtime handleRun
          // so RuntimeMode owns the live SSE subscription. We side-step
          // the modal's startTestRun (Tester) flow by passing through a
          // patient that has a non-Tester uuid; the modal then becomes
          // purely a preset+topK picker for us via custom onConfirm.
          onConfirm={(preset, topK) => {
            setRerunOpen(false);
            onRun(patientUuid, preset, topK);
          }}
        />
      )}
    </motion.div>
  );
}

/* ─── Timeline entry ─────────────────────────────────────────────── */
function TimelineEntry({
  read, agreement, onAgree, onInspect, onRerun,
}: {
  read:       RuntimeRunTimelineRead;
  agreement:  Agreement;
  onAgree:    (next: Agreement) => void;
  onInspect:  () => void;
  onRerun:    () => void;
}) {
  const conf = read.confidence;
  return (
    <li>
      <article
        className="pd-tl"
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
            {read.model ? (
              <>
                <span><Cpu size={10} strokeWidth={1.8} /> <strong>{read.model}</strong></span>
                <span className="pd-tl__sub-sep">·</span>
              </>
            ) : (
              <>
                <span className="pd-tl__model-empty">model not recorded</span>
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
          <div className="pd-tl__row">
            <AgreementCluster value={agreement} onChange={onAgree} />
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
        </div>
      </article>
    </li>
  );
}

/* 3-state pill cluster — same visual family as the past-runs card
   agreement badge but now interactive and per-read. */
function AgreementCluster({
  value, onChange,
}: {
  value:    Agreement;
  onChange: (next: Agreement) => void;
}) {
  const opts: Array<{
    key:  NonNullable<Agreement>;
    label: string;
    tone: "success" | "warning" | "critical";
    Icon: typeof Check;
  }> = [
    { key: "agree",     label: "Agree",     tone: "success",  Icon: Check         },
    { key: "uncertain", label: "Uncertain", tone: "warning",  Icon: AlertTriangle },
    { key: "disagree",  label: "Disagree",  tone: "critical", Icon: X             },
  ];
  return (
    <div
      className="pd-agree"
      role="radiogroup"
      aria-label="Your agreement with this read"
      onClick={(e) => e.stopPropagation()}
    >
      {opts.map((o) => {
        const active = value === o.key;
        return (
          <button
            key={o.key}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={(e) => { e.stopPropagation(); onChange(o.key); }}
            className={`pd-agree__btn pd-agree__btn--${o.tone}${active ? " is-active" : ""}`}
            title={`Mark this read as ${o.label.toLowerCase()}`}
          >
            <o.Icon size={11} strokeWidth={2.2} />
            {o.label}
          </button>
        );
      })}
    </div>
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
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.4"
              strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {points.map((p, i) => (
          <circle key={i} cx={xs(i)} cy={ys(p)} r="1.6"
                  fill="var(--bg-elevated)" stroke="var(--accent)" strokeWidth="1.2"
                  vectorEffect="non-scaling-stroke" />
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

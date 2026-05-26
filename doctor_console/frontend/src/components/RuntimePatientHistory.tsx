import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft, ChevronRight, Clock, FileText, Loader2, Play,
} from "lucide-react";
import { getRunTimeline } from "../api";
import { formatBackendDate, relativeBackend } from "../lib/datetime";
import { PatientPreviewDrawer } from "./PatientPreviewDrawer";
import type { ModelPreset, RuntimeRunTimelineResponse, RuntimeRunTimelineRead } from "../types";

interface Props {
  patientUuid:    string;
  /** Open a saved read in the result view. archiveId === null means
   *  the most recent (live) read; a string opens the snapshot. */
  onOpenRead:     (patientUuid: string, archiveId: string | null) => void;
  /** Fire a new pipeline run on this patient using the default preset. */
  onRun:          (patientUuid: string, preset: ModelPreset, topK: number) => void;
  /** Back to the patients list. */
  onBack:         () => void;
  defaultPreset?: ModelPreset;
  defaultTopK?:   number;
}

/* Patient demographics rendered as a clinician would read them aloud:
 * "45-year-old female · white". Returns the long form to match the
 * editorial Fraunces heading. */
function patientHeadline(p: RuntimeRunTimelineResponse["patient"]): string {
  const sex = p.gender === "F" ? "female"
            : p.gender === "M" ? "male"
            : p.gender || "patient";
  const age = p.age != null ? `${p.age}-year-old` : "Adult";
  const parts = [`${age} ${sex}`];
  if (p.race) parts.push(p.race);
  return parts.join(" · ");
}

/**
 * Per-patient history page.
 *
 * Header: patient identity + small UUID chip + actions (Preview chart,
 * Run pipeline, Re-run is just Run if there's at least one read).
 * Body:   a chronological "Reads" list, newest first. Each entry shows
 *         the local-clock date, relative time, top diagnosis,
 *         confidence, duration. Click anywhere on a read → opens the
 *         saved result view via onOpenRead.
 *
 * Real-clinical aesthetic: Fraunces for patient name + dates, mono for
 * relative times and metadata, calm tonal palette, no decorative noise.
 */
export function RuntimePatientHistory({
  patientUuid, onOpenRead, onRun, onBack, defaultPreset, defaultTopK = 3,
}: Props) {
  const [data,    setData]    = useState<RuntimeRunTimelineResponse | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const [busy,    setBusy]    = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getRunTimeline(patientUuid)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [patientUuid]);

  function fireRun() {
    if (!defaultPreset) {
      setError("Pick a model preset on the hero first, then come back to Run.");
      return;
    }
    setBusy(true);
    onRun(patientUuid, defaultPreset, defaultTopK);
  }

  return (
    <motion.div
      className="rt-patient"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
    >
      <button type="button" onClick={onBack} className="rt-patient__back">
        <ArrowLeft size={13} strokeWidth={1.8} />
        Back to patients
      </button>

      <header className="rt-patient__header">
        <div className="rt-patient__id">
          <div className="rt-patient__id-mono mono">{patientUuid.slice(0, 8)}…</div>
          <h2 className="rt-patient__title">
            {data ? patientHeadline(data.patient) : "Loading patient…"}
          </h2>
          {data?.patient.ground_truth_disease && (
            <div className="rt-patient__known">
              <span className="rt-patient__known-label mono">Known diagnosis</span>
              <span className="rt-patient__known-name">
                {data.patient.ground_truth_disease}
              </span>
            </div>
          )}
        </div>
        <div className="rt-patient__actions">
          <button
            type="button"
            className="rt-patient__action rt-patient__action--ghost"
            onClick={() => setPreview(patientUuid)}
            title="Inspect the patient's chart"
          >
            <FileText size={13} strokeWidth={1.8} />
            Preview chart
          </button>
          <button
            type="button"
            className="rt-patient__action rt-patient__action--primary"
            onClick={fireRun}
            disabled={busy}
          >
            <Play size={13} strokeWidth={2} />
            {data?.reads.length ? "Run again" : "Run pipeline"}
          </button>
        </div>
      </header>

      <section className="rt-patient__reads">
        <header className="rt-patient__reads-head">
          <div className="rt-patient__reads-eyebrow mono">Reads</div>
          <h3 className="rt-patient__reads-title">
            {data?.reads.length ?? 0} {(data?.reads.length ?? 0) === 1 ? "read on file" : "reads on file"}
          </h3>
        </header>

        {error && (
          <div className="rt-patient__error" role="alert">{error}</div>
        )}

        {!data ? (
          <div className="rt-patient__loading">
            <Loader2 size={14} strokeWidth={1.7} className="rt-patient__loading-spin" />
            Loading reads…
          </div>
        ) : data.reads.length === 0 ? (
          <div className="rt-patient__empty">
            This patient hasn't been read yet. Click <strong>Run pipeline</strong> to
            create the first read.
          </div>
        ) : (
          <ol className="rt-patient__list">
            {data.reads.map((r, i) => (
              <ReadItem
                key={r.archive_id ?? "live"}
                read={r}
                isLatest={i === 0}
                onOpen={() => onOpenRead(patientUuid, r.archive_id)}
              />
            ))}
          </ol>
        )}
      </section>

      <PatientPreviewDrawer
        patientUuid={preview}
        onClose={() => setPreview(null)}
      />
    </motion.div>
  );
}

function ReadItem({
  read, isLatest, onOpen,
}: {
  read:     RuntimeRunTimelineRead;
  isLatest: boolean;
  onOpen:   () => void;
}) {
  const conf = read.confidence;
  return (
    <li>
      <button
        type="button"
        className={`rt-read${isLatest ? " rt-read--latest" : ""}`}
        onClick={onOpen}
      >
        <div className="rt-read__when">
          <div className="rt-read__date">
            {formatBackendDate(read.ran_at)}
          </div>
          <div className="rt-read__rel mono">
            <Clock size={10} strokeWidth={1.8} />
            {relativeBackend(read.ran_at)}
            {read.duration_s != null && <> · took {Math.round(read.duration_s)}s</>}
            {isLatest && <span className="rt-read__latest-pill mono">latest</span>}
          </div>
        </div>
        <div className="rt-read__dx">
          {read.top_dx ? (
            <>
              <span className="rt-read__dx-name">{read.top_dx}</span>
              {conf != null && (
                <span className="rt-read__dx-conf mono">{Math.round(conf)}%</span>
              )}
            </>
          ) : (
            <span className="rt-read__dx-empty">No diagnosis recorded for this read.</span>
          )}
        </div>
        <ChevronRight size={14} strokeWidth={1.8} className="rt-read__chev" />
      </button>
    </li>
  );
}

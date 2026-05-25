import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, X } from "lucide-react";
import { getPatientCase, type CaseBundle } from "../api";
import { PatientEvidence } from "./PatientEvidence";
import type { PatientResult } from "../types";

interface Props {
  /** UUID of the patient to preview. When null/undefined the drawer is
   *  closed; setting it opens the drawer and triggers the case fetch. */
  patientUuid: string | null;
  onClose:     () => void;
}

/**
 * Read-only patient-chart drawer used everywhere the doctor wants to
 * inspect the input data without firing a run. Reuses PatientEvidence
 * (the same component the result view's "show chart" overlay uses) so
 * the chart looks identical regardless of entry point.
 *
 * Loads via /api/patients/<uuid>/case → CaseBundle and renders the chart
 * in the same slide-over chrome as the reasoning drawer / chart overlay.
 */
export function PatientPreviewDrawer({ patientUuid, onClose }: Props) {
  const [bundle, setBundle] = useState<CaseBundle | null>(null);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    if (!patientUuid) { setBundle(null); setError(null); return; }
    let cancelled = false;
    setBundle(null);
    setError(null);
    getPatientCase(patientUuid)
      .then((b) => { if (!cancelled) setBundle(b); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [patientUuid]);

  useEffect(() => {
    if (!patientUuid) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [patientUuid, onClose]);

  // PatientEvidence consumes a PatientResult, but we only have a
  // CaseBundle here. Wrap it in the minimum PatientResult shape the
  // component actually reads (case.ehrCase + case.labCase).
  const synthResult: PatientResult | null = bundle ? ({
    patient:         bundle.patient,
    resultSet:       { id: "preview", label: "Preview" } as PatientResult["resultSet"],
    case:            bundle,
    evaluation:      {},
    finalDiagnosis:  {},
    treatment:       {},
    agents:          [],
    agentOutputs:    {},
    agentNarratives: {},
    trace:           {},
    sessionMemory:   [],
    semanticMemory:  [],
    sharedMemory: {
      patientContext:  bundle.patient,
      agentOutputKeys: [],
      sessionEvents:   0,
      traceEntries:    0,
      notes:           [],
    },
  } as unknown as PatientResult) : null;

  return (
    <AnimatePresence>
      {patientUuid && (
        <>
          <motion.div
            key="prev-bd"
            className="chart-overlay__backdrop"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.16 }}
            onClick={onClose}
          />
          <motion.aside
            key="prev-panel"
            className="chart-overlay"
            role="dialog"
            aria-label="Patient chart"
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ duration: 0.24, ease: [0.2, 0.7, 0.3, 1] }}
          >
            <header className="chart-overlay__head">
              <h3 className="chart-overlay__title">
                {bundle
                  ? `${bundle.patient.age ?? "?"}${bundle.patient.gender ?? ""} · chart preview`
                  : `Loading ${patientUuid.slice(0, 8)}…`}
              </h3>
              <button
                type="button"
                className="chart-overlay__close"
                onClick={onClose}
                aria-label="Close patient preview"
              >
                <X size={14} strokeWidth={1.8} />
              </button>
            </header>
            <div className="chart-overlay__body">
              {error ? (
                <div className="empty-state" role="alert">
                  Couldn't load this patient: {error}
                </div>
              ) : !synthResult ? (
                <div className="empty-state" aria-live="polite">
                  <Loader2 size={16} strokeWidth={1.7} className="inline animate-spin" />
                  <span className="ml-2">Loading chart…</span>
                </div>
              ) : (
                <PatientEvidence result={synthResult} />
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

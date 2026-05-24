import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Play, Settings2, X } from "lucide-react";
import { AdvancedSettings, buildPrecisionRows } from "./runtime/AdvancedSettings";
import type { AdvancedSettingsValue } from "./runtime/AdvancedSettings";
import { getStatsOverview, startTestRun } from "../api";
import type { RankBucket, TestPatientSummary } from "../types";

interface Props {
  /** The patient to run. Used for header copy and the API call. */
  patient:  TestPatientSummary;
  /** Closes the modal without running. */
  onClose:  () => void;
  /** Fires once the run has been dispatched server-side. The parent owns
   *  the after-effects (navigate to the running view, refresh the list). */
  onStarted: (taskId: string) => void;
}

/**
 * Run / Re-run config modal.
 * Wraps the standard AdvancedSettings panel so a user can pick model preset,
 * top-K, and accuracy mode before firing startTestRun.  The previous
 * implementation called startTestRun directly from the row button, which
 * fired the request with default settings and offered no visible feedback
 * before the parent dismissed the journey.
 */
export function TestRunConfigModal({ patient, onClose, onStarted }: Props) {
  const [adv, setAdv] = useState<AdvancedSettingsValue>({
    presetId:     "",
    topK:         5,
    accuracyMode: "recommended",
  });
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cohort-wide rank precision — same source the editor uses, so the user
  // sees the trust signal for top-K right next to the picker.
  const [precision, setPrecision] = useState<{ buckets: RankBucket[]; n: number } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const data = await getStatsOverview("multi_level");
        setPrecision({ buckets: data.rankDistribution, n: data.aggregates.n });
      } catch {
        setPrecision(null);
      }
    })();
  }, []);
  const precisionRows = useMemo(
    () => precision ? buildPrecisionRows(precision.buckets, precision.n) : [],
    [precision],
  );

  // Escape closes the modal — same convention as the Smart Import drawer.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function run() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const task = await startTestRun(patient.test_uuid, {
        topK:         adv.topK,
        accuracyMode: adv.accuracyMode,
        presetId:     adv.presetId || undefined,
      });
      onStarted(task.taskId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start the pipeline.");
      setBusy(false);
    }
  }

  const wasRunBefore = !!patient.last_run_at;

  return (
    <motion.div
      className="merge-modal__backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.15 }}
      onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
    >
      <motion.div
        className="merge-modal run-config-modal"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
      >
        <header className="merge-modal__header">
          <div className="merge-modal__heading">
            <div className="merge-modal__eyebrow">
              <Settings2 size={11} strokeWidth={1.8} />
              {wasRunBefore ? "Re-run pipeline" : "Run pipeline"}
            </div>
            <h2 className="merge-modal__title">{patient.label}</h2>
            <p className="merge-modal__sub">
              Pick the model, top-K, and accuracy mode for this run, then dispatch.
              {wasRunBefore && patient.last_run_at && (
                <> Previous run was {new Date(patient.last_run_at).toLocaleString()}.</>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            className="merge-modal__close"
            aria-label="Close run config"
          >
            <X size={16} strokeWidth={1.6} />
          </button>
        </header>

        <div className="merge-modal__body">
          <AdvancedSettings
            value={adv}
            onChange={setAdv}
            precisionRows={precisionRows}
            precisionN={precision?.n}
          />
          {error && (
            <div className="merge-modal__warn run-config-modal__error">
              {error}
            </div>
          )}
        </div>

        <footer className="merge-modal__footer">
          <div /> {/* keep flex spacing consistent with the merge modal */}
          <div className="merge-modal__primary">
            <button
              onClick={onClose}
              disabled={busy}
              className="merge-modal__cancel"
            >
              Cancel
            </button>
            <button
              onClick={run}
              disabled={busy}
              className="merge-modal__merge"
            >
              {busy ? (
                <>
                  <Loader2 size={14} strokeWidth={2} className="run-config-modal__spinner" />
                  Starting…
                </>
              ) : (
                <>
                  <Play size={13} strokeWidth={2} />
                  {wasRunBefore ? "Re-run pipeline" : "Run pipeline"} →
                </>
              )}
            </button>
          </div>
        </footer>
      </motion.div>
    </motion.div>
  );
}

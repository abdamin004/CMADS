import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Play, Settings2, X } from "lucide-react";
import { AdvancedSettings, buildPrecisionRows } from "./runtime/AdvancedSettings";
import type { AdvancedSettingsValue } from "./runtime/AdvancedSettings";
import { getModelPresets, getStatsOverview, startTestRun } from "../api";
import type { ModelPreset, RankBucket, TestPatientSummary } from "../types";

interface Props {
  /** The patient to run. Used for header copy and the API call (the
   *  Tester startTestRun path). When `onConfirm` is provided the modal
   *  becomes a pure preset+top-K picker and the Tester path is bypassed
   *  — the parent owns dispatch. */
  patient:  TestPatientSummary;
  /** Closes the modal without running. */
  onClose:  () => void;
  /** Fires once the run has been dispatched server-side via the Tester
   *  path. Not called when `onConfirm` is set. */
  onStarted: (taskId: string) => void;
  /** When set, the Run button calls this with the chosen preset + top-K
   *  instead of firing startTestRun. Used by the runtime detail page so
   *  re-runs go through RuntimeMode.handleRun (which owns the SSE
   *  subscription, the result view, etc.). */
  onConfirm?: (preset: ModelPreset, topK: number) => void;
}

/**
 * Run / Re-run config modal.
 * Wraps the standard AdvancedSettings panel so a user can pick model preset,
 * top-K, and accuracy mode before firing startTestRun.  The previous
 * implementation called startTestRun directly from the row button, which
 * fired the request with default settings and offered no visible feedback
 * before the parent dismissed the journey.
 */
export function TestRunConfigModal({ patient, onClose, onStarted, onConfirm }: Props) {
  // Local preset list (only needed when onConfirm is set — we need to
  // resolve the picked preset id back into a ModelPreset object). For
  // the legacy Tester path we don't need this; startTestRun takes the
  // preset id directly.
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  useEffect(() => {
    if (!onConfirm) return;
    let cancelled = false;
    getModelPresets()
      .then((list) => { if (!cancelled) setPresets(list); })
      .catch(() => { /* graceful: error surfaced when user tries to run */ });
    return () => { cancelled = true; };
  }, [onConfirm]);
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
    // onConfirm path: pure preset+top-K picker. Resolve the selected
    // preset id (or the configured default) back into a ModelPreset
    // object and hand off to the parent.
    if (onConfirm) {
      const usable = presets.filter((p) => p.available !== false);
      const chosen = usable.find((p) => p.id === adv.presetId)
                  ?? usable.find((p) => p.default)
                  ?? usable[0];
      if (!chosen) {
        setError("No usable model presets are available.");
        return;
      }
      onConfirm(chosen, adv.topK);
      return;
    }
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

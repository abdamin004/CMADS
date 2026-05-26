import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, ArrowLeft, ClipboardList, Cloud, HardDrive, Home, RotateCw } from "lucide-react";
import { getModelPresets, getPatientCase, getTestPatientAsCase, getResult, getRun, openRunArchive, startRun, subscribeRun, type CaseBundle } from "../api";
import type { ModelPreset, PatientResult, RunTask } from "../types";
import { ModeSwitcher } from "./ModeSwitcher";
import { RuntimeHero } from "./RuntimeHero";
import { RuntimePastRuns } from "./RuntimePastRuns";
import { RuntimePatientDetail } from "./RuntimePatientDetail";
import { RuntimeResultView } from "./RuntimeResultView";
import { RuntimeRunningView } from "./RuntimeRunningView";
import { useUrlState } from "../useUrlState";
import {
  getRuntimeTask, setRuntimeTask,
  getViewIntent,  setViewIntent,
} from "../lib/runtimeHandoff";
import type { Mode } from "../useMode";

type Props = {
  mode: Mode;
  onModeChange: (next: Mode) => void;
  onHome: () => void;
};

type Phase = "idle" | "past-runs" | "patient-detail" | "running" | "completed" | "error" | "cancelled";

// Persistence of the active task across mode switches / home navigations
// lives in lib/runtimeHandoff so other surfaces (the Researcher My-test-
// patients list) can also push a task into this view.

/**
 * Fetch the CaseBundle appropriate for the task's result-set.
 * Tester runs store results in "mas_results_test" and their patient UUID is a
 * synthetic `ttest-…` id that doesn't exist in the Gold patient_cases
 * directory — so we reconstruct the bundle from the TestPatient document
 * instead of calling the normal /api/patients/{uuid}/case endpoint.
 */
function fetchCaseFor(t: RunTask): Promise<CaseBundle> {
  if (t.resultSet === "mas_results_test") {
    return getTestPatientAsCase(t.patientUuid);
  }
  return getPatientCase(t.patientUuid);
}

/**
 * Doctor runtime workspace — pure single-run flow.
 *
 *   idle      → RuntimeHero (UUID input + model selector)
 *   running   → Live agent flow streaming via SSE
 *   completed → RuntimeResultView (differential first, treatment, then "dive in")
 *
 * No sidebar. No patient browser. No prior-run history. The clinician's
 * mental model is "this patient, now". Past runs live in the Researcher
 * workspace if needed.
 */
export function RuntimeMode({ mode, onModeChange, onHome }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [task, setTask] = useState<RunTask | null>(null);
  const [result, setResult] = useState<PatientResult | undefined>();
  const [caseBundle, setCaseBundle] = useState<CaseBundle | undefined>();
  const [activeAgentId, setActiveAgentId] = useState<string>("ehr_analyst");
  const [error, setError] = useState<string | null>(null);
  // Remember the last Known-patient run params so the error screen can offer
  // "Try this patient again" without forcing the doctor to re-type the UUID.
  // Tester runs aren't retryable here (they're owned by TesterJourney's own
  // run-start callback), so this stays null for those.
  const lastRunRef = useRef<{ uuid: string; preset: ModelPreset; topK: number } | null>(null);
  // Cached default preset for the Past-Runs view's Run buttons. Pulled
  // from the same /api/model-presets endpoint the hero uses; we keep one
  // copy at this level so both surfaces stay in sync.
  const [defaultPreset, setDefaultPreset] = useState<ModelPreset | undefined>(undefined);
  // Patient whose detail page is currently showing. Mirrored into the
  // URL (`?p=<uuid>`) so the page is deep-linkable; useUrlState handles
  // browser back/forward.
  const [patientParam, setPatientParam] = useUrlState("p", "");
  const detailPatientUuid: string | null = patientParam ? patientParam : null;
  function openPatient(uuid: string) {
    setPatientParam(uuid);
    setPhase("patient-detail");
  }
  function closePatient() {
    setPatientParam("");
    setPhase("past-runs");
  }
  useEffect(() => {
    getModelPresets().then((list) => {
      const usable = list.filter((p) => p.available !== false);
      setDefaultPreset(usable.find((p) => p.default) ?? usable[0]);
    }).catch(() => { /* hero still works; Past Runs falls back gracefully */ });
  }, []);

  // Reset to the hero.
  const reset = useCallback(() => {
    setPhase("idle");
    setTask(null);
    setResult(undefined);
    setCaseBundle(undefined);
    setActiveAgentId("ehr_analyst");
    setError(null);
    setRuntimeTask(null);
    // Also clear any pending view-intent — Back from a past-run view should
    // land at the hero, not re-load the same result on the next mount.
    setViewIntent(null);
  }, []);

  // Kick off a run.
  const handleRun = useCallback(async (
    uuid: string,
    preset: ModelPreset,
    topK: number,
  ) => {
    setError(null);
    setResult(undefined);
    setCaseBundle(undefined);
    setActiveAgentId("ehr_analyst");
    setPhase("running");
    lastRunRef.current = { uuid, preset, topK };
    // Fetch the patient case immediately so the doctor can see the data
    // the system is reading while the run is in progress.
    // `uuid` here is always a Gold-layer UUID from the Known-patient flow.
    void getPatientCase(uuid)
      .then((bundle) => setCaseBundle(bundle))
      .catch(() => { /* non-fatal — the running view simply omits the data panel */ });
    try {
      const fresh = await startRun(uuid, { presetId: preset.id, topK });
      setTask(fresh);
      setRuntimeTask(fresh.taskId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase("error");
    }
  }, []);

  // Retry the last Known-patient run. Returns false when no run is on record
  // (e.g. error happened before lastRunRef was populated, or this was a
  // Tester-launched run) so the UI can hide the Retry CTA.
  const handleRetry = useCallback(() => {
    const last = lastRunRef.current;
    if (!last) return false;
    void handleRun(last.uuid, last.preset, last.topK);
    return true;
  }, [handleRun]);

  // On mount: hydrate state from one of two sources, in priority order:
  //
  //   1. A view-intent stashed by another surface (handoffToRuntimeView from
  //      the past-patients list) — load the completed result directly via
  //      getResult and jump straight to phase="completed" with a synthetic
  //      task. Used to *view* a past run without re-running it.
  //
  //   2. A previously-started task (stashed by handleRun above OR by
  //      handoffToRuntimeRun from the past-patients list when a re-run was
  //      kicked off) — fetch the task, subscribe to SSE if still in flight,
  //      otherwise jump to completed/error/cancelled.
  //
  // The view-intent takes priority because the user explicitly asked to view
  // a specific past run; any stale task in storage shouldn't override that.
  useEffect(() => {
    const intent = getViewIntent();
    if (intent) {
      // Don't clear the intent yet — React StrictMode mounts twice in dev,
      // and the first throwaway mount's setState gets discarded. We clear
      // only AFTER the result has been set, so the second (real) mount can
      // re-read the intent and re-fetch if the first effect was aborted.
      let cancelled = false;
      (async () => {
        try {
          const detail = await getResult(intent.resultSet, intent.patientUuid);
          if (cancelled) return;
          setResult(detail);
          // Synthesize a minimal task for downstream components that read
          // task.resultSet / task.patientUuid (e.g. the model pill in the
          // ribbon, the chart fetch path).
          setTask({
            taskId:      `view-${intent.patientUuid}`,
            patientUuid: intent.patientUuid,
            status:      "completed",
            resultSet:   intent.resultSet,
            agents:      detail.agents ?? [],
            agentNarratives: detail.agentNarratives ?? {},
          });
          setPhase("completed");
          // Now safe to clear — the next mount (e.g. user clicks Home and
          // re-enters Runtime) won't re-trigger the load.
          setViewIntent(null);
        } catch (err) {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Couldn't load that past run.");
            setPhase("error");
            setViewIntent(null);
          }
        }
      })();
      return () => { cancelled = true; };
    }

    const tid = getRuntimeTask();
    if (!tid) return;
    let cancelled = false;
    (async () => {
      try {
        const t = await getRun(tid);
        if (cancelled) return;
        setTask(t);
        void fetchCaseFor(t).then((b) => !cancelled && setCaseBundle(b)).catch(() => {});
        if (t.status === "running" || t.status === "queued") {
          setPhase("running");
        } else if (t.status === "cancelled") {
          // Show the cancelled banner inline in the running view.
          setPhase("running");
        } else if (t.status === "completed") {
          try {
            const detail = await getResult(t.resultSet, t.patientUuid);
            if (!cancelled) {
              setResult(detail);
              setPhase("completed");
            }
          } catch { /* fall through to idle */ }
        } else if (t.status === "error") {
          if (!cancelled) {
            setError(t.error || "Pipeline failed");
            setPhase("error");
          }
        }
      } catch {
        // Task expired on the backend (server restarted, etc.) — wipe.
        setRuntimeTask(null);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Subscribe to SSE while running.
  useEffect(() => {
    if (!task || (task.status !== "queued" && task.status !== "running")) return;
    return subscribeRun(
      task.taskId,
      (incoming) => {
        setTask(incoming);
        // Don't auto-switch the inspector to the evaluator — it's hidden
        // from the doctor view by design.
        if (incoming.activeAgentId && incoming.activeAgentId !== "evaluation") {
          setActiveAgentId(incoming.activeAgentId);
        }
        if (incoming.status === "completed") {
          void (async () => {
            try {
              const detail = await getResult(incoming.resultSet, incoming.patientUuid);
              setResult(detail);
              setPhase("completed");
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
              setPhase("error");
            }
          })();
        }
        if (incoming.status === "error") {
          setError(incoming.error || "Pipeline failed");
          setPhase("error");
        }
        if (incoming.status === "cancelled") {
          // Stay on "running" phase so the RuntimeRunningView can render
          // the cancelled banner inline — the view already handles this
          // via task.status === "cancelled".  No phase flip needed.
        }
      },
      (msg) => {
        setError(msg);
        setPhase("error");
      },
    );
  }, [task?.taskId, task?.status]);

  // View a saved past run without re-firing the pipeline. Loads either
  // the live mas_results_runtime/<uuid> bundle, or — when archiveId is
  // set — the snapshot under <uuid>/_history/<archiveId>/ that was
  // captured before a previous re-run overwrote the live files. Same
  // result-view shape either way.
  const viewPast = useCallback(async (uuid: string, archiveId?: string) => {
    setError(null);
    setResult(undefined);
    setCaseBundle(undefined);
    setActiveAgentId("ehr_analyst");
    setPhase("running");  // brief "loading" — RuntimeRunningView with no task → empty
    try {
      const detail = archiveId
        ? await openRunArchive(uuid, archiveId)
        : await getResult("mas_results_runtime", uuid);
      setResult(detail);
      setTask({
        taskId:          archiveId ? `view-${uuid}-${archiveId}` : `view-${uuid}`,
        patientUuid:     uuid,
        status:          "completed",
        resultSet:       "mas_results_runtime",
        agents:          detail.agents ?? [],
        agentNarratives: detail.agentNarratives ?? {},
      });
      setPhase("completed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load that run.");
      setPhase("error");
    }
  }, []);

  // Doctor view hides the LLM Evaluator agent — it compares against the
  // hidden ground truth and isn't part of the clinical narrative. The
  // evaluator still runs in the pipeline (its verdict gates the treatment
  // plan), it's just not surfaced in the doctor's agent flow.
  const workflowAgents = (task?.agents ?? []).filter((a) => a.id !== "evaluation");
  const safeActiveId = activeAgentId === "evaluation" ? "ehr_analyst" : activeAgentId;
  const selectedAgent = workflowAgents.find((a) => a.id === safeActiveId);
  const selectedNarrative = task?.agentNarratives?.[safeActiveId];

  return (
    <div className="runtime-shell">
      <div className="mode-ribbon mode-ribbon--runtime">
        <button type="button" className="mode-ribbon__brand mode-ribbon__brand--button" onClick={onHome} title="Back to home">
          <Home size={15} strokeWidth={1.7} />
          <strong>Your assistant</strong>
        </button>
        <div className="mode-ribbon__trust">
          {task?.modelOverride?.label ? (
            <span className="runtime-shell__model-pill">
              {task.modelOverride.location === "local" ? (
                <HardDrive size={12} strokeWidth={1.8} />
              ) : (
                <Cloud size={12} strokeWidth={1.8} />
              )}
              {task.modelOverride.label}
              <span className="mono runtime-shell__model-vendor">· {task.modelOverride.vendor}</span>
            </span>
          ) : null}
        </div>
        <button
          type="button"
          className={`runtime-shell__past-link${phase === "past-runs" ? " is-active" : ""}`}
          onClick={() => {
            // Toggling the ribbon button also clears any per-patient
            // URL state so the user lands on a clean dashboard, not
            // straight back into a stale detail page.
            setPatientParam("");
            setPhase(phase === "past-runs" ? "idle" : "past-runs");
          }}
          title="Past runs you have launched + verified patients to try"
        >
          <ClipboardList size={13} strokeWidth={1.8} />
          Past runs
        </button>
        <ModeSwitcher mode={mode} onChange={onModeChange} />
      </div>

      <main className="runtime-shell__main">
        {phase === "idle" ? <RuntimeHero onRun={handleRun} /> : null}

        {phase === "past-runs" ? (
          <RuntimePastRuns
            onOpenPatient={openPatient}
            onRun={handleRun}
            onBack={reset}
            defaultPreset={defaultPreset}
            defaultTopK={3}
          />
        ) : null}

        {phase === "patient-detail" && detailPatientUuid ? (
          <RuntimePatientDetail
            patientUuid={detailPatientUuid}
            onBack={closePatient}
            onRun={handleRun}
            defaultPreset={defaultPreset}
            defaultTopK={3}
          />
        ) : null}

        {phase === "running" ? (
          <RuntimeRunningView
            task={task}
            workflowAgents={workflowAgents}
            selectedAgent={selectedAgent}
            selectedNarrative={selectedNarrative}
            activeAgentId={safeActiveId}
            onSelectAgent={setActiveAgentId}
            caseBundle={caseBundle}
            onReset={reset}
          />
        ) : null}

        {phase === "completed" && result ? (
          <RuntimeResultView result={result} onReset={reset} />
        ) : null}

        {phase === "error" ? (
          <motion.section
            className="panel runtime-shell__error"
            role="alert"
            aria-live="assertive"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="runtime-shell__error-head">
              <AlertCircle size={20} strokeWidth={1.7} aria-hidden />
              <h2>The pipeline didn't finish</h2>
            </div>
            <p className="runtime-shell__error-body">
              {error ?? "Something went wrong before this run could complete."}
              {task?.patientUuid ? (
                <>
                  {" "}
                  <span className="mono runtime-shell__error-uuid">
                    Patient {task.patientUuid.slice(0, 8)}…
                  </span>
                </>
              ) : null}
            </p>
            <p className="runtime-shell__error-hint">
              Transient failures (model timeouts, network blips) usually clear on a second attempt.
              If it keeps failing, try a smaller model preset or a different patient.
            </p>
            <div className="runtime-shell__error-actions">
              {lastRunRef.current ? (
                <button
                  type="button"
                  className="runtime-solo__cta runtime-shell__error-cta--primary"
                  onClick={handleRetry}
                  autoFocus
                >
                  <RotateCw size={14} strokeWidth={1.8} aria-hidden />
                  Try this patient again
                </button>
              ) : null}
              <button
                type="button"
                className="runtime-shell__error-cta--secondary"
                onClick={reset}
              >
                <ArrowLeft size={14} strokeWidth={1.8} aria-hidden />
                Back to start
              </button>
            </div>
          </motion.section>
        ) : null}
      </main>
    </div>
  );
}


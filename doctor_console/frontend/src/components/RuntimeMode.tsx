import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Cloud, FlaskConical, HardDrive, Home } from "lucide-react";
import { getPatientCase, getTestPatientAsCase, getResult, getRun, listTestPatients, startRun, subscribeRun, type CaseBundle } from "../api";
import type { ModelPreset, PatientResult, RunTask } from "../types";
import { ModeSwitcher } from "./ModeSwitcher";
import { RuntimeHero } from "./RuntimeHero";
import { RuntimeResultView } from "./RuntimeResultView";
import { RuntimeRunningView } from "./RuntimeRunningView";
import { TesterJourney } from "./TesterJourney";
import type { Mode } from "../useMode";

type DoctorTab = "known" | "build";
type TesterView = "splash" | "picker" | "editor" | "my-tests";

type Props = {
  mode: Mode;
  onModeChange: (next: Mode) => void;
  onHome: () => void;
};

type Phase = "idle" | "running" | "completed" | "error";

// Persist the active task across mode switches / home navigations so the
// doctor can pop back into the runtime view and find the run still running
// (or its completed result).
const RUN_STORAGE_KEY = "cmads.runtime.activeTaskId";
function storedTaskId(): string | null {
  try { return window.localStorage.getItem(RUN_STORAGE_KEY); }
  catch { return null; }
}
function setStoredTaskId(taskId: string | null) {
  try {
    if (taskId) window.localStorage.setItem(RUN_STORAGE_KEY, taskId);
    else        window.localStorage.removeItem(RUN_STORAGE_KEY);
  } catch { /* ignore */ }
}

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

  // Doctor landing tab: "Known patient" (UUID flow) vs "Build / clone" (Tester body)
  const [doctorTab, setDoctorTab] = useState<DoctorTab>("known");
  // Pass-through initial view request into the embedded TesterJourney sub-router.
  // testerViewKey increments each time we want TesterJourney to re-apply the view
  // even if the view name didn't change (e.g. clicking "My test patients" twice).
  const [testerView, setTesterView] = useState<TesterView | undefined>(undefined);
  const [testerViewKey, setTesterViewKey] = useState(0);
  // Test patient count shown in the Doctor header link
  const [testCount, setTestCount] = useState(0);

  // Refresh test-patient count when landing tab is shown, and on initial mount.
  useEffect(() => {
    listTestPatients().then(rs => setTestCount(rs.length)).catch(() => {});
  }, [doctorTab]);

  // Reset to the hero.
  const reset = useCallback(() => {
    setPhase("idle");
    setTask(null);
    setResult(undefined);
    setCaseBundle(undefined);
    setActiveAgentId("ehr_analyst");
    setError(null);
    setStoredTaskId(null);
    setDoctorTab("known");
    setTesterView(undefined);
    setTesterViewKey(0);
  }, []);

  // Called by the embedded Tester body when it starts a run.
  // We're already in mode=runtime, so no setMode call needed.
  const handleTesterRunStarted = useCallback((taskId: string) => {
    setStoredTaskId(taskId);
    // Trigger the mount-effect path: set the stored key, then force a
    // re-read by bumping the task via getRun.
    (async () => {
      try {
        const t = await getRun(taskId);
        setTask(t);
        void fetchCaseFor(t).then((b) => setCaseBundle(b)).catch(() => {});
        if (t.status === "running" || t.status === "queued") {
          setPhase("running");
        } else if (t.status === "completed") {
          try {
            const detail = await getResult(t.resultSet, t.patientUuid);
            setResult(detail);
            setPhase("completed");
          } catch { /* fall through */ }
        } else if (t.status === "error") {
          setError(t.error || "Pipeline failed");
          setPhase("error");
        }
      } catch {
        setError("Could not load test run");
        setPhase("error");
      }
    })();
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
    // Fetch the patient case immediately so the doctor can see the data
    // the system is reading while the run is in progress.
    // `uuid` here is always a Gold-layer UUID from the Known-patient flow.
    void getPatientCase(uuid)
      .then((bundle) => setCaseBundle(bundle))
      .catch(() => { /* non-fatal — the running view simply omits the data panel */ });
    try {
      const fresh = await startRun(uuid, { presetId: preset.id, topK });
      setTask(fresh);
      setStoredTaskId(fresh.taskId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase("error");
    }
  }, []);

  // On mount: if we left a previous run in flight (or completed and didn't
  // reset), restore it so the doctor sees the same state when they return.
  useEffect(() => {
    const tid = storedTaskId();
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
        setStoredTaskId(null);
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
      },
      (msg) => {
        setError(msg);
        setPhase("error");
      },
    );
  }, [task?.taskId, task?.status]);

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
          {/* My test patients link — only shown on the idle landing */}
          {phase === "idle" && (
            <button
              type="button"
              className="doctor-header__test-link mono"
              onClick={() => {
                setDoctorTab("build");
                setTesterView("my-tests");
                setTesterViewKey((k) => k + 1);
              }}
            >
              <FlaskConical size={13} strokeWidth={1.7} />
              My test patients
              {testCount > 0 && <span className="doctor-header__test-badge">{testCount}</span>}
            </button>
          )}
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
        <ModeSwitcher mode={mode} onChange={onModeChange} />
      </div>

      <main className={`runtime-shell__main${phase === "idle" && doctorTab === "build" ? " runtime-shell__main--build" : ""}`}>
        {phase === "idle" ? (
          <>
            {/* Header narrative + segmented control woven together */}
            <div className="doctor-tab__bar">
              <div className="doctor-tab__narrative">
                <span className="doctor-tab__narrative-prefix">a second opinion</span>
                {doctorTab === "known" ? (
                  <span className="doctor-tab__narrative-suffix">with a known patient</span>
                ) : (
                  <span className="doctor-tab__narrative-suffix">with a patient you build</span>
                )}
              </div>
              <div className="doctor-tab__tabs">
                <button
                  type="button"
                  className={`doctor-tab__btn${doctorTab === "known" ? " is-active" : ""}`}
                  onClick={() => setDoctorTab("known")}
                >
                  Known patient
                </button>
                <button
                  type="button"
                  className={`doctor-tab__btn${doctorTab === "build" ? " is-active" : ""}`}
                  onClick={() => setDoctorTab("build")}
                >
                  Build / clone a patient
                </button>
              </div>
            </div>

            {doctorTab === "known" ? (
              <RuntimeHero onRun={handleRun} />
            ) : (
              <div className="doctor-tab__body">
                <TesterJourney
                  key={testerViewKey}
                  chrome="inline"
                  initialView={testerView}
                  onBack={() => setDoctorTab("known")}
                  onRunStarted={handleTesterRunStarted}
                />
              </div>
            )}
          </>
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
          />
        ) : null}

        {phase === "completed" && result ? (
          <RuntimeResultView result={result} onReset={reset} />
        ) : null}

        {phase === "error" ? (
          <motion.section
            className="panel runtime-shell__error"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="runtime-shell__error-head">
              <AlertCircle size={20} strokeWidth={1.7} />
              <h2>The pipeline failed for this run</h2>
            </div>
            <p>{error ?? "An unexpected error occurred."}</p>
            <button type="button" className="runtime-solo__cta" onClick={reset}>
              Try another patient
            </button>
          </motion.section>
        ) : null}
      </main>
    </div>
  );
}


import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowLeft, PanelLeftOpen, RotateCw } from "lucide-react";
import { getPatients, getResult, getResultSets, startRun, subscribeRun } from "../api";
import { TesterJourney } from "./TesterJourney";
import type { AgentCard, PatientListItem, PatientResult, ResultSet, RunTask } from "../types";
import { AgentFlow } from "./AgentFlow";
import { AgentInspector } from "./AgentInspector";
import { AgentsBoard } from "./AgentsBoard";
import { DashboardHero } from "./DashboardHero";
import { Disclosure } from "./Disclosure";
import { PatientBrowser } from "./PatientBrowser";
import { PatientDetailTabs, type TabDef } from "./PatientDetailTabs";
import { DataStructureExplainer, PatientEvidence } from "./PatientEvidence";
import { RawDataPanel } from "./RawDataPanel";
import { ResultsPanel } from "./ResultsPanel";
import { RunTimeline } from "./RunTimeline";
import { SimilarCases } from "./SimilarCases";
import { TreatmentReview } from "./TreatmentReview";
import { useUrlState } from "../useUrlState";

type Props = {
  /**
   * "researcher" hides the live-run button and reads from the canonical
   * research cohorts (mas_results, mas_results_improved_*, …).
   * "runtime" exposes the run button and defaults to the live cohort.
   */
  mode?: "researcher" | "runtime";
  /** Pre-selected result set (e.g. "mas_results_runtime" for Doctor runs). */
  defaultResultSet?: string;
  /** Optional ribbon at the top, used by Researcher mode for the tab strip. */
  ribbon?: React.ReactNode;
  /**
   * Custom landing hero shown when no patient is selected. If omitted, the
   * existing DashboardHero + AgentsBoard render. RuntimeMode passes the
   * <RuntimeHero> (UUID input + recent live runs) here.
   */
  landingHero?: (args: {
    patients: PatientListItem[];
    onRun: (uuid: string) => void;
    onOpenPatient: (uuid: string) => void;
  }) => React.ReactNode;
};

/**
 * Patient-by-patient drill-down view. Hosts the existing sidebar list +
 * detail tabs + agent inspector. Used as the "Patients" tab in Researcher
 * mode and as the post-run review surface in Runtime mode.
 *
 * Faithful extraction of the original App.tsx body — same URL keys (?p, ?a),
 * same loading cascade, same component composition.
 */
export function PatientExplorer({ mode = "researcher", defaultResultSet, ribbon, landingHero }: Props) {
  const [resultSets, setResultSets] = useState<ResultSet[]>([]);
  const [resultSetId, setResultSetId] = useUrlState("r", "");
  const [selectedUuidUrl, setSelectedUuidUrl] = useUrlState("p", "");
  const selectedUuid: string | undefined = selectedUuidUrl || undefined;
  const setSelectedUuid = (uuid: string | undefined) => setSelectedUuidUrl(uuid ?? "");
  const [selectedAgentId, setSelectedAgentId] = useUrlState("a", "final_diagnosis");
  const [patients, setPatients] = useState<PatientListItem[]>([]);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<PatientResult>();
  const [runTask, setRunTask] = useState<RunTask | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // URL-backed view state for the Researcher Patients tab. Set by the
  // dropdown in the Researcher menubar (see ResearcherMode.tsx). Defaults
  // to "explore" so deep-links with no view param still land on the
  // cohort roster.
  //   "explore"   → cohort browser (sidebar + detail)
  //   "create"    → TesterJourney splash → editor (cohort clone or scratch)
  //   "my-tests"  → TesterJourney "my-tests" sub-view (past custom runs)
  const [viewUrl, setViewUrl] = useUrlState("view", "");
  const view: "explore" | "create" | "my-tests" = (() => {
    if (viewUrl === "create") return "create";
    if (viewUrl === "my-tests") return "my-tests";
    return "explore";
  })();
  const [loadingSets, setLoadingSets] = useState(true);
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [loadingResult, setLoadingResult] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSets = useCallback(async () => {
    setLoadingSets(true);
    setError(null);
    try {
      const sets = await getResultSets({ includeRuntime: mode === "runtime" });
      setResultSets(sets);
      if (!resultSetId) {
        const fallback = defaultResultSet
          ?? (mode === "runtime" ? "mas_results_runtime" : "multi_level");
        setResultSetId(fallback);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingSets(false);
    }
  }, [resultSetId, mode, defaultResultSet]);

  const loadPatients = useCallback(async () => {
    if (!resultSetId) return;
    setLoadingPatients(true);
    setError(null);
    try {
      const rows = await getPatients(resultSetId, query);
      setPatients(rows);
      if (selectedUuid && !rows.some((row) => row.uuid === selectedUuid)) {
        const firstWithRun = rows.find((row) => row.hasRun) ?? rows[0];
        setSelectedUuid(firstWithRun?.uuid);
      }
    } catch (err) {
      setError(errorMessage(err));
      setPatients([]);
    } finally {
      setLoadingPatients(false);
    }
  }, [query, resultSetId, selectedUuid]);

  const loadResult = useCallback(async () => {
    if (!resultSetId || !selectedUuid) {
      setResult(undefined);
      return;
    }
    setLoadingResult(true);
    setError(null);
    try {
      const detail = await getResult(resultSetId, selectedUuid);
      setResult(detail);
      if (!detail.agents.some((agent) => agent.id === selectedAgentId)) {
        setSelectedAgentId("final_diagnosis");
      }
    } catch (err) {
      setResult(undefined);
      setError(errorMessage(err));
    } finally {
      setLoadingResult(false);
    }
  }, [resultSetId, selectedAgentId, selectedUuid]);

  useEffect(() => { void loadSets(); }, [loadSets]);
  useEffect(() => { void loadPatients(); }, [loadPatients]);
  useEffect(() => { void loadResult(); }, [loadResult]);

  useEffect(() => {
    if (!runTask || (runTask.status !== "queued" && runTask.status !== "running")) return;
    return subscribeRun(
      runTask.taskId,
      (task) => {
        setRunTask(task);
        if (task.activeAgentId) {
          setSelectedAgentId(task.activeAgentId);
        }
        if (task.status === "completed") {
          void handleCompletedRun(task);
        }
      },
      setError
    );
  }, [runTask?.taskId, runTask?.status]);

  const workflowAgents = useMemo(() => {
    if (runTask?.agents?.length && runTask.status !== "completed") return runTask.agents;
    return result?.agents ?? runTask?.agents ?? [];
  }, [result, runTask]);

  const selectedAgent: AgentCard | undefined = useMemo(
    () => workflowAgents.find((agent) => agent.id === selectedAgentId),
    [selectedAgentId, workflowAgents]
  );

  const isLiveRunActive =
    !!runTask && (runTask.status === "running" || runTask.status === "queued");

  const selectAgentAndScroll = useCallback((agentId: string) => {
    setSelectedAgentId(agentId);
    requestAnimationFrame(() => {
      const el = document.querySelector(".agent-inspector");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);
  const selectedNarrative = isLiveRunActive
    ? runTask?.agentNarratives?.[selectedAgentId]
    : runTask?.agentNarratives?.[selectedAgentId] ??
      result?.agentNarratives?.[selectedAgentId];

  async function handleRun(targetUuid?: string) {
    const uuid = targetUuid ?? selectedUuid;
    if (!uuid) return;
    setError(null);
    setSelectedAgentId("ehr_analyst");
    setResult(undefined);
    if (targetUuid && targetUuid !== selectedUuid) {
      setSelectedUuid(targetUuid);
    }
    try {
      const task = await startRun(uuid);
      setRunTask(task);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleCompletedRun(task: RunTask) {
    try {
      setResultSetId(task.resultSet);
      setSelectedUuid(task.patientUuid);
      const detail = await getResult(task.resultSet, task.patientUuid);
      setResult(detail);
      setSelectedAgentId("final_diagnosis");
      const rows = await getPatients(task.resultSet, query);
      setPatients(rows);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  // Sidebar visibility: only mount the cohort browser when the user is
  // actually exploring. On the landing chooser and inside the create
  // sub-flow it would either be empty (create) or visually conflict with
  // the two-card chooser (landing).
  const showSidebar = view === "explore";

  return (
    <div className="patient-explorer-frame">
      {ribbon}
      <div className={`app-shell${showSidebar && sidebarCollapsed ? " sidebar-is-collapsed" : ""}${showSidebar ? "" : " app-shell--no-sidebar"}`}>
      {showSidebar ? (
        <PatientBrowser
          patients={patients}
          selectedUuid={selectedUuid}
          query={query}
          loading={loadingPatients || loadingSets}
          runTask={runTask}
          collapsed={sidebarCollapsed}
          onCollapseChange={setSidebarCollapsed}
          onGoOverview={() => {
            setSelectedUuid(undefined);
            setSidebarCollapsed(false);
          }}
          onQueryChange={setQuery}
          onSelectPatient={(uuid) => {
            setSelectedUuid(uuid);
            setSelectedAgentId("final_diagnosis");
            setSidebarCollapsed(true);
          }}
          onRefresh={() => {
            void loadSets();
            void loadPatients();
            void loadResult();
          }}
          onRun={mode === "runtime" ? () => void handleRun() : undefined}
        />
      ) : null}

      <main className="workspace">
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
            {showSidebar && sidebarCollapsed ? (
              <button
                className="icon-button icon-button--md"
                type="button"
                onClick={() => setSidebarCollapsed(false)}
                title="Show patient roster"
                aria-label="Show patient roster"
              >
                <PanelLeftOpen size={16} aria-hidden />
              </button>
            ) : null}
            {mode === "researcher" && (view === "create" || view === "my-tests") ? (
              <button
                type="button"
                onClick={() => setViewUrl("")}
                className="patient-explorer__back-link"
                title="Back to the cohort roster"
              >
                <ArrowLeft size={14} strokeWidth={1.8} />
                Back to patients
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setSelectedUuid(undefined)}
                title="Return to overview"
                style={{
                  background: "none", border: "none", padding: 0, margin: 0,
                  textAlign: "left", color: "inherit", cursor: "pointer", font: "inherit",
                }}
              >
                <div className="eyebrow">Clinical Multi-Agent Decisioning</div>
                <h1>
                  {selectedUuid
                    ? "Patient Review"
                    : view === "create"
                    ? "Build a test patient"
                    : view === "my-tests"
                    ? "My test patients"
                    : "Patient explorer"}
                </h1>
              </button>
            )}
          </div>
        </header>

        {error ? (
          <div className="alert alert--with-action" role="alert" aria-live="polite">
            <AlertCircle size={18} aria-hidden />
            <span>{error}</span>
            <button
              type="button"
              className="alert__action"
              onClick={() => {
                // Re-fire all three loaders; whichever was failing will
                // resolve or surface its own fresh error.
                void loadSets();
                void loadPatients();
                void loadResult();
              }}
              disabled={loadingSets || loadingPatients || loadingResult}
            >
              <RotateCw size={13} strokeWidth={1.8} aria-hidden />
              Retry
            </button>
          </div>
        ) : null}

        <RunTimeline task={runTask} />

        {view === "create" || view === "my-tests" ? (
          <div className="patient-explorer__create-shell">
            <TesterJourney
              chrome="inline"
              hideBackLinks
              initialView={view === "my-tests" ? "my-tests" : "splash"}
              onBack={() => setViewUrl("")}
              onRunStarted={() => {
                // The run has been kicked off; return to the cohort
                // roster and refresh the patient list so the new test
                // patient appears once it lands.
                setViewUrl("");
                void loadPatients();
              }}
            />
          </div>
        ) : !selectedUuid ? (
          landingHero ? (
            landingHero({
              patients,
              onRun: (uuid) => void handleRun(uuid),
              onOpenPatient: (uuid) => {
                setSelectedUuid(uuid);
                setSelectedAgentId("final_diagnosis");
              },
            })
          ) : (
            <>
              <DashboardHero />
              <DataStructureExplainer />
              <Disclosure
                title={
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                    <span>Meet the crew that reads each patient</span>
                    <span className="simple-run__dive-tag mono">ADVANCED</span>
                  </span>
                }
                hint="Optional · introduces each of the seven roles in the system, what they do, and how they hand off."
              >
                <AgentsBoard />
              </Disclosure>
            </>
          )
        ) : null}

        {loadingResult ? <div className="loading-bar">Loading clinical run...</div> : null}

        {result && view === "explore" ? (
          <>
            <section className="patient-header panel" data-demo-anchor="patient-header">
              <div>
                <div className="eyebrow mono">{result.patient.uuid}</div>
                <h2>
                  {result.patient.age ?? "?"} year old {result.patient.gender ?? "patient"}
                  {result.patient.race ? `, ${result.patient.race}` : ""}
                </h2>
                <p>Cutoff date: {result.patient.cutoffDate || "not recorded"}</p>
              </div>
              <div className="metric-strip">
                <Metric label="Active conditions" value={result.case.caseStats.activeConditions} />
                <Metric label="Medications" value={result.case.caseStats.activeMedications} />
                <Metric label="Lab trends" value={result.case.caseStats.labTrends} />
                <Metric label="Critical flags" value={result.case.caseStats.criticalFlags} />
              </div>
            </section>

            <PatientDetailTabs
              defaultActive="input"
              tabs={buildPatientTabs({
                result,
                selectedUuid: selectedUuid!,
                resultSetId,
                workflowAgents,
                selectedAgentId,
                selectedAgent,
                selectedNarrative,
                runTask,
                setSelectedAgentId: selectAgentAndScroll,
                setSelectedUuid,
                loadPatients,
                mode,
              })}
            />
          </>
        ) : workflowAgents.length ? (
          <>
            <AgentFlow
              agents={workflowAgents}
              selectedAgentId={selectedAgentId}
              onSelectAgent={selectAgentAndScroll}
              activeAgentId={runTask?.activeAgentId}
            />
            <div className="content-grid single-column">
              <AgentInspector agent={selectedAgent} narrative={selectedNarrative} mode={mode} />
            </div>
          </>
        ) : null}
      </main>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value?: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value ?? 0}</strong>
    </div>
  );
}

function buildPatientTabs(args: {
  result: PatientResult;
  selectedUuid: string;
  resultSetId: string;
  workflowAgents: AgentCard[];
  selectedAgentId: string;
  selectedAgent: AgentCard | undefined;
  selectedNarrative: import("../types").AgentNarrative | undefined;
  runTask: RunTask | null | undefined;
  setSelectedAgentId: (id: string) => void;
  setSelectedUuid: (uuid: string | undefined) => void;
  loadPatients: () => Promise<void> | void;
  mode: "researcher" | "runtime";
}): TabDef[] {
  const {
    result, selectedUuid, resultSetId, workflowAgents,
    selectedAgentId, selectedAgent, selectedNarrative,
    runTask, setSelectedAgentId, setSelectedUuid, mode,
  } = args;

  const evalRecord = (result.evaluation ?? {}) as Record<string, unknown>;
  const matchType = String(evalRecord.match_type ?? "—").toUpperCase();
  const matchedDiagnosis = String(evalRecord.matched_diagnosis ?? "—");
  const primaryDiagnosis = String(
    (result.finalDiagnosis as Record<string, unknown> | undefined)?.primary_diagnosis ?? "Pending",
  );
  const matchRank = String(evalRecord.rank ?? "—");
  const target = String(result.patient.targetCondition ?? evalRecord.target ?? "—");
  const isClickable = matchType === "DIRECT" || matchType === "INDIRECT";

  // Mark unused locals as referenced so the lint pass doesn't complain.
  // (Match metadata is now surfaced in the Differential tab via ResultsPanel.)
  void matchedDiagnosis; void primaryDiagnosis; void matchRank; void target; void isClickable;

  const rawTab: TabDef | null = mode === "researcher"
    ? {
        id: "raw",
        label: "Raw data",
        badge: "RESEARCHER",
        hint: "Every persisted JSON artifact for this run — inputs, agent outputs, evaluation, trace, memory.",
        render: () => <RawDataPanel result={result} />,
      }
    : null;

  return [
    // Tab order matches the doctor console's runtime result view:
    //   Patient data → Differential → Treatment → Similar cases → Reasoning.
    // Researcher mode keeps "Overview" first as the at-a-glance landing.
    {
      id: "input", label: "Patient data",
      hint: "The chart and lab data the system read for this patient.",
      render: () => <PatientEvidence result={result} />,
    },
    {
      id: "differential", label: "Differential",
      hint: "The final ranked top-5 differential after Reviewer-Refiner, judged against the hidden ground truth.",
      render: () => <ResultsPanel result={result} />,
    },
    {
      id: "treatment", label: "Treatment",
      hint: "NICE-guideline plan with assumptions and missing-data warnings (DIRECT matches only).",
      render: () => <TreatmentReview result={result} />,
    },
    {
      id: "similar", label: "Similar cases",
      hint:
        mode === "runtime"
          ? "Past patients with similar presentations — labelled with their confirmed clinical diagnosis."
          : "Top-K Tier-4 case-based memory neighbours — read by the Diagnostic agent at run time as a clinical prior.",
      render: () => (
        <SimilarCases
          patientUuid={selectedUuid}
          resultSet={resultSetId}
          mode={mode}
          onOpenPatient={(uuid) => {
            setSelectedUuid(uuid);
            setSelectedAgentId("final_diagnosis");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      ),
    },
    {
      id: "reasoning", label: "Reasoning",
      badge: "EXPLAINABILITY",
      hint: "Each agent's narrative, in execution order. Click an agent in the workflow to inspect; click a section to expand.",
      render: () =>
        workflowAgents.length ? (
          <>
            <AgentFlow
              agents={workflowAgents}
              selectedAgentId={selectedAgentId}
              onSelectAgent={setSelectedAgentId}
              activeAgentId={runTask?.activeAgentId}
            />
            <div className="content-grid single-column">
              <AgentInspector
                agent={selectedAgent}
                narrative={selectedNarrative}
                mode={mode}
                rawOutput={
                  selectedAgent
                    ? (result.agentOutputs as Record<string, unknown>)?.[selectedAgent.id]
                    : undefined
                }
              />
            </div>
          </>
        ) : (
          <div className="panel"><p>No agent narrative for this patient yet.</p></div>
        ),
    },
    ...(rawTab ? [rawTab] : []),
  ];
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

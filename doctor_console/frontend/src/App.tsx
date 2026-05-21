import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, PanelLeftOpen, RefreshCw } from "lucide-react";
import { getPatients, getResult, getResultSets, startRun, subscribeRun } from "./api";
import type { AgentCard, AgentNarrative, PatientListItem, PatientResult, ResultSet, RunTask } from "./types";
import { AgentFlow } from "./components/AgentFlow";
import { AgentInspector } from "./components/AgentInspector";
import { AnnotationPanel } from "./components/AnnotationPanel";
import { AgentsBoard } from "./components/AgentsBoard";
import { DashboardHero } from "./components/DashboardHero";
import { PatientBrowser } from "./components/PatientBrowser";
import { PatientDetailTabs, type TabDef } from "./components/PatientDetailTabs";
import { PatientEvidence } from "./components/PatientEvidence";
import { ResultsPanel } from "./components/ResultsPanel";
import { RunTimeline } from "./components/RunTimeline";
import { SimilarCases } from "./components/SimilarCases";
import { TreatmentReview } from "./components/TreatmentReview";
import { useUrlState } from "./useUrlState";

export default function App() {
  const [resultSets, setResultSets] = useState<ResultSet[]>([]);
  // URL-driven: ?r=<resultSet>&p=<patientUuid>&a=<agentId>
  // Shareable links survive refresh; back/forward navigates between views.
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
  const [loadingSets, setLoadingSets] = useState(true);
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [loadingResult, setLoadingResult] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSets = useCallback(async () => {
    setLoadingSets(true);
    setError(null);
    try {
      const sets = await getResultSets();
      setResultSets(sets);
      // Default to the virtual "multi_level" aggregator, which unions every
      // multi-level-memory run so the doctor sees all patients the system
      // has actually processed with the 4-tier memory subsystem.
      if (!resultSetId) {
        setResultSetId("multi_level");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingSets(false);
    }
  }, [resultSetId]);

  const loadPatients = useCallback(async () => {
    if (!resultSetId) return;
    setLoadingPatients(true);
    setError(null);
    try {
      const rows = await getPatients(resultSetId, query);
      setPatients(rows);
      // Only auto-fall-back when a previously-selected patient has
      // disappeared from the roster. Leaving selection empty on a fresh
      // visit lets the overview hero render as the landing screen.
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

  useEffect(() => {
    void loadSets();
  }, [loadSets]);

  useEffect(() => {
    void loadPatients();
  }, [loadPatients]);

  useEffect(() => {
    void loadResult();
  }, [loadResult]);

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
  }, [query, runTask?.taskId, runTask?.status]);

  const workflowAgents = useMemo(() => {
    if (runTask?.agents?.length && runTask.status !== "completed") return runTask.agents;
    return result?.agents ?? runTask?.agents ?? [];
  }, [result, runTask]);

  const selectedAgent: AgentCard | undefined = useMemo(
    () => workflowAgents.find((agent) => agent.id === selectedAgentId),
    [selectedAgentId, workflowAgents]
  );

  // During an active live run, never fall back to the previously-loaded
  // result's narratives — a fresh run hasn't produced its narrative yet
  // for an agent that's still working, and we don't want to render the
  // PRIOR patient's stale output in its place.
  const isLiveRunActive =
    !!runTask && (runTask.status === "running" || runTask.status === "queued");
  const selectedNarrative = isLiveRunActive
    ? runTask?.agentNarratives?.[selectedAgentId]
    : runTask?.agentNarratives?.[selectedAgentId] ??
      result?.agentNarratives?.[selectedAgentId];

  async function handleRun() {
    if (!selectedUuid) return;
    setError(null);
    setSelectedAgentId("ehr_analyst");
    setResult(undefined);
    try {
      const task = await startRun(selectedUuid);
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

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-is-collapsed" : ""}`}>
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
        onRun={handleRun}
      />

      <main className="workspace">
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
            {sidebarCollapsed ? (
              <button
                className="icon-button"
                type="button"
                onClick={() => setSidebarCollapsed(false)}
                title="Show patient roster"
                style={{ minHeight: 36, width: 36 }}
              >
                <PanelLeftOpen size={16} />
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setSelectedUuid(undefined)}
              title="Return to overview"
              style={{
                background: "none",
                border: "none",
                padding: 0,
                margin: 0,
                textAlign: "left",
                color: "inherit",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <div className="eyebrow">Clinical Multi-Agent Decisioning</div>
              <h1>{selectedUuid ? "Patient Review" : "Overview"}</h1>
            </button>
          </div>
          <button className="ghost-button" type="button" onClick={() => void loadResult()}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </header>

        {error ? (
          <div className="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        ) : null}

        <RunTimeline task={runTask} />

        {!selectedUuid ? (
          <>
            <DashboardHero />
            <AgentsBoard />
          </>
        ) : null}

        {loadingResult ? <div className="loading-bar">Loading clinical run...</div> : null}

        {result ? (
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
              defaultActive="overview"
              tabs={buildPatientTabs({
                result,
                selectedUuid: selectedUuid!,
                resultSetId,
                workflowAgents,
                selectedAgentId,
                selectedAgent,
                selectedNarrative,
                runTask,
                setSelectedAgentId,
                setSelectedUuid,
                loadPatients,
              })}
            />
          </>
        ) : workflowAgents.length ? (
          <>
            <AgentFlow
              agents={workflowAgents}
              selectedAgentId={selectedAgentId}
              onSelectAgent={setSelectedAgentId}
              activeAgentId={runTask?.activeAgentId}
            />
            <div className="content-grid single-column">
              <AgentInspector agent={selectedAgent} narrative={selectedNarrative} />
            </div>
          </>
        ) : null}
      </main>
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
  selectedNarrative: AgentNarrative | undefined;
  runTask: RunTask | null | undefined;
  setSelectedAgentId: (id: string) => void;
  setSelectedUuid: (uuid: string | undefined) => void;
  loadPatients: () => Promise<void> | void;
}): TabDef[] {
  const {
    result,
    selectedUuid,
    resultSetId,
    workflowAgents,
    selectedAgentId,
    selectedAgent,
    selectedNarrative,
    runTask,
    setSelectedAgentId,
    setSelectedUuid,
    loadPatients,
  } = args;

  const evalRecord = (result.evaluation ?? {}) as Record<string, unknown>;
  const matchType = String(evalRecord.match_type ?? "—");
  const primaryDiagnosis =
    String(
      (result.finalDiagnosis as Record<string, unknown> | undefined)?.primary_diagnosis ??
        evalRecord.matched_diagnosis ??
        "Pending",
    );
  const target =
    String(result.patient.targetCondition ?? evalRecord.target ?? "—");

  return [
    {
      id: "overview",
      label: "Overview",
      hint: "At-a-glance: match outcome, primary diagnosis, and what to look at next.",
      render: () => (
        <section className="panel patient-overview">
          <div className="overview-grid">
            <div className={`overview-card overview-card--match match-${matchType.toLowerCase()}`}>
              <span className="overview-eyebrow">Match outcome</span>
              <strong>{matchType}</strong>
              <span className="overview-meta">
                Ground truth: <em>{target}</em>
              </span>
            </div>
            <div className="overview-card">
              <span className="overview-eyebrow">Primary diagnosis (final)</span>
              <strong className="overview-diagnosis">{primaryDiagnosis}</strong>
              <span className="overview-meta">
                Rank{" "}
                <em>{String(evalRecord.rank ?? "—")}</em> in the differential
              </span>
            </div>
            <div className="overview-card">
              <span className="overview-eyebrow">Where to look next</span>
              <ul className="overview-jumps">
                <li>
                  <strong>Input</strong> — the EHR + Lab data the agents see
                </li>
                <li>
                  <strong>Reasoning</strong> — agent-by-agent narrative
                </li>
                <li>
                  <strong>Differential</strong> — ranked top-5 final diagnoses
                </li>
                <li>
                  <strong>Treatment</strong> — NICE-guideline plan when DIRECT
                </li>
              </ul>
            </div>
          </div>
        </section>
      ),
    },
    {
      id: "input",
      label: "Input",
      hint: "Exactly the structured data the multi-agent pipeline receives.",
      render: () => <PatientEvidence result={result} />,
    },
    {
      id: "reasoning",
      label: "Reasoning",
      badge: workflowAgents.length || undefined,
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
              <AgentInspector agent={selectedAgent} narrative={selectedNarrative} />
            </div>
          </>
        ) : (
          <div className="panel"><p>No agent narrative for this patient yet.</p></div>
        ),
    },
    {
      id: "differential",
      label: "Differential",
      hint: "The final ranked top-5 differential after Reviewer-Refiner, judged against the hidden ground truth.",
      render: () => <ResultsPanel result={result} />,
    },
    {
      id: "treatment",
      label: "Treatment",
      hint: "NICE-guideline plan with assumptions and missing-data warnings (DIRECT matches only).",
      render: () => <TreatmentReview result={result} />,
    },
    {
      id: "review",
      label: "Review",
      hint: "Your verdict on this run — agree, uncertain, or disagree. Persisted.",
      render: () => (
        <AnnotationPanel
          patientUuid={selectedUuid}
          onChange={() => { void loadPatients(); }}
        />
      ),
    },
    {
      id: "similar",
      label: "Similar cases",
      hint: "Top-K Tier-4 neighbours from case-based memory. One click opens that patient.",
      render: () => (
        <SimilarCases
          patientUuid={selectedUuid}
          resultSet={resultSetId}
          onOpenPatient={(uuid) => {
            setSelectedUuid(uuid);
            setSelectedAgentId("final_diagnosis");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      ),
    },
  ];
}

function rate(num: unknown, den: unknown) {
  const n = Number(num || 0);
  const d = Number(den || 0);
  return d ? `${Math.round((100 * n) / d)}%` : "0%";
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

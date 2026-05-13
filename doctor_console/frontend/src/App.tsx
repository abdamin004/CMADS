import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, BrainCircuit, PanelLeftOpen, RefreshCw } from "lucide-react";
import { getPatients, getResult, getResultSets, startRun, subscribeRun } from "./api";
import type { AgentCard, PatientListItem, PatientResult, ResultSet, RunTask } from "./types";
import { AgentFlow } from "./components/AgentFlow";
import { AgentInspector } from "./components/AgentInspector";
import { MemoryTimeline } from "./components/MemoryTimeline";
import { PatientBrowser } from "./components/PatientBrowser";
import { PatientEvidence } from "./components/PatientEvidence";
import { ResultsPanel } from "./components/ResultsPanel";
import { RunTimeline } from "./components/RunTimeline";
import { SimilarCases } from "./components/SimilarCases";

export default function App() {
  const [resultSets, setResultSets] = useState<ResultSet[]>([]);
  const [resultSetId, setResultSetId] = useState("");
  const [patients, setPatients] = useState<PatientListItem[]>([]);
  const [selectedUuid, setSelectedUuid] = useState<string>();
  const [selectedAgentId, setSelectedAgentId] = useState("final_diagnosis");
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
      if (!selectedUuid || !rows.some((row) => row.uuid === selectedUuid)) {
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

  const selectedNarrative =
    runTask?.agentNarratives?.[selectedAgentId] ?? result?.agentNarratives?.[selectedAgentId];

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
            <div>
              <div className="eyebrow">Clinical Multi-Agent Decisioning</div>
              <h1>Patient Review</h1>
            </div>
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

        {!result && !loadingResult && !workflowAgents.length ? (
          <section className="empty-workspace">
            <BrainCircuit size={36} />
            <h2>No saved run selected</h2>
            <p>Select a patient with a saved run, or start a live run from the sidebar.</p>
          </section>
        ) : null}

        {loadingResult ? <div className="loading-bar">Loading clinical run...</div> : null}

        {result ? (
          <>
            <section className="patient-header panel">
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

            <PatientEvidence result={result} />
          </>
        ) : null}

        {workflowAgents.length ? (
          <>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Agent workflow</h2>
                  <p>Click a stage to inspect the doctor-readable output as soon as it is available.</p>
                </div>
              </div>
              <AgentFlow
                agents={workflowAgents}
                selectedAgentId={selectedAgentId}
                onSelectAgent={setSelectedAgentId}
              />
            </section>

            <div className={`content-grid ${result ? "" : "single-column"}`}>
              <AgentInspector agent={selectedAgent} narrative={selectedNarrative} />
              {result ? <ResultsPanel result={result} /> : null}
            </div>
          </>
        ) : null}

        {result ? (
          <>
            <SimilarCases
              patientUuid={selectedUuid}
              resultSet={resultSetId}
              onOpenPatient={(uuid) => {
                setSelectedUuid(uuid);
                setSelectedAgentId("final_diagnosis");
              }}
            />

            <MemoryTimeline result={result} />

            {result.semanticMemory.length ? (
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Semantic memory matches</h2>
                    <p>Cross-run disease statistics matching the final/evaluated diagnosis.</p>
                  </div>
                </div>
                <div className="semantic-list">
                  {result.semanticMemory.map((item) => (
                    <div className="semantic-row" key={String(item.disease)}>
                      <strong>{String(item.disease)}</strong>
                      <span>
                        Runs {String(item.runs_observed ?? 0)} | DIRECT {rate(item.direct_matches, item.runs_observed)} | Found {rate(Number(item.direct_matches ?? 0) + Number(item.indirect_matches ?? 0), item.runs_observed)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
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

function rate(num: unknown, den: unknown) {
  const n = Number(num || 0);
  const d = Number(den || 0);
  return d ? `${Math.round((100 * n) / d)}%` : "0%";
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

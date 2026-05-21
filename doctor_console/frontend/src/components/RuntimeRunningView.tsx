import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Brain, CheckCircle2, ClipboardList, ChevronDown, Pill,
  ShieldAlert, Sparkles, Wrench,
} from "lucide-react";
import { AgentFlow } from "./AgentFlow";
import { AgentInspector } from "./AgentInspector";
import { Disclosure } from "./Disclosure";
import { PatientEvidence } from "./PatientEvidence";
import type { CaseBundle } from "../api";
import type { AgentCard, AgentNarrative, PatientResult, RunTask } from "../types";

type Props = {
  task: RunTask | null;
  /** Agents shown in the doctor view — LLM Evaluator already filtered out. */
  workflowAgents: AgentCard[];
  activeAgentId: string;
  onSelectAgent: (id: string) => void;
  selectedAgent: AgentCard | undefined;
  selectedNarrative?: AgentNarrative;
  /** Gold-layer case bundle — shown alongside the progress so the doctor
   *  sees what data the system is reading while it works. */
  caseBundle?: CaseBundle;
};

type StageDef = {
  id: string;
  label: string;
  body: string;
  agentIds: string[];
  Icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
};

// Doctor-friendly descriptions — no agent names, no tech language.
const STAGES: StageDef[] = [
  {
    id: "evidence", label: "Going through the chart and labs",
    body: "Reading the patient's history, current problems, medications, and recent lab results.",
    agentIds: ["ehr_analyst", "lab_interpreter"], Icon: ClipboardList,
  },
  {
    id: "diagnostic", label: "Thinking through what could be going on",
    body: "Drafting a list of likely diagnoses and weighing the evidence for each one.",
    agentIds: ["diagnostic_reasoning"], Icon: Brain,
  },
  {
    id: "review", label: "Double-checking the leading guess",
    body: "Looking for findings that argue against the most likely diagnosis — a second opinion before committing.",
    agentIds: ["clinical_reviewer"], Icon: ShieldAlert,
  },
  {
    id: "refine", label: "Putting it all together",
    body: "Merging the first read with the second opinion to settle on the final ranked list.",
    agentIds: ["final_diagnosis"], Icon: Sparkles,
  },
  {
    id: "treatment", label: "Looking up the treatment plan",
    body: "Pulling the matching NICE guideline for the top match and drafting a management proposal.",
    agentIds: ["treatment_planning"], Icon: Pill,
  },
];

/**
 * Doctor-facing live run view.
 *
 * Heavy on what's-happening-now visibility — animated progress bar, live
 * elapsed timer, a single sentence about the active stage, stage chips that
 * tick from pending → in progress (pulsing) → complete (green check).
 * Everything tech (the agent graph + raw JSON inspector) lives behind a
 * single explicit "Want to see how it's thinking?" disclosure.
 */
export function RuntimeRunningView({
  task, workflowAgents, activeAgentId, onSelectAgent, selectedAgent, selectedNarrative, caseBundle,
}: Props) {
  // Build a partial PatientResult-shaped object so the existing
  // PatientEvidence renderer can be reused with no schema changes.
  const partialResult: PatientResult | undefined = useMemo(() => {
    if (!caseBundle) return undefined;
    return {
      patient: caseBundle.patient,
      resultSet: { id: "mas_results_runtime", label: "Runtime", path: "", patientCount: 0 },
      case: {
        ehrCase: caseBundle.ehrCase,
        labCase: caseBundle.labCase,
        groundTruth: caseBundle.groundTruth,
        caseStats: caseBundle.caseStats,
      },
      evaluation: {},
      finalDiagnosis: {},
      treatment: {},
      agents: [],
      agentOutputs: {},
      agentNarratives: {},
      trace: {},
      sessionMemory: [],
      semanticMemory: [],
      sharedMemory: {
        patientContext: "", agentOutputKeys: [], sessionEvents: 0, traceEntries: 0, notes: [],
      },
    };
  }, [caseBundle]);
  // Live "X seconds elapsed" counter on the active stage. Ticks every
  // 200 ms — tighter than 250 reads as smoother to the eye without the
  // re-render cost of a 100 ms loop.
  const startedAt = task?.startedAt ?? null;
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!startedAt) return;
    const id = window.setInterval(() => setNow(Date.now() / 1000), 200);
    return () => window.clearInterval(id);
  }, [startedAt]);
  const elapsed = startedAt ? Math.max(0, now - startedAt) : 0;

  const stagesWithState = useMemo(() => {
    return STAGES.map((stage) => {
      const stageAgents = workflowAgents.filter((a) => stage.agentIds.includes(a.id));
      const statuses = stageAgents.map((a) => a.status);
      const isDone = statuses.length > 0
        && statuses.every((s) => ["success", "completed", "partial", "skipped"].includes(String(s).toLowerCase()));
      const isRunning = statuses.some((s) => ["running", "queued"].includes(String(s).toLowerCase()));
      const isError = statuses.some((s) => ["error"].includes(String(s).toLowerCase()));
      return { ...stage, isDone, isRunning, isError, agents: stageAgents };
    });
  }, [workflowAgents]);

  const activeStage = stagesWithState.find((s) => s.isRunning)
    ?? stagesWithState.find((s) => !s.isDone)
    ?? stagesWithState[stagesWithState.length - 1];

  const completedCount = stagesWithState.filter((s) => s.isDone).length;
  const totalCount = stagesWithState.length;
  const progressPct = totalCount ? Math.round((100 * completedCount) / totalCount) : 0;

  // Latest event as a live ticker line ("just-happened" feel).
  const latestEvent = useMemo(() => {
    const ev = task?.events ?? [];
    if (!ev.length) return null;
    return ev[ev.length - 1];
  }, [task]);

  return (
    <motion.div
      className="simple-run"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <section className="panel simple-run__hero">
        <div className="simple-run__hero-row">
          <div className="simple-run__hero-icon">
            <motion.span
              key={activeStage?.id}
              className="simple-run__hero-pulse"
              initial={{ scale: 0.6, opacity: 0.0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
              aria-hidden
            />
            {activeStage ? <activeStage.Icon size={22} strokeWidth={1.5} /> : null}
          </div>
          <div className="simple-run__hero-text">
            <div className="eyebrow simple-run__hero-eyebrow">
              <span>Step {completedCount + 1} of {totalCount}</span>
              <span className="simple-run__hero-elapsed mono">
                · {formatElapsed(elapsed)}
              </span>
            </div>
            <motion.h2
              key={activeStage?.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.36, ease: [0.23, 1, 0.32, 1] }}
            >
              {activeStage?.label ?? "Working…"}
            </motion.h2>
            <motion.p
              key={activeStage?.id + "-body"}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.42, delay: 0.06, ease: [0.23, 1, 0.32, 1] }}
            >
              {activeStage?.body}
            </motion.p>
          </div>
        </div>
        <div className="simple-run__progress">
          <div className="simple-run__progress-track">
            <motion.div
              className="simple-run__progress-fill"
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.55, ease: [0.23, 1, 0.32, 1] }}
            />
            <div className="simple-run__progress-shimmer" aria-hidden />
          </div>
          <div className="simple-run__progress-label mono">{progressPct}%</div>
        </div>
        {latestEvent ? (
          <motion.div
            key={`${latestEvent.timestamp}-${latestEvent.title}`}
            className="simple-run__ticker"
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35 }}
          >
            <span className="simple-run__ticker-dot" />
            <span className="simple-run__ticker-title">{latestEvent.title}</span>
            <span className="simple-run__ticker-msg">{latestEvent.message}</span>
          </motion.div>
        ) : null}
      </section>

      <div className="simple-run__grid">
        <section className="simple-run__stages">
          {stagesWithState.map((stage) => {
            const Icon = stage.Icon;
            const tone = stage.isError ? "error"
              : stage.isRunning ? "running"
              : stage.isDone ? "done"
              : "pending";
            return (
              <article key={stage.id} className={`simple-run__stage simple-run__stage--${tone}`}>
                <div className="simple-run__stage-icon">
                  {stage.isDone ? (
                    <CheckCircle2 size={18} strokeWidth={1.7} />
                  ) : (
                    <Icon size={18} strokeWidth={1.5} />
                  )}
                  {stage.isRunning ? <span className="simple-run__stage-ring" aria-hidden /> : null}
                </div>
                <div className="simple-run__stage-text">
                  <div className="simple-run__stage-label">{stage.label}</div>
                  <div className="simple-run__stage-state mono">
                    {stage.isError    ? "error" :
                     stage.isRunning  ? "in progress…" :
                     stage.isDone     ? "complete" :
                                         "pending"}
                  </div>
                </div>
              </article>
            );
          })}
        </section>

        {partialResult ? (
          <section className="simple-run__data">
            <PatientEvidence result={partialResult} />
          </section>
        ) : null}
      </div>

      <div className="simple-run__dive">
        <Disclosure
          title={
            <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
              <Wrench size={14} strokeWidth={1.7} />
              <span>Want to see exactly how it's thinking?</span>
              <span className="simple-run__dive-tag mono">EXPLAINABILITY</span>
            </span>
          }
          hint="Opens the full agent-by-agent reasoning view — useful if you'd like to follow each step in detail."
        >
          <div className="simple-run__detail">
            <AgentFlow
              agents={workflowAgents}
              selectedAgentId={activeAgentId}
              onSelectAgent={onSelectAgent}
              activeAgentId={task?.activeAgentId}
            />
            <div className="content-grid single-column" style={{ marginTop: "1.25rem" }}>
              <AgentInspector agent={selectedAgent} narrative={selectedNarrative} />
            </div>
          </div>
        </Disclosure>
      </div>
    </motion.div>
  );
}

function formatElapsed(seconds: number): string {
  if (seconds < 1) return "starting…";
  if (seconds < 60) return `${Math.floor(seconds)}s elapsed`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds - m * 60);
  return `${m}m ${s.toString().padStart(2, "0")}s elapsed`;
}

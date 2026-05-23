import { motion, AnimatePresence } from "framer-motion";
import { Fragment, useState, useMemo } from "react";
import type { ComponentType } from "react";
import {
  RotateCw,
  ClipboardList,
  FlaskConical,
  Brain,
  ShieldAlert,
  Sparkles,
  Gavel,
  Pill,
} from "lucide-react";
import type { AgentCard } from "../types";

type Props = {
  agents: AgentCard[];
  selectedAgentId?: string;
  onSelectAgent: (agentId: string) => void;
  activeAgentId?: string | null;
};

type Stage = {
  index: number;
  label: string;
  description: string;
  agentIds: string[];
  accent?: "memory" | "review";
};

const STAGES: Stage[] = [
  { index: 1, label: "Evidence",   description: "Parallel chart + lab extraction",   agentIds: ["ehr_analyst", "lab_interpreter"] },
  { index: 2, label: "Reasoning",  description: "Adaptive critique loop",            agentIds: ["diagnostic_reasoning"] },
  { index: 3, label: "Review",     description: "Adversarial challenge",             agentIds: ["clinical_reviewer"], accent: "review" },
  { index: 4, label: "Refinement", description: "Merge primary with critique",       agentIds: ["final_diagnosis"], accent: "review" },
  { index: 5, label: "Evaluation", description: "LLM-as-judge verdict",              agentIds: ["evaluation"] },
  { index: 6, label: "Treatment",  description: "NICE-grounded plan, DIRECT only",   agentIds: ["treatment_planning"] },
];

const AGENT_PERSONA: Record<
  string,
  {
    icon: ComponentType<{ size?: number; strokeWidth?: number }>;
    title: string;
    verb: string;
    tint: string;
  }
> = {
  ehr_analyst:          { icon: ClipboardList, title: "EHR Analyst",          verb: "scanning the chart",              tint: "#6ea0ff" },
  lab_interpreter:      { icon: FlaskConical,  title: "Lab Interpreter",      verb: "reading laboratory trends",       tint: "#4ed68b" },
  diagnostic_reasoning: { icon: Brain,         title: "Diagnostic Reasoning", verb: "building a differential",         tint: "#f3b95a" },
  clinical_reviewer:    { icon: ShieldAlert,   title: "Clinical Reviewer",    verb: "challenging the primary",         tint: "#b794f6" },
  final_diagnosis:      { icon: Sparkles,      title: "Diagnostic Refiner",   verb: "merging critique with reasoning", tint: "#c8a4ff" },
  evaluation:           { icon: Gavel,         title: "LLM Evaluator",        verb: "scoring against ground truth",    tint: "#7ed7d0" },
  treatment_planning:   { icon: Pill,          title: "Treatment Planner",    verb: "retrieving NICE guidelines",      tint: "#f5a0a0" },
};

const STATUS = {
  success:   { color: "#4ed68b", glow: "rgba(78, 214, 139, 0.45)" },
  completed: { color: "#4ed68b", glow: "rgba(78, 214, 139, 0.45)" },
  partial:   { color: "#f3b95a", glow: "rgba(243, 185, 90, 0.45)" },
  running:   { color: "#6ea0ff", glow: "rgba(110, 160, 255, 0.55)" },
  queued:    { color: "#6ea0ff", glow: "rgba(110, 160, 255, 0.35)" },
  pending:   { color: "#6e7689", glow: "rgba(110, 118, 137, 0.20)" },
  skipped:   { color: "#6e7689", glow: "rgba(110, 118, 137, 0.18)" },
  missing:   { color: "#4d5567", glow: "rgba(77, 85, 103, 0.15)" },
  error:     { color: "#f06778", glow: "rgba(240, 103, 120, 0.45)" },
} as const;

type StatusKey = keyof typeof STATUS;

function statusMeta(status?: string) {
  if (!status) return { ...STATUS.missing, label: "missing" };
  const key = status.toLowerCase() as StatusKey;
  return { ...(STATUS[key] ?? STATUS.missing), label: status.toLowerCase() };
}

function formatMs(ms?: number) {
  if (!ms || ms <= 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function AgentFlow({
  agents,
  selectedAgentId,
  onSelectAgent,
  activeAgentId,
}: Props) {
  const [replayKey, setReplayKey] = useState(0);

  const agentsById = useMemo(() => {
    const m: Record<string, AgentCard> = {};
    agents.forEach((a) => {
      m[a.id] = a;
    });
    return m;
  }, [agents]);

  const totalMs = agents.reduce((acc, a) => acc + (a.executionMs ?? 0), 0);
  const successCount = agents.filter((a) =>
    /(success|completed)/i.test(a.status ?? "")
  ).length;
  // Derive the visible counts from the agents the caller actually passed
  // in, NOT the global AGENT_PERSONA — the doctor view drops the LLM
  // Evaluator from its workflow, and the header copy used to leak "seven
  // specialists" / "Six stages" regardless. The visible-stages filter
  // below produces the canonical "stages this view shows" count.
  const visibleStages = STAGES.filter((stage) =>
    stage.agentIds.some((id) => agents.some((a) => a.id === id))
  );
  const visibleAgentCount = agents.length;
  const stageWord = visibleStages.length === 1 ? "stage" : "stages";
  const specialistWord = visibleAgentCount === 1 ? "specialist" : "specialists";

  return (
    <div className="aflow" key={replayKey}>
      <header className="aflow__header">
        <div className="aflow__title-block">
          <div className="aflow__eyebrow">Agent Workflow</div>
          <h2 className="aflow__title">The crew at work</h2>
          <p className="aflow__lede">
            {visibleStages.length} {stageWord}, {visibleAgentCount}{" "}
            {specialistWord}. Click any crew member to inspect what they
            reasoned, the evidence they pulled, and what they handed off. The
            dashed retrograde arc is the Tier-4 case-based memory feeding
            back into reasoning.
          </p>
        </div>

        <div className="aflow__meta">
          <div className="aflow__stat">
            <span className="aflow__stat-label">Successful</span>
            <span className="aflow__stat-value">
              {successCount}
              <span className="aflow__stat-divider">/</span>
              {visibleAgentCount || visibleStages.length}
            </span>
          </div>
          <div className="aflow__stat">
            <span className="aflow__stat-label">Total runtime</span>
            <span className="aflow__stat-value">{formatMs(totalMs)}</span>
          </div>
          <button
            type="button"
            className="aflow__replay"
            onClick={() => setReplayKey((k) => k + 1)}
            title="Replay entrance animation"
          >
            <RotateCw size={13} />
            <span>Replay</span>
          </button>
        </div>
      </header>

      <div className="aflow__canvas">
        <div className="aflow__grid">
          {STAGES
            .filter((stage) => stage.agentIds.some((id) => agents.some((a) => a.id === id)))
            .map((stage, stageIdx, visible) => {
            const stageDelay = 0.12 + stageIdx * 0.085;
            const isLast = stageIdx === visible.length - 1;
            const hasActiveAgent =
              !!activeAgentId && stage.agentIds.includes(activeAgentId);

            return (
              <Fragment key={stage.index}>
                <motion.div
                  className={`aflow__stage${
                    stage.accent ? ` aflow__stage--${stage.accent}` : ""
                  }${hasActiveAgent ? " aflow__stage--active" : ""}`}
                  style={{ gridColumn: 2 * stageIdx + 1 }}
                  initial={{ opacity: 0, y: 18 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    delay: stageDelay,
                    duration: 0.5,
                    ease: [0.4, 0, 0.2, 1],
                  }}
                >
                  <div className="aflow__stage-head">
                    <div className="aflow__stage-num">
                      {/* Renumber by the visible position so the doctor view
                          (which hides the LLM Evaluator) shows Treatment as
                          Stage 05 instead of Stage 06. ``stageIdx`` is the
                          index inside the already-filtered ``visible`` array
                          above; ``+ 1`` makes it 1-based for display. */}
                      <span>{String(stageIdx + 1).padStart(2, "0")}</span>
                    </div>
                    <div className="aflow__stage-text">
                      <div className="aflow__stage-eyebrow">STAGE</div>
                      <div className="aflow__stage-label">{stage.label}</div>
                      <div className="aflow__stage-desc">{stage.description}</div>
                    </div>
                  </div>

                  <div className="aflow__agents">
                    {stage.agentIds.map((agentId, agentIdx) => {
                      const agent = agentsById[agentId];
                      const isSelected = agentId === selectedAgentId;
                      const isActive = agentId === activeAgentId;
                      return (
                        <CrewNode
                          key={agentId}
                          agentId={agentId}
                          agent={agent}
                          isSelected={isSelected}
                          isActive={isActive}
                          delay={stageDelay + 0.16 + agentIdx * 0.06}
                          onClick={() => onSelectAgent(agentId)}
                        />
                      );
                    })}
                  </div>
                </motion.div>

                {!isLast && (
                  <StageConnector
                    stageIdx={stageIdx}
                    delay={stageDelay + 0.35}
                    accent={stage.accent}
                  />
                )}
              </Fragment>
            );
          })}
        </div>

      </div>

      <footer className="aflow__legend">
        {(["success", "partial", "running", "skipped", "error"] as StatusKey[]).map(
          (k) => {
            const m = STATUS[k];
            return (
              <span key={k} className="aflow__legend-item">
                <span
                  className="aflow__legend-dot"
                  style={{
                    background: m.color,
                    boxShadow: `0 0 8px ${m.glow}`,
                  }}
                />
                <span className="aflow__legend-text">{k}</span>
              </span>
            );
          }
        )}
      </footer>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Crew node — persona avatar (icon, ring, thinking cog) + status row
// ─────────────────────────────────────────────────────────────────────────────
function CrewNode({
  agentId,
  agent,
  isSelected,
  isActive,
  delay,
  onClick,
}: {
  agentId: string;
  agent?: AgentCard;
  isSelected: boolean;
  isActive: boolean;
  delay: number;
  onClick: () => void;
}) {
  const persona = AGENT_PERSONA[agentId];
  const Icon = persona.icon;
  const statusStr = agent?.status ?? "";
  const effectiveStatus =
    isActive && !/(success|completed|error)/i.test(statusStr)
      ? "running"
      : statusStr;
  const meta = statusMeta(effectiveStatus);
  const exec = agent?.executionMs ?? 0;
  const isRunning = /(running|queued)/i.test(effectiveStatus) || isActive;
  const isSkipped = /(skipped|missing)/i.test(effectiveStatus);
  const isError = /error/i.test(effectiveStatus);

  const summary =
    agent?.summary?.trim() ||
    (isRunning
      ? "Reasoning in progress…"
      : isSkipped
        ? "Skipped by gate"
        : "Awaiting data");

  return (
    <motion.button
      type="button"
      onClick={onClick}
      className={[
        "aflow__crew",
        isSelected && "aflow__crew--selected",
        isActive && "aflow__crew--active",
        isRunning && "aflow__crew--running",
        isSkipped && "aflow__crew--skipped",
        isError && "aflow__crew--error",
      ]
        .filter(Boolean)
        .join(" ")}
      initial={{ opacity: 0, y: 12, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      whileHover={{ y: -3 }}
      whileTap={{ scale: 0.97 }}
      style={
        {
          ["--persona" as never]: persona.tint,
          ["--node-accent" as never]: meta.color,
          ["--node-glow" as never]: meta.glow,
        } as React.CSSProperties
      }
    >
      <span className="aflow__crew-bg" aria-hidden />

      <div className="aflow__crew-avatar">
        <span className="aflow__crew-ring" aria-hidden />
        {isRunning && (
          <span className="aflow__crew-ring aflow__crew-ring--spin" aria-hidden />
        )}
        <Icon size={20} strokeWidth={1.6} />
        {isRunning && (
          <span className="aflow__crew-cog" aria-hidden>
            <span /> <span /> <span />
          </span>
        )}
      </div>

      <div className="aflow__crew-name">{persona.title}</div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={summary}
          className="aflow__crew-verb"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.25 }}
        >
          {summary.length > 64 ? summary.slice(0, 62).trimEnd() + "…" : summary}
        </motion.div>
      </AnimatePresence>

      <div className="aflow__crew-foot">
        <span className="aflow__crew-status">
          <span
            className="aflow__crew-dot"
            style={{
              background: meta.color,
              boxShadow: `0 0 8px ${meta.glow}`,
            }}
          />
          <span className="aflow__crew-status-text">{meta.label}</span>
        </span>
        <span className="aflow__crew-time">
          {isRunning && exec === 0 ? <RunningClock /> : formatMs(exec)}
        </span>
      </div>
    </motion.button>
  );
}

function RunningClock() {
  return (
    <motion.span
      animate={{ opacity: [0.4, 1, 0.4] }}
      transition={{ duration: 1.4, repeat: Infinity }}
      style={{ fontVariantNumeric: "tabular-nums" }}
    >
      ···
    </motion.span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Connector arrow between stages (explicit grid-column placement)
// ─────────────────────────────────────────────────────────────────────────────
function StageConnector({
  stageIdx,
  delay,
  accent,
}: {
  stageIdx: number;
  delay: number;
  accent?: Stage["accent"];
}) {
  const stroke = accent === "review" ? "#b794f6" : "var(--ink-muted, #6e7689)";
  const pulseId = `pulse-${stageIdx}`;
  return (
    <div
      className="aflow__connector"
      aria-hidden
      style={{ gridColumn: 2 * stageIdx + 2 }}
    >
      <motion.svg
        viewBox="0 0 36 14"
        width="36"
        height="14"
        className="aflow__connector-svg"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay, duration: 0.4 }}
      >
        <motion.path
          id={pulseId}
          d="M 1 7 L 30 7"
          stroke={stroke}
          strokeWidth="1"
          fill="none"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay, duration: 0.6, ease: "easeOut" }}
        />
        <motion.path
          d="M 26 3 L 33 7 L 26 11"
          stroke={stroke}
          strokeWidth="1"
          fill="none"
          strokeLinejoin="round"
          strokeLinecap="round"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: delay + 0.45, duration: 0.25 }}
        />
        <circle r="1.1" fill={stroke}>
          <animateMotion
            dur="2.4s"
            repeatCount="indefinite"
            begin={`${delay + 1}s`}
          >
            <mpath href={`#${pulseId}`} />
          </animateMotion>
          <animate
            attributeName="opacity"
            values="0;1;1;0"
            keyTimes="0;0.15;0.85;1"
            dur="2.4s"
            repeatCount="indefinite"
            begin={`${delay + 1}s`}
          />
        </circle>
      </motion.svg>
    </div>
  );
}

function MemoryLoop() {
  // Arc from the right side of the timeline back to Stage 2 (Reasoning).
  const startX = 92;
  const endX = 23;
  const yTop = 0;
  const yBottom = 28;
  const path = `M ${startX} ${yTop}
                C ${startX} ${yBottom + 6},
                  ${endX} ${yBottom + 6},
                  ${endX} ${yTop}`;

  return (
    <div className="aflow__memory" aria-hidden>
      <motion.svg
        viewBox="0 0 100 36"
        preserveAspectRatio="none"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.85, duration: 0.5 }}
      >
        <defs>
          <linearGradient id="memoryGradient" x1="100%" y1="0%" x2="0%" y2="0%">
            <stop offset="0%" stopColor="#b794f6" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#b794f6" stopOpacity="0.45" />
          </linearGradient>
        </defs>

        <motion.path
          id="memoryPath"
          d={path}
          stroke="url(#memoryGradient)"
          strokeWidth="0.6"
          strokeDasharray="1.6 1.4"
          fill="none"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 0.9, duration: 1.3, ease: "easeInOut" }}
        />

        <motion.path
          d={`M ${endX - 1.8} -1.2 L ${endX} 1.4 L ${endX + 1.8} -1.2`}
          stroke="#b794f6"
          strokeWidth="0.6"
          fill="none"
          strokeLinejoin="round"
          strokeLinecap="round"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.9 }}
          transition={{ delay: 2.0, duration: 0.3 }}
        />

        <circle r="0.9" fill="#b794f6" style={{ filter: "drop-shadow(0 0 1px #b794f6)" }}>
          <animateMotion dur="4s" repeatCount="indefinite" begin="2.2s">
            <mpath href="#memoryPath" />
          </animateMotion>
          <animate
            attributeName="opacity"
            values="0;1;1;0"
            keyTimes="0;0.1;0.9;1"
            dur="4s"
            repeatCount="indefinite"
            begin="2.2s"
          />
        </circle>
      </motion.svg>

      <motion.div
        className="aflow__memory-label"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1.8, duration: 0.5 }}
      >
        <span className="aflow__memory-tag">TIER&nbsp;4</span>
        <span className="aflow__memory-text">memory prior</span>
      </motion.div>
    </div>
  );
}

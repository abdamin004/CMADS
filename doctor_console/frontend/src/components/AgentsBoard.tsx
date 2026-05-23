import { useEffect, useState, Fragment } from "react";
import type { ComponentType } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileCode2 } from "lucide-react";
import {
  ArchivistRobot,
  ChemistRobot,
  StrategistRobot,
  InspectorRobot,
  EditorRobot,
  JudgeRobot,
  PharmacistRobot,
} from "@/components/AgentRobots";
import { getAgentPrompt, type AgentPrompt } from "../api";

// Agents that have a YAML prompt file on disk (under `prompts/`). The
// LLM Evaluator runs a hard-coded judge prompt from src/evaluation/, not a
// per-agent YAML, so it is intentionally excluded from the prompt picker.
const AGENT_IDS_WITH_PROMPTS = new Set([
  "ehr_analyst",
  "lab_interpreter",
  "diagnostic_reasoning",
  "clinical_reviewer",
  "final_diagnosis",
  "treatment_planning",
]);

type CrewEntry = {
  id: string;
  Robot: ComponentType<{ active?: boolean }>;
  stage: string;
  name: string;
  persona: string;
  description: string;
  tint: string;
};

const CREW: CrewEntry[] = [
  {
    id: "ehr_analyst",
    Robot: ArchivistRobot,
    stage: "Stage 01",
    name: "EHR Analyst",
    persona: "the Archivist",
    description:
      "Reads the patient chart end-to-end — active conditions, resolved history, active medications, prior encounters, and risk scores — and emits a structured clinical summary the rest of the pipeline can reason over.",
    tint: "#6ea0ff",
  },
  {
    id: "lab_interpreter",
    Robot: ChemistRobot,
    stage: "Stage 01",
    name: "Lab Interpreter",
    persona: "the Chemist",
    description:
      "Runs alongside the Archivist. Compares every lab against its reference range, computes trends over time, ranks abnormalities by severity, and surfaces critical flags as upstream evidence for the diagnostic step.",
    tint: "#4ed68b",
  },
  {
    id: "diagnostic_reasoning",
    Robot: StrategistRobot,
    stage: "Stage 02",
    name: "Diagnostic Reasoning",
    persona: "the Strategist",
    description:
      "Builds a ranked differential through an adaptive multi-round critique loop, stopping when confidence crosses 75 % or after three rounds — and runs an anti-anchoring split when a Tier-4 prior case is retrieved.",
    tint: "#f3b95a",
  },
  {
    id: "clinical_reviewer",
    Robot: InspectorRobot,
    stage: "Stage 03",
    name: "Clinical Reviewer",
    persona: "the Inspector",
    description:
      "Independently re-examines the evidence and the differential. Challenges the primary diagnosis, names missed alternatives, and tags each candidate as verified, refuted, or uncertain — without overwriting the original output.",
    tint: "#b794f6",
  },
  {
    id: "final_diagnosis",
    Robot: EditorRobot,
    stage: "Stage 04",
    name: "Diagnostic Refiner",
    persona: "the Editor",
    description:
      "Merges the Strategist's reasoning with the Inspector's critique into the final ranked differential. Promotes verified diagnoses, demotes refuted ones, and keeps the earlier chain intact so the decision path remains auditable.",
    tint: "#c8a4ff",
  },
  {
    id: "evaluation",
    Robot: JudgeRobot,
    stage: "Stage 05",
    name: "LLM Evaluator",
    persona: "the Judge",
    description:
      "Runs on a different model than the reasoning agents. Compares the final differential against the hidden Synthea ground truth and adjudicates each candidate as DIRECT, INDIRECT, or MISS with a rank-when-found.",
    tint: "#7ed7d0",
  },
  {
    id: "treatment_planning",
    Robot: PharmacistRobot,
    stage: "Stage 06",
    name: "Treatment Planner",
    persona: "the Pharmacist",
    description:
      "Only runs when the Judge returns DIRECT. Retrieves the matching NICE guideline passages from Qdrant and assembles a treatment plan with prescribed medications, interaction checks, contraindications, and assumption warnings.",
    tint: "#f5a0a0",
  },
];

export function AgentsBoard() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const selectedMember = selected
    ? CREW.find((m) => m.id === selected) ?? null
    : null;

  return (
    <section className="agents-board" aria-labelledby="agents-board-title">
      <header className="agents-board__header">
        <p className="agents-board__eyebrow">The Crew</p>
        <h2 className="agents-board__title" id="agents-board-title">
          The clinical reasoning flow.
        </h2>
        <p className="agents-board__lede">
          Seven agents, six stages, one diagnosis. Tap any agent to read
          its role in the pipeline. Their eyes follow your cursor.
        </p>
      </header>

      <div className="agents-board__flow" role="list">
        {CREW.map((member, i) => {
          const isHovered = hovered === member.id;
          const isSelected = selected === member.id;
          const isActive = isHovered || isSelected;
          const isLast = i === CREW.length - 1;

          return (
            <Fragment key={member.id}>
              <motion.button
                type="button"
                role="listitem"
                className={`agents-board__node${
                  isSelected ? " agents-board__node--selected" : ""
                }${isHovered ? " agents-board__node--hovered" : ""}`}
                onMouseEnter={() => setHovered(member.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() =>
                  setSelected((s) => (s === member.id ? null : member.id))
                }
                onFocus={() => setHovered(member.id)}
                onBlur={() => setHovered(null)}
                aria-pressed={isSelected}
                aria-label={`${member.name}, ${member.persona}. ${
                  isSelected ? "Hide" : "Show"
                } description.`}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{
                  delay: 0.1 + i * 0.07,
                  duration: 0.5,
                  ease: [0.4, 0, 0.2, 1],
                }}
                whileHover={{ y: -4 }}
                whileTap={{ scale: 0.96 }}
                style={
                  { ["--persona" as never]: member.tint } as React.CSSProperties
                }
              >
                <span className="agents-board__node-bg" aria-hidden />
                <div className="agents-board__node-robot">
                  <member.Robot active={isActive} />
                </div>
                <div className="agents-board__node-text">
                  <div className="agents-board__node-tag">
                    <span className="agents-board__node-tag-kind">AGENT</span>
                    <span className="agents-board__node-tag-sep">·</span>
                    <span className="agents-board__node-tag-stage">
                      {member.stage.replace("Stage ", "")}
                    </span>
                  </div>
                  <div className="agents-board__node-name">{member.name}</div>
                  <div className="agents-board__node-persona">
                    {member.persona}
                  </div>
                </div>
              </motion.button>

              {!isLast && (
                <Connector
                  delay={0.18 + i * 0.07}
                  highlight={
                    selected === member.id ||
                    selected === CREW[i + 1]?.id ||
                    hovered === member.id ||
                    hovered === CREW[i + 1]?.id
                  }
                />
              )}
            </Fragment>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        {selectedMember ? (
          <motion.div
            key={selectedMember.id}
            className="agents-board__detail"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.32, ease: [0.4, 0, 0.2, 1] }}
            style={
              {
                ["--persona" as never]: selectedMember.tint,
              } as React.CSSProperties
            }
          >
            <div className="agents-board__detail-inner">
              <div className="agents-board__detail-row">
                <div className="agents-board__detail-id">
                  <span className="agents-board__detail-tag">
                    AGENT · {selectedMember.stage}
                  </span>
                  <h3 className="agents-board__detail-name">
                    {selectedMember.name}
                  </h3>
                  <p className="agents-board__detail-persona">
                    {selectedMember.persona}
                  </p>
                </div>
                <p className="agents-board__detail-desc">
                  {selectedMember.description}
                </p>
                <button
                  type="button"
                  className="agents-board__detail-close"
                  onClick={() => setSelected(null)}
                  aria-label="Close description"
                >
                  Close
                </button>
              </div>
              {AGENT_IDS_WITH_PROMPTS.has(selectedMember.id) ? (
                <AgentPromptInline agentId={selectedMember.id} />
              ) : null}
            </div>
          </motion.div>
        ) : (
          <motion.p
            key="prompt"
            className="agents-board__prompt"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            Tap an agent to read what it does.
          </motion.p>
        )}
      </AnimatePresence>
    </section>
  );
}

/**
 * Lazily-fetched prompt template embedded inside each agent's expanded
 * detail card in the AgentsBoard. The fetch is gated on first expand so a
 * doctor that never opens the prompt pays no network cost.
 */
function AgentPromptInline({ agentId }: { agentId: string }) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState<AgentPrompt | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || prompt || loading) return;
    setLoading(true);
    setError(null);
    getAgentPrompt(agentId)
      .then((p) => setPrompt(p))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [open, agentId, prompt, loading]);

  return (
    <details
      className="agent-prompt"
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="agent-prompt__summary">
        <FileCode2 size={14} strokeWidth={1.8} />
        <span className="agent-prompt__title">View prompt template</span>
        <span className="agent-prompt__hint mono">
          prompts/{agentId}.yaml
          {prompt ? ` · ${prompt.lineCount} lines` : ""}
        </span>
        <span className="agent-prompt__toggle" aria-hidden="true">▾</span>
      </summary>
      <div className="agent-prompt__body">
        {loading ? (
          <div className="empty-state compact">Loading prompt…</div>
        ) : error ? (
          <div className="error-box">{error}</div>
        ) : prompt ? (
          <pre className="raw-json agent-prompt__yaml">{prompt.text}</pre>
        ) : null}
      </div>
    </details>
  );
}

function Connector({
  delay,
  highlight,
}: {
  delay: number;
  highlight: boolean;
}) {
  return (
    <motion.div
      className="agents-board__connector"
      aria-hidden
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ delay, duration: 0.4 }}
    >
      <svg viewBox="0 0 36 14" width="36" height="14">
        <motion.path
          d="M 2 7 L 30 7"
          stroke={highlight ? "#c8a4ff" : "var(--ink-muted, #6e7689)"}
          strokeWidth={highlight ? "1.4" : "1"}
          strokeLinecap="round"
          fill="none"
          animate={{ pathLength: 1 }}
          initial={{ pathLength: 0 }}
          transition={{ delay, duration: 0.6, ease: "easeOut" }}
        />
        <motion.path
          d="M 26 3 L 33 7 L 26 11"
          stroke={highlight ? "#c8a4ff" : "var(--ink-muted, #6e7689)"}
          strokeWidth={highlight ? "1.4" : "1"}
          strokeLinejoin="round"
          strokeLinecap="round"
          fill="none"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: delay + 0.45, duration: 0.25 }}
        />
      </svg>
    </motion.div>
  );
}

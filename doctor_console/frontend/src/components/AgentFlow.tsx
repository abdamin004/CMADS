import { ReactFlow, Background, Controls, MarkerType, type Edge, type Node } from "@xyflow/react";
import type { AgentCard } from "../types";

type Props = {
  agents: AgentCard[];
  selectedAgentId?: string;
  onSelectAgent: (agentId: string) => void;
};

const STATUS_COLORS: Record<string, string> = {
  success: "#4ed68b",
  completed: "#4ed68b",
  partial: "#f3b95a",
  running: "#6ea0ff",
  queued: "#6ea0ff",
  pending: "#6e7689",
  skipped: "#6e7689",
  missing: "#6e7689",
  error: "#f06778",
};

const NODE_WIDTH = 240;
const NODE_HEIGHT = 116;

const positions: Record<string, { x: number; y: number }> = {
  ehr_analyst:           { x:   50, y:   40 },
  lab_interpreter:       { x:   50, y:  220 },
  diagnostic_reasoning:  { x:  370, y:  130 },
  clinical_reviewer:     { x:  690, y:  130 },
  final_diagnosis:       { x: 1010, y:  130 },
  evaluation:            { x: 1330, y:  130 },
  treatment_planning:    { x: 1650, y:   40 },
  memory_consolidation:  { x: 1650, y:  220 },
};

const edges: Edge[] = [
  { id: "ehr-diag",      source: "ehr_analyst",          target: "diagnostic_reasoning", label: "EHR" },
  { id: "lab-diag",      source: "lab_interpreter",       target: "diagnostic_reasoning", label: "Labs" },
  { id: "diag-review",   source: "diagnostic_reasoning",  target: "clinical_reviewer",    label: "Differential" },
  { id: "review-refine", source: "clinical_reviewer",     target: "final_diagnosis",      label: "Critique" },
  { id: "refine-eval",   source: "final_diagnosis",       target: "evaluation",           label: "Final Dx" },
  { id: "eval-treat",    source: "evaluation",            target: "treatment_planning",   label: "DIRECT only" },
  { id: "treat-memory",  source: "treatment_planning",    target: "memory_consolidation", label: "Outcome" },
  { id: "memory-diag",   source: "memory_consolidation",  target: "diagnostic_reasoning", label: "Memory prior", animated: true },
];

export function AgentFlow({ agents, selectedAgentId, onSelectAgent }: Props) {
  const styledEdges: Edge[] = edges.map((e) => ({
    ...e,
    type: "smoothstep",
    style: {
      stroke: e.animated ? "#b794f6" : "#3a4358",
      strokeWidth: e.animated ? 1.6 : 1.4,
      strokeDasharray: e.animated ? "6 4" : undefined,
    },
    labelStyle: {
      fill: "#b0b8c8",
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 10,
      letterSpacing: "0.06em",
      textTransform: "uppercase" as const,
      fontWeight: 500,
    },
    labelBgStyle: {
      fill: "#11151c",
      stroke: "#242b39",
      strokeWidth: 1,
    },
    labelBgPadding: [6, 4] as [number, number],
    labelBgBorderRadius: 3,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: e.animated ? "#b794f6" : "#3a4358",
      width: 14,
      height: 14,
    },
  }));

  const nodes: Node[] = agents.map((agent) => {
    const isSelected = agent.id === selectedAgentId;
    const statusColor = STATUS_COLORS[agent.status] ?? STATUS_COLORS.pending;
    return {
      id: agent.id,
      position: positions[agent.id] ?? { x: 0, y: 0 },
      data: {
        label: (
          <div className="agent-node">
            <div
              className="agent-node-rail"
              style={{ background: statusColor }}
            />
            <div className="agent-node-body">
              <div className="agent-node-title">{agent.label}</div>
              <div
                className="agent-node-status"
                style={{
                  color: statusColor,
                  background: statusColor + "1f",
                  borderColor: statusColor,
                }}
              >
                {agent.status}
              </div>
              <div className="agent-node-summary">{agent.summary || "—"}</div>
            </div>
          </div>
        ),
      },
      style: {
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        padding: 0,
        borderRadius: 8,
        border: isSelected ? "1.5px solid #6ea0ff" : "1px solid #242b39",
        background: "#161a23",
        boxShadow: isSelected
          ? "0 0 0 3px rgba(110, 160, 255, 0.18)"
          : "none",
        transition: "border-color 0.18s ease, box-shadow 0.18s ease",
      },
    };
  });

  return (
    <div className="flow-shell">
      <ReactFlow
        nodes={nodes}
        edges={styledEdges}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1.0 }}
        minZoom={0.3}
        maxZoom={1.4}
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onSelectAgent(node.id)}
      >
        <Background color="#1e2330" gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

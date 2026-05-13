import { Clock, ClipboardList, Stethoscope } from "lucide-react";
import type { AgentCard, AgentNarrative } from "../types";

type Props = {
  agent?: AgentCard;
  narrative?: AgentNarrative;
};

export function AgentInspector({ agent, narrative }: Props) {
  if (!agent) {
    return (
      <section className="panel">
        <h2>Agent inspector</h2>
        <p className="muted">Select a node in the workflow graph.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{agent.label}</h2>
          <p>{agent.summary}</p>
        </div>
        <span className={`status-badge status-${agent.status}`}>{agent.status}</span>
      </div>
      <div className="agent-meta">
        <span><Clock size={15} /> {formatMs(agent.executionMs)}</span>
        <span><Stethoscope size={15} /> {agent.hasOutput ? "clinical summary ready" : "waiting for agent output"}</span>
      </div>
      {agent.error ? <div className="error-box">{agent.error}</div> : null}
      {narrative ? <NarrativeView narrative={narrative} /> : <PendingNarrative status={agent.status} />}
    </section>
  );
}

function NarrativeView({ narrative }: { narrative: AgentNarrative }) {
  return (
    <div className="narrative">
      {narrative.metrics.length ? (
        <div className="narrative-metrics">
          {narrative.metrics.map((metric) => (
            <div className="narrative-metric" key={`${metric.label}-${String(metric.value)}`}>
              <span>{metric.label}</span>
              <strong>{String(metric.value)}</strong>
            </div>
          ))}
        </div>
      ) : null}

      {narrative.callouts.length ? (
        <div className="clinical-callouts">
          {narrative.callouts.map((callout, index) => (
            <div className="clinical-callout" key={`${callout}-${index}`}>
              <ClipboardList size={15} />
              <span>{callout}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="narrative-sections">
        {narrative.sections.map((section) => (
          <div className="narrative-section" key={section.title}>
            <h3>{section.title}</h3>
            {section.items.length ? (
              <ul>
                {section.items.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <div className="empty-state compact">{section.empty || "No readable items saved."}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PendingNarrative({ status }: { status: string }) {
  const label = status === "running"
    ? "This agent is running. Its clinical summary will appear here as soon as the stage completes."
    : "This agent has not produced a clinical summary yet.";
  return <div className="empty-state">{label}</div>;
}

function formatMs(value?: number) {
  if (typeof value !== "number") return "not recorded";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

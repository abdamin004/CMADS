import { Clock, ClipboardList, Stethoscope, FileJson } from "lucide-react";
import type { AgentCard, AgentNarrative } from "../types";
import { Disclosure } from "./Disclosure";

type Props = {
  agent?: AgentCard;
  narrative?: AgentNarrative;
  /** Raw persisted output for this agent (result.agentOutputs[agent.id]). */
  rawOutput?: unknown;
};

export function AgentInspector({ agent, narrative, rawOutput }: Props) {
  if (!agent) {
    return (
      <section className="panel">
        <h2>Agent inspector</h2>
        <p className="muted">Select a node in the workflow graph.</p>
      </section>
    );
  }

  return (
    <section className="panel agent-inspector">
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
      {narrative ? (
        <NarrativeView
          key={agent.id}
          agentId={agent.id}
          narrative={narrative}
          rawOutput={rawOutput}
        />
      ) : (
        <PendingNarrative status={agent.status} />
      )}
    </section>
  );
}

function NarrativeView({
  agentId,
  narrative,
  rawOutput,
}: {
  agentId: string;
  narrative: AgentNarrative;
  rawOutput?: unknown;
}) {
  // Compact at-a-glance metrics row stays visible — small enough not to dominate.
  // Everything else is grouped into named dropdowns. Doctor opens what they
  // want; nothing dumps wholesale.

  const hasCallouts = narrative.callouts.length > 0;
  const hasSections = narrative.sections.length > 0;
  const hasRawOutput =
    rawOutput !== undefined &&
    rawOutput !== null &&
    !(typeof rawOutput === "object" && rawOutput !== null && Object.keys(rawOutput).length === 0);

  return (
    <div className="narrative" data-demo-anchor="agent-narrative">
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

      <div className="disclosure-stack">
        {hasCallouts ? (
          <Disclosure
            tone="callout"
            title="Clinical highlights"
            badge={narrative.callouts.length}
            hint={`${narrative.callouts.length} alerts — short, non-narrative findings the agent flagged.`}
            defaultOpen
            demoAnchor="agent-disclosure-highlights"
          >
            <div className="clinical-callouts">
              {narrative.callouts.map((callout, index) => (
                <div className="clinical-callout" key={`${callout}-${index}`}>
                  <ClipboardList size={15} />
                  <span>{callout}</span>
                </div>
              ))}
            </div>
          </Disclosure>
        ) : null}

        {hasSections
          ? narrative.sections.map((section, idx) => (
              <Disclosure
                key={`${agentId}-${section.title}`}
                title={section.title}
                badge={section.items.length || undefined}
                hint={
                  section.items.length
                    ? `${section.items.length} ${section.items.length === 1 ? "item" : "items"}`
                    : section.empty || "no items"
                }
                /* Open the first narrative section by default for context; rest closed. */
                defaultOpen={idx === 0}
                demoAnchor={`agent-section-${section.title.toLowerCase().replace(/\s+/g, "-")}`}
              >
                {section.items.length ? (
                  <ul className="narrative-list">
                    {section.items.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="empty-state compact">
                    {section.empty || "No readable items saved."}
                  </div>
                )}
              </Disclosure>
            ))
          : null}

        {hasRawOutput ? (
          <Disclosure
            tone="muted"
            title={
              <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
                <FileJson size={14} /> Raw agent output (JSON)
              </span>
            }
            hint="The persisted JSON this agent wrote to disk. For audit and debugging."
            demoAnchor="agent-disclosure-raw"
          >
            <pre className="raw-json raw-json--agent">
              {JSON.stringify(rawOutput, null, 2)}
            </pre>
          </Disclosure>
        ) : null}
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

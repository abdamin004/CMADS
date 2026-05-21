import { Clock, ClipboardList, Stethoscope, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
        <NarrativeView agentId={agent.id} narrative={narrative} />
      ) : (
        <PendingNarrative status={agent.status} />
      )}
    </section>
  );
}

function NarrativeView({
  agentId,
  narrative,
}: {
  agentId: string;
  narrative: AgentNarrative;
}) {
  // Progressive disclosure: only the FIRST section is expanded by default.
  // Others reveal on click. Resetting whenever the selected agent changes.
  const firstSectionKey = narrative.sections[0]?.title;
  const initiallyOpen = useMemo(
    () => (firstSectionKey ? new Set([firstSectionKey]) : new Set<string>()),
    // Recompute when the agent changes so each new agent starts collapsed-but-for-first.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [agentId, firstSectionKey],
  );
  const [openSections, setOpenSections] = useState<Set<string>>(initiallyOpen);

  const toggle = (title: string) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };
  const allOpen = openSections.size === narrative.sections.length && narrative.sections.length > 0;
  const expandAll = () =>
    setOpenSections(
      allOpen ? new Set() : new Set(narrative.sections.map((s) => s.title)),
    );

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

      {narrative.sections.length ? (
        <>
          <div className="narrative-sections-toolbar">
            <span className="muted">
              {narrative.sections.length} {narrative.sections.length === 1 ? "section" : "sections"}
            </span>
            <button
              type="button"
              className="narrative-expand-toggle"
              onClick={expandAll}
            >
              {allOpen ? "Collapse all" : "Expand all"}
            </button>
          </div>
          <div className="narrative-sections collapsible">
            {narrative.sections.map((section) => {
              const isOpen = openSections.has(section.title);
              return (
                <div
                  className="narrative-section narrative-section--collapsible"
                  key={section.title}
                  data-demo-anchor={`agent-section-${section.title.toLowerCase().replace(/\s+/g, "-")}`}
                  data-open={isOpen ? "true" : "false"}
                >
                  <button
                    type="button"
                    className="narrative-section-summary"
                    aria-expanded={isOpen}
                    onClick={() => toggle(section.title)}
                  >
                    <ChevronDown
                      size={15}
                      className="narrative-section-chevron"
                      style={{ transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)" }}
                    />
                    <h3>{section.title}</h3>
                    <span className="narrative-section-count">
                      {section.items.length || (section.empty ? 0 : "")}
                    </span>
                  </button>
                  <AnimatePresence initial={false}>
                    {isOpen ? (
                      <motion.div
                        key="content"
                        className="narrative-section-content"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2, ease: [0.22, 0.65, 0.3, 0.96] }}
                      >
                        {section.items.length ? (
                          <ul>
                            {section.items.map((item, index) => (
                              <li key={`${item}-${index}`}>{item}</li>
                            ))}
                          </ul>
                        ) : (
                          <div className="empty-state compact">
                            {section.empty || "No readable items saved."}
                          </div>
                        )}
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </>
      ) : null}
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

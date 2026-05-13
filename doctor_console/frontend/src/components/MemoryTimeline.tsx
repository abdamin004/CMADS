import { Database, GitBranch, ListTree } from "lucide-react";
import type { PatientResult, SessionEvent } from "../types";

type Props = {
  result?: PatientResult;
};

export function MemoryTimeline({ result }: Props) {
  if (!result) {
    return null;
  }
  const events = result.sessionMemory;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Shared memory and agent conversation</h2>
          <p>What agents wrote to state, what later stages could read, and what was consolidated after the run.</p>
        </div>
      </div>

      <div className="memory-grid">
        <div className="memory-tile">
          <Database size={18} />
          <span>Patient context</span>
          <strong>Gold EHR + Lab</strong>
        </div>
        <div className="memory-tile">
          <GitBranch size={18} />
          <span>Agent output slots</span>
          <strong>{result.sharedMemory.agentOutputKeys.length}</strong>
        </div>
        <div className="memory-tile">
          <ListTree size={18} />
          <span>Session events</span>
          <strong>{events.length}</strong>
        </div>
      </div>

      <div className="memory-notes">
        {result.sharedMemory.notes.map((note) => (
          <span key={note}>{note}</span>
        ))}
      </div>

      <div className="timeline">
        {events.length === 0 ? (
          <div className="empty-state">This run has no session_memory.json timeline.</div>
        ) : (
          events.map((event, index) => <TimelineItem key={`${event.agent_id}-${event.timestamp}-${index}`} event={event} />)
        )}
      </div>
    </section>
  );
}

function TimelineItem({ event }: { event: SessionEvent }) {
  return (
    <div className="timeline-item">
      <div className={`timeline-dot type-${event.event_type}`} />
      <div className="timeline-body">
        <div className="timeline-meta">
          <span>{event.agent_id}</span>
          <span>{event.event_type}</span>
          <span>{event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ""}</span>
        </div>
        <div className="timeline-summary">{event.summary}</div>
        {event.tags?.length ? <div className="timeline-tags">{event.tags.join(" / ")}</div> : null}
      </div>
    </div>
  );
}

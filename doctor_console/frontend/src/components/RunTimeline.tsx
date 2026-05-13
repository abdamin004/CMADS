import { Activity, CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import type { RunTask } from "../types";

type Props = {
  task?: RunTask | null;
};

export function RunTimeline({ task }: Props) {
  if (!task) return null;
  const events = task.events ?? [];
  const icon = task.status === "completed"
    ? <CheckCircle2 size={18} />
    : task.status === "error"
      ? <XCircle size={18} />
      : <Activity size={18} />;

  return (
    <section className="panel live-run-panel">
      <div className="panel-heading">
        <div>
          <h2>Live agent run</h2>
          <p>Agent outputs appear as readable clinical notes when each stage completes.</p>
        </div>
        <span className={`status-badge status-${task.status}`}>{task.status}</span>
      </div>

      <div className="live-run-summary">
        <div className={`live-run-icon status-${task.status}`}>{icon}</div>
        <div>
          <strong>{task.patientUuid}</strong>
          <span>{task.error || activeMessage(task)}</span>
        </div>
      </div>

      <div className="run-event-list">
        {events.length ? (
          events.slice(-10).reverse().map((event, index) => (
            <div className="run-event" key={`${event.timestamp}-${index}`}>
              <CircleDashed size={13} />
              <div>
                <strong>{event.title}</strong>
                <span>{event.message}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state compact">No live events yet.</div>
        )}
      </div>
    </section>
  );
}

function activeMessage(task: RunTask) {
  if (task.status === "queued") return "Waiting for the backend worker.";
  if (task.status === "running") {
    const active = task.agents?.find((agent) => agent.id === task.activeAgentId);
    return active ? `${active.label}: ${active.summary}` : "Agents are processing this patient.";
  }
  if (task.status === "completed") return "Run completed. The final result is loading below.";
  return "Run status unavailable.";
}

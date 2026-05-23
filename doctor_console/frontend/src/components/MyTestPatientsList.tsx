import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { deleteTestPatient, listTestPatients, startTestRun } from "../api";
import type { TestPatientSummary } from "../types";

interface Props {
  onEdit:  (testUuid: string) => void;
  onRun:   (taskId: string) => void;
  onNew:   () => void;
}

export function MyTestPatientsList({ onEdit, onRun, onNew }: Props) {
  const [rows, setRows] = useState<TestPatientSummary[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  function load() { listTestPatients().then(setRows); }
  useEffect(load, []);

  async function rerun(uuid: string) {
    setBusy(uuid);
    const task = await startTestRun(uuid);
    setBusy(null);
    onRun(task.taskId);
  }

  async function remove(uuid: string) {
    if (!window.confirm("Delete this test patient? Past run results stay in the audit trail."))
      return;
    await deleteTestPatient(uuid);
    load();
  }

  function relative(iso?: string | null): string {
    if (!iso) return "—";
    const d = (Date.now() - new Date(iso).getTime()) / 1000;
    if (d < 60)        return `${Math.round(d)}s ago`;
    if (d < 3600)      return `${Math.round(d/60)}min ago`;
    if (d < 86400)     return `${Math.round(d/3600)}h ago`;
    return `${Math.round(d/86400)}d ago`;
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-medium text-slate-100">My test patients</h2>
        {rows.length > 0 && (
          <button onClick={onNew}
            className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500">
            + New from scratch
          </button>
        )}
      </div>
      {rows.length === 0 && (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-slate-800 bg-slate-900/60 px-8 py-12 text-center">
          <FlaskConical size={36} strokeWidth={1.2} className="text-slate-600" />
          <div>
            <h3 className="mb-1 text-base font-medium text-slate-300">No test patients yet.</h3>
            <p className="text-sm text-slate-500">
              Build one from scratch or clone a Synthea patient to get started.
            </p>
          </div>
          <button onClick={onNew}
            className="mt-1 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500">
            + New from scratch
          </button>
        </div>
      )}
      <ul className="divide-y divide-slate-800">
        {rows.map(r => (
          <li key={r.test_uuid} className="flex items-center gap-4 py-3 text-sm">
            <div className="flex-1">
              <div className="text-slate-100">{r.label}</div>
              <div className="text-xs text-slate-500">
                created {relative(r.created_at)} · {r.run_count} run{r.run_count === 1 ? "" : "s"}
                {r.last_run_at && ` · last run ${relative(r.last_run_at)}`}
                {r.source_uuid && ` · cloned from ${r.source_uuid.slice(0,11)}`}
              </div>
            </div>
            <button onClick={() => rerun(r.test_uuid)} disabled={busy === r.test_uuid}
              className="rounded-md bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-500 disabled:opacity-40">
              {r.last_run_at ? "Re-run" : "Run"}
            </button>
            <button onClick={() => onEdit(r.test_uuid)}
              className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800">
              Edit
            </button>
            <button onClick={() => remove(r.test_uuid)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

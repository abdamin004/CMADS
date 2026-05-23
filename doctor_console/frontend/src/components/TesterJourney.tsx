import { useEffect, useState } from "react";
import { PatientPicker }         from "./PatientPicker";
import { PatientBuilderEditor }  from "./PatientBuilderEditor";
import { MyTestPatientsList }    from "./MyTestPatientsList";
import { createTestPatient, getTestPatient, listTestPatients,
         startTestRun, updateTestPatient } from "../api";
import type { TestPatientPayload } from "../types";

const EMPTY: TestPatientPayload = {
  label: "",
  demographics: { age: 60, gender: "M" },
  conditions:   { active: [] },
  medications:  { active: [] },
  visits:       {},
  labs:         { latest_labs: [] },
  ground_truth: {},
};

type View = "splash" | "picker" | "editor" | "my-tests";

interface Props {
  onBack:        () => void;
  onRunStarted:  (taskId: string) => void;
}

export function TesterJourney({ onBack, onRunStarted }: Props) {
  const [view, setView]         = useState<View>("splash");
  const [payload, setPayload]   = useState<TestPatientPayload>(EMPTY);
  const [editingUuid, setEditingUuid] = useState<string | null>(null);
  const [saving, setSaving]     = useState(false);
  const [testCount, setTestCount] = useState(0);

  useEffect(() => { listTestPatients().then(rs => setTestCount(rs.length)); }, [view]);

  async function saveOnly(): Promise<string | null> {
    setSaving(true);
    try {
      if (editingUuid) {
        await updateTestPatient(editingUuid, payload);
        return editingUuid;
      }
      const created = await createTestPatient(payload);
      setEditingUuid(created.test_uuid);
      return created.test_uuid;
    } finally { setSaving(false); }
  }

  async function saveAndRun() {
    const uuid = await saveOnly();
    if (!uuid) return;
    const task = await startTestRun(uuid);
    onRunStarted(task.taskId);
  }

  async function startEdit(uuid: string) {
    const doc = await getTestPatient(uuid);
    setPayload({
      label: doc.label,
      source_uuid: doc.source_uuid,
      demographics: doc.demographics as any,
      conditions:   doc.conditions   as any,
      medications:  doc.medications  as any,
      visits:       doc.visits       as any,
      labs:         doc.labs         as any,
      ground_truth: doc.ground_truth as any,
    });
    setEditingUuid(uuid);
    setView("editor");
  }

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-slate-400 hover:text-slate-100">←</button>
          <h1 className="text-lg font-medium">Tester (build &amp; run)</h1>
        </div>
        <button onClick={() => setView("my-tests")}
          className="text-sm text-emerald-300 hover:text-emerald-200">
          My test patients ({testCount})
        </button>
      </header>

      {view === "splash" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <h2 className="text-2xl text-slate-100">How would you like to start?</h2>
          <div className="flex gap-4">
            <button
              onClick={() => { setPayload(EMPTY); setEditingUuid(null); setView("picker"); }}
              className="rounded-lg border border-slate-700 bg-slate-900 px-6 py-8 text-left hover:border-emerald-600">
              <div className="text-lg font-medium">Start from cohort</div>
              <div className="mt-1 text-sm text-slate-400">
                Filter the 3.3k Synthea patients by disease, age, and gender, preview, and clone one as a template.
              </div>
            </button>
            <button
              onClick={() => { setPayload(EMPTY); setEditingUuid(null); setView("editor"); }}
              className="rounded-lg border border-slate-700 bg-slate-900 px-6 py-8 text-left hover:border-emerald-600">
              <div className="text-lg font-medium">Start from scratch</div>
              <div className="mt-1 text-sm text-slate-400">
                Open an empty patient and fill in only the details that matter.
              </div>
            </button>
          </div>
        </div>
      )}

      {view === "picker" && (
        <div className="flex-1 overflow-hidden">
          <PatientPicker onTemplate={(p) => { setPayload({ ...EMPTY, ...p }); setView("editor"); }} />
        </div>
      )}

      {view === "editor" && (
        <div className="flex-1 overflow-hidden">
          <PatientBuilderEditor
            payload={payload}
            onChange={setPayload}
            onSaveDraft={saveOnly}
            onSaveAndRun={saveAndRun}
            saving={saving}
          />
        </div>
      )}

      {view === "my-tests" && (
        <div className="flex-1 overflow-y-auto">
          <MyTestPatientsList
            onEdit={startEdit}
            onRun={onRunStarted}
            onNew={() => { setPayload(EMPTY); setEditingUuid(null); setView("editor"); }}
          />
        </div>
      )}
    </div>
  );
}

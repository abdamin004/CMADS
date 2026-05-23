import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Filter, Pencil, FlaskConical, ClipboardList } from "lucide-react";
import { PatientPicker }         from "./PatientPicker";
import { PatientBuilderEditor }  from "./PatientBuilderEditor";
import { MyTestPatientsList }    from "./MyTestPatientsList";
import { createTestPatient, getTestPatient, listTestPatients,
         startTestRun, updateTestPatient } from "../api";
import type { TestPatientPayload } from "../types";

// Shared Framer Motion variants for sub-view cross-fades — mirrors App.tsx
const VIEW_VARIANTS = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -8 },
};
const VIEW_TRANSITION = { duration: 0.2, ease: "easeOut" as const };

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
  /** When "inline" the component skips its own header (back arrow + title +
   *  my-test-patients link) and renders only the body sub-router. The parent
   *  is responsible for placing those controls in its own chrome.
   *  Defaults to "full" (standalone TesterJourney header). */
  chrome?:       "full" | "inline";
  /** When chrome="inline" the parent can imperatively request a sub-view
   *  (e.g. deep-link from the "My test patients" link in the Doctor header). */
  initialView?:  View;
}

export function TesterJourney({ onBack, onRunStarted, chrome = "full", initialView }: Props) {
  const [view, setView]         = useState<View>(initialView ?? "splash");
  const [payload, setPayload]   = useState<TestPatientPayload>(EMPTY);
  const [editingUuid, setEditingUuid] = useState<string | null>(null);
  const [saving, setSaving]     = useState(false);
  const [testCount, setTestCount] = useState(0);

  // Allow the parent to flip the view from outside (e.g. deep-link from the
  // Doctor header's "My test patients" link).
  useEffect(() => {
    if (initialView) setView(initialView);
  }, [initialView]);

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

  // When chrome="inline" we render only the body; the wrapping <div> has no
  // fixed height so the parent's layout dictates the available space.
  const wrapClass = chrome === "inline"
    ? "flex flex-col text-slate-100"
    : "flex h-screen flex-col bg-slate-950 text-slate-100";

  return (
    <div className={wrapClass}>
      {chrome === "full" && (
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
      )}

      <AnimatePresence mode="wait">
        {view === "splash" && (
          <motion.div
            key="splash"
            variants={VIEW_VARIANTS}
            initial="initial" animate="animate" exit="exit"
            transition={VIEW_TRANSITION}
            className="flex flex-1 flex-col items-center justify-center gap-8 p-8"
          >
            <div className="text-center">
              <div className="mode-chooser__card-eyebrow mono mb-1">How would you like to start?</div>
              <h2 className="text-3xl font-medium text-slate-100" style={{ fontFamily: "Fraunces, serif", letterSpacing: "-0.02em" }}>
                Build a test patient.
              </h2>
            </div>
            <div className="flex gap-6" style={{ maxWidth: 840 }}>

              {/* Card 1 — Start from cohort */}
              <button
                type="button"
                onClick={() => { setPayload(EMPTY); setEditingUuid(null); setView("picker"); }}
                className="tester-splash__card tester-splash__card--cohort"
              >
                <div className="mode-chooser__card-head">
                  <div className="mode-chooser__card-icon" style={{ color: "var(--success)", borderColor: "var(--success)", background: "var(--success-soft)" }}>
                    <Filter size={28} strokeWidth={1.4} />
                  </div>
                  <span className="mode-chooser__card-eyebrow mono">Familiar starting point</span>
                </div>
                <h3 className="mode-chooser__card-title">Clone a known patient.</h3>
                <p className="mode-chooser__card-body">
                  Filter the 3,348-patient Synthea cohort by disease, age, and
                  gender. Preview, copy, edit — and run.
                </p>
                <ul className="mode-chooser__card-points">
                  <li><FlaskConical size={14} strokeWidth={1.6} /> Faceted browse · Disease + Age + Gender</li>
                  <li><Filter size={14} strokeWidth={1.6} /> Preview before you commit</li>
                  <li><ClipboardList size={14} strokeWidth={1.6} /> See the ground-truth diagnosis as you go</li>
                </ul>
                <span className="mode-chooser__card-cta" style={{ color: "var(--success)" }}>Browse the cohort →</span>
              </button>

              {/* Card 2 — Start from scratch */}
              <button
                type="button"
                onClick={() => { setPayload(EMPTY); setEditingUuid(null); setView("editor"); }}
                className="tester-splash__card tester-splash__card--scratch"
              >
                <div className="mode-chooser__card-head">
                  <div className="mode-chooser__card-icon" style={{ color: "var(--violet)", borderColor: "var(--violet)", background: "var(--violet-soft)" }}>
                    <Pencil size={28} strokeWidth={1.4} />
                  </div>
                  <span className="mode-chooser__card-eyebrow mono">Blank canvas</span>
                </div>
                <h3 className="mode-chooser__card-title">Sketch your own.</h3>
                <p className="mode-chooser__card-body">
                  Open an empty patient and fill in only the details that matter.
                  Autocomplete pulls from the cohort vocabulary so the agents still
                  recognise everything.
                </p>
                <ul className="mode-chooser__card-points">
                  <li><Pencil size={14} strokeWidth={1.6} /> Two-pane editor · navigator on the left</li>
                  <li><FlaskConical size={14} strokeWidth={1.6} /> Autocomplete · conditions, meds, labs</li>
                  <li><ClipboardList size={14} strokeWidth={1.6} /> Save &amp; run in one click</li>
                </ul>
                <span className="mode-chooser__card-cta" style={{ color: "var(--violet)" }}>Open the editor →</span>
              </button>
            </div>
          </motion.div>
        )}

        {view === "picker" && (
          <motion.div
            key="picker"
            variants={VIEW_VARIANTS}
            initial="initial" animate="animate" exit="exit"
            transition={VIEW_TRANSITION}
            className="flex-1 overflow-hidden"
          >
            <PatientPicker onTemplate={(p) => { setPayload({ ...EMPTY, ...p }); setView("editor"); }} />
          </motion.div>
        )}

        {view === "editor" && (
          <motion.div
            key="editor"
            variants={VIEW_VARIANTS}
            initial="initial" animate="animate" exit="exit"
            transition={VIEW_TRANSITION}
            className="flex-1 overflow-hidden"
          >
            <PatientBuilderEditor
              payload={payload}
              onChange={setPayload}
              onSaveDraft={saveOnly}
              onSaveAndRun={saveAndRun}
              saving={saving}
            />
          </motion.div>
        )}

        {view === "my-tests" && (
          <motion.div
            key="my-tests"
            variants={VIEW_VARIANTS}
            initial="initial" animate="animate" exit="exit"
            transition={VIEW_TRANSITION}
            className="flex-1 overflow-y-auto"
          >
            <MyTestPatientsList
              onEdit={startEdit}
              onRun={onRunStarted}
              onNew={() => { setPayload(EMPTY); setEditingUuid(null); setView("editor"); }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

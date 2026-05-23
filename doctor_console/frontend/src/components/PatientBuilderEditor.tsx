import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Check } from "lucide-react";
import { DemographicsForm } from "./tester/DemographicsForm";
import { ConditionsForm }   from "./tester/ConditionsForm";
import { MedicationsForm }  from "./tester/MedicationsForm";
import { LabsForm }         from "./tester/LabsForm";
import { VisitsForm }       from "./tester/VisitsForm";
import { GroundTruthForm }  from "./tester/GroundTruthForm";
import type { TestPatientPayload } from "../types";

type Section = "demographics" | "conditions" | "medications"
              | "labs" | "visits" | "ground_truth";

const SECTIONS: Array<[Section, string, (p: TestPatientPayload) => string]> = [
  ["demographics", "Demographics",
    (p) => `${p.demographics?.age ?? "?"} · ${p.demographics?.gender ?? "?"}`],
  ["conditions", "Active conditions",
    (p) => `${(p.conditions?.active ?? []).length} active`],
  ["medications", "Active medications",
    (p) => `${(p.medications?.active ?? []).length} active`],
  ["labs", "Recent labs",
    (p) => `${(p.labs?.latest_labs ?? []).length} labs`],
  ["visits", "Visits summary",
    (p) => `${(p.visits as { total?: number })?.total ?? 0} total`],
  ["ground_truth", "Ground truth",
    (p) => p.ground_truth?.target_condition?.name ?? "(blank)"],
];

interface Props {
  payload:     TestPatientPayload;
  onChange:    (p: TestPatientPayload) => void;
  onSaveDraft: () => void;
  onSaveAndRun: () => void;
  saving?:     boolean;
}

export function PatientBuilderEditor({ payload, onChange, onSaveDraft, onSaveAndRun, saving }: Props) {
  const [section, setSection] = useState<Section>("demographics");
  const [justSaved, setJustSaved] = useState(false);

  function patch<K extends keyof TestPatientPayload>(k: K, v: TestPatientPayload[K]) {
    onChange({ ...payload, [k]: v });
  }

  async function handleSaveAndRun() {
    await onSaveAndRun();
    // Brief "Pipeline started ✓" confirmation — visible for ~1 s before the
    // parent transitions to the running view.
    setJustSaved(true);
    setTimeout(() => setJustSaved(false), 1200);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        {/* LEFT: navigator */}
        <aside className="w-64 shrink-0 space-y-1 border-r border-slate-800 pr-3">
          <input type="text"
            className="mb-3 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            placeholder="Label (required)"
            value={payload.label}
            onChange={(e) => onChange({ ...payload, label: e.target.value })} />
          {SECTIONS.map(([key, title, summary]) => {
            const isActive = section === key;
            return (
              <button
                key={key}
                onClick={() => setSection(key)}
                aria-current={isActive ? "page" : undefined}
                className={`builder-nav__btn${isActive ? " builder-nav__btn--active" : ""}`}
              >
                <div className="font-medium">{title}</div>
                <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{summary(payload)}</div>
              </button>
            );
          })}
        </aside>
        {/* RIGHT: focused section */}
        <section className="flex-1 overflow-y-auto pr-2">
          {section === "demographics"  && <DemographicsForm value={payload.demographics}
              onChange={(v) => patch("demographics", v)} />}
          {section === "conditions"    && <ConditionsForm value={payload.conditions}
              onChange={(v) => patch("conditions", v)} />}
          {section === "medications"   && <MedicationsForm value={payload.medications}
              onChange={(v) => patch("medications", v)} />}
          {section === "labs"          && <LabsForm value={payload.labs}
              onChange={(v) => patch("labs", v)} />}
          {section === "visits"        && <VisitsForm value={payload.visits}
              onChange={(v) => patch("visits", v)} />}
          {section === "ground_truth"  && <GroundTruthForm value={payload.ground_truth}
              onChange={(v) => patch("ground_truth", v)} />}
        </section>
      </div>
      {/* BOTTOM action bar */}
      <div className="flex items-center justify-end gap-3 border-t border-slate-800 bg-slate-950 px-4 py-3">
        <button onClick={onSaveDraft} disabled={saving || !payload.label}
          className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40">
          Save draft
        </button>
        <button onClick={handleSaveAndRun} disabled={saving || !payload.label}
          className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40">
          <AnimatePresence mode="wait" initial={false}>
            {saving ? (
              <motion.span
                key="saving"
                className="inline-flex items-center gap-2"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}
                  className="inline-flex"
                >
                  <Loader2 size={14} strokeWidth={2} />
                </motion.span>
                Saving…
              </motion.span>
            ) : justSaved ? (
              <motion.span
                key="saved"
                className="inline-flex items-center gap-2"
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <Check size={14} strokeWidth={2.5} />
                Pipeline started
              </motion.span>
            ) : (
              <motion.span
                key="idle"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                Save &amp; run pipeline →
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </div>
  );
}

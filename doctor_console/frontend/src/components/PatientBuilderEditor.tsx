import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Check, ChevronRight, ChevronDown } from "lucide-react";
import { DemographicsForm } from "./tester/DemographicsForm";
import { ConditionsForm }   from "./tester/ConditionsForm";
import { MedicationsForm }  from "./tester/MedicationsForm";
import { LabsForm }         from "./tester/LabsForm";
import { GroundTruthForm }  from "./tester/GroundTruthForm";
import { AdvancedSettings } from "./runtime/AdvancedSettings";
import type { AdvancedSettingsValue } from "./runtime/AdvancedSettings";
import type { TestPatientPayload } from "../types";

// "Visits summary" intentionally NOT in the editor navigator: visit counts
// are low signal for the agents' diagnostic reasoning and high friction for
// a clinician sketching a patient. The TestPatient document still carries
// payload.visits (so cloned cohort patients keep their visit history on
// the saved doc) — the editor just doesn't surface it.
type Section = "demographics" | "conditions" | "medications"
              | "labs" | "ground_truth";

const SECTIONS: Array<[Section, string, (p: TestPatientPayload) => string]> = [
  ["demographics", "Demographics",
    (p) => `${p.demographics?.age ?? "?"} · ${p.demographics?.gender ?? "?"}`],
  ["conditions", "Active conditions",
    (p) => `${(p.conditions?.active ?? []).length} active`],
  ["medications", "Active medications",
    (p) => `${(p.medications?.active ?? []).length} active`],
  ["labs", "Recent labs",
    (p) => `${(p.labs?.latest_labs ?? []).length} labs`],
  ["ground_truth", "Ground truth",
    (p) => p.ground_truth?.target_condition?.name ?? "(blank)"],
];

interface Props {
  payload:      TestPatientPayload;
  onChange:     (p: TestPatientPayload) => void;
  onSaveDraft:  () => void;
  onSaveAndRun: (opts?: AdvancedSettingsValue) => void;
  saving?:      boolean;
}

export function PatientBuilderEditor({ payload, onChange, onSaveDraft, onSaveAndRun, saving }: Props) {
  const [section, setSection] = useState<Section>("demographics");
  const [justSaved, setJustSaved] = useState(false);
  // Track whether user has unsaved changes (any field touched)
  const [dirty, setDirty] = useState(false);
  // Advanced run settings (model preset + top-K + accuracy mode)
  const [adv, setAdv] = useState<AdvancedSettingsValue>({
    presetId:     "",
    topK:         5,
    accuracyMode: "recommended",
  });
  const [advancedOpen, setAdvancedOpen] = useState(false);

  function patch<K extends keyof TestPatientPayload>(k: K, v: TestPatientPayload[K]) {
    onChange({ ...payload, [k]: v });
    setDirty(true);
  }

  function handleLabelChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...payload, label: e.target.value });
    setDirty(true);
  }

  async function handleSaveDraft() {
    await onSaveDraft();
    setDirty(false);
  }

  async function handleSaveAndRun() {
    await onSaveAndRun(adv);
    setDirty(false);
    // Brief "Pipeline started ✓" confirmation — visible for ~600ms before the
    // parent transitions to the running view.
    setJustSaved(true);
    setTimeout(() => setJustSaved(false), 600);
  }

  const canSave = !!payload.label && !saving;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        {/* LEFT: navigator */}
        <aside className="w-64 shrink-0 space-y-1 border-r border-slate-800 pr-3">
          <input type="text"
            className="mb-3 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="Label (required)"
            value={payload.label}
            onChange={handleLabelChange} />
          {SECTIONS.map(([key, title, summary]) => {
            const isActive = section === key;
            return (
              <button
                key={key}
                onClick={() => setSection(key)}
                aria-current={isActive ? "page" : undefined}
                className={`builder-nav__btn${isActive ? " builder-nav__btn--active" : ""}`}
              >
                <div className="builder-nav__btn-row">
                  <div className="builder-nav__btn-title">{title}</div>
                  {isActive && (
                    <ChevronRight size={13} strokeWidth={2.2} className="builder-nav__btn-chevron" />
                  )}
                </div>
                <div className={`mt-0.5 line-clamp-2 text-xs builder-nav__btn-summary${isActive ? " builder-nav__btn-summary--active" : ""}`}>
                  {summary(payload)}
                </div>
              </button>
            );
          })}
        </aside>
        {/* RIGHT: focused section — animated on section switch */}
        <section className="flex-1 overflow-y-auto pr-2">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={section}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              {section === "demographics"  && <DemographicsForm value={payload.demographics}
                  onChange={(v) => patch("demographics", v)} />}
              {section === "conditions"    && <ConditionsForm value={payload.conditions}
                  onChange={(v) => patch("conditions", v)} />}
              {section === "medications"   && <MedicationsForm value={payload.medications}
                  onChange={(v) => patch("medications", v)} />}
              {section === "labs"          && <LabsForm value={payload.labs}
                  onChange={(v) => patch("labs", v)} />}
              {section === "ground_truth"  && <GroundTruthForm value={payload.ground_truth}
                  onChange={(v) => patch("ground_truth", v)} />}
            </motion.div>
          </AnimatePresence>
        </section>
      </div>
      {/* Advanced settings disclosure — sits above the action bar */}
      <div className="border-t border-slate-800 bg-slate-950">
        <button
          type="button"
          className="flex w-full items-center gap-2 px-4 py-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          onClick={() => setAdvancedOpen((o) => !o)}
          aria-expanded={advancedOpen}
        >
          <ChevronDown
            size={13}
            strokeWidth={2}
            className={`transition-transform duration-200${advancedOpen ? " rotate-180" : ""}`}
          />
          <span className="mono">Advanced settings</span>
          {!advancedOpen && adv.presetId && (
            <span className="ml-1 text-slate-500 mono">
              · {adv.presetId} · Top {adv.topK}
            </span>
          )}
        </button>
        <AnimatePresence initial={false}>
          {advancedOpen && (
            <motion.div
              key="adv"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-3">
                <AdvancedSettings value={adv} onChange={setAdv} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* BOTTOM action bar */}
      <div className="flex items-center justify-end gap-3 border-t border-slate-800 bg-slate-950 px-4 py-3">
        {/* Save for later */}
        <div className="relative inline-flex items-center gap-2">
          {/* Unsaved-changes dot — pulses when dirty and label is set */}
          {dirty && payload.label && (
            <motion.span
              className="absolute -left-4 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-emerald-400"
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
            />
          )}
          <button onClick={handleSaveDraft} disabled={!canSave}
            className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 hover:border-slate-600 transition-colors disabled:opacity-40">
            Save for later
          </button>
        </div>
        {/* Save & run pipeline */}
        <button
          onClick={handleSaveAndRun}
          disabled={!canSave}
          className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white
                     hover:bg-emerald-500 hover:shadow-lg hover:shadow-emerald-600/20
                     focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 focus-visible:outline-none
                     transition-all disabled:opacity-40"
        >
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

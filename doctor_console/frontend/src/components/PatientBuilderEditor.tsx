import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Check, ChevronRight, ChevronDown } from "lucide-react";
import { DemographicsForm } from "./tester/DemographicsForm";
import { ConditionsForm }   from "./tester/ConditionsForm";
import { MedicationsForm }  from "./tester/MedicationsForm";
import { LabsForm }         from "./tester/LabsForm";
import { SmartImportModal } from "./SmartImportModal";
import { PreviewMergeModal } from "./PreviewMergeModal";
import { AdvancedSettings } from "./runtime/AdvancedSettings";
import type { AdvancedSettingsValue } from "./runtime/AdvancedSettings";
import { getModelPresets } from "../api";
import type { ExtractResponse, ModelPreset, TestPatientPayload } from "../types";

// "Visits summary" intentionally NOT in the editor navigator: visit counts
// are low signal for the agents' diagnostic reasoning and high friction for
// a clinician sketching a patient. The TestPatient document still carries
// payload.visits (so cloned cohort patients keep their visit history on
// the saved doc) — the editor just doesn't surface it.
// "Ground truth" is also intentionally NOT in the navigator: this editor is
// for testing (second-opinion), not evaluation — there is no known target
// disease. Cloned cohort patients still carry ground_truth in the saved doc
// for the audit trail, but the clinician doesn't see or edit it here.
type Section = "demographics" | "conditions" | "medications" | "labs";

const SECTIONS: Array<[Section, string, (p: TestPatientPayload) => string]> = [
  ["demographics", "Demographics",
    (p) => `${p.demographics?.age ?? "?"} · ${p.demographics?.gender ?? "?"}`],
  ["conditions", "Active conditions",
    (p) => `${(p.conditions?.active ?? []).length} active`],
  ["medications", "Active medications",
    (p) => `${(p.medications?.active ?? []).length} active`],
  ["labs", "Recent labs",
    (p) => `${(p.labs?.latest_labs ?? []).length} labs`],
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
  // Smart Import modal state — triggered from inside the Recent labs tab.
  // The modal flow is: SmartImportModal (paste / file / image) → extract →
  // PreviewMergeModal (per-row checkboxes) → merge into payload.
  const [showSmartImport, setShowSmartImport] = useState(false);
  const [extractResult,   setExtractResult]   = useState<ExtractResponse | null>(null);
  const [showPreview,     setShowPreview]     = useState(false);
  // Fetch preset list to resolve a friendly label for the summary string —
  // identical pattern to RuntimeHero so the Known and Build/clone paths read
  // the same way in the collapsed summary.
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  useEffect(() => {
    (async () => {
      try { setPresets(await getModelPresets()); } catch { setPresets([]); }
    })();
  }, []);
  const selectedPreset = presets.find((p) => p.id === adv.presetId);
  const advancedSummary = useMemo(() => {
    const modelLabel = selectedPreset?.label ?? "default model";
    return `${modelLabel} · Top ${adv.topK}`;
  }, [selectedPreset, adv.topK]);

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
                  onChange={(v) => patch("labs", v)}
                  onSmartImport={() => setShowSmartImport(true)} />}
            </motion.div>
          </AnimatePresence>
        </section>
      </div>
      {/* Advanced settings disclosure — same markup + classes as RuntimeHero so
          the Known and Build/clone paths render identically. */}
      <div className="border-t border-slate-800 bg-slate-950 px-4 py-2">
        <details
          className="runtime-solo__advanced"
          open={advancedOpen}
          onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="runtime-solo__advanced-summary">
            <ChevronDown size={14} strokeWidth={1.9} className="runtime-solo__advanced-caret" />
            <span className="runtime-solo__advanced-label">Advanced settings</span>
            <span className="runtime-solo__advanced-current mono">{advancedSummary}</span>
          </summary>
          <AdvancedSettings value={adv} onChange={setAdv} />
        </details>
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

      {/* Smart Import modals — triggered from the Recent labs tab.
          The user can paste text, drop a PDF/FHIR JSON, or snap a photo of
          a lab slip; results merge into the current payload via the
          preview-with-checkboxes modal. */}
      <AnimatePresence>
        {showSmartImport && (
          <SmartImportModal
            key="smart-import-modal"
            onClose={() => setShowSmartImport(false)}
            onExtract={(r) => {
              setExtractResult(r);
              setShowSmartImport(false);
              setShowPreview(true);
            }}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {showPreview && extractResult && (
          <PreviewMergeModal
            key="preview-merge-modal"
            result={extractResult}
            current={payload}
            onCancel={() => { setShowPreview(false); setExtractResult(null); }}
            onMerge={(merged) => {
              onChange(merged);
              setDirty(true);
              setShowPreview(false);
              setExtractResult(null);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

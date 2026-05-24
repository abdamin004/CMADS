import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Check, ChevronRight, Settings2, X } from "lucide-react";
import { DemographicsForm } from "./tester/DemographicsForm";
import { ConditionsForm }   from "./tester/ConditionsForm";
import { MedicationsForm }  from "./tester/MedicationsForm";
import { LabsForm }         from "./tester/LabsForm";
import { SmartImportModal } from "./SmartImportModal";
import { PreviewMergeModal } from "./PreviewMergeModal";
import { AdvancedSettings, buildPrecisionRows } from "./runtime/AdvancedSettings";
import type { AdvancedSettingsValue } from "./runtime/AdvancedSettings";
import { getModelPresets, getStatsOverview } from "../api";
import type { ExtractResponse, ModelPreset, RankBucket, TestPatientPayload } from "../types";

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

  // Cohort-wide rank distribution (same data RuntimeHero shows). For a
  // custom patient there is no target disease, so we use the overall
  // mas_results precision — "across the whole cohort, X% of the time the
  // right diagnosis was in the top K". Lets the Top-K picker render the
  // same trust signal as the Known-patient flow.
  const [precision, setPrecision] = useState<{ buckets: RankBucket[]; n: number } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const data = await getStatsOverview("multi_level");
        setPrecision({ buckets: data.rankDistribution, n: data.aggregates.n });
      } catch { setPrecision(null); }
    })();
  }, []);
  const precisionRows = useMemo(
    () => precision ? buildPrecisionRows(precision.buckets, precision.n) : [],
    [precision],
  );

  // Escape closes the Advanced settings drawer.
  useEffect(() => {
    if (!advancedOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setAdvancedOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advancedOpen]);

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

  // Section titles + sub-copy for the form header — same source of truth
  // as the navigator labels (SECTIONS) so a change in one flows to the other.
  const SECTION_HEAD: Record<Section, { title: string; sub: string }> = {
    demographics: {
      title: "Demographics",
      sub: "Age, gender, and demographics. The seven-agent pipeline reads this as the patient's baseline.",
    },
    conditions: {
      title: "Active conditions",
      sub: "Diagnoses already known at the data-cutoff date. The diagnostic-reasoning agent uses these to constrain the differential.",
    },
    medications: {
      title: "Active medications",
      sub: "Drugs the patient is currently on. The pipeline cross-checks every proposed diagnosis against this list.",
    },
    labs: {
      title: "Recent labs",
      sub: "The lab interpreter agent reads these as its primary evidence. Paste a lab slip to import quickly.",
    },
  };
  const head = SECTION_HEAD[section];

  return (
    // The editor is a designed editing surface — centered to a comfortable
    // max-width so it does not sprawl off the left of a wide viewport,
    // and divided into three columns: navigator, form, and breathing
    // room. Each form section opens with a serif heading + a one-line
    // sub-copy so the page reads as the editor for this patient, not a
    // floating panel of inputs.
    <div className="patient-builder flex h-full flex-col">
      <div className="patient-builder__body flex flex-1 min-h-0 overflow-hidden">
        <div className="patient-builder__inner flex flex-1 min-h-0 gap-10 overflow-hidden px-10 lg:px-14 py-8">
          {/* LEFT: navigator */}
          <aside className="patient-builder__nav w-64 shrink-0 space-y-1">
            <input type="text"
              className="patient-builder__label-input mb-4 w-full rounded-md px-3 py-2 text-sm focus:outline-none"
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
          {/* CENTER: focused section — animated on section switch */}
          <section className="patient-builder__section flex-1 min-w-0 overflow-y-auto">
            <div className="patient-builder__section-body">
              <header className="patient-builder__section-head">
                <h2 className="patient-builder__section-title">{head.title}</h2>
                <p className="patient-builder__section-sub">{head.sub}</p>
              </header>
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
            </div>
          </section>
          {/* RIGHT RAIL: live patient summary — visible on wide viewports.
              Gives the page a designed third region and shows the user
              what the agents will read as they type. */}
          <aside className="patient-builder__summary">
            <div className="patient-builder__summary-card">
              <div className="patient-builder__summary-eyebrow">Patient at a glance</div>
              <div className="patient-builder__summary-row">
                <span className="patient-builder__summary-row-label">Label</span>
                <span className={`patient-builder__summary-row-value${!payload.label ? " patient-builder__summary-row-value--muted" : ""}`}>
                  {payload.label || "(unnamed)"}
                </span>
              </div>
              <div className="patient-builder__summary-row">
                <span className="patient-builder__summary-row-label">Age · Gender</span>
                <span className="patient-builder__summary-row-value">
                  {payload.demographics?.age ?? "?"} · {payload.demographics?.gender ?? "?"}
                </span>
              </div>
              {payload.demographics?.race && (
                <div className="patient-builder__summary-row">
                  <span className="patient-builder__summary-row-label">Race</span>
                  <span className="patient-builder__summary-row-value">{payload.demographics.race}</span>
                </div>
              )}
              {payload.demographics?.bmi != null && (
                <div className="patient-builder__summary-row">
                  <span className="patient-builder__summary-row-label">BMI</span>
                  <span className="patient-builder__summary-row-value">{payload.demographics.bmi}</span>
                </div>
              )}
              <div className="patient-builder__summary-row">
                <span className="patient-builder__summary-row-label">Active conditions</span>
                <span className="patient-builder__summary-row-value">
                  {(payload.conditions?.active ?? []).length}
                </span>
              </div>
              <div className="patient-builder__summary-row">
                <span className="patient-builder__summary-row-label">Active medications</span>
                <span className="patient-builder__summary-row-value">
                  {(payload.medications?.active ?? []).length}
                </span>
              </div>
              <div className="patient-builder__summary-row">
                <span className="patient-builder__summary-row-label">Recent labs</span>
                <span className="patient-builder__summary-row-value">
                  {(payload.labs?.latest_labs ?? []).length}
                </span>
              </div>
              <p className="patient-builder__summary-hint">
                This is the snapshot the seven-agent pipeline will read when you
                click <strong>Save &amp; run pipeline</strong>.
              </p>
            </div>
          </aside>
        </div>
      </div>
      {/* BOTTOM action bar — combined: advanced settings trigger + save
          actions in a single horizontal row, full editor width. */}
      <div className="patient-builder__actions flex items-center justify-between gap-3 px-10 lg:px-14 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={() => setAdvancedOpen(true)}
            className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-transparent px-3 py-2 text-sm text-slate-200 hover:bg-slate-800/50 hover:border-slate-600 transition-colors"
          >
            <Settings2 size={14} strokeWidth={1.7} />
            Advanced settings
          </button>
          <span className="mono text-xs text-slate-500 truncate" title={advancedSummary}>
            {advancedSummary}
          </span>
        </div>
        <div className="flex items-center gap-3">
        {/* Save for later */}
        <div className="relative inline-flex items-center gap-2">
          {/* Unsaved-changes dot — pulses when dirty and label is set */}
          {dirty && payload.label && (
            <motion.span
              className="patient-builder__dirty-dot absolute -left-4 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full"
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
            />
          )}
          <button onClick={handleSaveDraft} disabled={!canSave}
            className="patient-builder__btn patient-builder__btn--ghost rounded-md px-3 py-2 text-sm transition-colors disabled:opacity-40">
            Save for later
          </button>
        </div>
        {/* Save & run pipeline */}
        <button
          onClick={handleSaveAndRun}
          disabled={!canSave}
          className="patient-builder__btn patient-builder__btn--primary inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all disabled:opacity-40 focus-visible:outline-none"
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

      {/* Advanced settings slide-over panel. Opens from the right with a
          fixed width on desktop / full-width on small screens; backdrop dims
          the page so the user knows where they are. Close via the X button,
          the backdrop click, or Escape. */}
      <AnimatePresence>
        {advancedOpen && (
          <>
            <motion.div
              key="adv-backdrop"
              className="fixed inset-0 z-40 bg-slate-950/60"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={() => setAdvancedOpen(false)}
            />
            <motion.aside
              key="adv-drawer"
              role="dialog"
              aria-label="Advanced settings"
              className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-slate-800 bg-slate-950 shadow-2xl shadow-black/60"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
            >
              <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
                <div className="flex items-center gap-2">
                  <Settings2 size={16} strokeWidth={1.7} className="text-emerald-400" />
                  <h2 className="text-base font-medium text-slate-100">Advanced settings</h2>
                </div>
                <button
                  type="button"
                  onClick={() => setAdvancedOpen(false)}
                  aria-label="Close advanced settings"
                  className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
                >
                  <X size={16} strokeWidth={1.8} />
                </button>
              </header>
              <div className="flex-1 overflow-y-auto px-5 py-4">
                <AdvancedSettings
                  value={adv}
                  onChange={setAdv}
                  precisionRows={precisionRows}
                  precisionN={precision?.n}
                />
              </div>
              <footer className="border-t border-slate-800 px-5 py-3">
                <button
                  type="button"
                  onClick={() => setAdvancedOpen(false)}
                  className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 transition-colors"
                >
                  Done
                </button>
              </footer>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

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

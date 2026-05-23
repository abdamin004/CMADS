import { AlertTriangle, BookOpen, ChevronRight, FlaskConical, HeartPulse, Info, ListChecks, Pill, Stethoscope, TestTube2, FileJson, User, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { PatientResult } from "../types";

type Props = {
  result: PatientResult;
};

export function PatientEvidence({ result }: Props) {
  const ehrCase = result.case.ehrCase;
  const labCase = result.case.labCase;
  const activeConditions = readArray(readRecord(ehrCase.conditions)?.active);
  const activeMeds = readArray(readRecord(ehrCase.medications)?.active);
  const vitals = readArray(labCase.recent_vitals);
  const latestLabs = readArray(labCase.latest_labs);
  const criticalFlags = readArray(readRecord(labCase.critical_flags)?.flags);
  const demo = readRecord(ehrCase.demographics) ?? {};
  const comorbidity = readRecord(ehrCase.comorbidity) ?? {};
  const riskScores = readRecord(ehrCase.risk_scores) ?? {};

  const [showRawJson, setShowRawJson] = useState(false);

  // Maps an evidence category name → the full unsliced list to render in
  // the slide-over drawer. Each category card calls openDrawer with its
  // own data; the drawer renders whatever's there until closed.
  type DrawerData = { title: string; icon: ReactNode; items: Array<{ main: string; meta: string }> } | null;
  const [drawer, setDrawer] = useState<DrawerData>(null);
  useEffect(() => {
    if (!drawer) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setDrawer(null); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  // Per-category mappers — used both inline (first 6) and in the drawer (all).
  const conditionItems = activeConditions.map((item) => ({
    main: String(item.condition || item.name || "Condition"),
    meta: [item.start_date, item.code].filter(Boolean).join(" | "),
  }));
  const flagItems = criticalFlags.map((item) => ({
    main: String(item.lab_name || item.test_name || "Critical flag"),
    meta: `${String(item.value ?? "")} ${String(item.units ?? item.unit ?? "")} | ${String(item.flag ?? "")}`,
  }));
  const vitalItems = vitals.map((item) => ({
    main: String(item.vital || "Vital"),
    meta: `${String(item.value ?? "")} ${String(item.units ?? item.unit ?? "")} | ${String(item.date ?? "")}`,
  }));
  const labItems = latestLabs.map((item) => ({
    main: String(item.lab_name || item.test_name || "Lab"),
    meta: `${String(item.value ?? "")} ${String(item.units ?? item.unit ?? "")} | ${String(item.date ?? "")}`,
  }));

  return (
    <>
      <section className="panel evidence-panel" data-demo-anchor="patient-input">
      <div className="panel-heading">
        <div>
          <h2>Your patient at a glance</h2>
          <p>
            {activeConditions.length} active condition{activeConditions.length === 1 ? "" : "s"} ·{" "}
            {activeMeds.length} medication{activeMeds.length === 1 ? "" : "s"} on the chart ·{" "}
            {criticalFlags.length} critical flag{criticalFlags.length === 1 ? "" : "s"}
          </p>
        </div>
        <button
          type="button"
          className="json-toggle"
          onClick={() => setShowRawJson((v) => !v)}
          data-demo-anchor="patient-input-json-toggle"
        >
          <FileJson size={14} />
          {showRawJson ? "Hide raw data" : "Show raw data"}
        </button>
      </div>

      <div className="demographics-strip">
        <User size={14} />
        <span>
          {String(demo.age ?? "?")} y/o
          {demo.gender ? ` · ${String(demo.gender)}` : ""}
          {demo.race ? ` · ${String(demo.race)}` : ""}
          {Object.keys(comorbidity).length > 0
            ? ` · comorbidity flags: ${Object.entries(comorbidity)
                .filter(([, v]) => v === true || v === "true")
                .map(([k]) => k.replace(/_/g, " "))
                .slice(0, 4)
                .join(", ") || "none truthy"}`
            : ""}
          {Object.keys(riskScores).length > 0
            ? ` · risk scores: ${Object.keys(riskScores).slice(0, 3).join(", ")}`
            : ""}
        </span>
      </div>

      <div className="evidence-grid">
        <EvidenceList
          icon={<ListChecks size={17} />}
          title="Active problems"
          items={conditionItems}
          empty="No active problems recorded."
          onOpen={() => setDrawer({ title: "Active problems", icon: <ListChecks size={17} />, items: conditionItems })}
        />
        <EvidenceList
          icon={<AlertTriangle size={17} />}
          title="Critical flags"
          items={flagItems}
          empty="No critical flags saved."
          onOpen={() => setDrawer({ title: "Critical flags", icon: <AlertTriangle size={17} />, items: flagItems })}
        />
        <EvidenceList
          icon={<HeartPulse size={17} />}
          title="Recent vitals"
          items={vitalItems}
          empty="No recent vitals saved."
          onOpen={() => setDrawer({ title: "Recent vitals", icon: <HeartPulse size={17} />, items: vitalItems })}
        />
        <EvidenceList
          icon={<TestTube2 size={17} />}
          title="Latest labs"
          items={labItems}
          empty="No latest labs saved."
          onOpen={() => setDrawer({ title: "Latest labs", icon: <TestTube2 size={17} />, items: labItems })}
        />
      </div>

      {/* Drawer: opens when any of the four evidence cards is pressed and
          shows every item in that category (no slice cap). Same right-side
          slide-over pattern used for Advanced settings — close via X, the
          backdrop click, or Escape. */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div
              key="ev-backdrop"
              className="fixed inset-0 z-40 bg-slate-950/60"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={() => setDrawer(null)}
            />
            <motion.aside
              key="ev-drawer"
              role="dialog"
              aria-label={drawer.title}
              className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-slate-800 bg-slate-950 shadow-2xl shadow-black/60"
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
            >
              <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
                <div className="flex items-center gap-2 text-slate-100">
                  <span className="text-emerald-400">{drawer.icon}</span>
                  <h2 className="text-base font-medium">{drawer.title}</h2>
                  <span className="ml-2 mono text-xs text-slate-500">{drawer.items.length} {drawer.items.length === 1 ? "row" : "rows"}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setDrawer(null)}
                  aria-label={`Close ${drawer.title}`}
                  className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
                >
                  <X size={16} strokeWidth={1.8} />
                </button>
              </header>
              <div className="flex-1 overflow-y-auto px-5 py-3">
                {drawer.items.length === 0 ? (
                  <div className="rounded-md border border-dashed border-slate-700 px-4 py-6 text-center text-sm text-slate-500">
                    Nothing recorded.
                  </div>
                ) : (
                  <ul className="divide-y divide-slate-800">
                    {drawer.items.map((item, i) => (
                      <li key={`${item.main}-${i}`} className="py-2.5">
                        <div className="text-sm font-medium text-slate-100 break-words">{item.main}</div>
                        <div className="mt-0.5 font-mono text-xs text-slate-400 break-words">{item.meta || "not dated"}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {showRawJson ? (
        <div className="raw-json-grid" data-demo-anchor="patient-input-json">
          <details open>
            <summary><FileJson size={14} /> ehr_case.json</summary>
            <pre className="raw-json">{JSON.stringify(ehrCase, null, 2)}</pre>
          </details>
          <details open>
            <summary><FileJson size={14} /> lab_case.json</summary>
            <pre className="raw-json">{JSON.stringify(labCase, null, 2)}</pre>
          </details>
        </div>
      ) : null}
    </section>
    </>
  );
}

/**
 * Master-detail explainer — left column lists data categories as selectable
 * cards, right column shows the selected card's plain-English description
 * plus a structured field table. Patient-independent: this is the schema,
 * not the record.
 */
export function DataStructureExplainer() {
  const [selectedId, setSelectedId] = useState<string>(DATA_FIELDS[0].id);
  const selected = DATA_FIELDS.find((f) => f.id === selectedId) ?? DATA_FIELDS[0];
  return (
    <details className="panel data-explainer" open>
      <summary className="data-explainer__head">
        <Info size={15} strokeWidth={1.8} />
        <span>What information does the system read for every patient?</span>
        <span className="data-explainer__head-toggle" aria-hidden="true">▾</span>
      </summary>
      <div className="data-explainer__layout">
        <ul className="data-explainer__list" role="tablist" aria-label="Data categories">
          {DATA_FIELDS.map((field) => {
            const isActive = field.id === selectedId;
            return (
              <li key={field.id} role="presentation">
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  aria-controls="data-explainer-detail"
                  className={`data-explainer__item${isActive ? " is-active" : ""}`}
                  onClick={() => setSelectedId(field.id)}
                >
                  <span className="data-explainer__item-icon">{field.icon}</span>
                  <span className="data-explainer__item-meta">
                    <strong>{field.name}</strong>
                    <em>{field.tagline}</em>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <div
          className="data-explainer__detail"
          id="data-explainer-detail"
          role="tabpanel"
          aria-live="polite"
        >
          <header className="data-explainer__detail-head">
            <span className="data-explainer__detail-icon">{selected.icon}</span>
            <div>
              <h3>{selected.name}</h3>
              <p className="data-explainer__detail-tagline">{selected.tagline}</p>
            </div>
          </header>
          <p className="data-explainer__detail-why">{selected.why}</p>
          <div className="data-explainer__detail-table">
            <div className="data-explainer__detail-eyebrow eyebrow">
              {selected.shape === "array"
                ? `One row per item — each contains these fields`
                : "The data has these fields"}
            </div>
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Type</th>
                  <th>What it means</th>
                </tr>
              </thead>
              <tbody>
                {selected.fields.map((row) => (
                  <tr key={row.key}>
                    <td><code className="mono">{row.key}</code></td>
                    <td className="data-explainer__detail-type">{row.type}</td>
                    <td>{row.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </details>
  );
}

type DataFieldSpec = {
  id: string;
  icon: ReactNode;
  name: string;
  tagline: string;
  why: string;
  /** "object" = a single record with keyed fields. "array" = a list of items each with these fields. */
  shape: "object" | "array";
  fields: Array<{ key: string; type: string; desc: string }>;
};

const DATA_FIELDS: DataFieldSpec[] = [
  {
    id: "demographics",
    icon: <User size={16} />,
    name: "Demographics",
    tagline: "Who the patient is",
    why: "Age, sex, race, and ethnicity. The system uses these to pick the right reference ranges (such as eGFR), choose age-appropriate guideline pathways, and watch for sex-specific drug dosing.",
    shape: "object",
    fields: [
      { key: "age",       type: "years",   desc: "Patient age at the case cutoff date." },
      { key: "gender",    type: "M / F",   desc: "Recorded sex — drives sex-specific thresholds and dosing." },
      { key: "race",      type: "string",  desc: "Self-reported race; used in some risk-score formulas." },
      { key: "ethnicity", type: "string",  desc: "Hispanic / non-Hispanic, where recorded." },
    ],
  },
  {
    id: "conditions",
    icon: <Stethoscope size={16} />,
    name: "Active conditions",
    tagline: "What's on the problem list",
    why: "The patient's open diagnoses with onset dates. The progression over time — for instance CKD stage 1 → stage 3 → end-stage renal disease — is usually the strongest single clue the system has.",
    shape: "array",
    fields: [
      { key: "condition",  type: "string", desc: "Plain-language diagnosis name." },
      { key: "code",       type: "SNOMED", desc: "Standardised SNOMED-CT code so the system recognises synonyms." },
      { key: "start_date", type: "ISO date", desc: "When this diagnosis first appeared on the chart." },
      { key: "status",     type: "string", desc: "Active vs. resolved (only active conditions reach the agents)." },
    ],
  },
  {
    id: "medications",
    icon: <Pill size={16} />,
    name: "Medications",
    tagline: "What they are currently taking",
    why: "Active drug list. Tells the system what is already being managed (metformin points to diabetes; an ACE inhibitor points to hypertension or renal protection), and is later checked for interactions and contraindications when the treatment plan is built.",
    shape: "array",
    fields: [
      { key: "medication", type: "string", desc: "Drug name (generic preferred)." },
      { key: "dose",       type: "string", desc: "Strength and unit, e.g. 10 mg." },
      { key: "frequency",  type: "string", desc: "How often — once daily, b.i.d., as needed, etc." },
      { key: "class",      type: "string", desc: "Therapeutic class (statin, ACE-i, biguanide, …)." },
      { key: "start_date", type: "ISO date", desc: "When the prescription started." },
    ],
  },
  {
    id: "vitals",
    icon: <HeartPulse size={16} />,
    name: "Recent vitals",
    tagline: "Blood pressure, heart rate, weight, oxygen",
    why: "The most recent bedside numbers. They pick up the acute picture — for example uncontrolled blood pressure or decompensated heart failure — that the problem list alone may not show.",
    shape: "array",
    fields: [
      { key: "vital", type: "string",   desc: "What was measured (BP, HR, weight, SpO₂, …)." },
      { key: "value", type: "number",   desc: "The numeric reading." },
      { key: "units", type: "string",   desc: "Units — mm Hg, bpm, kg, %, etc." },
      { key: "date",  type: "ISO date", desc: "When the measurement was taken." },
    ],
  },
  {
    id: "labs",
    icon: <TestTube2 size={16} />,
    name: "Latest labs",
    tagline: "The most recent lab numbers",
    why: "Key results such as eGFR, HbA1c, lipids, electrolytes, and troponin, with their values, units, and dates. The Lab Interpreter agent reads each line and notes anything outside the expected range.",
    shape: "array",
    fields: [
      { key: "lab_name",        type: "string",  desc: "The lab analyte (eGFR, HbA1c, K, troponin, …)." },
      { key: "value",           type: "number",  desc: "The measured value." },
      { key: "units",           type: "string",  desc: "Reporting units — mg/dL, mmol/L, %, mL/min/1.73m², …" },
      { key: "date",            type: "ISO date", desc: "When the sample was drawn." },
      { key: "reference_range", type: "string",  desc: "Lab's normal range, if reported." },
      { key: "flag",            type: "string",  desc: "H / L / Critical, when the lab flagged it." },
    ],
  },
  {
    id: "critical_flags",
    icon: <AlertTriangle size={16} />,
    name: "Critical flags",
    tagline: "Things that must not be missed",
    why: "Auto-detected red flags such as hyperkalaemia, eGFR below 15, blood pressure over 180/110, or critical anaemia. These are highlighted to the agents and used by the Clinical Reviewer to challenge the differential.",
    shape: "array",
    fields: [
      { key: "lab_name", type: "string", desc: "What is being flagged (potassium, eGFR, BP, …)." },
      { key: "value",    type: "number", desc: "The value that tripped the alert." },
      { key: "units",    type: "string", desc: "Units for the value." },
      { key: "flag",     type: "HIGH / LOW / CRITICAL", desc: "Severity of the alert." },
    ],
  },
  {
    id: "comorbidity",
    icon: <ListChecks size={16} />,
    name: "Comorbidity flags",
    tagline: "Yes / no markers for common conditions",
    why: "Simple true-or-false markers — has diabetes, has hypertension, has chronic kidney disease, has ischemic heart disease, and so on — computed from the chart so the system can quickly spot common syndromic clusters.",
    shape: "object",
    fields: [
      { key: "has_dm",      type: "true / false", desc: "Diabetes mellitus (any type)." },
      { key: "has_htn",     type: "true / false", desc: "Essential hypertension." },
      { key: "has_ckd",     type: "true / false", desc: "Chronic kidney disease at any stage." },
      { key: "has_ihd",     type: "true / false", desc: "Ischemic heart disease / coronary artery disease." },
      { key: "has_chf",     type: "true / false", desc: "Heart failure (HFrEF or HFpEF)." },
      { key: "has_obesity", type: "true / false", desc: "BMI in obese range or coded as obesity." },
    ],
  },
  {
    id: "risk_scores",
    icon: <FlaskConical size={16} />,
    name: "Risk scores",
    tagline: "Computed clinical risk estimates",
    why: "Standard clinical scores where the data allow — a 10-year ASCVD risk, a CHA₂DS₂-VASc score, and the like. They give the system a numerical anchor when deciding how aggressively to act.",
    shape: "object",
    fields: [
      { key: "ascvd_10yr",      type: "percent",  desc: "10-year atherosclerotic cardiovascular disease risk." },
      { key: "chads_vasc",      type: "0–9",      desc: "Stroke risk in atrial fibrillation (CHA₂DS₂-VASc)." },
      { key: "has_bled",        type: "0–9",      desc: "Bleeding risk on anticoagulation (HAS-BLED)." },
      { key: "egfr_ckd_epi",    type: "mL/min/1.73m²", desc: "Estimated glomerular filtration rate (CKD-EPI)." },
    ],
  },
];

function EvidenceList({
  icon,
  title,
  items,
  empty,
  onOpen,
  previewCount = 5,
}: {
  icon: ReactNode;
  title: string;
  items: Array<{ main: string; meta: string }>;
  empty: string;
  onOpen?: () => void;
  previewCount?: number;
}) {
  const preview = items.slice(0, previewCount);
  const hidden  = Math.max(0, items.length - preview.length);
  // The card is interactive whenever it has data — pressing anywhere opens
  // the drawer with the full unsliced list. Empty cards render as plain
  // panels (no point opening an empty drawer).
  const interactive = items.length > 0 && !!onOpen;
  const Wrap = interactive ? "button" : "div";
  const wrapProps = interactive
    ? { type: "button" as const,
        onClick: onOpen,
        className: "evidence-card evidence-card--interactive",
        title: `Open ${title} — ${items.length} ${items.length === 1 ? "item" : "items"}` }
    : { className: "evidence-card" };
  return (
    <Wrap {...wrapProps}>
      <div className="evidence-title">
        {icon}
        <h3>{title}</h3>
        {interactive && (
          <span className="evidence-card__count mono">
            {items.length}
            <ChevronRight size={13} strokeWidth={2} className="evidence-card__chev" />
          </span>
        )}
      </div>
      {items.length ? (
        <>
          <div className="evidence-list">
            {preview.map((item, index) => (
              <div className="evidence-row" key={`${item.main}-${index}`}>
                <strong>{item.main}</strong>
                <span>{item.meta || "not dated"}</span>
              </div>
            ))}
          </div>
          {hidden > 0 && (
            <div className="evidence-card__more mono">+{hidden} more — click to view all</div>
          )}
        </>
      ) : (
        <div className="empty-state">{empty}</div>
      )}
    </Wrap>
  );
}

function readRecord(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return undefined;
}

function readArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

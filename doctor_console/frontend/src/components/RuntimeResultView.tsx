import { useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle, BookOpen, Brain, ChevronDown, ClipboardList,
  FlaskConical, Pill, RotateCw, Stethoscope, Users2,
} from "lucide-react";
import type { AgentCard, AgentNarrative, PatientResult } from "../types";
import { cascadeListContainer, cascadeRow } from "../lib/motion";
import { AgentFlow } from "./AgentFlow";
import { AgentInspector } from "./AgentInspector";
import { Disclosure } from "./Disclosure";
import { PatientDetailTabs, type TabDef } from "./PatientDetailTabs";
import { PatientEvidence } from "./PatientEvidence";
import { RawDataPanel } from "./RawDataPanel";
import { SimilarCases } from "./SimilarCases";
import { TreatmentReview } from "./TreatmentReview";

type Props = {
  result: PatientResult;
  onReset: () => void;
  /** Researcher-only: append a "Raw data" tab exposing every persisted
   *  JSON artifact for this run. Off by default so the doctor view stays
   *  clean. */
  showRawData?: boolean;
};

/**
 * Doctor-facing result view after a live run completes — tab-organised.
 *
 * Differential is the default tab (the one the clinician opened the system
 * for). Treatment plan, Similar past cases, Agent reasoning and Input data
 * each live on their own tab. The LLM Evaluator is hidden everywhere —
 * its verdict still gates the treatment plan but it's not part of the
 * clinical narrative the doctor reads.
 */
export function RuntimeResultView({ result, onReset, showRawData = false }: Props) {
  const finalDx = result.finalDiagnosis as Record<string, unknown>;
  const primary = String(finalDx.primary_diagnosis ?? "Pending");
  const differential = Array.isArray(finalDx.differential)
    ? (finalDx.differential as Record<string, unknown>[])
    : [];
  // Actual K the doctor picked at run-time. We honour the length of the
  // produced differential so the copy never lies — if the doctor asked
  // for "Top 3" the labels read "top-3", "ranked top 3", etc.
  const topK = differential.length || 5;
  const unresolved = Array.isArray(finalDx.unresolved_findings)
    ? (finalDx.unresolved_findings as unknown[]).map(String)
    : [];
  const workup = Array.isArray(finalDx.recommended_workup)
    ? (finalDx.recommended_workup as unknown[]).map(String)
    : [];

  const treatmentObj = result.treatment as Record<string, unknown> | undefined;
  const hasTreatment = !!treatmentObj
    && Object.keys(treatmentObj).length > 0
    && !!treatmentObj.primary_diagnosis_treated
    && !String(treatmentObj.primary_diagnosis_treated).startsWith("SKIPPED");

  // Hide the LLM Evaluator from the doctor's reasoning view.
  const doctorAgents = result.agents.filter((a) => a.id !== "evaluation");

  const tabs: TabDef[] = [
    {
      id: "input",
      label: "Patient data",
      hint: "The chart and lab data the system read for this patient.",
      render: () => <PatientEvidence result={result} />,
    },
    {
      id: "differential",
      label: "Differential",
      hint: `What CMADS thinks this patient has — ranked top-${topK}.`,
      render: () => (
        <DifferentialPanel
          topK={topK}
          primary={primary}
          differential={differential}
          unresolved={unresolved}
          workup={workup}
        />
      ),
    },
    {
      id: "treatment",
      label: "Treatment",
      hint: "A starting plan when the system is confident about the diagnosis.",
      render: () => (
        <TreatmentPanel hasPlan={hasTreatment} result={result} treatmentObj={treatmentObj} />
      ),
    },
    {
      id: "similar",
      label: "Similar cases",
      hint: "Past patients with similar presentations and their confirmed diagnoses.",
      render: () => (
        <SimilarCases
          patientUuid={result.patient.uuid}
          resultSet={result.resultSet.id}
          mode="runtime"
        />
      ),
    },
    {
      id: "reasoning",
      label: "Reasoning",
      badge: "EXPLAINABILITY",
      hint: "Optional · step-by-step narrative for each part of the system's thinking. Useful if you want to verify how it reached the answer.",
      render: () => <ReasoningPanel result={result} doctorAgents={doctorAgents} />,
    },
    ...(showRawData
      ? [{
          id: "raw",
          label: "Raw data",
          badge: "RESEARCHER",
          hint: "Every persisted JSON artifact for this run — inputs, agent outputs, evaluation, trace, memory.",
          render: () => <RawDataPanel result={result} />,
        } as TabDef]
      : []),
  ];

  return (
    <div className="runtime-result">
      <RuntimeResultHeader patient={result.patient} primary={primary} onReset={onReset} />
      <PatientDetailTabs defaultActive="input" tabs={tabs} />
    </div>
  );
}

function RuntimeResultHeader({
  patient, primary, onReset,
}: {
  patient: PatientResult["patient"];
  primary: string;
  onReset: () => void;
}) {
  return (
    <section className="panel runtime-result__head">
      <div>
        <div className="eyebrow mono">{patient.uuid}</div>
        <h1>
          {patient.age ?? "?"} year old {patient.gender ?? "patient"}
          {patient.race ? `, ${patient.race}` : ""}
        </h1>
        {/* Primary diagnosis is intentionally NOT shown — doctor reads the
            full ranked differential in the dedicated tab. Cutoff date stays
            so the doctor knows when the chart snapshot was taken. */}
        <p>Data cutoff: {patient.cutoffDate || "not recorded"}</p>
      </div>
      <button type="button" className="ghost-button" onClick={onReset}>
        <RotateCw size={14} />
        Run another patient
      </button>
    </section>
  );
}

/* ─── Differential tab body ─────────────────────────────────────────── */

function DifferentialPanel({
  primary, differential, unresolved, workup, topK,
}: {
  primary: string;
  differential: Record<string, unknown>[];
  unresolved: string[];
  workup: string[];
  topK: number;
}) {
  return (
    <div className="runtime-tab-body">
      <section className="panel differential-hero">
        <header className="panel-heading">
          <div>
            <div className="eyebrow">
              <Stethoscope size={11} strokeWidth={2} /> Differential diagnosis
            </div>
            <h2>What CMADS thinks this patient has</h2>
            <p>
              The top {topK} most likely diagnoses, ranked. Read it as a
              structured second opinion — keep what fits, set aside what
              doesn't.
            </p>
          </div>
        </header>

        {/* Primary diagnosis hero banner removed in the doctor view — the
            full ranked differential below is the second-opinion surface;
            we don't want to over-emphasise the model's #1 pick. */}

        {differential.length === 0 ? (
          <div className="empty-state">No differential produced.</div>
        ) : (
          <motion.ol
            className="differential-hero__list"
            initial="hidden"
            animate="visible"
            variants={cascadeListContainer}
          >
            {differential.slice(0, topK).map((dx, i) => (
              <DiagnosisRow key={`${String(dx.name)}-${i}`} dx={dx} index={i} />
            ))}
          </motion.ol>
        )}
      </section>

      {(unresolved.length > 0 || workup.length > 0) ? (
        <FollowUpSection unresolved={unresolved} workup={workup} />
      ) : null}
    </div>
  );
}

/* ─── Treatment tab body ────────────────────────────────────────────── */

function TreatmentPanel({
  hasPlan, result, treatmentObj,
}: {
  hasPlan: boolean;
  result: PatientResult;
  treatmentObj?: Record<string, unknown>;
}) {
  return (
    <div className="runtime-tab-body">
      <section className="panel runtime-result__treatment">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">
              <Pill size={11} strokeWidth={2} /> Treatment plan
            </div>
            <h2>A management plan you can lean on</h2>
            <p>
              Start it, change it, or set it aside — every suggestion is yours
              to keep or override.
            </p>
          </div>
        </div>
        {hasPlan ? (
          <TreatmentReview result={result} />
        ) : (
          <div className="empty-state">
            {treatmentObj?.treatment_summary
              ? String(treatmentObj.treatment_summary)
              : "No treatment plan was produced for this run. The pipeline gates plan generation on the evaluator identifying one of the eight guideline-backed diseases."}
          </div>
        )}
      </section>
    </div>
  );
}

/* ─── Follow-up section (gaps + next steps) ─────────────────────────── */

type ClinicalArea = "Cardiac" | "Renal" | "Metabolic" | "Infection" | "Imaging" | "Medications" | "Other";

const AREA_KEYWORDS: Array<[ClinicalArea, RegExp]> = [
  ["Cardiac",     /ecg|ekg|echo|cardiac|troponin|ck.?mb|wall motion|left ventric|qt|holter/i],
  ["Renal",       /renal|kidney|ultrasound (?:of|for) (?:the )?(?:kidney|renal)|nephro|gfr|urin|albumin\/creatinine|acr|obstruction/i],
  ["Metabolic",   /lactate|anion gap|metabolic|electrolyte|abg|arterial blood gas|cmp|bmp|glucose|hba1c/i],
  ["Infection",   /infect|crp|procalcitonin|culture|wbc|sepsis|fever/i],
  ["Imaging",     /ct |mri|x-?ray|imaging|ultrasound|sono/i],
  ["Medications", /nsaid|medication|dosing|adherence|drug|pharmac/i],
];

function classifyArea(text: string): ClinicalArea {
  for (const [area, re] of AREA_KEYWORDS) {
    if (re.test(text)) return area;
  }
  return "Other";
}

function FollowUpSection({ unresolved, workup }: { unresolved: string[]; workup: string[] }) {
  return (
    <section className="follow-up-grid">
      {unresolved.length > 0 ? (
        <FollowUpPanel
          variant="gaps"
          eyebrow={`${unresolved.length} unresolved finding${unresolved.length === 1 ? "" : "s"}`}
          title="What's missing from this patient's picture"
          items={unresolved}
        />
      ) : null}
      {workup.length > 0 ? (
        <FollowUpPanel
          variant="actions"
          eyebrow={`${workup.length} suggested next step${workup.length === 1 ? "" : "s"}`}
          title="What to order or check next"
          items={workup}
        />
      ) : null}
    </section>
  );
}

function FollowUpPanel({
  variant, eyebrow, title, items,
}: {
  variant: "gaps" | "actions";
  eyebrow: string;
  title: string;
  items: string[];
}) {
  // Group items by clinical area for faster scanning. Falls back to "Other"
  // when the heuristic doesn't catch anything.
  const groups = new Map<ClinicalArea, string[]>();
  items.forEach((item) => {
    const area = classifyArea(item);
    const list = groups.get(area) ?? [];
    list.push(item);
    groups.set(area, list);
  });
  // Preserve a stable group order.
  const orderedAreas: ClinicalArea[] = ["Cardiac", "Renal", "Metabolic", "Infection", "Imaging", "Medications", "Other"];
  const ordered = orderedAreas
    .filter((a) => groups.has(a))
    .map((a) => ({ area: a, items: groups.get(a) ?? [] }));

  return (
    <article className={`follow-up follow-up--${variant}`}>
      <Disclosure
        defaultOpen={true}
        demoAnchor={`follow-up-${variant}`}
        title={
          <div className="follow-up__head">
            <div className={`follow-up__icon follow-up__icon--${variant}`}>
              {variant === "gaps" ? <AlertCircle size={18} strokeWidth={1.7} /> : <BookOpen size={18} strokeWidth={1.7} />}
            </div>
            <div className="follow-up__head-text">
              <div className="follow-up__eyebrow mono">{eyebrow}</div>
              <h3 className="follow-up__title">{title}</h3>
            </div>
          </div>
        }
      >
        <div className="follow-up__groups">
          {ordered.map(({ area, items }) => (
            <Disclosure
              key={area}
              defaultOpen={false}
              demoAnchor={`follow-up-${variant}-${area.toLowerCase()}`}
              title={<span className="follow-up__group-label mono">{area}</span>}
              badge={items.length}
              hint={
                items.length === 1
                  ? "1 item — click to see"
                  : `${items.length} items — click to see them all`
              }
            >
              <ol className="follow-up__list">
                {items.map((item, i) => (
                  <li key={i} className="follow-up__item">
                    <span className="follow-up__chev" aria-hidden>
                      {variant === "gaps" ? "›" : "→"}
                    </span>
                    <span className="follow-up__text">{item}</span>
                  </li>
                ))}
              </ol>
            </Disclosure>
          ))}
        </div>
      </Disclosure>
    </article>
  );
}

/* ─── Reasoning tab body ────────────────────────────────────────────── */

function ReasoningPanel({
  result, doctorAgents,
}: {
  result: PatientResult;
  doctorAgents: AgentCard[];
}) {
  const [selectedAgentId, setSelectedAgentId] = useState<string>(
    doctorAgents.find((a) => a.id === "final_diagnosis")?.id ?? doctorAgents[0]?.id ?? "ehr_analyst",
  );
  const selectedAgent = doctorAgents.find((a) => a.id === selectedAgentId);
  const selectedNarrative: AgentNarrative | undefined =
    result.agentNarratives?.[selectedAgentId];

  return (
    <div className="runtime-tab-body">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">
              <Brain size={11} strokeWidth={2} /> Agent reasoning
            </div>
            <h2>How CMADS arrived at this differential</h2>
            <p>Click any agent in the workflow to see its narrative and raw output.</p>
          </div>
        </div>
        <AgentFlow
          agents={doctorAgents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={setSelectedAgentId}
        />
      </section>
      <AgentInspector
        agent={selectedAgent}
        narrative={selectedNarrative}
        rawOutput={
          selectedAgent
            ? (result.agentOutputs as Record<string, unknown>)?.[selectedAgent.id]
            : undefined
        }
      />
    </div>
  );
}

/* ─── Differential row + evidence rendering ─────────────────────────── */

type EvidenceItem = {
  finding: string;
  source?: string;
  strength?: string;
};

function normaliseEvidence(raw: unknown): EvidenceItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry): EvidenceItem | null => {
      if (typeof entry === "string") return { finding: entry };
      if (entry && typeof entry === "object") {
        const obj = entry as Record<string, unknown>;
        const finding =
          (typeof obj.finding === "string" && obj.finding) ||
          (typeof obj.text === "string" && obj.text) ||
          (typeof obj.description === "string" && obj.description) ||
          (typeof obj.name === "string" && obj.name) ||
          (typeof obj.evidence === "string" && obj.evidence) ||
          "";
        if (!finding) return null;
        return {
          finding,
          source: typeof obj.source === "string" ? obj.source : undefined,
          strength: typeof obj.strength === "string" ? obj.strength : undefined,
        };
      }
      return null;
    })
    .filter((x): x is EvidenceItem => x !== null);
}

function DiagnosisRow({ dx, index }: { dx: Record<string, unknown>; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const name = String(dx.name ?? "Unnamed diagnosis");
  const probability =
    typeof dx.probability === "number" ? dx.probability
    : typeof dx.confidence === "number" ? dx.confidence
    : undefined;
  const rationale = typeof dx.rationale === "string" ? dx.rationale
    : typeof dx.reasoning === "string" ? dx.reasoning
    : "";
  const supporting = normaliseEvidence(dx.supporting_evidence ?? dx.evidence);
  const refuting = normaliseEvidence(dx.refuting_evidence);

  const pctText =
    probability !== undefined
      ? `${Math.round((probability > 1 ? probability : probability * 100))}%`
      : null;
  const tone = index === 0 ? "primary" : index === 1 ? "second" : "tertiary";

  return (
    <motion.li
      className={`differential-row differential-row--${tone}`}
      variants={cascadeRow}
    >
      <button
        type="button"
        className="differential-row__head"
        onClick={() => setOpen((s) => !s)}
        aria-expanded={open}
      >
        <span className="differential-row__rank mono">#{index + 1}</span>
        <span className="differential-row__name">{name}</span>
        {pctText ? <span className="differential-row__pct mono">{pctText}</span> : null}
        <ChevronDown size={14} className={`differential-row__chev${open ? " is-open" : ""}`} />
      </button>
      {open ? (
        <div className="differential-row__body">
          {rationale ? <p className="differential-row__rationale">{rationale}</p> : null}
          {supporting.length > 0 ? (
            <EvidenceList label="Supporting evidence" items={supporting} tone="supporting" />
          ) : null}
          {refuting.length > 0 ? (
            <EvidenceList label="What argues against" items={refuting} tone="refuting" />
          ) : null}
        </div>
      ) : null}
    </motion.li>
  );
}

function EvidenceList({
  label, items, tone,
}: { label: string; items: EvidenceItem[]; tone: "supporting" | "refuting" }) {
  return (
    <div className={`differential-row__evidence differential-row__evidence--${tone}`}>
      <div className="differential-row__evidence-label mono">
        {tone === "supporting" ? <ClipboardList size={12} /> : <AlertCircle size={12} />}
        {label}
      </div>
      <ul className="evidence-list">
        {items.map((item, i) => (
          <li key={i} className="evidence-list__item">
            <span className="evidence-list__finding">{item.finding}</span>
            {item.source || item.strength ? (
              <span className="evidence-list__tags">
                {item.source ? (
                  <span className="evidence-list__tag evidence-list__tag--source mono">
                    {prettifySource(item.source)}
                  </span>
                ) : null}
                {item.strength ? (
                  <span
                    className={`evidence-list__tag evidence-list__tag--strength evidence-list__tag--strength-${item.strength.toLowerCase()} mono`}
                  >
                    {item.strength.toLowerCase()}
                  </span>
                ) : null}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function prettifySource(source: string): string {
  return source
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

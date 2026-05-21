import { AlertTriangle, HeartPulse, ListChecks, TestTube2, FileJson, User } from "lucide-react";
import { useState, type ReactNode } from "react";
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

  return (
    <section className="panel evidence-panel" data-demo-anchor="patient-input">
      <div className="panel-heading">
        <div>
          <h2>Patient input — what the agents see</h2>
          <p>{activeConditions.length} active conditions · {activeMeds.length} active medications · {criticalFlags.length} critical flags · {Object.keys(demo).length} demographic fields</p>
        </div>
        <button
          type="button"
          className="json-toggle"
          onClick={() => setShowRawJson((v) => !v)}
          data-demo-anchor="patient-input-json-toggle"
        >
          <FileJson size={14} />
          {showRawJson ? "Hide raw JSON" : "Show raw input JSON"}
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
          items={activeConditions.slice(0, 6).map((item) => ({
            main: String(item.condition || item.name || "Condition"),
            meta: [item.start_date, item.code].filter(Boolean).join(" | "),
          }))}
          empty="No active problems recorded."
        />
        <EvidenceList
          icon={<AlertTriangle size={17} />}
          title="Critical flags"
          items={criticalFlags.slice(0, 6).map((item) => ({
            main: String(item.lab_name || "Critical flag"),
            meta: `${String(item.value ?? "")} ${String(item.units ?? "")} | ${String(item.flag ?? "")}`,
          }))}
          empty="No critical flags saved."
        />
        <EvidenceList
          icon={<HeartPulse size={17} />}
          title="Recent vitals"
          items={vitals.slice(0, 6).map((item) => ({
            main: String(item.vital || "Vital"),
            meta: `${String(item.value ?? "")} ${String(item.units ?? "")} | ${String(item.date ?? "")}`,
          }))}
          empty="No recent vitals saved."
        />
        <EvidenceList
          icon={<TestTube2 size={17} />}
          title="Latest labs"
          items={latestLabs.slice(0, 6).map((item) => ({
            main: String(item.lab_name || "Lab"),
            meta: `${String(item.value ?? "")} ${String(item.units ?? "")} | ${String(item.date ?? "")}`,
          }))}
          empty="No latest labs saved."
        />
      </div>

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
  );
}

function EvidenceList({
  icon,
  title,
  items,
  empty
}: {
  icon: ReactNode;
  title: string;
  items: Array<{ main: string; meta: string }>;
  empty: string;
}) {
  return (
    <div className="evidence-card">
      <div className="evidence-title">
        {icon}
        <h3>{title}</h3>
      </div>
      {items.length ? (
        <div className="evidence-list">
          {items.map((item, index) => (
            <div className="evidence-row" key={`${item.main}-${index}`}>
              <strong>{item.main}</strong>
              <span>{item.meta || "not dated"}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">{empty}</div>
      )}
    </div>
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

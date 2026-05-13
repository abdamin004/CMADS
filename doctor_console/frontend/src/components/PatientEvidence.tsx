import { AlertTriangle, HeartPulse, ListChecks, TestTube2 } from "lucide-react";
import type { ReactNode } from "react";
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

  return (
    <section className="panel evidence-panel">
      <div className="panel-heading">
        <div>
          <h2>Patient evidence</h2>
          <p>{activeConditions.length} active conditions, {activeMeds.length} active medications, {criticalFlags.length} critical flags</p>
        </div>
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

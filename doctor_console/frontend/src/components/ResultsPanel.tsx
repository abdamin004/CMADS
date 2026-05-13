import { ClipboardCheck, Pill, ShieldCheck, Stethoscope } from "lucide-react";
import type { PatientResult } from "../types";

type Props = {
  result?: PatientResult;
};

export function ResultsPanel({ result }: Props) {
  if (!result) return null;
  const differential = Array.isArray(result.finalDiagnosis.differential)
    ? result.finalDiagnosis.differential as Record<string, unknown>[]
    : [];
  const medications = Array.isArray(result.treatment.medications)
    ? result.treatment.medications as Record<string, unknown>[]
    : [];

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Clinical result</h2>
          <p>Final differential, benchmark evaluation, and treatment output.</p>
        </div>
        <span className={`match-pill match-${String(result.evaluation.match_type || "none").toLowerCase()}`}>
          {String(result.evaluation.match_type || "not evaluated")}
        </span>
      </div>

      <div className="result-summary">
        <div className="result-card">
          <Stethoscope size={20} />
          <span>Final primary</span>
          <strong>{String(result.finalDiagnosis.primary_diagnosis || "No final diagnosis")}</strong>
        </div>
        <div className="result-card">
          <ShieldCheck size={20} />
          <span>Evaluator match</span>
          <strong>{String(result.evaluation.matched_diagnosis || "None")}</strong>
        </div>
        <div className="result-card">
          <ClipboardCheck size={20} />
          <span>Ground truth</span>
          <strong>{result.patient.targetCondition || "Not available"}</strong>
        </div>
      </div>

      <div className="columns-two">
        <div>
          <h3>Ranked differential</h3>
          <div className="dx-list">
            {differential.length === 0 ? (
              <div className="empty-state">No differential saved.</div>
            ) : (
              differential.slice(0, 8).map((dx, index) => (
                <div className="dx-row" key={`${String(dx.name)}-${index}`}>
                  <span className="rank">#{String(dx.rank || index + 1)}</span>
                  <span className="dx-name">{String(dx.name || "Unnamed diagnosis")}</span>
                  <span className="prob">{formatProbability(dx.probability)}</span>
                </div>
              ))
            )}
          </div>
        </div>
        <div>
          <h3>Treatment plan</h3>
          <div className="med-list">
            {medications.length === 0 ? (
              <div className="empty-state">
                {String(result.treatment.treatment_summary || "No treatment plan saved.")}
              </div>
            ) : (
              medications.slice(0, 6).map((med, index) => (
                <div className="med-row" key={`${String(med.medication)}-${index}`}>
                  <Pill size={15} />
                  <div>
                    <strong>{String(med.medication || "Medication")}</strong>
                    <span>{String(med.purpose || med.nice_justification || "")}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function formatProbability(value: unknown) {
  if (typeof value !== "number") return "";
  return `${Math.round(value * 100)}%`;
}

import { AlertTriangle, Ban, BookOpen, ChevronDown, Clock, Link2, Pill, Target } from "lucide-react";
import type { PatientResult } from "../types";

type Props = { result: PatientResult };

/**
 * Doctor-facing treatment plan view. Re-organised on 2026-05-22 so the
 * clinical orders (what to give, what blocks it, what interacts) stay at
 * the top, and every NICE-reference / model-reasoning detail is moved
 * into a single ``Why this plan`` explainability disclosure at the
 * bottom — the card was previously too dense to scan during a real
 * consultation.
 */
export function TreatmentReview({ result }: Props) {
  const tx = result.treatment as Record<string, unknown>;
  const meds = arr(tx.medications);
  const interactions = arr(tx.interactions_checked);
  const contraindications = arr(tx.contraindications);
  const warnings = arr(tx.assumptions_warnings);
  const summary = str(tx.treatment_summary);
  const guideline = str(tx.nice_guideline_used);

  if (!meds.length && !interactions.length && !contraindications.length && !warnings.length && !summary) {
    return null;
  }

  const sevContra = contraindications.length;
  const sevInter = interactions.length;
  const sevWarn = warnings.length;

  // Anything that reflects how the system *justified* the plan goes into
  // the Why-this-plan section, NOT the doctor's primary scan area.
  const medsWithJustification = meds
    .map((m) => m as Record<string, unknown>)
    .filter((o) => str(o.nice_justification));
  const hasExplainability =
    Boolean(guideline) || medsWithJustification.length > 0;

  return (
    <section className="panel treatment-review">
      {/* No panel heading here on purpose — the parent (TreatmentPanel in
          the doctor view, or the Treatment tab in the researcher view)
          already labels this section. Rendering a second "Treatment plan"
          h2 looked like the same title was written twice on screen. */}

      {/* 1. Plan-at-a-glance */}
      {summary ? (
        <div className="tx-block tx-summary">
          <h3>Plan at a glance</h3>
          <p>{summary}</p>
        </div>
      ) : null}

      {/* 2. Prescribed medications — each med is a collapsible row.
            Sorted by line so first-line agents lead. Header carries the
            scannable summary (name + line chip + dose); the body opens to
            show duration and purpose neatly labelled. */}
      {meds.length ? (
        <div className="tx-block tx-meds">
          <h3>
            <Pill size={16} /> Prescribed medications
            <span className="tx-count">{meds.length}</span>
          </h3>
          <ul className="tx-med-list">
            {sortByLine(meds).map((m, i) => {
              const o = m as Record<string, unknown>;
              const name = str(o.medication) || "Medication";
              const dose = str(o.dose);
              const duration = str(o.duration);
              const line = str(o.line).replace("_", " ");
              const purpose = str(o.purpose);
              const hasDetail = Boolean(duration || purpose);
              return (
                <li key={i} className="tx-med-card">
                  <details open={i === 0}>
                    <summary>
                      <div className="tx-med-card__main">
                        <strong className="tx-med-card__name">{name}</strong>
                        <div className="tx-med-card__chips">
                          {line ? (
                            <span className={`tx-chip tx-chip--line ${chipForLine(line)}`}>{line}</span>
                          ) : null}
                          {dose ? <span className="tx-chip">{dose}</span> : null}
                        </div>
                      </div>
                      {hasDetail ? (
                        <ChevronDown
                          size={14}
                          strokeWidth={2}
                          className="tx-med-card__chevron"
                        />
                      ) : null}
                    </summary>
                    {hasDetail ? (
                      <div className="tx-med-card__body">
                        {duration ? (
                          <div className="tx-med-card__field">
                            <span className="tx-med-card__label mono">
                              <Clock size={11} strokeWidth={2} /> Duration
                            </span>
                            <span className="tx-med-card__value">{duration}</span>
                          </div>
                        ) : null}
                        {purpose ? (
                          <div className="tx-med-card__field">
                            <span className="tx-med-card__label mono">
                              <Target size={11} strokeWidth={2} /> Why this medicine
                            </span>
                            <span className="tx-med-card__value">{purpose}</span>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </details>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {/* 3. Contraindications — safety, stays on the main scan. */}
      {sevContra ? (
        <div className="tx-block tx-contra">
          <h3>
            <Ban size={16} /> Contraindications
            <span className="tx-count tx-count--critical">{sevContra}</span>
          </h3>
          <ul>
            {contraindications.map((c, i) => {
              const o = c as Record<string, unknown>;
              return (
                <li key={i}>
                  <strong>{str(o.drug) || "Drug"}</strong>
                  <span>{str(o.reason)}</span>
                  {str(o.alternative) ? <em>Use instead: {str(o.alternative)}</em> : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {/* 4. Drug interactions — safety, stays on the main scan. */}
      {sevInter ? (
        <div className="tx-block tx-interactions">
          <h3>
            <Link2 size={16} /> Drug interactions
            <span className="tx-count">{sevInter}</span>
          </h3>
          <ul>
            {sortBySeverity(interactions).map((it, i) => {
              const o = it as Record<string, unknown>;
              const pair = arr(o.drug_pair).map(str).filter(Boolean).join(" + ");
              const sev = str(o.severity).toLowerCase();
              return (
                <li key={i} className={`sev-${sev || "moderate"}`}>
                  <strong>{pair || "Drug pair"}</strong>
                  <span className="sev-pill">{sev || "moderate"}</span>
                  <p>{str(o.interaction)}</p>
                  {str(o.action) ? <em>Action: {str(o.action)}</em> : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {/* 5. Explainability — NICE guideline used + per-medication
            justifications. Planner assumptions / missing-data are kept in
            their own separate dropdown below so the doctor can collapse
            each independently. */}
      {hasExplainability ? (
        <details className="tx-block tx-why">
          <summary>
            <BookOpen size={14} strokeWidth={1.8} />
            <span className="tx-why__title">Why this plan</span>
            <span className="tx-why__hint">
              {guideline ? "NICE source" : ""}
              {medsWithJustification.length
                ? `${guideline ? " · " : ""}${medsWithJustification.length} medication rationale${medsWithJustification.length === 1 ? "" : "s"}`
                : ""}
            </span>
            <ChevronDown size={14} strokeWidth={2} className="tx-why__chevron" />
          </summary>
          <div className="tx-why__body">
            {guideline ? (
              <div className="tx-why__section">
                <div className="tx-why__label mono">NICE guideline used</div>
                <p className="tx-why__guideline">
                  <BookOpen size={12} strokeWidth={1.8} /> {guideline}
                </p>
              </div>
            ) : null}

            {medsWithJustification.length ? (
              <div className="tx-why__section">
                <div className="tx-why__label mono">Why each medication</div>
                <ul className="tx-why__list">
                  {medsWithJustification.map((o, i) => (
                    <li key={i}>
                      <strong>{str(o.medication) || "Medication"}</strong>
                      <span>{str(o.nice_justification)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </details>
      ) : null}

      {/* 6. Planner assumptions & missing data — its own dropdown so the
            doctor can collapse it independently from the NICE rationale. */}
      {sevWarn ? (
        <details className="tx-block tx-why tx-why--warnings">
          <summary>
            <AlertTriangle size={14} strokeWidth={1.8} />
            <span className="tx-why__title">Assumptions &amp; missing data</span>
            <span className="tx-why__hint">
              {sevWarn} assumption{sevWarn === 1 ? "" : "s"} the planner relied on
            </span>
            <ChevronDown size={14} strokeWidth={2} className="tx-why__chevron" />
          </summary>
          <div className="tx-why__body">
            <div className="tx-why__section">
              <div className="tx-why__label mono">What the planner assumed</div>
              <ul className="tx-why__list tx-why__list--warnings">
                {warnings.map((w, i) => (
                  <li key={i}>{str(w)}</li>
                ))}
              </ul>
            </div>
          </div>
        </details>
      ) : null}

    </section>
  );
}

/**
 * Sort prescribed medications by line-of-therapy so first-line agents
 * lead the list, followed by second / third / adjunct, with anything
 * unlabelled at the bottom. Ties keep the original order (stable sort).
 */
function sortByLine(list: unknown[]): unknown[] {
  const weight = (l: string) => {
    const v = l.toLowerCase();
    if (v.includes("first"))   return 0;
    if (v.includes("second"))  return 1;
    if (v.includes("third"))   return 2;
    if (v.includes("fourth"))  return 3;
    if (v.includes("adjunct") || v.includes("add-on") || v.includes("add on")) return 4;
    return 5;
  };
  return [...list].map((o, i) => ({ o, i })).sort((a, b) => {
    const la = str((a.o as Record<string, unknown>).line);
    const lb = str((b.o as Record<string, unknown>).line);
    const w = weight(la) - weight(lb);
    return w !== 0 ? w : a.i - b.i;
  }).map((x) => x.o);
}

function chipForLine(line: string): string {
  const v = line.toLowerCase();
  if (v.includes("first")) return "tx-chip--first";
  if (v.includes("second")) return "tx-chip--second";
  if (v.includes("third")) return "tx-chip--third";
  if (v.includes("adjunct") || v.includes("add-on")) return "tx-chip--adjunct";
  return "";
}

function sortBySeverity(list: unknown[]): unknown[] {
  const weight = (s: string) =>
    s.includes("severe") || s.includes("major") ? 0 :
    s.includes("moderate") ? 1 :
    s.includes("mild") || s.includes("minor") ? 2 : 3;
  return [...list].sort((a, b) => {
    const sa = str((a as Record<string, unknown>).severity).toLowerCase();
    const sb = str((b as Record<string, unknown>).severity).toLowerCase();
    return weight(sa) - weight(sb);
  });
}

function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function str(v: unknown): string {
  if (typeof v === "string") return v;
  if (v == null) return "";
  return String(v);
}

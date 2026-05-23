import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ClipboardCheck,
  ChevronRight,
  Quote,
} from "lucide-react";
import type { PatientResult } from "../types";
import { matchGlyph } from "../lib/matchType";
import { MetricTile } from "./ui/MetricTile";

type Props = {
  result?: PatientResult;
};

export function ResultsPanel({ result }: Props) {
  if (!result) return null;

  const differential = Array.isArray(result.finalDiagnosis.differential)
    ? (result.finalDiagnosis.differential as Record<string, unknown>[])
    : [];

  const matchType = String(result.evaluation.match_type || "").toUpperCase();
  const matchedDiagnosis = String(result.evaluation.matched_diagnosis || "");
  // The evaluator emits ``rank`` in evaluation.json (string "1", "2" …).
  // The old code read ``match_rank`` which doesn't exist, so the rank-based
  // fallback never fired and DIRECT/INDIRECT patients showed no matched row
  // whenever the LLM rephrased the diagnosis between the differential and
  // the judge — accept both field names + coerce to a number.
  const matchRank = Number(
    result.evaluation.rank ?? result.evaluation.match_rank ?? 0,
  );
  const evalReason = String(
    result.evaluation.eval_reason || result.evaluation.reason || "",
  );
  // Show the panel-level "matched to: …" banner for any DIRECT/INDIRECT
  // verdict so the doctor always sees which diagnosis the system credits
  // — even when no row in the visible top-5 string-matches the judge's
  // exact wording. This is the authoritative read.
  const showMatchBanner =
    (matchType === "DIRECT" || matchType === "INDIRECT") && !!matchedDiagnosis;

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Differential diagnosis</h2>
          <p>The final ranked top-5 after Reviewer-Refiner, judged against the hidden ground truth.</p>
        </div>
        {(() => {
          const Glyph = matchGlyph(matchType);
          return (
            <span className={`match-pill match-${(matchType || "none").toLowerCase()}`}>
              <Glyph size={12} strokeWidth={2} aria-hidden />
              {matchType || "not evaluated"}
            </span>
          );
        })()}
      </div>

      <div className="result-summary result-summary--single">
        <MetricTile
          variant="result"
          icon={<ClipboardCheck size={20} aria-hidden />}
          label="Ground truth"
          value={result.patient.targetCondition || "Not available"}
        />
      </div>

      {/* Authoritative match banner — shown whenever the judge returned
          DIRECT or INDIRECT, so the doctor always sees the matched
          diagnosis even if no row below string-matches exactly. */}
      {showMatchBanner ? (
        <div className={`match-banner match-${matchType.toLowerCase()}`}>
          <span className="match-banner__tag">
            {(() => {
              const Glyph = matchGlyph(matchType);
              return <Glyph size={12} strokeWidth={2} aria-hidden />;
            })()}
            {matchType === "DIRECT" ? "DIRECT MATCH" : "INDIRECT MATCH"}
          </span>
          <span className="match-banner__body">
            <strong>{matchedDiagnosis}</strong>
            {matchRank ? (
              <span className="match-banner__rank mono">
                · ranked #{matchRank} in the differential
              </span>
            ) : null}
          </span>
          {evalReason ? (
            <span className="match-banner__reason">{evalReason}</span>
          ) : null}
        </div>
      ) : null}

      <div className="differential-full">
        <h3>Ranked differential</h3>
        <p className="dx-list-hint">
          Each diagnosis is expandable to show the supporting evidence the
          agents pulled and the reasoning behind the rank.
        </p>
        <div className="dx-list">
          {differential.length === 0 ? (
            <div className="empty-state">No differential saved.</div>
          ) : (
            differential
              .slice(0, 8)
              .map((dx, index) => (
                <DiagnosisRow
                  key={`${String(dx.name)}-${index}`}
                  dx={dx}
                  index={index}
                  matchedDiagnosis={matchedDiagnosis}
                  matchType={matchType}
                  matchRank={matchRank}
                  evalReason={evalReason}
                />
              ))
          )}
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-diagnosis row with evidence / reasoning expander
// ─────────────────────────────────────────────────────────────────────────────
function DiagnosisRow({
  dx,
  index,
  matchedDiagnosis,
  matchType,
  matchRank,
  evalReason,
}: {
  dx: Record<string, unknown>;
  index: number;
  matchedDiagnosis: string;
  matchType: string;
  matchRank: number;
  evalReason: string;
}) {
  const rank =
    typeof dx.rank === "number" ? dx.rank : (typeof dx.rank === "string" ? Number(dx.rank) : index + 1);
  const name = String(dx.name || "Unnamed diagnosis");
  const probability = typeof dx.probability === "number" ? dx.probability : 0;
  const probPct = Math.round(probability * 100);
  const evidence = Array.isArray(dx.supporting_evidence)
    ? (dx.supporting_evidence as Array<Record<string, unknown> | string>)
    : [];
  const reasoning = String(dx.reasoning || "").trim();

  // Per-row match detection. The differential agents and the LLM judge
  // often rephrase the same diagnosis (e.g. "Atherosclerotic CAD with
  // recent MI" vs "Coronary artery disease"). Use a tolerant matcher:
  //   1. exact equality, OR
  //   2. case-insensitive substring either way (judge text contains the
  //      row name, or vice versa), OR
  //   3. row rank == evaluator rank.
  // Last branch alone is sufficient when ``rank`` lines up, so DIRECT /
  // INDIRECT patients always have a highlighted row.
  const norm = (s: string) =>
    s.toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
  const normName = norm(name);
  const normMatched = norm(matchedDiagnosis);
  const isMatch =
    (matchType === "DIRECT" || matchType === "INDIRECT") &&
    (
      (!!matchedDiagnosis && (
        normName === normMatched
        || (normMatched.length > 6 && normName.includes(normMatched))
        || (normName.length > 6 && normMatched.includes(normName))
      ))
      || (matchRank > 0 && rank === matchRank)
    );

  const hasDetail = evidence.length > 0 || reasoning.length > 0;
  const [open, setOpen] = useState(false);

  const matchClass = isMatch ? ` dx-row--match dx-row--${matchType.toLowerCase()}` : "";

  return (
    <div className={`dx-row${matchClass}${open ? " dx-row--open" : ""}`}>
      <button
        type="button"
        className="dx-row__head"
        onClick={() => hasDetail && setOpen((o) => !o)}
        aria-expanded={open}
        aria-disabled={!hasDetail}
      >
        <span className={`dx-row__rank dx-row__rank--${rank <= 3 ? rank : "other"}`}>
          {String(rank).padStart(2, "0")}
        </span>

        <span className="dx-row__name-block">
          <span className="dx-row__name">{name}</span>
          {isMatch ? (
            <span className={`dx-row__match-tag match-${matchType.toLowerCase()}`}>
              {(() => {
                const Glyph = matchGlyph(matchType);
                return <Glyph size={11} strokeWidth={2} aria-hidden />;
              })()}
              {matchType === "DIRECT" ? "DIRECT MATCH" : "INDIRECT MATCH"}
            </span>
          ) : null}
        </span>

        <span className="dx-row__prob">{probPct}%</span>

        {hasDetail ? (
          <motion.span
            className="dx-row__chevron"
            animate={{ rotate: open ? 90 : 0 }}
            transition={{ duration: 0.2 }}
            aria-hidden
          >
            <ChevronRight size={16} />
          </motion.span>
        ) : (
          <span className="dx-row__chevron dx-row__chevron--empty" aria-hidden />
        )}
      </button>

      {/* Full-width probability bar lives below the head row so it never
          collides with the diagnosis name on narrow panel widths. */}
      <div className="dx-row__bar" aria-hidden>
        <span
          className="dx-row__bar-fill"
          style={{ width: `${Math.max(2, probPct)}%` }}
        />
      </div>

      <AnimatePresence initial={false}>
        {open && hasDetail ? (
          <motion.div
            className="dx-row__detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div className="dx-row__detail-inner">
              {isMatch && evalReason ? (
                <div className={`dx-row__match-note match-${matchType.toLowerCase()}`}>
                  <strong>
                    {matchType === "DIRECT"
                      ? "Direct match. "
                      : "Indirect match. "}
                  </strong>
                  {evalReason}
                </div>
              ) : null}

              {evidence.length > 0 ? (
                <div className="dx-row__evidence">
                  <div className="dx-row__detail-label">Supporting evidence</div>
                  <ul>
                    {evidence.map((e, i) => {
                      if (e && typeof e === "object" && !Array.isArray(e)) {
                        const obj = e as Record<string, unknown>;
                        const source = String(obj.source ?? "?");
                        const finding = String(obj.finding ?? "");
                        return (
                          <li key={i}>
                            <span className="dx-row__evidence-source">
                              {source}
                            </span>
                            <span className="dx-row__evidence-text">
                              {finding}
                            </span>
                          </li>
                        );
                      }
                      return (
                        <li key={i}>
                          <span className="dx-row__evidence-text">
                            {String(e)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}

              {reasoning ? (
                <div className="dx-row__reasoning">
                  <div className="dx-row__detail-label">Why this rank</div>
                  <p>
                    <Quote size={12} />
                    {reasoning}
                  </p>
                </div>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

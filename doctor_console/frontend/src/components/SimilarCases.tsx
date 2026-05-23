import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight, BrainCircuit, ChevronDown, HeartPulse, Loader2,
  Pill, Stethoscope, TestTube2, User,
} from "lucide-react";
import { getSimilarCases } from "../api";
import type { SimilarCase, SimilarCasesResponse } from "../types";

type Props = {
  patientUuid?: string;
  resultSet: string;
  onOpenPatient?: (uuid: string) => void;
  /**
   * "researcher" (default): show each neighbour's diagnosis as recorded by
   * past CMADS outputs (matched_diagnosis, match_type, rank). Match-type
   * filter is shown.
   *
   * "runtime": show each neighbour's confirmed *clinical* diagnosis from
   * their Synthea ground truth. The match-type filter is hidden — past
   * AI matches are not what a doctor in the loop wants to see.
   */
  mode?: "researcher" | "runtime";
};

const MATCH_OPTIONS = ["DIRECT", "INDIRECT", "MISS"] as const;

export function SimilarCases({ patientUuid, resultSet, onOpenPatient, mode = "researcher" }: Props) {
  const [topK, setTopK] = useState(5);
  const [filters, setFilters] = useState<string[]>(["DIRECT", "INDIRECT"]);
  // Self-exclusion is the default policy in both Researcher and Doctor
  // dashboards — a patient's own UUID is never useful as a "similar case",
  // and exposing it as a toggle invites a leakage footgun. Kept as a const
  // so the request payload still includes it, but it's no longer a control.
  const excludeSelf = true;
  const [data, setData] = useState<SimilarCasesResponse>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSimilar = useCallback(async () => {
    if (!patientUuid) {
      setData(undefined);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await getSimilarCases(patientUuid, {
        topK,
        matchFilter: mode === "runtime" ? [] : filters,
        excludeSelf,
        resultSet,
        mode,
      });
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(undefined);
    } finally {
      setLoading(false);
    }
  }, [patientUuid, topK, filters.join(","), excludeSelf, resultSet, mode]);

  useEffect(() => {
    void fetchSimilar();
  }, [fetchSimilar]);

  const toggleFilter = (mt: string) => {
    setFilters((prev) =>
      prev.includes(mt) ? prev.filter((f) => f !== mt) : [...prev, mt]
    );
  };

  const totalIndexed = data?.totalIndexed ?? 0;
  const results = useMemo(() => data?.results ?? [], [data]);

  if (!patientUuid) {
    return null;
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Similar past cases</h2>
          <p>
            {mode === "runtime" ? (
              <>
                Past patients with similar presentations, labelled with their
                <strong> confirmed clinical diagnosis</strong> (Synthea ground truth).
                Use them as a reference library — not as AI predictions.
              </>
            ) : (
              <>
                Vector search over <span className="mono">patient_cases</span> · BioLORD-2023 embeddings.
                Use prior outcomes to anchor or challenge the current assessment.
              </>
            )}
          </p>
        </div>
        <div className="similar-section__head-right">
          <div className="eyebrow">{mode === "runtime" ? "Reference library" : "Collection"}</div>
          <div className="mono similar-section__head-meta">
            {data?.collection ?? "patient_cases"} · {totalIndexed} indexed
          </div>
        </div>
      </div>

      <div className="similar-controls">
        <label>
          Top-K
          <input
            type="number"
            min={1}
            max={20}
            value={topK}
            onChange={(e) => setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 5)))}
          />
        </label>
        {mode === "researcher" ? (
          <label>
            Filter outcome
            <div className="filter-chips">
              {MATCH_OPTIONS.map((mt) => (
                <button
                  key={mt}
                  type="button"
                  className={`filter-chip ${filters.includes(mt) ? "active" : ""}`}
                  onClick={() => toggleFilter(mt)}
                >
                  {mt}
                </button>
              ))}
            </div>
          </label>
        ) : null}
      </div>

      {data?.queryText ? (
        <details className="similar-query-card">
          <summary className="similar-query-card__summary">
            <span className="similar-query-card__eyebrow mono">
              What the system uses to find similar patients
            </span>
            <span className="similar-query-card__hint mono">
              {data.isPatientIndexed ? "stored" : "computed from current data"}
            </span>
          </summary>
          <SimilarQueryBlocks queryText={data.queryText} />
        </details>
      ) : null}

      {error ? (
        <div className="error-box" style={{ marginTop: "var(--space-4)" }}>
          {error}
        </div>
      ) : null}

      {data?.error ? (
        <div className="empty-state" style={{ marginTop: "var(--space-4)" }}>
          {data.error}
        </div>
      ) : null}

      {loading ? (
        <div className="empty-state similar-section__loading">
          <Loader2 size={16} className="spin" />
          Searching case history…
        </div>
      ) : null}

      {!loading && !error && !results.length ? (
        <div className="empty-state" style={{ marginTop: "var(--space-4)" }}>
          No similar cases under the current filters.
        </div>
      ) : null}

      <div className="similar-grid" style={{ marginTop: "var(--space-4)" }}>
        {results.map((c) => (
          <SimilarCard
            key={c.patientUuid + String(c.indexedAt)}
            c={c}
            onOpen={onOpenPatient}
            mode={mode}
          />
        ))}
      </div>
    </section>
  );
}

function SimilarCard({
  c,
  onOpen,
  mode,
}: {
  c: SimilarCase;
  onOpen?: (uuid: string) => void;
  mode: "researcher" | "runtime";
}) {
  const isRuntime = mode === "runtime";
  const mtClass = isRuntime ? "match-clinical" : `match-${(c.matchType || "none").toLowerCase()}`;
  const mtLabelClass = `mt-${(c.matchType || "none").toLowerCase()}`;
  const scorePct = Math.max(0, Math.min(100, Math.round((c.similarity ?? 0) * 100)));
  const headline = isRuntime
    ? (c.groundTruthDiagnosis || c.matchedDiagnosis || "Unrecorded diagnosis")
    : (c.matchedDiagnosis || "Unrecorded diagnosis");

  return (
    <article className={`similar-card ${mtClass}`}>
      <div>
        <div className="similar-dx">{headline}</div>
        <div className="similar-meta">
          <span className="mono">{c.patientUuid?.slice(0, 12)}…</span>
          {isRuntime ? (
            <>
              {" · "}
              <span className="mt-clinical">CONFIRMED</span>
              {c.groundTruthCode ? <> · <span className="mono">{c.groundTruthCode}</span></> : null}
            </>
          ) : (
            <>
              {" · "}
              <span className={mtLabelClass}>{c.matchType || "—"}</span>
              {c.rankWhenFound ? <> · rank {c.rankWhenFound}</> : null}
              {c.canonicalFamily ? <> · {c.canonicalFamily}</> : null}
            </>
          )}
        </div>
        {c.caseText ? (
          <details className="similar-text-card">
            <summary>
              <span className="similar-text-card__eyebrow mono">
                Demographics · Conditions · Medications
              </span>
              <ChevronDown size={13} strokeWidth={2} className="similar-text-card__chevron" />
            </summary>
            <div className="similar-text-card__body">
              <SimilarQueryBlocks queryText={c.caseText} compact />
            </div>
          </details>
        ) : null}
        <div className="similar-actions">
          {onOpen && c.patientUuid ? (
            <button type="button" onClick={() => onOpen(c.patientUuid!)}>
              <ArrowUpRight size={14} style={{ display: "inline", marginRight: 6 }} />
              Review this patient
            </button>
          ) : null}
          {c.evidencePatterns?.length ? (
            <details>
              <summary
                style={{
                  display: "inline-block",
                  padding: "0.3rem 0.7rem",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  fontFamily: "Manrope, sans-serif",
                  fontSize: "0.76rem",
                  color: "var(--ink-soft)",
                }}
              >
                <BrainCircuit size={12} style={{ display: "inline", marginRight: 6 }} />
                {c.evidencePatterns.length} evidence patterns
              </summary>
              <ul
                style={{
                  marginTop: "0.5rem",
                  padding: 0,
                  listStyle: "none",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.3rem",
                }}
              >
                {c.evidencePatterns.map((ep, i) => (
                  <li
                    key={i}
                    style={{
                      fontSize: "0.78rem",
                      color: "var(--ink-muted)",
                      fontFamily: "JetBrains Mono, monospace",
                      padding: "0.3rem 0.5rem",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      background: "var(--bg-elevated)",
                    }}
                  >
                    {ep}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      </div>
      <div className="similar-score-block">
        <div className="lbl">Similarity</div>
        <div className="val">{(c.similarity ?? 0).toFixed(2)}</div>
        <div className="similar-bar">
          <div style={{ width: `${scorePct}%` }} />
        </div>
      </div>
    </article>
  );
}

/* The server-side case-based-memory query text is a single line:
   "Demographics: age 53, F, white. Active conditions: …; …. Active
    medications: …; …." Render it as titled cards with icons to match
   the PatientEvidence evidence-grid look. */

type Block = {
  key: string;
  label: string;
  icon: React.ReactNode;
  items: string[];
  inline?: boolean;
};

function SimilarQueryBlocks({
  queryText,
  compact = false,
}: {
  queryText: string;
  /** Tighter tile padding/font used inside each similar-patient card. */
  compact?: boolean;
}) {
  const blocks = parseQueryText(queryText);
  if (blocks.length === 0) {
    return <div className="similar-query">{queryText}</div>;
  }
  return (
    <div className={`similar-query-grid${compact ? " similar-query-grid--compact" : ""}`}>
      {blocks.map((b) => (
        <article
          key={b.key}
          className={
            "similar-query-tile"
            + (b.inline ? " similar-query-tile--inline" : "")
            + (compact ? " similar-query-tile--compact" : "")
          }
        >
          <header className="similar-query-tile__head">
            <span className="similar-query-tile__icon">{b.icon}</span>
            <h4>{b.label}</h4>
            <span className="similar-query-tile__count mono">{b.items.length}</span>
          </header>
          {b.inline ? (
            <p className="similar-query-tile__inline">{b.items.join(" · ")}</p>
          ) : (
            <ul className="similar-query-tile__list">
              {b.items.map((it, i) => (
                <QueryItem key={i} text={it} kind={b.key} />
              ))}
            </ul>
          )}
        </article>
      ))}
    </div>
  );
}

/**
 * Render one item inside a query-block tile. Cleans noisy Synthea
 * decorations ("(disorder)", "(finding)") and parses lab strings of the
 * form ``Creatinine = 1.8 mg/dL (high)`` into a name + value + tone
 * pill, so the lab tile reads as a proper table.
 */
function QueryItem({ text, kind }: { text: string; kind: string }) {
  if (kind === "labs") {
    const m = text.match(/^(.*?)\s*=\s*(.+?)(?:\s*\((.+?)\))?\s*$/);
    if (m) {
      const [, name, value, cls] = m;
      const tone = classifyTone(cls || "");
      return (
        <li className="similar-query-item similar-query-item--lab">
          <span className="similar-query-item__name">{name}</span>
          <span className="similar-query-item__value mono">{value}</span>
          {cls ? (
            <span className={`similar-query-item__pill similar-query-item__pill--${tone}`}>
              {cls}
            </span>
          ) : null}
        </li>
      );
    }
  }
  if (kind === "conditions") {
    // Strip "(disorder)", "(finding)", "(situation)" suffixes that aren't
    // clinically informative and just clutter the row.
    const cleaned = text.replace(
      /\s*\((disorder|finding|situation|context-dependent category|navigational concept|qualifier value)\)\s*$/i,
      "",
    );
    return (
      <li className="similar-query-item">
        <span className="similar-query-item__name">{cleaned}</span>
      </li>
    );
  }
  return (
    <li className="similar-query-item">
      <span className="similar-query-item__name">{text}</span>
    </li>
  );
}

function classifyTone(cls: string): "high" | "low" | "normal" | "abn" {
  const c = cls.toLowerCase();
  if (c.includes("high") || c.includes("elevated") || c.includes("critical-high")) return "high";
  if (c.includes("low")  || c.includes("depleted") || c.includes("critical-low"))  return "low";
  if (c.includes("normal") || c.includes("within")) return "normal";
  return "abn";
}

function parseQueryText(text: string): Block[] {
  const sectionRe =
    /([A-Z][A-Za-z][A-Za-z ]*?):\s+([\s\S]*?)(?=(?:\. [A-Z][A-Za-z][A-Za-z ]*?:\s)|$)/g;
  const out: Block[] = [];
  let m: RegExpExecArray | null;
  while ((m = sectionRe.exec(text)) !== null) {
    const name = m[1].trim();
    let body = m[2].trim();
    if (body.endsWith(".")) body = body.slice(0, -1).trim();
    const items = splitItems(body);
    if (items.length === 0) continue;
    out.push(blockFor(name, items));
  }
  return out;
}

function splitItems(body: string): string[] {
  if (body.includes(";")) {
    return body.split(/\s*;\s*/).map((s) => s.trim()).filter(Boolean);
  }
  return body.split(/\s*,\s*/).map((s) => s.trim()).filter(Boolean);
}

function blockFor(name: string, items: string[]): Block {
  const lower = name.toLowerCase();
  if (lower.startsWith("demographic")) {
    return { key: "demographics", label: "Demographics", icon: <User size={14} strokeWidth={1.8} />, items, inline: true };
  }
  if (lower.includes("medication")) {
    return { key: "medications", label: "Medications", icon: <Pill size={14} strokeWidth={1.8} />, items };
  }
  if (lower.includes("condition") || lower.includes("problem")) {
    return { key: "conditions", label: "Active conditions", icon: <Stethoscope size={14} strokeWidth={1.8} />, items };
  }
  if (lower.includes("lab")) {
    return { key: "labs", label: "Recent labs", icon: <TestTube2 size={14} strokeWidth={1.8} />, items };
  }
  if (lower.includes("vital")) {
    return { key: "vitals", label: "Vitals", icon: <HeartPulse size={14} strokeWidth={1.8} />, items };
  }
  return {
    key: lower.replace(/\s+/g, "-"),
    label: name,
    icon: <ChevronDown size={14} strokeWidth={1.8} />,
    items,
  };
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BrainCircuit, Loader2 } from "lucide-react";
import { getSimilarCases } from "../api";
import type { SimilarCase, SimilarCasesResponse } from "../types";

type Props = {
  patientUuid?: string;
  resultSet: string;
  onOpenPatient?: (uuid: string) => void;
};

const MATCH_OPTIONS = ["DIRECT", "INDIRECT", "MISS"] as const;

export function SimilarCases({ patientUuid, resultSet, onOpenPatient }: Props) {
  const [topK, setTopK] = useState(5);
  const [filters, setFilters] = useState<string[]>(["DIRECT", "INDIRECT"]);
  const [excludeSelf, setExcludeSelf] = useState(true);
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
        matchFilter: filters,
        excludeSelf,
        resultSet,
      });
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(undefined);
    } finally {
      setLoading(false);
    }
  }, [patientUuid, topK, filters.join(","), excludeSelf, resultSet]);

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
            Vector search over <span className="mono">patient_cases</span> · BioLORD-2023 embeddings.
            Use prior outcomes to anchor or challenge the current assessment.
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="eyebrow">Collection</div>
          <div className="mono" style={{ fontSize: "0.84rem" }}>
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
        <label>
          Exclude self
          <button
            type="button"
            className={`filter-chip ${excludeSelf ? "active" : ""}`}
            onClick={() => setExcludeSelf((s) => !s)}
            style={{ minWidth: 90 }}
          >
            {excludeSelf ? "✓ excluded" : "included"}
          </button>
        </label>
      </div>

      {data?.queryText ? (
        <details>
          <summary
            style={{
              cursor: "pointer",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: "0.72rem",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--ink-muted)",
              marginBottom: "0.4rem",
            }}
          >
            Query text used for vector search
            {data.isPatientIndexed ? " · stored" : " · computed from current data"}
          </summary>
          <div className="similar-query">{data.queryText}</div>
        </details>
      ) : null}

      {error ? (
        <div className="error-box" style={{ marginTop: "0.8rem" }}>
          {error}
        </div>
      ) : null}

      {data?.error ? (
        <div className="empty-state" style={{ marginTop: "0.8rem" }}>
          {data.error}
        </div>
      ) : null}

      {loading ? (
        <div
          className="empty-state"
          style={{
            marginTop: "0.8rem",
            display: "flex",
            alignItems: "center",
            gap: "0.6rem",
          }}
        >
          <Loader2 size={16} className="spin" />
          Searching case history…
        </div>
      ) : null}

      {!loading && !error && !results.length ? (
        <div className="empty-state" style={{ marginTop: "0.8rem" }}>
          No similar cases under the current filters.
        </div>
      ) : null}

      <div className="similar-grid" style={{ marginTop: "0.8rem" }}>
        {results.map((c) => (
          <SimilarCard key={c.patientUuid + String(c.indexedAt)} c={c} onOpen={onOpenPatient} />
        ))}
      </div>
    </section>
  );
}

function SimilarCard({
  c,
  onOpen,
}: {
  c: SimilarCase;
  onOpen?: (uuid: string) => void;
}) {
  const mtClass = `match-${(c.matchType || "none").toLowerCase()}`;
  const mtLabelClass = `mt-${(c.matchType || "none").toLowerCase()}`;
  const scorePct = Math.max(0, Math.min(100, Math.round((c.similarity ?? 0) * 100)));

  return (
    <article className={`similar-card ${mtClass}`}>
      <div>
        <div className="similar-dx">{c.matchedDiagnosis || "Unrecorded diagnosis"}</div>
        <div className="similar-meta">
          <span className="mono">{c.patientUuid?.slice(0, 12)}…</span>
          {" · "}
          <span className={mtLabelClass}>{c.matchType || "—"}</span>
          {c.rankWhenFound ? <> · rank {c.rankWhenFound}</> : null}
          {c.canonicalFamily ? <> · {c.canonicalFamily}</> : null}
        </div>
        {c.caseText ? <div className="similar-text">{c.caseText}…</div> : null}
        <div className="similar-actions">
          {onOpen && c.patientUuid ? (
            <button type="button" onClick={() => onOpen(c.patientUuid!)}>
              <ArrowUpRight size={14} style={{ display: "inline", marginRight: 6 }} />
              Open chart
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

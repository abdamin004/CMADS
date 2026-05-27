import { useMemo, useState } from "react";
import { Check, Copy, Download, FileJson, Search } from "lucide-react";
import { Disclosure } from "./Disclosure";
import type { PatientResult } from "../types";

type Props = {
  result: PatientResult;
};

type Artifact = {
  id: string;
  label: string;
  hint: string;
  payload: unknown;
};

/**
 * Researcher-only "Raw data" tab. Surfaces every persisted JSON artifact
 * the pipeline wrote for this patient — pipeline inputs, the final
 * diagnosis bundle, the evaluator verdict, the treatment plan, each
 * agent's raw output, the execution trace, and the session/semantic
 * memory snapshots. Each artifact lives behind its own Disclosure so the
 * page does not dump tens of KB on first paint; copy + download per
 * artifact, and a "download everything" bundle at the top.
 */
export function RawDataPanel({ result }: Props) {
  const [query, setQuery] = useState("");

  const artifacts: Artifact[] = useMemo(() => {
    const out: Artifact[] = [
      {
        id: "final_diagnosis",
        label: "final_diagnosis.json",
        hint: "Refined top-5 differential after Reviewer-Refiner.",
        payload: result.finalDiagnosis,
      },
      {
        id: "evaluation",
        label: "evaluation.json",
        hint: "LLM-as-judge verdict (DIRECT / INDIRECT / MISS) vs Synthea ground truth.",
        payload: result.evaluation,
      },
      {
        id: "treatment",
        label: "treatment_planning.json",
        hint: "NICE-guideline plan (populated only for DIRECT matches).",
        payload: result.treatment,
      },
      {
        id: "ehr_case",
        label: "ehr_case.json",
        hint: "Pipeline input — Gold EHR bundle the agents read.",
        payload: result.case?.ehrCase,
      },
      {
        id: "lab_case",
        label: "lab_case.json",
        hint: "Pipeline input — lab panels and trends.",
        payload: result.case?.labCase,
      },
      {
        id: "ground_truth",
        label: "ground_truth.json",
        hint: "Hidden Synthea label — used by the evaluator, never seen by the diagnostic agents.",
        payload: result.case?.groundTruth,
      },
      {
        id: "execution_trace",
        label: "execution_trace.json",
        hint: "Per-agent invocation trace (start, finish, status, errors).",
        payload: result.trace,
      },
      {
        id: "session_memory",
        label: "session_memory.json",
        hint: "Ordered timeline of intra-run events appended to shared memory.",
        payload: result.sessionMemory,
      },
      {
        id: "semantic_memory",
        label: "semantic_memory (top-K)",
        hint: "Tier-4 case-based memory neighbours injected at run-time.",
        payload: result.semanticMemory,
      },
    ];

    const agentOutputs = (result.agentOutputs ?? {}) as Record<string, unknown>;
    for (const agent of result.agents) {
      const payload = agentOutputs[agent.id];
      if (payload === undefined) continue;
      out.push({
        id: `agent:${agent.id}`,
        label: `${agent.id}.json`,
        hint: `Raw output written by the ${agent.label} agent.`,
        payload,
      });
    }
    return out;
  }, [result]);

  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!q) return artifacts;
    return artifacts.filter((a) =>
      a.label.toLowerCase().includes(q) || a.hint.toLowerCase().includes(q)
    );
  }, [artifacts, q]);

  function downloadBundle() {
    const bundle = {
      patient: result.patient,
      resultSet: result.resultSet,
      case: result.case,
      finalDiagnosis: result.finalDiagnosis,
      evaluation: result.evaluation,
      treatment: result.treatment,
      agentOutputs: result.agentOutputs,
      trace: result.trace,
      sessionMemory: result.sessionMemory,
      semanticMemory: result.semanticMemory,
    };
    downloadJson(`patient-${result.patient.uuid}-raw.json`, bundle);
  }

  return (
    <section className="panel raw-panel">
      <header className="raw-panel__head">
        <div>
          <div className="eyebrow mono">
            <FileJson size={12} /> Researcher · raw artifacts
          </div>
          <h2>Raw data</h2>
          <p className="muted">
            Every JSON file the pipeline persisted for this patient — pipeline
            inputs, the final differential, the evaluator verdict, each
            agent's output, the execution trace, and the memory snapshots.
            Open any block to inspect; copy or download to keep an audit copy.
          </p>
        </div>
        <button
          type="button"
          className="raw-panel__bundle"
          onClick={downloadBundle}
          title="Download every artifact as one JSON file"
        >
          <Download size={13} strokeWidth={1.8} />
          Download bundle
        </button>
      </header>

      <div className="raw-panel__toolbar">
        <div className="raw-panel__search">
          <Search size={13} strokeWidth={1.8} className="raw-panel__search-icon" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter artifacts (e.g. evaluation, ehr_case, diagnostic)…"
            className="raw-panel__search-input"
          />
        </div>
        <span className="raw-panel__count mono">
          {filtered.length} / {artifacts.length} artifacts
        </span>
      </div>

      <div className="raw-panel__list">
        {filtered.length === 0 ? (
          <div className="empty-state compact">No artifacts match that filter.</div>
        ) : (
          filtered.map((artifact) => (
            <ArtifactBlock
              key={artifact.id}
              artifact={artifact}
              patientUuid={result.patient.uuid}
            />
          ))
        )}
      </div>
    </section>
  );
}

function ArtifactBlock({
  artifact,
  patientUuid,
}: {
  artifact: Artifact;
  patientUuid: string;
}) {
  const json = useMemo(() => safeStringify(artifact.payload), [artifact.payload]);
  const sizeKb = Math.max(1, Math.round((json.length / 1024) * 10) / 10);
  const empty =
    artifact.payload === undefined ||
    artifact.payload === null ||
    (Array.isArray(artifact.payload) && artifact.payload.length === 0) ||
    (typeof artifact.payload === "object" &&
      artifact.payload !== null &&
      !Array.isArray(artifact.payload) &&
      Object.keys(artifact.payload as Record<string, unknown>).length === 0);

  return (
    <Disclosure
      tone="muted"
      title={
        <span className="raw-panel__title">
          <FileJson size={13} strokeWidth={1.8} />
          <code>{artifact.label}</code>
          {empty ? (
            <span className="raw-panel__pill raw-panel__pill--empty">empty</span>
          ) : (
            <span className="raw-panel__pill mono">{sizeKb} kB</span>
          )}
        </span>
      }
      hint={artifact.hint}
      demoAnchor={`raw-artifact-${artifact.id}`}
    >
      {empty ? (
        <div className="empty-state compact">
          No payload was persisted for this artifact.
        </div>
      ) : (
        <div className="raw-panel__block">
          <div className="raw-panel__actions">
            <CopyButton text={json} />
            <button
              type="button"
              className="raw-panel__btn"
              onClick={() => downloadJson(`${patientUuid}-${artifact.label.replace(/[^a-z0-9_.-]/gi, "_")}`, artifact.payload)}
              title="Download this artifact"
            >
              <Download size={12} strokeWidth={1.8} />
              Download
            </button>
          </div>
          <pre className="raw-json raw-json--panel">{json}</pre>
        </div>
      )}
    </Disclosure>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      window.setTimeout(() => setDone(false), 1400);
    } catch {
      /* clipboard blocked — silently no-op */
    }
  }
  return (
    <button
      type="button"
      className={`raw-panel__btn${done ? " is-done" : ""}`}
      onClick={copy}
      title="Copy JSON to clipboard"
    >
      {done ? (
        <>
          <Check size={12} strokeWidth={2} />
          Copied
        </>
      ) : (
        <>
          <Copy size={12} strokeWidth={1.8} />
          Copy
        </>
      )}
    </button>
  );
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([safeStringify(payload)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".json") ? filename : `${filename}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

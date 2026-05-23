import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Cpu, Loader2, RotateCw } from "lucide-react";
import { getModelComparison } from "../api";
import type { ComparisonResult } from "../types";
import { ComparisonView } from "./ComparisonView";

type Props = { onOpenPatient?: (uuid: string) => void };

/**
 * Model head-to-head: GPT-OSS-120B vs Med42-70B on the **controlled
 * 20-patient cohort**. Both arms run the same seven-agent pipeline on the
 * same Synthea patients with memory off, so the only thing that differs is
 * the underlying LLM. This is the proper A/B — comparing against the full
 * 160-patient mas_results would conflate cohort size + model effects.
 *
 * No cohort picker — this is the fixed controlled study the thesis
 * reports, so the UI keeps it focused.
 */
// GPT-OSS is the principal/candidate (right arm, green) and Med42 is the
// baseline (left arm, neutral). Same seven-agent pipeline + same 20-patient
// cohort with memory off — the only difference is the LLM.
const BASELINE = "mas_results_med42";           // Med42-70B    · baseline arm
const CANDIDATE = "mas_results_baseline_no_mem"; // GPT-OSS-120B · principal arm

export function ModelComparisonTab({ onOpenPatient }: Props) {
  const [data, setData] = useState<ComparisonResult | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getModelComparison(BASELINE, CANDIDATE));
    } catch (err) {
      setData(undefined);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return (
      <div className="empty-state">
        <Loader2 size={16} className="spin" /> Loading GPT-OSS vs Med42 comparison…
      </div>
    );
  }
  if (error) {
    return (
      <div className="alert alert--with-action" role="alert" aria-live="polite">
        <AlertCircle size={16} aria-hidden />
        <span>{error}</span>
        <button type="button" className="alert__action" onClick={() => void load()} disabled={loading}>
          <RotateCw size={13} strokeWidth={1.8} aria-hidden />
          Retry
        </button>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="comparison-tab">
      <section className="panel comparison-tab__intro">
        <div className="comparison-tab__intro-icon">
          <Cpu size={24} strokeWidth={1.4} />
        </div>
        <div>
          <div className="eyebrow">Model head-to-head</div>
          <h2>GPT-OSS 120B vs Med42 70B</h2>
          <p>
            Both runs use the same seven-agent pipeline and the same Gold-layer
            patients; only the underlying LLM differs. Paired on the
            {" "}{data.pairedN} patients where both arms produced an evaluation.
          </p>
        </div>
      </section>

      <ComparisonView
        data={data}
        onOpenPatient={onOpenPatient}
      />
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, RotateCw } from "lucide-react";
import { getMasVsSingleLlmComparison } from "../api";
import type { ComparisonResult } from "../types";
import { ComparisonView } from "./ComparisonView";

type Props = { onOpenPatient?: (uuid: string) => void };

/**
 * 7-agent pipeline vs single-prompt LLM baseline. Demonstrates the value of
 * the multi-agent architecture against the simplest possible control.
 */
export function MasVsSingleLlmTab({ onOpenPatient }: Props) {
  const [data, setData] = useState<ComparisonResult | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getMasVsSingleLlmComparison());
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
      <div className="empty-state"><Loader2 size={16} className="spin" /> Loading comparison…</div>
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
    <ComparisonView
      data={data}
      headline="CMADS beats a single-prompt LLM on the same patients."
      methodology={
        `Both arms use the same reasoning model — GPT-OSS-120B served through Groq at temperature 0.1 — ` +
        `and the same judge. The single-prompt baseline is shown first; CMADS — the principal ` +
        `multi-agent pipeline — sits second as the configuration we recommend leaning on. ` +
        `Compared on ${data.pairedN} patients that appear in both runs.`
      }
      onOpenPatient={onOpenPatient}
    />
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight, ChevronDown, Loader2, Play, Stethoscope,
} from "lucide-react";
import { getModelPresets, getPatients, getStatsOverview } from "../api";
import type { ModelPreset, PatientListItem } from "../types";
import { AdvancedSettings, buildPrecisionRows } from "./runtime/AdvancedSettings";
import type { AdvancedSettingsValue } from "./runtime/AdvancedSettings";

type Props = {
  onRun: (
    uuid: string,
    preset: ModelPreset,
    topK: number,
  ) => void;
};

const GOLD_RESULT_SET = "mas_results"; // any non-runtime cohort lists every Gold UUID

/**
 * Doctor entry surface — single-purpose: type a Gold-layer UUID, click Run.
 *
 * UUID + Run is the only thing visible by default. Model preset, top-K
 * precision, and the system-accuracy mode (multi-level memory vs
 * single-level baseline) live inside a collapsible Advanced panel.
 */
export function RuntimeHero({ onRun }: Props) {
  const [value, setValue] = useState("");
  const [suggestions, setSuggestions] = useState<PatientListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [adv, setAdv] = useState<AdvancedSettingsValue>({
    presetId: "",
    topK: 3,
    accuracyMode: "recommended",
  });
  const [precision, setPrecision] = useState<{ buckets: { label: string; count: number }[]; n: number } | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = "runtime-uuid-input";

  useEffect(() => {
    (async () => {
      try {
        const data = await getStatsOverview("multi_level");
        setPrecision({ buckets: data.rankDistribution, n: data.aggregates.n });
      } catch {
        setPrecision(null);
      }
    })();
  }, []);

  const fetchSuggestions = useCallback(async (q: string) => {
    setLoading(true);
    try {
      // Doctor runtime only ever picks patients that are:
      //   • UNSEEN — no run anywhere in ``data/gold/mas_results*``, AND
      //   • VERIFIED — in the 1000-patient cohort that the LLM
      //     detectability verifier signed off on
      //     (``data/gold/cohort_1k_verify_verification_results.json``).
      // That intersection is the only pool of "fresh + clean" cases the
      // doctor should ever run live.
      const rows = await getPatients(GOLD_RESULT_SET, q, {
        unseenOnly: true,
        verifiedOnly: true,
      });
      setSuggestions(rows);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (value.length === 0 || value.length >= 3) {
        void fetchSuggestions(value);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [value, fetchSuggestions]);

  // We need the preset list only to resolve the label for the summary string.
  // AdvancedSettings fetches it internally too; this is a lightweight parallel
  // fetch just for the summary display — no state is shared.
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  useEffect(() => {
    (async () => {
      try { setPresets(await getModelPresets()); } catch { setPresets([]); }
    })();
  }, []);

  const validUuid = useMemo(
    () => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.trim()),
    [value],
  );
  const matchedSuggestion = suggestions.find((s) => s.uuid === value.trim());
  const selectedPreset = presets.find((p) => p.id === adv.presetId);
  const canRun = (validUuid || !!matchedSuggestion) && !!value.trim() && !!adv.presetId;

  function submit() {
    const uuid = matchedSuggestion?.uuid ?? value.trim();
    if (!uuid || !adv.presetId) return;
    // Resolve the full preset object for the caller; fall back to a minimal stub
    // if the preset list hasn't loaded yet (extremely unlikely in practice).
    const preset = selectedPreset ?? ({ id: adv.presetId } as ModelPreset);
    onRun(uuid, preset, adv.topK);
  }

  const precisionRows = useMemo(
    () => precision ? buildPrecisionRows(precision.buckets, precision.n) : [],
    [precision],
  );

  // Compact summary string shown inside the Advanced <summary> element.
  const advancedSummary = useMemo(() => {
    const modelLabel = selectedPreset?.label ?? "default model";
    return `${modelLabel} · Top ${adv.topK}`;
  }, [selectedPreset, adv.topK]);

  return (
    <motion.section
      className="runtime-solo"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
    >
      <div className="runtime-solo__inner">
        <div className="runtime-solo__brand">
          <Stethoscope size={18} strokeWidth={1.5} />
          <span className="mono">Let's look at a patient</span>
        </div>
        <h1 className="runtime-solo__title">
          Let's look at this patient together.
        </h1>
        <p className="runtime-solo__lede">
          Pull up the patient and I'll walk through their chart and lab work
          with you. In about two minutes you'll see what looks most likely,
          what's worth checking next, and a management plan for the top
          match — for you to take, change, or set aside.
        </p>

        <form
          className="runtime-solo__form"
          onSubmit={(e) => { e.preventDefault(); if (canRun) submit(); }}
        >
          <label htmlFor={inputId} className="runtime-solo__label mono">
            Patient UUID
          </label>
          <div className="runtime-solo__row">
            <div className="runtime-solo__input-wrap">
              <input
                id={inputId}
                ref={inputRef}
                type="text"
                value={value}
                placeholder="e.g.  4b265e38-b837-001f-9059-5020ec1e3e26"
                onFocus={() => setOpen(true)}
                onBlur={() => window.setTimeout(() => setOpen(false), 120)}
                onChange={(e) => { setValue(e.target.value); setOpen(true); }}
                autoComplete="off"
                spellCheck={false}
                className="runtime-solo__input mono"
              />
              {open && (suggestions.length > 0 || loading) ? (
                <div className="runtime-solo__suggestions">
                  {loading ? (
                    <div className="runtime-solo__suggest-row runtime-solo__suggest-row--meta">
                      <Loader2 size={14} className="spin" />
                      Searching {value ? `“${value}”` : "Gold layer"}…
                    </div>
                  ) : (
                    <div className="runtime-solo__suggest-header mono">
                      {suggestions.length} patient{suggestions.length === 1 ? "" : "s"}
                      {value ? <> matching “{value}”</> : <> available · scroll to browse</>}
                    </div>
                  )}
                  {suggestions.map((s) => (
                    <button
                      key={s.uuid}
                      type="button"
                      className="runtime-solo__suggest-row"
                      onMouseDown={() => { setValue(s.uuid); setOpen(false); inputRef.current?.blur(); }}
                    >
                      <span className="mono">{s.uuid}</span>
                      <span className="runtime-solo__suggest-meta">
                        {s.age ? `${s.age} yo` : ""} {s.gender ?? ""}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <button type="submit" className="runtime-solo__cta" disabled={!canRun}>
              <Play size={16} />
              Run pipeline
              <ArrowRight size={16} />
            </button>
          </div>

          <details
            className="runtime-solo__advanced"
            open={advancedOpen}
            onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary className="runtime-solo__advanced-summary">
              <ChevronDown size={14} strokeWidth={1.9} className="runtime-solo__advanced-caret" />
              <span className="runtime-solo__advanced-label">Advanced settings</span>
              <span className="runtime-solo__advanced-current mono">{advancedSummary}</span>
            </summary>

            <AdvancedSettings
              value={adv}
              onChange={setAdv}
              precisionRows={precisionRows}
              precisionN={precision?.n}
            />
          </details>
        </form>

      </div>
    </motion.section>
  );
}


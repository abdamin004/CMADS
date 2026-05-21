import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight, ChevronDown, Cloud, HardDrive, Loader2, Play,
  Sparkles, Stethoscope, Zap,
} from "lucide-react";
import { getModelPresets, getPatients, getStatsOverview } from "../api";
import type { AccuracyMode, ModelPreset, PatientListItem, RankBucket } from "../types";

type Props = {
  onRun: (
    uuid: string,
    preset: ModelPreset,
    topK: number,
    accuracyMode: AccuracyMode,
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
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [presetId, setPresetId] = useState<string>("");
  const [precision, setPrecision] = useState<{ buckets: RankBucket[]; n: number } | null>(null);
  const [selectedK, setSelectedK] = useState<1 | 2 | 3 | 5>(3);
  const [accuracyMode, setAccuracyMode] = useState<AccuracyMode>("recommended");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = "runtime-uuid-input";

  useEffect(() => {
    (async () => {
      try {
        const list = await getModelPresets();
        setPresets(list);
        const usable = list.filter((p) => p.available !== false);
        const def = usable.find((p) => p.default) ?? usable[0];
        if (def) setPresetId(def.id);
      } catch {
        setPresets([]);
      }
    })();
  }, []);

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
      const rows = await getPatients(GOLD_RESULT_SET, q);
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

  const validUuid = useMemo(
    () => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.trim()),
    [value],
  );
  const matchedSuggestion = suggestions.find((s) => s.uuid === value.trim());
  const selectedPreset = presets.find((p) => p.id === presetId);
  const canRun = (validUuid || !!matchedSuggestion) && !!value.trim() && !!selectedPreset;

  function submit() {
    const uuid = matchedSuggestion?.uuid ?? value.trim();
    if (!uuid || !selectedPreset) return;
    onRun(uuid, selectedPreset, selectedK, accuracyMode);
  }

  function formatSeconds(s: number | null | undefined): string {
    if (s === null || s === undefined) return "—";
    if (s < 60) return `${Math.round(s)}s`;
    const m = Math.floor(s / 60);
    const r = Math.round(s - m * 60);
    return r ? `${m}m ${r}s` : `${m}m`;
  }
  function formatUsd(v: number | null | undefined): string {
    if (v === null || v === undefined) return "—";
    if (v === 0) return "free";
    if (v < 0.01) return "<$0.01";
    return `$${v.toFixed(2)}`;
  }

  const precisionRows = useMemo(() => {
    if (!precision) return [];
    const lookup: Record<string, number> = {};
    precision.buckets.forEach((b) => { lookup[b.label] = b.count; });
    const k1 = (lookup["1"] ?? 0);
    const k2 = k1 + (lookup["2"] ?? 0);
    const k3 = k2 + (lookup["3"] ?? 0);
    const k5 = k3 + (lookup["4-5"] ?? 0);
    return [
      { k: 1, count: k1 },
      { k: 2, count: k2 },
      { k: 3, count: k3 },
      { k: 5, count: k5 },
    ].map((r) => ({ ...r, pct: precision.n ? (100 * r.count) / precision.n : 0 }));
  }, [precision]);

  // Compact summary string shown inside the Advanced <summary> element.
  const advancedSummary = useMemo(() => {
    const modelLabel = selectedPreset?.label ?? "default model";
    const modeLabel = accuracyMode === "recommended"
      ? "Multi-level memory"
      : "Fast baseline";
    return `${modelLabel} · Top ${selectedK} · ${modeLabel}`;
  }, [selectedPreset, selectedK, accuracyMode]);

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

            <div className="runtime-solo__advanced-body">
              {/* 1. Accuracy mode */}
              <div className="runtime-solo__adv-section">
                <div className="runtime-solo__label mono">System accuracy mode</div>
                <div className="runtime-solo__accuracy-cards" role="radiogroup" aria-label="System accuracy mode">
                  <button
                    type="button"
                    role="radio"
                    aria-checked={accuracyMode === "recommended"}
                    className={`runtime-solo__accuracy-card${accuracyMode === "recommended" ? " is-active" : ""}`}
                    onClick={() => setAccuracyMode("recommended")}
                  >
                    <span className="runtime-solo__accuracy-head">
                      <Sparkles size={14} strokeWidth={1.9} />
                      <strong>Recommended</strong>
                      <span className="runtime-solo__accuracy-pill">76.9% DIRECT</span>
                    </span>
                    <span className="runtime-solo__accuracy-desc">
                      Multi-level memory enabled. Principal headline
                      configuration on the paired-160 cohort.
                    </span>
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={accuracyMode === "fast"}
                    className={`runtime-solo__accuracy-card${accuracyMode === "fast" ? " is-active" : ""}`}
                    onClick={() => setAccuracyMode("fast")}
                  >
                    <span className="runtime-solo__accuracy-head">
                      <Zap size={14} strokeWidth={1.9} />
                      <strong>Fast baseline</strong>
                      <span className="runtime-solo__accuracy-pill runtime-solo__accuracy-pill--muted">53.8% DIRECT</span>
                    </span>
                    <span className="runtime-solo__accuracy-desc">
                      Single-level memory. Roughly 30 s faster per run;
                      lower accuracy on the same cohort.
                    </span>
                  </button>
                </div>
              </div>

              {/* 2. Top-K precision picker + trust signal */}
              <div className="runtime-solo__adv-section">
                <div className="runtime-solo__label mono">
                  How many suggestions are you willing to read through?
                </div>
                <div className="runtime-solo__precision-picker" role="radiogroup" aria-label="How many top suggestions">
                  {([
                    { k: 1, label: "Just the top guess" },
                    { k: 2, label: "Top 2" },
                    { k: 3, label: "Top 3" },
                    { k: 5, label: "Top 5" },
                  ] as const).map((opt) => (
                    <button
                      key={opt.k}
                      type="button"
                      role="radio"
                      aria-checked={selectedK === opt.k}
                      className={`runtime-solo__precision-chip${selectedK === opt.k ? " is-active" : ""}`}
                      onClick={() => setSelectedK(opt.k)}
                    >
                      <span>{opt.label}</span>
                    </button>
                  ))}
                </div>
                {precisionRows.length ? (() => {
                  const row = precisionRows.find((r) => r.k === selectedK);
                  if (!row) return null;
                  const headline =
                    row.pct >= 85 ? "the answer is almost always there." :
                    row.pct >= 70 ? "the answer is usually there." :
                    row.pct >= 50 ? "the answer is there about half the time." :
                                    "the answer is there sometimes.";
                  return (
                    <div className="runtime-solo__precision-result">
                      <span className="runtime-solo__precision-pct">
                        {row.pct.toFixed(0)}%
                      </span>
                      <span className="runtime-solo__precision-explain">
                        {selectedK === 1
                          ? "of the time, the right diagnosis was the very first one suggested"
                          : `of the time, the right diagnosis was in the top ${selectedK} — ${headline}`}
                        <span className="runtime-solo__precision-n mono">
                          (measured on {precision?.n} past patients with confirmed diagnoses)
                        </span>
                      </span>
                    </div>
                  );
                })() : null}
              </div>

              {/* 3. Model picker */}
              <div className="runtime-solo__adv-section">
                <div className="runtime-solo__label mono">Which engine should help you?</div>
                <div className="runtime-solo__model-list">
                  {presets.map((p) => {
                    const isActive = p.id === presetId;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        className={`runtime-solo__model-item${isActive ? " is-active" : ""}`}
                        onClick={() => setPresetId(p.id)}
                        aria-pressed={isActive}
                      >
                        <div className="runtime-solo__model-item-head">
                          <span className="runtime-solo__model-item-name">{p.label}</span>
                          <span className={`runtime-solo__model-loc runtime-solo__model-loc--${p.location}`}>
                            {p.location === "cloud" ? (
                              <><Cloud size={11} strokeWidth={1.9} /> {p.vendor}</>
                            ) : (
                              <><HardDrive size={11} strokeWidth={1.9} /> {p.vendor}</>
                            )}
                          </span>
                        </div>
                        <div className="runtime-solo__model-item-meta mono">
                          <span title="Measured time per patient">
                            ⏱ {formatSeconds(p.runtimeSeconds)}
                          </span>
                          <span title="Cost per patient">
                            $ {formatUsd(p.costUsdPerPatient)}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </details>
        </form>

      </div>
    </motion.section>
  );
}

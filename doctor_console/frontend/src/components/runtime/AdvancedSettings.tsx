/**
 * AdvancedSettings — reusable model-preset + top-K panel.
 *
 * Used by:
 *   • RuntimeHero          (Known-patient flow, full-width disclosure)
 *   • PatientBuilderEditor (Tester flow, embedded in the action bar)
 *
 * The precision-signal rows (% of the time right answer was in top-K) are
 * optional: pass `precisionRows` from the parent if you want them; omit for
 * the compact Tester version.
 */

import { useEffect, useState } from "react";
import { Cloud, HardDrive } from "lucide-react";
import { getModelPresets } from "../../api";
import type { ModelPreset, RankBucket } from "../../types";

// ── Public types ────────────────────────────────────────────────────────────

export interface AdvancedSettingsValue {
  presetId: string;
  topK: number;
  accuracyMode: "recommended" | "fast";
}

export interface PrecisionRow {
  k: 1 | 2 | 3 | 5;
  count: number;
  pct: number;
}

interface Props {
  value: AdvancedSettingsValue;
  onChange: (next: AdvancedSettingsValue) => void;
  /**
   * When provided the top-K picker shows a trust signal (% of past patients
   * where the correct diagnosis was in the top-K).  Omit for a simpler picker
   * with no statistical callout.
   */
  precisionRows?: PrecisionRow[];
  precisionN?: number;
}

// ── Helper ──────────────────────────────────────────────────────────────────

export function buildPrecisionRows(
  buckets: RankBucket[],
  n: number,
): PrecisionRow[] {
  const lookup: Record<string, number> = {};
  buckets.forEach((b) => { lookup[b.label] = b.count; });
  const k1 = lookup["1"] ?? 0;
  const k2 = k1 + (lookup["2"] ?? 0);
  const k3 = k2 + (lookup["3"] ?? 0);
  const k5 = k3 + (lookup["4-5"] ?? 0);
  return (
    [
      { k: 1 as const, count: k1 },
      { k: 2 as const, count: k2 },
      { k: 3 as const, count: k3 },
      { k: 5 as const, count: k5 },
    ] as Array<{ k: 1 | 2 | 3 | 5; count: number }>
  ).map((r) => ({ ...r, pct: n ? (100 * r.count) / n : 0 }));
}

// ── Component ────────────────────────────────────────────────────────────────

export function AdvancedSettings({ value, onChange, precisionRows, precisionN }: Props) {
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [modelQuery, setModelQuery] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const list = await getModelPresets();
        setPresets(list);
        // If no presetId has been chosen yet, default to the first available preset.
        if (!value.presetId) {
          const usable = list.filter((p) => p.available !== false);
          const def = usable.find((p) => p.default) ?? usable[0];
          if (def) onChange({ ...value, presetId: def.id });
        }
      } catch {
        setPresets([]);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const topKOptions = [
    { k: 1 as const, label: "Just the top guess" },
    { k: 2 as const, label: "Top 2" },
    { k: 3 as const, label: "Top 3" },
    { k: 5 as const, label: "Top 5" },
  ];

  const precisionRow = precisionRows?.find((r) => r.k === value.topK);
  const headline =
    !precisionRow ? null :
    precisionRow.pct >= 85 ? "the answer is almost always there." :
    precisionRow.pct >= 70 ? "the answer is usually there." :
    precisionRow.pct >= 50 ? "the answer is there about half the time." :
                             "the answer is there sometimes.";

  const available   = presets.filter((p) => p.available !== false);
  const unavailable = presets.filter((p) => p.available === false);
  const recommended = available.filter((p) => p.recommended);
  const others      = available.filter((p) => !p.recommended);
  const q = modelQuery.trim().toLowerCase();
  const matchesQuery = (p: ModelPreset) => {
    if (!q) return true;
    return (
      p.label.toLowerCase().includes(q) ||
      (p.model || "").toLowerCase().includes(q) ||
      (p.vendor || "").toLowerCase().includes(q)
    );
  };
  const filteredOthers = others.filter(matchesQuery);

  return (
    <div className="runtime-solo__advanced-body">
      {/* ── System accuracy / memory mode ── */}
      <div className="runtime-solo__adv-section">
        <div className="runtime-solo__label mono">System accuracy</div>
        <div className="runtime-solo__accuracy-cards" role="radiogroup" aria-label="System accuracy mode">
          {(
            [
              {
                id: "recommended" as const,
                title: "Multi-level memory",
                pill: "recommended",
                pillMuted: false,
                desc: "Full seven-agent pipeline — EHR analyst, lab interpreter, diagnostic loop, adversarial reviewer, refiner, and treatment planner. Best accuracy; ~2 min per patient.",
              },
              {
                id: "fast" as const,
                title: "Baseline (fast)",
                pill: "faster",
                pillMuted: true,
                desc: "Single-LLM pass — skips the multi-agent loop. Lower precision but noticeably quicker. Good for iterating on a patient sketch.",
              },
            ] as const
          ).map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={value.accuracyMode === opt.id}
              className={`runtime-solo__accuracy-card${value.accuracyMode === opt.id ? " is-active" : ""}`}
              onClick={() => onChange({ ...value, accuracyMode: opt.id })}
            >
              <div className="runtime-solo__accuracy-head">
                {opt.title}
                <span className={`runtime-solo__accuracy-pill${opt.pillMuted ? " runtime-solo__accuracy-pill--muted" : ""}`}>
                  {opt.pill}
                </span>
              </div>
              <div className="runtime-solo__accuracy-desc">{opt.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Top-K picker ── */}
      <div className="runtime-solo__adv-section">
        <div className="runtime-solo__label mono">
          How many suggestions are you willing to read through?
        </div>
        <div
          className="runtime-solo__precision-picker"
          role="radiogroup"
          aria-label="How many top suggestions"
        >
          {topKOptions.map((opt) => (
            <button
              key={opt.k}
              type="button"
              role="radio"
              aria-checked={value.topK === opt.k}
              className={`runtime-solo__precision-chip${value.topK === opt.k ? " is-active" : ""}`}
              onClick={() => onChange({ ...value, topK: opt.k })}
            >
              <span>{opt.label}</span>
            </button>
          ))}
        </div>

        {precisionRow && headline && (
          <div className="runtime-solo__precision-result">
            <span className="runtime-solo__precision-pct">
              {precisionRow.pct.toFixed(0)}%
            </span>
            <span className="runtime-solo__precision-explain">
              {value.topK === 1
                ? "of the time, the right diagnosis was the very first one suggested"
                : `of the time, the right diagnosis was in the top ${value.topK} — ${headline}`}
              {precisionN != null && (
                <span className="runtime-solo__precision-n mono">
                  (measured on {precisionN} past patients with confirmed diagnoses)
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* ── Model picker ── */}
      <div className="runtime-solo__adv-section">
        <div className="runtime-solo__label mono">Which model should help you?</div>
        <div className="model-picker">
          {recommended.length > 0 && (
            <>
              <div className="model-picker__group-label mono">
                <span className="model-picker__group-dot model-picker__group-dot--star" />
                Recommended · {recommended.length}
              </div>
              <ul className="model-picker__list">
                {recommended.map((p) => (
                  <ModelRow
                    key={p.id}
                    p={p}
                    isActive={p.id === value.presetId}
                    onSelect={() => onChange({ ...value, presetId: p.id })}
                  />
                ))}
              </ul>
            </>
          )}

          {others.length > 0 && (
            <>
              <div className="model-picker__group-head">
                <div className="model-picker__group-label mono">
                  <span className="model-picker__group-dot model-picker__group-dot--ok" />
                  All available models · {filteredOthers.length} / {others.length}
                </div>
                <input
                  className="model-picker__search mono"
                  type="search"
                  value={modelQuery}
                  onChange={(e) => setModelQuery(e.target.value)}
                  placeholder="search by name, model id, or vendor…"
                />
              </div>
              <ul className="model-picker__list model-picker__list--scroll">
                {filteredOthers.length > 0 ? (
                  filteredOthers.map((p) => (
                    <ModelRow
                      key={p.id}
                      p={p}
                      isActive={p.id === value.presetId}
                      onSelect={() => onChange({ ...value, presetId: p.id })}
                    />
                  ))
                ) : (
                  <li className="model-picker__empty">
                    No models match "{modelQuery}".
                  </li>
                )}
              </ul>
            </>
          )}

          {unavailable.length > 0 && (
            <>
              <div className="model-picker__group-label model-picker__group-label--muted mono">
                <span className="model-picker__group-dot model-picker__group-dot--off" />
                Not configured · {unavailable.length}
              </div>
              <ul className="model-picker__list model-picker__list--unavailable">
                {unavailable.map((p) => (
                  <ModelRow
                    key={p.id}
                    p={p}
                    isActive={false}
                    disabled
                    onSelect={() => {}}
                  />
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── ModelRow ────────────────────────────────────────────────────────────────

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

export function ModelRow({
  p,
  isActive,
  disabled = false,
  onSelect,
}: {
  p: ModelPreset;
  isActive: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={
          `model-row${isActive ? " is-active" : ""}${disabled ? " is-disabled" : ""}`
        }
        onClick={disabled ? undefined : onSelect}
        aria-pressed={isActive}
        aria-disabled={disabled}
        disabled={disabled}
      >
        <div className="model-row__left">
          <div className="model-row__name-row">
            <span className="model-row__name">{p.label}</span>
            <span className={`model-row__loc model-row__loc--${p.location}`}>
              {p.location === "cloud" ? (
                <><Cloud size={11} strokeWidth={1.9} /> {p.vendor}</>
              ) : (
                <><HardDrive size={11} strokeWidth={1.9} /> {p.vendor}</>
              )}
            </span>
          </div>
          {disabled ? (
            <div className="model-row__reason">{p.unavailableReason || "Not configured"}</div>
          ) : (
            <div className="model-row__meta mono">
              <span title="Measured time per patient">⏱ {formatSeconds(p.runtimeSeconds)}</span>
              <span title="Cost per patient">$ {formatUsd(p.costUsdPerPatient)}</span>
            </div>
          )}
        </div>
        <div className="model-row__right">
          {isActive ? <span className="model-row__check">✓</span> : null}
        </div>
      </button>
    </li>
  );
}

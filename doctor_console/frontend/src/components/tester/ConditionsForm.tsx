import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Calendar, Plus, Sparkles, Trash2, Zap } from "lucide-react";
import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["conditions"];
  onChange: (next: TestPatientPayload["conditions"]) => void;
}

// Quick-add shortcuts — the conditions most frequent across the cohort.
// Codes are SNOMED so the agent receives a clean code+label pair, identical
// to what the VocabularyCombobox would have produced.
const COMMON_CONDITIONS: VocabularyItem[] = [
  { label: "Essential hypertension",                 code: "59621000"  },
  { label: "Type 2 diabetes mellitus",               code: "44054006"  },
  { label: "Chronic kidney disease stage 3",         code: "433144002" },
  { label: "Ischemic heart disease",                 code: "414545008" },
  { label: "Atrial fibrillation",                    code: "49436004"  },
  { label: "Hyperlipidemia",                         code: "55822004"  },
  { label: "Chronic obstructive pulmonary disease",  code: "13645005"  },
  { label: "Asthma",                                 code: "195967001" },
];

/* ────────────────────────────────────────────────────────────────────────
   Body-system classification.
   Pure presentation aid — the payload schema only carries a label + code.
   We infer a system from keywords so we can tint the row, group the list
   when it grows past 4 items, and surface a small tally so a polypathic
   patient stays scannable. Falls back to "other" when no rule matches.
   ──────────────────────────────────────────────────────────────────── */
type System =
  | "cardiovascular" | "endocrine" | "renal" | "respiratory"
  | "musculoskeletal" | "gastrointestinal" | "neurologic"
  | "psychiatric" | "infectious" | "hematology" | "oncology" | "other";

const SYSTEM_RULES: Array<{ match: RegExp; system: System }> = [
  { match: /\b(hypertens|heart|coronary|ischemi|cardiac|angina|atrial|afib|chf|congestive|valv|aortic|pericard|myocard|hyperlipid|cholesterol|stroke)/i, system: "cardiovascular" },
  { match: /\b(diabet|insulin|glycemi|thyroid|hashimoto|graves|hypothyroid|hyperthyroid|adrenal|cushing|addison|pituitary|metabolic syndrome|obesity)/i,            system: "endocrine"      },
  { match: /\b(kidney|renal|nephrit|nephrot|esrd|ckd|dialysis|glomerul|uremia)/i,                                                                                  system: "renal"           },
  { match: /\b(copd|asthma|emphysema|pneumon|bronch|pulmonary|tubercul|lung|respirator)/i,                                                                          system: "respiratory"     },
  { match: /\b(arthrit|osteo|fibromyal|gout|spondyl|bursitis|tendon|fracture|rheumat)/i,                                                                            system: "musculoskeletal" },
  { match: /\b(gerd|ulcer|hepatit|cirrhos|colit|crohn|\bibs\b|gastro|liver|biliary|pancreatit|cholelith|esophag)/i,                                                 system: "gastrointestinal"},
  { match: /\b(seizure|epilep|migraine|parkinson|alzheim|dementia|multiple sclerosis|\bms\b|neuropath)/i,                                                           system: "neurologic"      },
  { match: /\b(depress|anxiety|bipolar|schizoph|adhd|ptsd|\bocd\b|psychiatric|alcohol|substance|opioid)/i,                                                          system: "psychiatric"     },
  { match: /\b(hiv|aids|sepsis|infection|cellulit|abscess|covid|influenza|sars)/i,                                                                                  system: "infectious"      },
  { match: /\b(anemia|leuk|lymph|throm|coagul|sickle|hematol)/i,                                                                                                    system: "hematology"      },
  { match: /\b(cancer|malignan|carcinoma|tumou?r|metasta|lymphoma|leukemia|neoplasm)/i,                                                                             system: "oncology"        },
];

const SYSTEM_META: Record<System, { label: string; tone: string }> = {
  cardiovascular:   { label: "Cardiovascular",     tone: "critical" },
  endocrine:        { label: "Endocrine",          tone: "warning"  },
  renal:            { label: "Renal",              tone: "accent"   },
  respiratory:      { label: "Respiratory",        tone: "spark"    },
  musculoskeletal:  { label: "Musculoskeletal",    tone: "warning"  },
  gastrointestinal: { label: "Gastrointestinal",   tone: "warning"  },
  neurologic:       { label: "Neurologic",         tone: "violet"   },
  psychiatric:      { label: "Psychiatric",        tone: "violet"   },
  infectious:       { label: "Infectious",         tone: "critical" },
  hematology:       { label: "Hematology",         tone: "critical" },
  oncology:         { label: "Oncology",           tone: "critical" },
  other:            { label: "Other",              tone: "muted"    },
};

// Render order when grouping — frequency-first, then alphabetical-ish for
// the rarer ones. Drives the order of mini-section headers.
const SYSTEM_ORDER: System[] = [
  "cardiovascular", "endocrine", "renal", "respiratory",
  "musculoskeletal", "gastrointestinal", "neurologic",
  "psychiatric", "infectious", "hematology", "oncology", "other",
];

function systemFor(name?: string): System {
  if (!name) return "other";
  for (const r of SYSTEM_RULES) if (r.match.test(name)) return r.system;
  return "other";
}

/* Chronic / acute inference — keyword-only. "Chronic", "stage N", "type N"
   read as chronic; "acute", "exacerbation" read as acute. Anything else
   stays unmarked. */
type Chronicity = "chronic" | "acute" | null;
function chronicityFor(name?: string): Chronicity {
  if (!name) return null;
  if (/\b(chronic|stage\s*\d|type\s*[12]|long[-\s]?standing|persistent)/i.test(name)) return "chronic";
  if (/\b(acute|exacerbation|flare|sudden|new[-\s]?onset)/i.test(name))                return "acute";
  return null;
}

export function ConditionsForm({ value, onChange }: Props) {
  const active = value?.active ?? [];
  const [expanded, setExpanded] = useState<number | null>(null);

  function add(item: VocabularyItem) {
    const key = (item.code ?? item.label).toLowerCase();
    const exists = active.some(
      (c) => (c.code ?? c.condition).toLowerCase() === key,
    );
    if (exists) return;
    onChange({
      active: [...active, { condition: item.label, code: item.code ?? undefined }],
    });
  }
  function remove(idx: number) {
    onChange({ active: active.filter((_, i) => i !== idx) });
    setExpanded(null);
  }
  function patchDate(idx: number, date: string) {
    onChange({
      active: active.map((c, i) =>
        i === idx ? { ...c, start_date: date || undefined } : c,
      ),
    });
  }
  function clearAll() {
    if (active.length === 0) return;
    onChange({ active: [] });
    setExpanded(null);
  }

  const usedKeys = new Set(
    active.map((c) => (c.code ?? c.condition).toLowerCase()),
  );
  const suggestions = COMMON_CONDITIONS.filter(
    (c) => !usedKeys.has((c.code ?? c.label).toLowerCase()),
  ).slice(0, 6);

  // Compute (system, chronicity) once and reuse so the renderer doesn't
  // re-scan the keyword tables on every interaction.
  const enriched = useMemo(
    () => active.map((c, i) => ({
      idx:         i,
      cond:        c,
      system:      systemFor(c.condition),
      chronicity:  chronicityFor(c.condition),
    })),
    [active],
  );

  // System tally for the inline distribution bar (rendered when ≥ 2 systems
  // are represented). Each segment width is proportional to the share.
  const tally = useMemo(() => {
    if (active.length < 2) return [] as Array<{ system: System; count: number }>;
    const counts = new Map<System, number>();
    enriched.forEach((e) => counts.set(e.system, (counts.get(e.system) ?? 0) + 1));
    if (counts.size < 2) return [];
    return SYSTEM_ORDER
      .filter((s) => counts.has(s))
      .map((s) => ({ system: s, count: counts.get(s)! }));
  }, [enriched, active.length]);

  // Group when the list is long enough to benefit from headers. Below the
  // threshold the flat list reads better — no point fragmenting six rows
  // into four single-row buckets.
  const useGrouping = active.length >= 4;
  const groups = useMemo(() => {
    if (!useGrouping) return [{ system: null as System | null, items: enriched }];
    const map = new Map<System, typeof enriched>();
    enriched.forEach((e) => {
      if (!map.has(e.system)) map.set(e.system, []);
      map.get(e.system)!.push(e);
    });
    return SYSTEM_ORDER
      .filter((s) => map.has(s))
      .map((s) => ({ system: s as System | null, items: map.get(s as System)! }));
  }, [enriched, useGrouping]);

  return (
    <div className="cond-form">
      <VocabularyCombobox
        kind="condition"
        placeholder="Search a condition by name or SNOMED code…"
        onPick={add}
      />

      {suggestions.length > 0 && (
        <div className="cond-form__suggest">
          <span className="cond-form__suggest-eyebrow">
            <Sparkles size={11} strokeWidth={1.8} />
            Common in this cohort
          </span>
          <div className="cond-form__suggest-row">
            {suggestions.map((s) => (
              <button
                key={s.code ?? s.label}
                type="button"
                onClick={() => add(s)}
                className="cond-suggest-chip"
                title={`Add ${s.label}${s.code ? ` (${s.code})` : ""}`}
              >
                <Plus size={11} strokeWidth={2.2} />
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {active.length > 0 && (
        <div className="cond-form__count-row">
          <span className="cond-form__count">
            <strong>{active.length}</strong>
            {active.length === 1 ? " active condition" : " active conditions"}
          </span>
          <button type="button" onClick={clearAll} className="cond-form__clear">
            Clear all
          </button>
        </div>
      )}

      {/* Inline body-system tally. Renders once 2+ systems are represented;
          a single thin segmented bar plus a chip legend reads as a quick
          "what does this patient have going on" summary. */}
      {tally.length > 0 && (
        <div className="cond-tally" aria-label="Body system distribution">
          <div className="cond-tally__bar" role="presentation">
            {tally.map(({ system, count }) => (
              <span
                key={system}
                className={`cond-tally__seg cond-tally__seg--${SYSTEM_META[system].tone}`}
                style={{ flex: count }}
                title={`${SYSTEM_META[system].label} · ${count}`}
              />
            ))}
          </div>
          <div className="cond-tally__legend">
            {tally.map(({ system, count }) => (
              <span
                key={system}
                className={`cond-tally__chip cond-tally__chip--${SYSTEM_META[system].tone}`}
              >
                {SYSTEM_META[system].label}
                <span className="cond-tally__chip-count mono">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {active.length === 0 && (
        <div className="cond-form__empty">
          <div className="cond-form__empty-mark" aria-hidden="true" />
          <div>
            <div className="cond-form__empty-title">
              No conditions on file yet
            </div>
            <div className="cond-form__empty-sub">
              Search above, or pick from the common-cohort chips to seed
              the diagnostic-reasoning agent's prior.
            </div>
          </div>
        </div>
      )}

      {/* Grouped or flat list. Group headers only appear when useGrouping
          is true (≥ 4 conditions); below that, the flat list keeps the
          visual weight tight. */}
      <motion.div className="cond-groups" layout>
        {groups.map((g) => (
          <div key={g.system ?? "_flat"} className="cond-group">
            {g.system && (
              <header className="cond-group__head">
                <span
                  className={`cond-group__dot cond-group__dot--${SYSTEM_META[g.system].tone}`}
                  aria-hidden="true"
                />
                <span className="cond-group__title">
                  {SYSTEM_META[g.system].label}
                </span>
                <span className="cond-group__count mono">{g.items.length}</span>
              </header>
            )}
            <motion.ul className="cond-list" layout>
              <AnimatePresence initial={false} mode="popLayout">
                {g.items.map(({ idx, cond: c, system, chronicity }) => {
                  const isOpen = expanded === idx;
                  return (
                    <motion.li
                      key={`${c.code ?? c.condition}-${idx}`}
                      layout
                      initial={{ opacity: 0, y: -6, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0,  scale: 1 }}
                      exit={{ opacity: 0, scale: 0.96 }}
                      transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
                      className={`cond-card cond-card--${SYSTEM_META[system].tone}`}
                    >
                      <div className="cond-card__row">
                        <div className="cond-card__main">
                          <span className="cond-card__name">{c.condition}</span>
                          {c.code && (
                            <span className="cond-card__code mono">{c.code}</span>
                          )}
                          {chronicity && (
                            <span className={`cond-card__acuity cond-card__acuity--${chronicity}`}>
                              {chronicity === "chronic"
                                ? <Activity size={10} strokeWidth={2} />
                                : <Zap size={10} strokeWidth={2} />}
                              {chronicity}
                            </span>
                          )}
                          {!useGrouping && system !== "other" && (
                            <span className={`cond-card__system cond-card__system--${SYSTEM_META[system].tone}`}>
                              {SYSTEM_META[system].label}
                            </span>
                          )}
                        </div>
                        <div className="cond-card__actions">
                          <button
                            type="button"
                            onClick={() => setExpanded(isOpen ? null : idx)}
                            className={`cond-card__meta-btn${isOpen ? " is-open" : ""}${c.start_date ? " has-date" : ""}`}
                            aria-expanded={isOpen}
                            aria-label={
                              c.start_date
                                ? `Edit onset date (${c.start_date})`
                                : "Add onset date"
                            }
                          >
                            <Calendar size={12} strokeWidth={1.8} />
                            {c.start_date
                              ? <span className="mono">{c.start_date}</span>
                              : <span>onset</span>}
                          </button>
                          <button
                            type="button"
                            onClick={() => remove(idx)}
                            className="cond-card__remove"
                            aria-label={`Remove ${c.condition}`}
                          >
                            <Trash2 size={13} strokeWidth={1.7} />
                          </button>
                        </div>
                      </div>
                      <AnimatePresence initial={false}>
                        {isOpen && (
                          <motion.div
                            key="meta"
                            className="cond-card__meta"
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.16, ease: "easeOut" }}
                          >
                            <label className="cond-card__meta-label">
                              Onset
                              <input
                                type="date"
                                value={c.start_date ?? ""}
                                onChange={(e) => patchDate(idx, e.target.value)}
                                className="cond-card__date"
                              />
                            </label>
                            {c.start_date && (
                              <button
                                type="button"
                                onClick={() => patchDate(idx, "")}
                                className="cond-card__meta-clear"
                              >
                                Clear
                              </button>
                            )}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
            </motion.ul>
          </div>
        ))}
      </motion.div>
    </div>
  );
}

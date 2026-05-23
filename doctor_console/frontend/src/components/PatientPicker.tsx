import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Search, X } from "lucide-react";
import { browseCohort, getCohortTemplate, getDiseaseCounts } from "../api";
import type { CohortBrowseRow, TestPatientPayload } from "../types";

/* ─── Constants ─────────────────────────────────────────────────────────── */

const DISEASES = [
  "Ischemic heart disease",
  "Chronic congestive heart failure",
  "Essential hypertension",
  "Diabetes mellitus type 2",
  "End-stage renal disease",
  "Chronic kidney disease stage 3",
  "Chronic kidney disease stage 2",
  "Metabolic syndrome X",
];

const AGE_MIN = 0;
const AGE_MAX = 120;
const AGE_TICKS = [0, 20, 40, 60, 80, 100, 120];
const GENDER_OPTIONS = ["", "M", "F", "Other"] as const;
type GenderOption = (typeof GENDER_OPTIONS)[number];

/* ─── Helpers ────────────────────────────────────────────────────────────── */

function genderColors(gender: string | null) {
  if (gender === "F") return "bg-emerald-600/20 text-emerald-100";
  if (gender === "M") return "bg-sky-600/20 text-sky-100";
  return "bg-slate-700/40 text-slate-300";
}

function isDefaultAge(range: [number, number]) {
  return range[0] === AGE_MIN && range[1] === AGE_MAX;
}

/**
 * Strip the SNOMED qualifier suffix from a condition / diagnosis name so
 * "Chronic kidney disease stage 4 (disorder)" reads as "Chronic kidney
 * disease stage 4" in the UI. The suffixes are SNOMED's semantic-tag
 * artifacts (disorder / finding / situation / procedure / observable
 * entity / morphologic abnormality / qualifier value) and add no
 * clinical signal at the patient picker level.
 */
function stripSnomedSuffix(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/\s*\((disorder|finding|situation|procedure|observable entity|morphologic abnormality|qualifier value|substance|body structure)\)\s*$/i, "")
    .trim();
}

/* ─── DualRangeSlider ────────────────────────────────────────────────────── */
// Two stacked <input type="range"> with CSS to create a real dual-thumb
// track fill. The z-index trick ensures whichever thumb is closer to the
// pointer is always "on top" and grabbable.

interface SliderProps {
  min?: number;
  max?: number;
  value: [number, number];
  onChange: (v: [number, number]) => void;
}

function DualRangeSlider({ min = 0, max = 120, value, onChange }: SliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [lo, hi] = value;

  const loPercent = ((lo - min) / (max - min)) * 100;
  const hiPercent = ((hi - min) / (max - min)) * 100;

  const handleLo = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const next = Math.min(Number(e.target.value), hi - 1);
      onChange([next, hi]);
    },
    [hi, onChange],
  );

  const handleHi = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const next = Math.max(Number(e.target.value), lo + 1);
      onChange([lo, next]);
    },
    [lo, onChange],
  );

  return (
    <div className="picker-slider__root">
      {/* Track visual */}
      <div ref={trackRef} className="picker-slider__track">
        {/* Filled region between thumbs */}
        <div
          className="picker-slider__fill"
          style={{
            left: `${loPercent}%`,
            width: `${hiPercent - loPercent}%`,
          }}
        />
      </div>

      {/* Low thumb */}
      <input
        type="range"
        min={min}
        max={max}
        value={lo}
        onChange={handleLo}
        className="picker-slider__input"
        style={{ zIndex: lo > max - 10 ? 5 : 3 }}
        aria-label="Minimum age"
      />

      {/* High thumb */}
      <input
        type="range"
        min={min}
        max={max}
        value={hi}
        onChange={handleHi}
        className="picker-slider__input"
        style={{ zIndex: 4 }}
        aria-label="Maximum age"
      />

      {/* Tick marks */}
      <div className="picker-slider__ticks">
        {AGE_TICKS.map((t) => (
          <span
            key={t}
            className="picker-slider__tick"
            style={{ left: `${((t - min) / (max - min)) * 100}%` }}
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ─── ActiveFilterChips ──────────────────────────────────────────────────── */

interface ChipsProps {
  disease: string;
  ageRange: [number, number];
  gender: string;
  onClearDisease: () => void;
  onClearAge: () => void;
  onClearGender: () => void;
  onClearAll: () => void;
}

function ActiveFilterChips({
  disease,
  ageRange,
  gender,
  onClearDisease,
  onClearAge,
  onClearGender,
  onClearAll,
}: ChipsProps) {
  const hasDisease = disease !== "";
  const hasAge = !isDefaultAge(ageRange);
  const hasGender = gender !== "";
  const hasAny = hasDisease || hasAge || hasGender;

  return (
    <AnimatePresence initial={false}>
      {hasAny && (
        <motion.div
          key="chips-bar"
          layout
          initial={{ opacity: 0, height: 0, marginBottom: 0 }}
          animate={{ opacity: 1, height: "auto", marginBottom: 8 }}
          exit={{ opacity: 0, height: 0, marginBottom: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className="picker-chips__bar"
        >
          <div className="picker-chips__pills">
            <AnimatePresence mode="popLayout">
              {hasDisease && (
                <motion.button
                  key="chip-disease"
                  layout
                  initial={{ opacity: 0, scale: 0.88, x: -4 }}
                  animate={{ opacity: 1, scale: 1, x: 0 }}
                  exit={{ opacity: 0, scale: 0.88, x: -4 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                  onClick={onClearDisease}
                  className="picker-chips__pill"
                >
                  <span className="picker-chips__pill-label">
                    Disease: <strong>{disease}</strong>
                  </span>
                  <X size={11} className="picker-chips__pill-x" />
                </motion.button>
              )}
              {hasAge && (
                <motion.button
                  key="chip-age"
                  layout
                  initial={{ opacity: 0, scale: 0.88, x: -4 }}
                  animate={{ opacity: 1, scale: 1, x: 0 }}
                  exit={{ opacity: 0, scale: 0.88, x: -4 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                  onClick={onClearAge}
                  className="picker-chips__pill"
                >
                  <span className="picker-chips__pill-label">
                    Age:{" "}
                    <strong>
                      {ageRange[0]}–{ageRange[1]}
                    </strong>
                  </span>
                  <X size={11} className="picker-chips__pill-x" />
                </motion.button>
              )}
              {hasGender && (
                <motion.button
                  key="chip-gender"
                  layout
                  initial={{ opacity: 0, scale: 0.88, x: -4 }}
                  animate={{ opacity: 1, scale: 1, x: 0 }}
                  exit={{ opacity: 0, scale: 0.88, x: -4 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                  onClick={onClearGender}
                  className="picker-chips__pill"
                >
                  <span className="picker-chips__pill-label">
                    Gender: <strong>{gender}</strong>
                  </span>
                  <X size={11} className="picker-chips__pill-x" />
                </motion.button>
              )}
            </AnimatePresence>
          </div>
          <button onClick={onClearAll} className="picker-chips__clear-all">
            Clear all
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ─── Props ──────────────────────────────────────────────────────────────── */

interface Props {
  onTemplate: (payload: TestPatientPayload) => void;
}

/* ─── PatientPicker ──────────────────────────────────────────────────────── */

export function PatientPicker({ onTemplate }: Props) {
  /* Filter state */
  const [disease, setDisease] = useState<string>("");
  const [ageRange, setAgeRange] = useState<[number, number]>([0, 120]);
  const [gender, setGender] = useState<string>("");
  const [diseaseSearch, setDiseaseSearch] = useState<string>("");

  /* Data state */
  const [rows, setRows] = useState<CohortBrowseRow[]>([]);
  const [selected, setSelected] = useState<CohortBrowseRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<TestPatientPayload | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  /* Disease counts from new endpoint */
  const [diseaseCounts, setDiseaseCounts] = useState<
    Record<string, number> | null
  >(null);
  const [countsLoading, setCountsLoading] = useState(true);

  /* Fetch disease counts once on mount */
  useEffect(() => {
    setCountsLoading(true);
    getDiseaseCounts()
      .then(setDiseaseCounts)
      .catch(() => setDiseaseCounts(null))
      .finally(() => setCountsLoading(false));
  }, []);

  /* Fetch patient list whenever filters change */
  useEffect(() => {
    setLoading(true);
    browseCohort({
      disease: disease || undefined,
      age_min: ageRange[0],
      age_max: ageRange[1],
      gender: gender || undefined,
      limit: 500,
    })
      .then((r) => {
        setRows(r);
        setSelected(null);
        setPreview(null);
      })
      .finally(() => setLoading(false));
  }, [disease, ageRange[0], ageRange[1], gender]);

  /* Fetch full template when selection changes */
  useEffect(() => {
    if (!selected) {
      setPreview(null);
      return;
    }
    setPreviewLoading(true);
    getCohortTemplate(selected.uuid)
      .then(setPreview)
      .catch(() => setPreview(null))
      .finally(() => setPreviewLoading(false));
  }, [selected?.uuid]);

  function useTemplate() {
    if (!preview) return;
    onTemplate(preview);
  }

  /* Derived */
  const filteredDiseases = DISEASES.filter((d) =>
    d.toLowerCase().includes(diseaseSearch.toLowerCase()),
  );

  const displayGender = selected?.gender ?? null;
  const displayAge = selected?.age ?? null;

  /* Clear helpers */
  const clearAll = () => {
    setDisease("");
    setAgeRange([AGE_MIN, AGE_MAX]);
    setGender("");
  };

  return (
    <div className="flex h-full flex-col gap-6 px-6 lg:px-10 py-6 lg:flex-row">
      {/* ────────────────────────────── LEFT: facets ──────────────────────── */}
      <aside className="picker-aside shrink-0 space-y-0 border-b border-slate-800 pb-3 lg:w-60 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-4">

        {/* A. Active filter chips */}
        <ActiveFilterChips
          disease={disease}
          ageRange={ageRange}
          gender={gender}
          onClearDisease={() => setDisease("")}
          onClearAge={() => setAgeRange([AGE_MIN, AGE_MAX])}
          onClearGender={() => setGender("")}
          onClearAll={clearAll}
        />

        {/* B. Disease combobox */}
        <div className="picker-section">
          <div className="picker-section__label">Disease</div>

          {/* Search input */}
          <div className="picker-disease__search-wrap">
            <Search size={13} className="picker-disease__search-icon" />
            <input
              type="text"
              value={diseaseSearch}
              onChange={(e) => setDiseaseSearch(e.target.value)}
              placeholder="Filter by disease…"
              className="picker-disease__search-input"
            />
            {diseaseSearch && (
              <button
                onClick={() => setDiseaseSearch("")}
                className="picker-disease__search-clear"
                aria-label="Clear search"
              >
                <X size={11} />
              </button>
            )}
          </div>

          {/* Disease pills */}
          <div className="picker-disease__list">
            <AnimatePresence initial={false} mode="sync">
              {filteredDiseases.map((d) => {
                const active = disease === d;
                const count = diseaseCounts?.[d];
                return (
                  <motion.button
                    key={d}
                    layout
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.12, ease: "easeOut" }}
                    onClick={() => setDisease(active ? "" : d)}
                    className={`picker-disease__pill${active ? " picker-disease__pill--active" : ""}`}
                  >
                    <span className="picker-disease__pill-name">{d}</span>
                    <span className="picker-disease__pill-count">
                      {countsLoading ? (
                        <span className="picker-disease__pill-count-loading" />
                      ) : count != null ? (
                        count
                      ) : (
                        "—"
                      )}
                    </span>
                  </motion.button>
                );
              })}
              {filteredDiseases.length === 0 && (
                <motion.div
                  key="no-match"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="picker-disease__empty"
                >
                  No match
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* C. Age range slider */}
        <div className="picker-section">
          <div className="picker-section__label">Age range</div>
          <div className="picker-age__readout">
            <span className="picker-age__value">{ageRange[0]}</span>
            <span className="picker-age__sep">–</span>
            <span className="picker-age__value">{ageRange[1]}</span>
            <span className="picker-age__unit">yrs</span>
          </div>
          <DualRangeSlider value={ageRange} onChange={setAgeRange} />
        </div>

        {/* D. Gender — segmented control */}
        <div className="picker-section">
          <div className="picker-section__label">Gender</div>
          <div className="segmented w-full">
            {GENDER_OPTIONS.map((g) => (
              <button
                key={g || "any"}
                onClick={() => setGender(g === gender ? "" : g)}
                className={`segmented__btn flex-1 justify-center${gender === g ? " segmented__btn--active" : ""}`}
              >
                {g || "Any"}
              </button>
            ))}
          </div>
        </div>
      </aside>

      {/* ────────────────────────────── MIDDLE: list ──────────────────────── */}
      <section className="shrink-0 overflow-y-auto border-b border-slate-800 pb-2 lg:w-80 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-2">
        {/* E. Result count chip */}
        <div className="mb-2 flex items-center">
          {loading ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800 px-2.5 py-0.5 text-xs text-slate-400">
              <Loader2 size={10} className="animate-spin" />
              <span>Searching…</span>
            </span>
          ) : (
            <AnimatePresence mode="wait">
              <motion.span
                key={rows.length}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.15, ease: "easeOut" }}
                className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800 px-2.5 py-0.5 text-xs text-slate-400"
              >
                <span className="font-medium text-emerald-300 tabular-nums">
                  {rows.length}
                </span>
                <span>patient{rows.length === 1 ? "" : "s"}</span>
              </motion.span>
            </AnimatePresence>
          )}
        </div>

        <ul className="space-y-1">
          {rows.map((row) => (
            <li key={row.uuid}>
              <button
                onClick={() => setSelected(row)}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm transition-colors
                           ${
                             selected?.uuid === row.uuid
                               ? "border border-emerald-600/30 bg-emerald-600/20 text-emerald-200"
                               : "border border-transparent text-slate-300 hover:bg-slate-800"
                           }`}
              >
                <div className="font-mono text-xs text-slate-500">
                  {row.uuid.slice(0, 11)}
                </div>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="font-medium">
                    {row.age ?? "?"}
                    <span className="ml-0.5">{row.gender ?? "?"}</span>
                  </span>
                  {row.disease && (
                    <span className="inline-flex items-center rounded-full border border-emerald-700/50 bg-emerald-900/30 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
                      {stripSnomedSuffix(row.disease)}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {row.active_count} active conditions
                </div>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* ────────────────────────────── RIGHT: clinical preview ───────────── */}
      <section className="flex-1 overflow-y-auto pr-2">
        {!selected && (
          <div className="flex h-full items-center justify-center text-center">
            <div className="max-w-xs">
              <p className="text-sm text-slate-500">
                Select a patient to see their clinical summary, then "Use as
                template" to start editing.
              </p>
            </div>
          </div>
        )}
        {selected && (
          <div className="space-y-5">
            {/* Avatar + identity block */}
            <div className="flex items-start gap-4">
              <div
                className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-full text-center ${genderColors(displayGender)}`}
              >
                <span className="text-lg font-semibold leading-tight">
                  {displayAge ?? "?"}
                </span>
                <span className="text-xs">{displayGender ?? "?"}</span>
              </div>
              <div className="min-w-0 flex-1">
                {/* Ground-truth disease gets its own prominent line right
                    next to the age/gender avatar — it's the most clinically
                    important fact about this patient, not a footnote. */}
                {preview?.ground_truth?.target_condition?.name && (
                  <div className="flex items-baseline gap-2">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                      Target diagnosis
                    </span>
                  </div>
                )}
                {preview?.ground_truth?.target_condition?.name ? (
                  <div className="mt-0.5">
                    <span className="inline-flex items-center rounded-md border border-emerald-600/50 bg-emerald-600/15 px-3 py-1.5 text-base font-medium text-emerald-200">
                      {stripSnomedSuffix(preview.ground_truth.target_condition.name)}
                    </span>
                  </div>
                ) : (
                  <div className="truncate font-mono text-xs text-slate-500">
                    {selected.uuid}
                  </div>
                )}
                {/* Secondary demographics (BMI / race / location) + UUID
                    line below the headline. UUID is moved down when the
                    target diagnosis is present so the disease leads. */}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-400">
                  {preview?.demographics?.bmi != null && (
                    <span>BMI {preview.demographics.bmi}</span>
                  )}
                  {preview?.demographics?.race && (
                    <span>{preview.demographics.race}</span>
                  )}
                  {(() => {
                    const loc = preview?.demographics?.location as unknown;
                    if (!loc) return null;
                    if (typeof loc === "string") return <span>{loc}</span>;
                    if (typeof loc === "object") {
                      const o = loc as Record<string, unknown>;
                      const parts = [o.city, o.state].filter(
                        (x): x is string =>
                          typeof x === "string" && x.length > 0,
                      );
                      return parts.length ? (
                        <span>{parts.join(", ")}</span>
                      ) : null;
                    }
                    return null;
                  })()}
                </div>
                {preview?.ground_truth?.target_condition?.name && (
                  <div className="mt-1 truncate font-mono text-[10px] text-slate-600">
                    {selected.uuid}
                  </div>
                )}
              </div>
            </div>

            {previewLoading && (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 size={14} className="animate-spin" />
                Loading clinical data…
              </div>
            )}

            {preview && !previewLoading && (
              <>
                {/* Active conditions — full list, no slice cap. The preview
                    pane is scrollable so a patient with 29 conditions can
                    still show them all. Names have their SNOMED qualifier
                    suffix stripped for legibility. */}
                {(preview.conditions?.active ?? []).length > 0 && (
                  <div>
                    <div className="mb-2 flex items-baseline gap-2">
                      <span className="text-sm font-medium uppercase tracking-wide text-slate-300">
                        Active conditions
                      </span>
                      <span className="mono text-xs text-slate-500">
                        {(preview.conditions!.active ?? []).length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {(preview.conditions!.active ?? []).map((c, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center rounded-md border border-slate-700 bg-slate-900/60 px-2.5 py-1 text-sm text-slate-200"
                        >
                          {stripSnomedSuffix(c.condition)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recent labs — full list. Lab name + value/unit on a single
                    row with consistent typography. */}
                {(preview.labs?.latest_labs ?? []).length > 0 && (
                  <div>
                    <div className="mb-2 flex items-baseline gap-2">
                      <span className="text-sm font-medium uppercase tracking-wide text-slate-300">
                        Recent labs
                      </span>
                      <span className="mono text-xs text-slate-500">
                        {(preview.labs!.latest_labs ?? []).length}
                      </span>
                    </div>
                    <div className="divide-y divide-slate-800 rounded-md border border-slate-800">
                      {(preview.labs!.latest_labs ?? []).map((lab, i) => {
                        const labAny = lab as Record<string, unknown>;
                        const name =
                          (labAny.test_name as string) ||
                          (labAny.lab_name as string) ||
                          "—";
                        const value = labAny.value;
                        const unit =
                          (labAny.unit as string) ||
                          (labAny.units as string) ||
                          "";
                        return (
                          <div
                            key={i}
                            className="flex items-baseline justify-between gap-3 px-3 py-2 text-sm"
                          >
                            <span className="text-slate-200">{name}</span>
                            <span className="whitespace-nowrap font-mono tabular-nums text-slate-400">
                              {value != null ? String(value) : "—"}
                              {unit ? <span className="ml-1 text-slate-500">{unit}</span> : null}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* CTA */}
            <button
              onClick={useTemplate}
              disabled={!preview || previewLoading}
              className="w-full rounded-md bg-emerald-600 px-3 py-2.5 text-sm font-medium text-white
                         transition-colors hover:bg-emerald-500 focus-visible:outline-none
                         focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-40"
            >
              Use as template →
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

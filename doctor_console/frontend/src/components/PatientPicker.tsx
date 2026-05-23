import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { browseCohort, getCohortTemplate } from "../api";
import type { CohortBrowseRow, TestPatientPayload } from "../types";

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

interface Props {
  onTemplate: (payload: TestPatientPayload) => void;
}

/** Coloring convention: F → emerald, M → sky, Other → slate */
function genderColors(gender: string | null) {
  if (gender === "F") return "bg-emerald-600/20 text-emerald-100";
  if (gender === "M") return "bg-sky-600/20 text-sky-100";
  return "bg-slate-700/40 text-slate-300";
}

export function PatientPicker({ onTemplate }: Props) {
  const [disease, setDisease] = useState<string>("");
  const [ageRange, setAgeRange] = useState<[number, number]>([0, 120]);
  const [gender, setGender] = useState<string>("");
  const [rows, setRows] = useState<CohortBrowseRow[]>([]);
  const [selected, setSelected] = useState<CohortBrowseRow | null>(null);
  const [loading, setLoading] = useState(false);
  // Full payload fetched lazily when a row is selected
  const [preview, setPreview] = useState<TestPatientPayload | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    browseCohort({
      disease: disease || undefined,
      age_min: ageRange[0], age_max: ageRange[1],
      gender:  gender || undefined,
      limit:   50,
    }).then((r) => { setRows(r); setSelected(null); setPreview(null); })
      .finally(() => setLoading(false));
  }, [disease, ageRange[0], ageRange[1], gender]);

  // Fetch full template when selection changes
  useEffect(() => {
    if (!selected) { setPreview(null); return; }
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

  const displayGender = selected?.gender ?? null;
  const displayAge = selected?.age ?? null;

  return (
    <div className="flex h-full flex-col gap-4 p-4 lg:flex-row">
      {/* LEFT: facets */}
      <aside className="shrink-0 space-y-5 border-b border-slate-800 pb-3 text-sm lg:w-56 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-3">
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Disease</div>
          {DISEASES.map(d => (
            <label key={d} className="mb-1 flex items-center gap-2 cursor-pointer">
              <input type="radio" name="disease" checked={disease === d}
                onChange={() => setDisease(d === disease ? "" : d)}
                className="accent-emerald-500" />
              <span className="text-slate-300">{d}</span>
            </label>
          ))}
          {disease && (
            <button onClick={() => setDisease("")}
              className="mt-1 text-xs text-slate-500 underline hover:text-slate-300 transition-colors">clear</button>
          )}
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Age</div>
          <div className="flex items-center gap-2 text-slate-300">
            <input type="number" min={0} max={120} value={ageRange[0]}
              onChange={(e) => setAgeRange([Number(e.target.value), ageRange[1]])}
              className="w-16 rounded bg-slate-800 px-2 py-1 text-center focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500" />
            <span className="text-slate-500">–</span>
            <input type="number" min={0} max={120} value={ageRange[1]}
              onChange={(e) => setAgeRange([ageRange[0], Number(e.target.value)])}
              className="w-16 rounded bg-slate-800 px-2 py-1 text-center focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500" />
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Gender</div>
          <div className="flex gap-2">
            {["", "M", "F", "Other"].map((g) => (
              <button key={g || "any"}
                onClick={() => setGender(g === gender ? "" : g)}
                className={`rounded-md px-3 py-1 text-xs transition-colors
                           ${gender === g ? "bg-emerald-600 text-white"
                                          : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}>
                {g || "Any"}
              </button>
            ))}
          </div>
        </div>
      </aside>

      {/* MIDDLE: list */}
      <section className="shrink-0 overflow-y-auto border-b border-slate-800 pb-2 lg:w-80 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-2">
        <div className="mb-2 text-xs text-slate-400">
          {loading ? (
            <span className="inline-flex items-center gap-1.5">
              <Loader2 size={10} className="animate-spin" />Loading…
            </span>
          ) : `${rows.length} patient${rows.length === 1 ? "" : "s"}`}
        </div>
        <ul className="space-y-1">
          {rows.map(row => (
            <li key={row.uuid}>
              <button onClick={() => setSelected(row)}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm transition-colors
                           ${selected?.uuid === row.uuid
                              ? "bg-emerald-600/20 text-emerald-200 border border-emerald-600/30"
                              : "text-slate-300 hover:bg-slate-800 border border-transparent"}`}>
                <div className="font-mono text-xs text-slate-500">{row.uuid.slice(0,11)}</div>
                <div className="font-medium">{row.age ?? "?"}
                  <span className="ml-0.5">{row.gender ?? "?"}</span>
                  {row.disease && <span className="ml-2 text-xs text-slate-400">· {row.disease}</span>}
                </div>
                <div className="mt-0.5 text-xs text-slate-500">{row.active_count} active conditions</div>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* RIGHT: clinical preview pane */}
      <section className="flex-1 overflow-y-auto pr-2">
        {!selected && (
          <div className="flex h-full items-center justify-center text-center">
            <div className="max-w-xs">
              <p className="text-sm text-slate-500">
                Select a patient to see their clinical summary, then "Use as template" to start editing.
              </p>
            </div>
          </div>
        )}
        {selected && (
          <div className="space-y-5">
            {/* ── Avatar + identity block ── */}
            <div className="flex items-start gap-4">
              <div className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-full text-center ${genderColors(displayGender)}`}>
                <span className="text-lg font-semibold leading-tight">{displayAge ?? "?"}</span>
                <span className="text-xs">{displayGender ?? "?"}</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-mono text-xs text-slate-500 truncate">{selected.uuid}</div>
                {preview?.ground_truth?.target_condition?.name && (
                  <div className="mt-1">
                    <span className="inline-flex items-center rounded-full border border-emerald-600/40 bg-emerald-600/15 px-2.5 py-0.5 text-xs font-medium text-emerald-300">
                      {preview.ground_truth.target_condition.name}
                    </span>
                  </div>
                )}
                {preview?.demographics && (
                  <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-400">
                    {preview.demographics.bmi != null && (
                      <span>BMI {preview.demographics.bmi}</span>
                    )}
                    {preview.demographics.race && (
                      <span>{preview.demographics.race}</span>
                    )}
                    {/* Synthea stores location as {city, state, zip, county};
                        accept both that and a plain string. Render objects as
                        React children would crash the whole app. */}
                    {(() => {
                      const loc = preview.demographics.location as unknown;
                      if (!loc) return null;
                      if (typeof loc === "string") return <span>{loc}</span>;
                      if (typeof loc === "object") {
                        const o = loc as Record<string, unknown>;
                        const parts = [o.city, o.state].filter((x): x is string => typeof x === "string" && x.length > 0);
                        return parts.length ? <span>{parts.join(", ")}</span> : null;
                      }
                      return null;
                    })()}
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
                {/* ── Top conditions ── */}
                {(preview.conditions?.active ?? []).length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
                      Top conditions
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {(preview.conditions!.active ?? []).slice(0, 5).map((c, i) => (
                        <span key={i}
                          className="inline-flex items-center rounded-md border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-300">
                          {c.condition}
                        </span>
                      ))}
                      {(preview.conditions!.active ?? []).length > 5 && (
                        <span className="inline-flex items-center rounded-md border border-slate-700/50 px-2 py-0.5 text-xs text-slate-500">
                          +{(preview.conditions!.active ?? []).length - 5} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* ── Recent labs ──
                    The cohort's latest_labs entries use Synthea's field
                    names ({lab_name, value, units}); the editor's own
                    LabsForm uses the canonical ({test_name, value, unit}).
                    Read both so the preview works for cohort data AND
                    test patients the clinician built. */}
                {(preview.labs?.latest_labs ?? []).length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
                      Recent labs
                    </div>
                    <div className="space-y-1">
                      {(preview.labs!.latest_labs ?? []).slice(0, 5).map((lab, i) => {
                        const labAny = lab as Record<string, unknown>;
                        const name = (labAny.test_name as string) || (labAny.lab_name as string) || "—";
                        const value = labAny.value;
                        const unit = (labAny.unit as string) || (labAny.units as string) || "";
                        return (
                          <div key={i} className="flex items-baseline justify-between rounded-md border border-slate-800 bg-slate-900/60 px-3 py-1 text-xs">
                            <span className="text-slate-300">{name}</span>
                            <span className="ml-2 font-mono text-slate-400 tabular-nums whitespace-nowrap">
                              {value != null ? String(value) : "—"}{unit ? ` ${unit}` : ""}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── CTA ── */}
            <button onClick={useTemplate} disabled={!preview || previewLoading}
              className="w-full rounded-md bg-emerald-600 px-3 py-2.5 text-sm font-medium text-white
                         hover:bg-emerald-500 focus-visible:ring-2 focus-visible:ring-emerald-500
                         focus-visible:outline-none transition-colors disabled:opacity-40">
              Use as template →
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

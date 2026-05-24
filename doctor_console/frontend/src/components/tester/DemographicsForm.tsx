import type { TestPatientPayload } from "../../types";

interface Props {
  value: TestPatientPayload["demographics"];
  onChange: (next: TestPatientPayload["demographics"]) => void;
}

// Synthea's race categories. Held to the cohort's vocabulary so downstream
// agents recognise them.
const RACE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "white",    label: "White" },
  { value: "black",    label: "Black" },
  { value: "asian",    label: "Asian" },
  { value: "hispanic", label: "Hispanic" },
  { value: "native",   label: "Native" },
  { value: "other",    label: "Other" },
];

// Tone tokens map to existing CSS palette pills (--success / --warning /
// --critical / --accent / --violet / --spark). Bands kept loose so the
// editor never reads as a clinical judgement.
function ageBand(age?: number): { label: string; tone: string } | null {
  if (age == null || Number.isNaN(age) || age <= 0) return null;
  if (age < 2)   return { label: "Infant",      tone: "violet"  };
  if (age < 12)  return { label: "Child",       tone: "violet"  };
  if (age < 18)  return { label: "Adolescent",  tone: "spark"   };
  if (age < 40)  return { label: "Young adult", tone: "success" };
  if (age < 65)  return { label: "Adult",       tone: "success" };
  if (age < 80)  return { label: "Older adult", tone: "warning" };
  return            { label: "Elderly",      tone: "warning" };
}

function bmiBand(bmi?: number): { label: string; tone: string } | null {
  if (bmi == null || Number.isNaN(bmi) || bmi <= 0) return null;
  if (bmi < 18.5) return { label: "Underweight",   tone: "accent"   };
  if (bmi < 25)   return { label: "Healthy range", tone: "success"  };
  if (bmi < 30)   return { label: "Overweight",    tone: "warning"  };
  if (bmi < 35)   return { label: "Obesity I",     tone: "warning"  };
  if (bmi < 40)   return { label: "Obesity II",    tone: "critical" };
  return             { label: "Obesity III",   tone: "critical" };
}

export function DemographicsForm({ value, onChange }: Props) {
  function set<K extends keyof typeof value>(k: K, v: (typeof value)[K]) {
    onChange({ ...value, [k]: v });
  }
  const age = ageBand(value.age);
  const bmi = bmiBand(value.bmi);
  // BMI scale fill — clamped to 45 so realistic adult range fills meaningfully.
  const bmiPct = value.bmi
    ? Math.min(100, Math.max(0, ((value.bmi) / 45) * 100))
    : 0;

  return (
    <div className="demo-form">
      {/* Row 1 — Age + Sex.  Two equally-weighted blocks; the Age field
          uses a serif display numeral and a live life-stage pill so the
          field reads as a piece of evidence, not a raw input. */}
      <div className="demo-form__row">
        <div className="demo-form__field">
          <span className="demo-form__label">Age</span>
          <div className="demo-form__age">
            <input
              type="number" min={0} max={120}
              value={value.age || ""}
              onChange={(e) =>
                set("age", e.target.value === "" ? 0 : Number(e.target.value))
              }
              className="demo-form__age-input"
              placeholder="—"
              inputMode="numeric"
              aria-label="Age in years"
            />
            <span className="demo-form__age-unit">years</span>
            {age && (
              <span className={`demo-pill demo-pill--${age.tone}`}>
                {age.label}
              </span>
            )}
          </div>
        </div>

        <div className="demo-form__field">
          <span className="demo-form__label">Sex assigned at birth</span>
          <div className="demo-seg" role="radiogroup" aria-label="Sex">
            {(["M","F","Other"] as const).map((g) => {
              const active = value.gender === g;
              const long = g === "M" ? "Male" : g === "F" ? "Female" : "Other";
              return (
                <button
                  key={g}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => set("gender", g)}
                  className={`demo-seg__btn${active ? " is-active" : ""}`}
                >
                  <span className="demo-seg__mark">{g}</span>
                  <span className="demo-seg__long">{long}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Row 2 — Race as a chip group.  Native <select> read as
          spreadsheet UI; toggling pills keeps the editor in the
          tactile/picker family the rest of the screen uses. */}
      <div className="demo-form__field">
        <span className="demo-form__label">
          Race <span className="demo-form__optional">optional</span>
        </span>
        <div className="demo-chips">
          {RACE_OPTIONS.map((o) => {
            const active = value.race === o.value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => set("race", active ? undefined : o.value)}
                className={`demo-chip${active ? " is-active" : ""}`}
                aria-pressed={active}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Row 3 — BMI with computed category pill and tonal scale bar.
          The bar serves a single purpose: a fast at-a-glance "where
          on the scale does this patient sit" without forcing the
          user to remember the cut-offs. */}
      <div className="demo-form__field">
        <span className="demo-form__label">
          BMI <span className="demo-form__optional">optional</span>
        </span>
        <div className="demo-form__bmi">
          <div className="demo-form__bmi-row">
            <input
              type="number" step="0.1" min={0} max={80}
              value={value.bmi ?? ""}
              onChange={(e) =>
                set("bmi", e.target.value === "" ? undefined : Number(e.target.value))
              }
              className="demo-form__bmi-input"
              placeholder="—"
              inputMode="decimal"
              aria-label="Body mass index"
            />
            <span className="demo-form__bmi-unit">kg/m²</span>
            {bmi ? (
              <span className={`demo-pill demo-pill--${bmi.tone}`}>
                {bmi.label}
              </span>
            ) : (
              <span className="demo-form__bmi-hint">
                Healthy adult range 18.5 – 24.9
              </span>
            )}
          </div>
          <div className="demo-form__bmi-scale" aria-hidden="true">
            <div className="demo-form__bmi-scale-track">
              <span className="demo-form__bmi-mark" style={{ left: `${(18.5/45)*100}%` }} />
              <span className="demo-form__bmi-mark" style={{ left: `${(25/45)*100}%`   }} />
              <span className="demo-form__bmi-mark" style={{ left: `${(30/45)*100}%`   }} />
              <span className="demo-form__bmi-mark" style={{ left: `${(35/45)*100}%`   }} />
              <div
                className={`demo-form__bmi-scale-fill${bmi ? ` demo-form__bmi-scale-fill--${bmi.tone}` : ""}`}
                style={{ width: `${bmiPct}%` }}
              />
            </div>
            <div className="demo-form__bmi-scale-legend">
              <span>under</span><span>healthy</span><span>over</span><span>obese</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

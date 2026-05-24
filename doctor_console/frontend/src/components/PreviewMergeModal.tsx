import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  X,
  Check,
  AlertTriangle,
  RotateCcw,
  Trash2,
  Sparkles,
} from "lucide-react";
import type { ExtractResponse, SnapSuggestion, TestPatientPayload } from "../types";

interface Props {
  result:   ExtractResponse;
  current:  TestPatientPayload; // for diff display + base of merge
  onCancel: () => void;
  onMerge:  (merged: TestPatientPayload) => void;
}

/*
 * Editable state for the preview. Each extracted value is held with:
 *   - `val`      — the user-editable string (numbers held as strings for
 *                  uncontrolled-input parity, parsed at merge time)
 *   - `checked`  — whether to include in the merge
 *   - `present`  — was this field detected in the extraction at all?
 *   - `original` — the raw extracted text, so we can show a revert button
 *                  when the user has manually edited it
 *
 * Snap suggestions ("Hgb" → "Hemoglobin") are kept alongside each row and
 * applied by writing the suggested label into the editable `val`. After
 * the user accepts a snap, the row's `val` differs from `original`, so the
 * revert button takes the place of the snap chip — one affordance at a
 * time, no contradicting buttons.
 */
type DemoSpec = {
  val:      string;
  checked:  boolean;
  present:  boolean;
  original: string;
};
type EditDemo = {
  age:    DemoSpec;
  gender: DemoSpec;
  bmi:    DemoSpec;
  race:   DemoSpec;
};
type EditCond = {
  name:     string;
  code?:    string;
  checked:  boolean;
  original: string;
  snap?:    SnapSuggestion;
};
type EditMed = {
  name:     string;
  code?:    string;
  checked:  boolean;
  original: string;
  snap?:    SnapSuggestion;
};
type EditLab = {
  name:     string;
  value:    string;
  unit:     string;
  checked:  boolean;
  original: string;
  snap?:    SnapSuggestion;
};

export function PreviewMergeModal({ result, current, onCancel, onMerge }: Props) {
  const ex = result.extracted as TestPatientPayload | undefined;
  const demoEx  = (ex?.demographics ?? {}) as Record<string, unknown>;
  const condsEx = ex?.conditions?.active ?? [];
  const medsEx  = ex?.medications?.active ?? [];
  const labsEx  = ex?.labs?.latest_labs ?? [];

  const condSnap = useMemo(
    () => Object.fromEntries(result.snap_suggestions.conditions.map((s) => [s.from.toLowerCase(), s])),
    [result],
  );
  const medSnap = useMemo(
    () => Object.fromEntries(result.snap_suggestions.medications.map((s) => [s.from.toLowerCase(), s])),
    [result],
  );
  const labSnap = useMemo(
    () => Object.fromEntries(result.snap_suggestions.labs.map((s) => [s.from.toLowerCase(), s])),
    [result],
  );

  const [demo, setDemo] = useState<EditDemo>(() => {
    const age    = demoEx.age    != null ? String(demoEx.age)    : "";
    const gender = demoEx.gender != null ? String(demoEx.gender) : "";
    const bmi    = demoEx.bmi    != null ? String(demoEx.bmi)    : "";
    const race   = demoEx.race   != null ? String(demoEx.race)   : "";
    return {
      age:    { val: age,    checked: age    !== "", present: age    !== "", original: age    },
      gender: { val: gender, checked: gender !== "", present: gender !== "", original: gender },
      bmi:    { val: bmi,    checked: bmi    !== "", present: bmi    !== "", original: bmi    },
      race:   { val: race,   checked: race   !== "", present: race   !== "", original: race   },
    };
  });

  const [conds, setConds] = useState<EditCond[]>(() =>
    condsEx.map((c) => ({
      name: c.condition || "",
      code: c.code,
      checked: true,
      original: c.condition || "",
      snap: condSnap[(c.condition ?? "").toLowerCase()],
    })),
  );
  const [meds, setMeds] = useState<EditMed[]>(() =>
    medsEx.map((m) => ({
      name: m.medication || "",
      code: m.rx_code,
      checked: true,
      original: m.medication || "",
      snap: medSnap[(m.medication ?? "").toLowerCase()],
    })),
  );
  const [labs, setLabs] = useState<EditLab[]>(() =>
    labsEx.map((l) => ({
      name: l.test_name || "",
      value: l.value ?? "",
      unit: l.unit ?? "",
      checked: true,
      original: l.test_name || "",
      snap: labSnap[(l.test_name ?? "").toLowerCase()],
    })),
  );

  // Live counts — drives the footer chip + the merge-button label so the
  // user always sees what's about to land in the editor.
  const counts = useMemo(() => {
    let d = 0;
    if (demo.age.checked    && demo.age.val    !== "") d++;
    if (demo.gender.checked && demo.gender.val !== "") d++;
    if (demo.bmi.checked    && demo.bmi.val    !== "") d++;
    if (demo.race.checked   && demo.race.val   !== "") d++;
    return {
      demo: d,
      cond: conds.filter((c) => c.checked && c.name.trim() !== "").length,
      med:  meds.filter((m) => m.checked && m.name.trim() !== "").length,
      lab:  labs.filter((l) => l.checked && l.name.trim() !== "").length,
    };
  }, [demo, conds, meds, labs]);
  const total = counts.demo + counts.cond + counts.med + counts.lab;

  function setAll(v: boolean) {
    setDemo((d) => ({
      age:    { ...d.age,    checked: v && d.age.present },
      gender: { ...d.gender, checked: v && d.gender.present },
      bmi:    { ...d.bmi,    checked: v && d.bmi.present },
      race:   { ...d.race,   checked: v && d.race.present },
    }));
    setConds((xs) => xs.map((x) => ({ ...x, checked: v })));
    setMeds((xs)  => xs.map((x) => ({ ...x, checked: v })));
    setLabs((xs)  => xs.map((x) => ({ ...x, checked: v })));
  }

  function merge() {
    const next: TestPatientPayload = {
      ...current,
      label: current.label || ex?.label || "Smart-imported patient",
      demographics: { ...current.demographics },
      conditions:   { active: [...(current.conditions?.active  ?? [])] },
      medications:  { active: [...(current.medications?.active ?? [])] },
      labs:         { latest_labs: [...(current.labs?.latest_labs ?? [])] },
    };

    if (demo.age.checked    && demo.age.val    !== "") next.demographics.age    = Number(demo.age.val);
    if (demo.gender.checked && demo.gender.val !== "") next.demographics.gender = demo.gender.val;
    if (demo.bmi.checked    && demo.bmi.val    !== "") next.demographics.bmi    = Number(demo.bmi.val);
    if (demo.race.checked   && demo.race.val   !== "") next.demographics.race   = demo.race.val;

    conds.forEach((c) => {
      if (!c.checked || !c.name.trim()) return;
      next.conditions!.active!.push({ condition: c.name.trim(), code: c.code });
    });
    meds.forEach((m) => {
      if (!m.checked || !m.name.trim()) return;
      next.medications!.active!.push({ medication: m.name.trim(), rx_code: m.code });
    });
    labs.forEach((l) => {
      if (!l.checked || !l.name.trim()) return;
      next.labs!.latest_labs!.push({
        test_name: l.name.trim(),
        value: l.value,
        unit:  l.unit,
      });
    });
    onMerge(next);
  }

  // Diff-friendly "was" values from the current editor payload — only
  // shown when the user already had a value and the extracted value is
  // different (i.e. the merge would actually overwrite something).
  const wasAge    = current.demographics?.age    != null ? String(current.demographics.age)    : "";
  const wasGender = current.demographics?.gender ?? "";
  const wasBmi    = current.demographics?.bmi    != null ? String(current.demographics.bmi)    : "";
  const wasRace   = current.demographics?.race   ?? "";

  return (
    <motion.div
      className="merge-modal__backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.15 }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <motion.div
        className="merge-modal"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
      >
        <header className="merge-modal__header">
          <div className="merge-modal__heading">
            <div className="merge-modal__eyebrow">
              <Sparkles size={11} strokeWidth={1.8} />
              Smart import · review
            </div>
            <h2 className="merge-modal__title">Edit, then merge</h2>
            <p className="merge-modal__sub">
              Every field is editable. Uncheck a row to skip it. Snap shortcuts replace
              free-text labels with the cohort canonical name.
            </p>
          </div>
          <button onClick={onCancel} className="merge-modal__close" aria-label="Close review">
            <X size={16} strokeWidth={1.6} />
          </button>
        </header>

        <div className="merge-modal__body">
          {result.warnings.length > 0 && (
            <div className="merge-modal__warn">
              <AlertTriangle size={14} strokeWidth={1.8} />
              <span>{result.warnings.join(" · ")}</span>
            </div>
          )}

          {/* ── Demographics ─────────────────────────────────────────────── */}
          <PreviewSection title="Demographics" count={counts.demo} total={4}>
            <div className="merge-list">
              <DemoRow label="Age"    spec={demo.age}    type="number"
                       was={wasAge}
                       onChange={(p) => setDemo((d) => ({ ...d, age:    { ...d.age,    ...p } }))} />
              <DemoRow label="Gender" spec={demo.gender} type="text"
                       was={wasGender}
                       onChange={(p) => setDemo((d) => ({ ...d, gender: { ...d.gender, ...p } }))} />
              <DemoRow label="BMI"    spec={demo.bmi}    type="number" step="0.1"
                       was={wasBmi}
                       onChange={(p) => setDemo((d) => ({ ...d, bmi:    { ...d.bmi,    ...p } }))} />
              <DemoRow label="Race"   spec={demo.race}   type="text"
                       was={wasRace}
                       onChange={(p) => setDemo((d) => ({ ...d, race:   { ...d.race,   ...p } }))} />
            </div>
          </PreviewSection>

          {/* ── Conditions ───────────────────────────────────────────────── */}
          {conds.length > 0 && (
            <PreviewSection title="Conditions" count={counts.cond} total={conds.length}>
              <ul className="merge-list">
                {conds.map((c, i) => (
                  <li key={i}
                      className={`merge-row${!c.checked ? " merge-row--off" : ""}`}>
                    <input type="checkbox" className="merge-row__check"
                           checked={c.checked}
                           onChange={(e) => setConds((xs) => xs.map((x, j) => j === i ? { ...x, checked: e.target.checked } : x))} />
                    <input type="text" className="merge-row__input"
                           value={c.name} disabled={!c.checked}
                           onChange={(e) => setConds((xs) => xs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
                    {c.code && <span className="merge-row__code mono">{c.code}</span>}
                    <RowAffordances
                      hasSnap={!!c.snap && c.name === c.original}
                      isEdited={c.name !== c.original}
                      snap={c.snap}
                      onSnap={()    => setConds((xs) => xs.map((x, j) => j === i ? { ...x, name: c.snap!.to } : x))}
                      onRevert={() => setConds((xs) => xs.map((x, j) => j === i ? { ...x, name: x.original } : x))}
                      onRemove={() => setConds((xs) => xs.filter((_, j) => j !== i))}
                    />
                  </li>
                ))}
              </ul>
            </PreviewSection>
          )}

          {/* ── Medications ──────────────────────────────────────────────── */}
          {meds.length > 0 && (
            <PreviewSection title="Medications" count={counts.med} total={meds.length}>
              <ul className="merge-list">
                {meds.map((m, i) => (
                  <li key={i}
                      className={`merge-row${!m.checked ? " merge-row--off" : ""}`}>
                    <input type="checkbox" className="merge-row__check"
                           checked={m.checked}
                           onChange={(e) => setMeds((xs) => xs.map((x, j) => j === i ? { ...x, checked: e.target.checked } : x))} />
                    <input type="text" className="merge-row__input"
                           value={m.name} disabled={!m.checked}
                           onChange={(e) => setMeds((xs) => xs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
                    {m.code && <span className="merge-row__code mono">rx {m.code}</span>}
                    <RowAffordances
                      hasSnap={!!m.snap && m.name === m.original}
                      isEdited={m.name !== m.original}
                      snap={m.snap}
                      onSnap={()    => setMeds((xs) => xs.map((x, j) => j === i ? { ...x, name: m.snap!.to } : x))}
                      onRevert={() => setMeds((xs) => xs.map((x, j) => j === i ? { ...x, name: x.original } : x))}
                      onRemove={() => setMeds((xs) => xs.filter((_, j) => j !== i))}
                    />
                  </li>
                ))}
              </ul>
            </PreviewSection>
          )}

          {/* ── Labs (the star of this modal) ────────────────────────────── */}
          {labs.length > 0 && (
            <PreviewSection title="Recent labs" count={counts.lab} total={labs.length}>
              <ul className="merge-list merge-list--labs">
                {labs.map((l, i) => (
                  <li key={i}
                      className={`merge-lab-row${!l.checked ? " merge-lab-row--off" : ""}`}>
                    <input type="checkbox" className="merge-row__check"
                           checked={l.checked}
                           onChange={(e) => setLabs((xs) => xs.map((x, j) => j === i ? { ...x, checked: e.target.checked } : x))} />
                    <input type="text" className="merge-row__input merge-lab-row__name"
                           value={l.name} disabled={!l.checked}
                           aria-label={`Lab ${i + 1} name`}
                           onChange={(e) => setLabs((xs) => xs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
                    <input type="text" inputMode="decimal"
                           className="merge-row__input merge-lab-row__value mono"
                           value={l.value} disabled={!l.checked}
                           placeholder="—"
                           aria-label={`Lab ${i + 1} value`}
                           onChange={(e) => setLabs((xs) => xs.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
                    <input type="text"
                           className="merge-row__input merge-lab-row__unit mono"
                           value={l.unit} disabled={!l.checked}
                           placeholder="unit"
                           aria-label={`Lab ${i + 1} unit`}
                           onChange={(e) => setLabs((xs) => xs.map((x, j) => j === i ? { ...x, unit: e.target.value } : x))} />
                    <RowAffordances
                      hasSnap={!!l.snap && l.name === l.original}
                      isEdited={l.name !== l.original}
                      snap={l.snap}
                      onSnap={()    => setLabs((xs) => xs.map((x, j) => j === i ? { ...x, name: l.snap!.to } : x))}
                      onRevert={() => setLabs((xs) => xs.map((x, j) => j === i ? { ...x, name: x.original } : x))}
                      onRemove={() => setLabs((xs) => xs.filter((_, j) => j !== i))}
                    />
                  </li>
                ))}
              </ul>
            </PreviewSection>
          )}
        </div>

        <footer className="merge-modal__footer">
          <div className="merge-modal__bulk">
            <button onClick={() => setAll(true)}  className="merge-modal__bulk-btn">Accept all</button>
            <button onClick={() => setAll(false)} className="merge-modal__bulk-btn">Reject all</button>
          </div>
          <div className="merge-modal__primary">
            <span className="merge-modal__counter">
              <strong>{total}</strong>{" "}
              {total === 1 ? "field will merge" : "fields will merge"}
            </span>
            <button onClick={onCancel} className="merge-modal__cancel">Cancel</button>
            <button onClick={merge} disabled={total === 0} className="merge-modal__merge">
              <Check size={14} strokeWidth={2} />
              Merge {total > 0 ? `${total} ` : ""}field{total === 1 ? "" : "s"} →
            </button>
          </div>
        </footer>
      </motion.div>
    </motion.div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────── */

function PreviewSection({
  title, count, total, children,
}: {
  title: string;
  count: number;
  total: number;
  children: React.ReactNode;
}) {
  return (
    <section className="merge-section">
      <header className="merge-section__head">
        <h3 className="merge-section__title">{title}</h3>
        <span className="merge-section__count mono">
          {count}<span className="merge-section__count-sep"> / </span>{total}
        </span>
      </header>
      {children}
    </section>
  );
}

function DemoRow({ label, spec, type, step, was, onChange }: {
  label: string;
  spec: DemoSpec;
  type: "text" | "number";
  step?: string;
  was?: string;
  onChange: (patch: Partial<DemoSpec>) => void;
}) {
  const willOverwrite = !!was && was !== spec.val && spec.checked && spec.val !== "";
  return (
    <div className={`merge-row${!spec.present ? " merge-row--absent" : ""}${!spec.checked && spec.present ? " merge-row--off" : ""}`}>
      <input type="checkbox" className="merge-row__check"
             disabled={!spec.present}
             checked={spec.checked && spec.present}
             onChange={(e) => onChange({ checked: e.target.checked })} />
      <span className="merge-row__demo-label">{label}</span>
      {spec.present ? (
        <input
          type={type}
          step={step}
          value={spec.val}
          disabled={!spec.checked}
          className={`merge-row__input merge-row__input--demo${willOverwrite ? " is-overwrite" : ""}`}
          onChange={(e) => onChange({ val: e.target.value })}
        />
      ) : (
        <span className="merge-row__absent-text">not detected</span>
      )}
      {was && (
        <span className={`merge-row__was${willOverwrite ? " is-overwrite" : ""}`}>
          was <span className="mono">{was}</span>
        </span>
      )}
      {spec.present && spec.val !== spec.original && (
        <button type="button" className="merge-row__revert"
                title={`Revert to extracted (${spec.original})`}
                onClick={() => onChange({ val: spec.original })}>
          <RotateCcw size={11} strokeWidth={1.8} />
        </button>
      )}
    </div>
  );
}

function RowAffordances({
  hasSnap, isEdited, snap, onSnap, onRevert, onRemove,
}: {
  hasSnap:  boolean;
  isEdited: boolean;
  snap?:    SnapSuggestion;
  onSnap:   () => void;
  onRevert: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="merge-row__actions">
      {hasSnap && snap && (
        <button type="button" className="merge-row__snap"
                onClick={onSnap}
                title={`Cohort canonical: ${snap.to} (${Math.round(snap.score * 100)}% confidence)`}>
          snap → <span className="mono">{snap.to}</span>
        </button>
      )}
      {isEdited && (
        <button type="button" className="merge-row__revert"
                onClick={onRevert}
                title="Revert to extracted text">
          <RotateCcw size={11} strokeWidth={1.8} />
        </button>
      )}
      <button type="button" className="merge-row__remove"
              onClick={onRemove}
              aria-label="Reject row">
        <Trash2 size={12} strokeWidth={1.7} />
      </button>
    </div>
  );
}

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { X, Check, AlertTriangle } from "lucide-react";
import type { ExtractResponse, SnapSuggestion, TestPatientPayload } from "../types";

interface Props {
  result:   ExtractResponse;
  current:  TestPatientPayload; // current editor payload (for conflict display)
  onCancel: () => void;
  onMerge:  (merged: TestPatientPayload) => void;
}

type Toggles = {
  demographics: { age?: boolean; gender?: boolean; race?: boolean; bmi?: boolean };
  conditions:   boolean[];
  medications:  boolean[];
  labs:         boolean[];
};

type Snaps = {
  conditions:  Record<number, boolean>; // if true, replace 'from' with 'to'
  medications: Record<number, boolean>;
  labs:        Record<number, boolean>;
};

export function PreviewMergeModal({ result, current, onCancel, onMerge }: Props) {
  const ex = result.extracted as TestPatientPayload | undefined;

  const demoEx   = (ex?.demographics ?? {}) as Record<string, unknown>;
  const condsEx  = ex?.conditions?.active ?? [];
  const medsEx   = ex?.medications?.active ?? [];
  const labsEx   = ex?.labs?.latest_labs ?? [];

  const [toggles, setToggles] = useState<Toggles>(() => ({
    demographics: {
      age:    demoEx.age != null,
      gender: !!demoEx.gender,
      race:   !!demoEx.race,
      bmi:    demoEx.bmi != null,
    },
    conditions:  condsEx.map(() => true),
    medications: medsEx.map(() => true),
    labs:        labsEx.map(() => true),
  }));

  const [snaps, setSnaps] = useState<Snaps>({
    conditions:  {},
    medications: {},
    labs:        {},
  });

  const condSnap = useMemo(
    () =>
      Object.fromEntries(
        result.snap_suggestions.conditions.map((s) => [s.from.toLowerCase(), s])
      ),
    [result]
  );
  const medSnap = useMemo(
    () =>
      Object.fromEntries(
        result.snap_suggestions.medications.map((s) => [s.from.toLowerCase(), s])
      ),
    [result]
  );
  const labSnap = useMemo(
    () =>
      Object.fromEntries(
        result.snap_suggestions.labs.map((s) => [s.from.toLowerCase(), s])
      ),
    [result]
  );

  function setAll(v: boolean) {
    setToggles({
      demographics: { age: v, gender: v, race: v, bmi: v },
      conditions:   condsEx.map(() => v),
      medications:  medsEx.map(() => v),
      labs:         labsEx.map(() => v),
    });
  }

  function merge() {
    const next: TestPatientPayload = {
      ...current,
      label:       current.label || ex?.label || "Smart-imported patient",
      demographics: { ...current.demographics },
      conditions:  { active: [...(current.conditions?.active  ?? [])] },
      medications: { active: [...(current.medications?.active ?? [])] },
      labs:        { latest_labs: [...(current.labs?.latest_labs ?? [])] },
    };

    if (toggles.demographics.age    && demoEx.age    != null) next.demographics.age    = Number(demoEx.age);
    if (toggles.demographics.gender && demoEx.gender)         next.demographics.gender = String(demoEx.gender);
    if (toggles.demographics.race   && demoEx.race)           next.demographics.race   = String(demoEx.race);
    if (toggles.demographics.bmi    && demoEx.bmi   != null)  next.demographics.bmi    = Number(demoEx.bmi);

    condsEx.forEach((c, i) => {
      if (!toggles.conditions[i]) return;
      const snapHit = condSnap[(c.condition ?? "").toLowerCase()];
      const final   = snapHit && snaps.conditions[i] ? snapHit.to : c.condition;
      next.conditions!.active!.push({ condition: final, code: c.code });
    });

    medsEx.forEach((m, i) => {
      if (!toggles.medications[i]) return;
      const snapHit = medSnap[(m.medication ?? "").toLowerCase()];
      const final   = snapHit && snaps.medications[i] ? snapHit.to : m.medication;
      next.medications!.active!.push({ medication: final, rx_code: m.rx_code });
    });

    labsEx.forEach((l, i) => {
      if (!toggles.labs[i]) return;
      const snapHit = labSnap[(l.test_name ?? "").toLowerCase()];
      const final   = snapHit && snaps.labs[i] ? snapHit.to : l.test_name;
      next.labs!.latest_labs!.push({
        test_name: final,
        value:     l.value,
        unit:      l.unit,
      });
    });

    onMerge(next);
  }

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15 }}
    >
      <motion.div
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border border-slate-800 bg-slate-900 shadow-2xl"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <h2 className="text-lg font-medium text-slate-100">
            Review extracted fields
          </h2>
          <button
            onClick={onCancel}
            className="text-slate-400 hover:text-slate-100 transition-colors"
          >
            <X size={18} />
          </button>
        </header>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {result.warnings.length > 0 && (
            <div className="rounded-md border border-amber-700/40 bg-amber-900/20 px-3 py-2 text-sm text-amber-300">
              <AlertTriangle size={14} className="mr-1 inline" />
              {result.warnings.join(" · ")}
            </div>
          )}

          {/* Demographics */}
          <Section title="Demographics">
            <Row
              checked={toggles.demographics.age ?? false}
              onChange={(v) =>
                setToggles((t) => ({
                  ...t,
                  demographics: { ...t.demographics, age: v },
                }))
              }
              disabled={demoEx.age == null}
              label="Age"
              value={demoEx.age != null ? String(demoEx.age) : "(not detected)"}
              was={
                current.demographics?.age != null
                  ? `was: ${current.demographics.age}`
                  : undefined
              }
            />
            <Row
              checked={toggles.demographics.gender ?? false}
              onChange={(v) =>
                setToggles((t) => ({
                  ...t,
                  demographics: { ...t.demographics, gender: v },
                }))
              }
              disabled={!demoEx.gender}
              label="Gender"
              value={String(demoEx.gender ?? "(not detected)")}
              was={
                current.demographics?.gender
                  ? `was: ${current.demographics.gender}`
                  : undefined
              }
            />
            <Row
              checked={toggles.demographics.bmi ?? false}
              onChange={(v) =>
                setToggles((t) => ({
                  ...t,
                  demographics: { ...t.demographics, bmi: v },
                }))
              }
              disabled={demoEx.bmi == null}
              label="BMI"
              value={demoEx.bmi != null ? String(demoEx.bmi) : "(not detected)"}
            />
          </Section>

          {condsEx.length > 0 && (
            <Section title={`Active conditions (${condsEx.length})`}>
              {condsEx.map((c, i) => {
                const snapHit = condSnap[(c.condition ?? "").toLowerCase()];
                return (
                  <Row
                    key={i}
                    checked={toggles.conditions[i] ?? false}
                    onChange={(v) =>
                      setToggles((t) => {
                        const arr = [...t.conditions];
                        arr[i] = v;
                        return { ...t, conditions: arr };
                      })
                    }
                    label={c.condition || "(unknown)"}
                    value={c.code ? `code ${c.code}` : ""}
                    snap={
                      snapHit
                        ? {
                            suggestion: snapHit,
                            applied:    !!snaps.conditions[i],
                            onToggle:   () =>
                              setSnaps((s) => ({
                                ...s,
                                conditions: {
                                  ...s.conditions,
                                  [i]: !s.conditions[i],
                                },
                              })),
                          }
                        : undefined
                    }
                  />
                );
              })}
            </Section>
          )}

          {medsEx.length > 0 && (
            <Section title={`Active medications (${medsEx.length})`}>
              {medsEx.map((m, i) => {
                const snapHit = medSnap[(m.medication ?? "").toLowerCase()];
                return (
                  <Row
                    key={i}
                    checked={toggles.medications[i] ?? false}
                    onChange={(v) =>
                      setToggles((t) => {
                        const arr = [...t.medications];
                        arr[i] = v;
                        return { ...t, medications: arr };
                      })
                    }
                    label={m.medication || "(unknown)"}
                    value={m.rx_code ? `rx ${m.rx_code}` : ""}
                    snap={
                      snapHit
                        ? {
                            suggestion: snapHit,
                            applied:    !!snaps.medications[i],
                            onToggle:   () =>
                              setSnaps((s) => ({
                                ...s,
                                medications: {
                                  ...s.medications,
                                  [i]: !s.medications[i],
                                },
                              })),
                          }
                        : undefined
                    }
                  />
                );
              })}
            </Section>
          )}

          {labsEx.length > 0 && (
            <Section title={`Recent labs (${labsEx.length})`}>
              {labsEx.map((l, i) => {
                const snapHit = labSnap[(l.test_name ?? "").toLowerCase()];
                return (
                  <Row
                    key={i}
                    checked={toggles.labs[i] ?? false}
                    onChange={(v) =>
                      setToggles((t) => {
                        const arr = [...t.labs];
                        arr[i] = v;
                        return { ...t, labs: arr };
                      })
                    }
                    label={l.test_name || "(unknown)"}
                    value={`${l.value ?? "—"}${l.unit ? " " + l.unit : ""}`}
                    snap={
                      snapHit
                        ? {
                            suggestion: snapHit,
                            applied:    !!snaps.labs[i],
                            onToggle:   () =>
                              setSnaps((s) => ({
                                ...s,
                                labs: { ...s.labs, [i]: !s.labs[i] },
                              })),
                          }
                        : undefined
                    }
                  />
                );
              })}
            </Section>
          )}
        </div>

        {/* Footer */}
        <footer className="flex items-center justify-between border-t border-slate-800 px-5 py-3">
          <div className="flex gap-2">
            <button
              onClick={() => setAll(false)}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 transition-colors"
            >
              Reject all
            </button>
            <button
              onClick={() => setAll(true)}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 transition-colors"
            >
              Accept all
            </button>
          </div>
          <div className="flex gap-3">
            <button
              onClick={onCancel}
              className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={merge}
              className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 transition-colors"
            >
              <Check size={14} />
              Merge →
            </button>
          </div>
        </footer>
      </motion.div>
    </motion.div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

interface RowProps {
  checked:   boolean;
  onChange:  (v: boolean) => void;
  disabled?: boolean;
  label:     string;
  value:     string;
  was?:      string;
  snap?:     {
    suggestion: SnapSuggestion;
    applied:    boolean;
    onToggle:   () => void;
  };
}

function Row({ checked, onChange, disabled, label, value, was, snap }: RowProps) {
  return (
    <label
      className={`flex items-start gap-2 rounded-md px-2 py-1.5 text-sm${
        disabled ? " opacity-50" : " hover:bg-slate-800/60 cursor-pointer"
      }`}
    >
      <input
        type="checkbox"
        disabled={disabled}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 accent-emerald-500"
      />
      <div className="flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-slate-100">{label}</span>
          {value && (
            <span className="font-mono text-xs text-slate-400">{value}</span>
          )}
          {was && (
            <span className="ml-auto text-xs text-slate-500 italic">{was}</span>
          )}
        </div>
        {snap && (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              snap.onToggle();
            }}
            className={`mt-1 inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors${
              snap.applied
                ? " bg-emerald-600/20 text-emerald-300 border border-emerald-600/40"
                : " border border-slate-700 text-slate-400 hover:border-emerald-600/30 hover:text-slate-200"
            }`}
          >
            {snap.applied ? "✓ snapped to: " : "snap to: "}
            <span className="font-mono">{snap.suggestion.to}</span>
            <span className="text-slate-600">
              ({Math.round(snap.suggestion.score * 100)}%)
            </span>
          </button>
        )}
      </div>
    </label>
  );
}

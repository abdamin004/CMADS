import { useCallback, useEffect, useState } from "react";
import { Check, MessageSquare, X } from "lucide-react";
import { deleteAnnotation, getAnnotation, saveAnnotation } from "../api";
import type { Annotation } from "../types";

type Props = {
  patientUuid?: string;
  onChange?: (annotation: Annotation) => void;
};

type Agreement = "agree" | "disagree" | "uncertain";

export function AnnotationPanel({ patientUuid, onChange }: Props) {
  const [agreement, setAgreement] = useState<Agreement>("uncertain");
  const [notes, setNotes] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [loaded, setLoaded] = useState<Annotation | undefined>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  // Hydrate when the patient changes.
  useEffect(() => {
    if (!patientUuid) return;
    let cancelled = false;
    setError(null);
    void getAnnotation(patientUuid)
      .then((a) => {
        if (cancelled) return;
        setLoaded(a);
        setAgreement(((a.agreement as Agreement | undefined) ?? "uncertain"));
        setNotes(a.notes ?? "");
        setReviewer(a.reviewer ?? "");
      })
      .catch((err) => !cancelled && setError(String(err)));
    return () => { cancelled = true; };
  }, [patientUuid]);

  const handleSave = useCallback(async () => {
    if (!patientUuid) return;
    setSaving(true); setError(null);
    try {
      const next = await saveAnnotation(patientUuid, { agreement, notes, reviewer });
      setLoaded(next);
      onChange?.(next);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 1400);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }, [agreement, notes, onChange, patientUuid, reviewer]);

  const handleClear = useCallback(async () => {
    if (!patientUuid) return;
    setSaving(true); setError(null);
    try {
      const next = await deleteAnnotation(patientUuid);
      setLoaded(next);
      setAgreement("uncertain"); setNotes(""); setReviewer("");
      onChange?.(next);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }, [onChange, patientUuid]);

  if (!patientUuid) return null;
  const hasExisting = loaded?.exists;

  return (
    <section className="panel annotation-panel">
      <div className="panel-heading">
        <div>
          <h2>Reviewer note</h2>
          <p>
            Record whether you agree with the agents' final diagnosis, and any context the next reviewer should know.
            {loaded?.updatedAt ? <> Last updated <span className="mono">{loaded.updatedAt}</span>.</> : null}
          </p>
        </div>
        {hasExisting ? (
          <span className={`agreement-pill agreement-${agreement}`}>
            {agreement === "agree" ? "Agree" : agreement === "disagree" ? "Disagree" : "Uncertain"}
          </span>
        ) : null}
      </div>

      <div className="annotation-grid">
        <fieldset className="annotation-radios">
          <legend>Verdict</legend>
          {(["agree", "uncertain", "disagree"] as Agreement[]).map((opt) => (
            <label key={opt} className={`agreement-option ${agreement === opt ? "is-active" : ""}`}>
              <input
                type="radio"
                name="agreement"
                value={opt}
                checked={agreement === opt}
                onChange={() => setAgreement(opt)}
              />
              <span>{opt === "agree" ? "I agree" : opt === "disagree" ? "I disagree" : "I'm uncertain"}</span>
            </label>
          ))}
        </fieldset>

        <label className="annotation-field">
          <span>Notes</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Reasoning, missed evidence, follow-up needed…"
          />
        </label>

        <label className="annotation-field annotation-reviewer">
          <span>Reviewer initials</span>
          <input
            type="text"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            maxLength={16}
            placeholder="AM"
          />
        </label>
      </div>

      <div className="annotation-actions">
        <button className="run-button" type="button" onClick={handleSave} disabled={saving}>
          <Check size={14} /> {hasExisting ? "Update note" : "Save note"}
        </button>
        {hasExisting ? (
          <button className="ghost-button" type="button" onClick={handleClear} disabled={saving}>
            <X size={14} /> Clear
          </button>
        ) : null}
        {savedFlash ? (
          <span className="annotation-saved-flash"><MessageSquare size={14} /> Saved</span>
        ) : null}
        {error ? <span className="annotation-error">{error}</span> : null}
      </div>
    </section>
  );
}

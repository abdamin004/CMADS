import { useEffect, useMemo, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Eye, FlaskConical, Pencil, Play, Search, Trash2 } from "lucide-react";
import { deleteTestPatient, listTestPatients } from "../api";
import { handoffToRuntimeRun } from "../lib/runtimeHandoff";
import { parseBackendDate, relativeBackend } from "../lib/datetime";
import { TestRunConfigModal } from "./TestRunConfigModal";
import type { TestPatientSummary } from "../types";

/* ────────────────────────────────────────────────────────────────────────
   "My test patients" — past custom-patient runs view.
   This is a runtime list, not an evaluation list: no target_condition,
   no DIRECT/INDIRECT/MISS scoring. A row is either a draft (never run)
   or has at least one completed run; we surface the actual outcome of
   the most recent run (top diagnosis + confidence) and how long it took.
   ──────────────────────────────────────────────────────────────────── */

interface Props {
  onEdit:  (testUuid: string) => void;
  /** Kept for backwards-compat; the run hand-off is now self-contained
   *  (we flip the URL to ?mode=runtime so RuntimeMode picks the task up
   *  on its mount), but the parent can still react to the kick-off — e.g.
   *  reload its patient list before unmounting. */
  onRun:   (taskId: string) => void;
  /** Open the most recent completed run for this test patient. The parent
   *  decides where it renders (Researcher inline keeps the user on the
   *  past-runs page; previous behaviour was a flip to the Doctor runtime
   *  workspace, which lost the back link). */
  onView:  (testUuid: string) => void;
  onNew:   () => void;
}

type Status    = "draft" | "ran";
type FilterKey = Status | "ALL";

const STATUS_META: Record<Status, { label: string; glyph: string; tone: "muted" | "success" }> = {
  draft: { label: "Draft",  glyph: "○", tone: "muted"   },
  ran:   { label: "Ran",    glyph: "▶", tone: "success" },
};

function deriveStatus(r: TestPatientSummary): Status {
  return r.last_run_at ? "ran" : "draft";
}

// Shared parser appends Z to naïve backend ISO strings so the local
// clock isn't off by the user's UTC offset.
const relative = relativeBackend;
const toDateMs = (iso?: string | null): number => {
  const d = parseBackendDate(iso); return d ? d.getTime() : 0;
};

export function MyTestPatientsList({ onEdit, onRun, onView, onNew }: Props) {
  const [rows, setRows]     = useState<TestPatientSummary[] | null>(null);
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [query, setQuery]   = useState("");
  const [sort, setSort]     = useState<"recent" | "created" | "runs" | "confidence" | "label">("recent");
  // Run/Re-run no longer fires immediately. Clicking the button opens a
  // config modal so the user can pick model preset / top-K / accuracy
  // before the pipeline actually starts. `runFor` holds the in-flight
  // patient so the modal can read its label + previous-run hint.
  const [runFor, setRunFor] = useState<TestPatientSummary | null>(null);

  function load() { listTestPatients().then(setRows); }
  useEffect(load, []);

  async function remove(uuid: string) {
    if (!window.confirm("Delete this test patient? Past run results stay in the audit trail."))
      return;
    await deleteTestPatient(uuid);
    load();
  }

  const list = rows ?? [];

  const summary = useMemo(() => {
    const runs    = list.reduce((a, r) => a + (r.run_count ?? 0), 0);
    const ran     = list.filter((r) => r.last_run_at).length;
    const drafts  = list.length - ran;
    const lastRun = list.map((r) => r.last_run_at).filter(Boolean).sort().pop() as string | undefined;
    return { patients: list.length, runs, ran, drafts, lastRun };
  }, [list]);

  const counts: Record<FilterKey, number> = useMemo(() => {
    const s = list.map(deriveStatus);
    return {
      ALL:   list.length,
      ran:   s.filter((x) => x === "ran").length,
      draft: s.filter((x) => x === "draft").length,
    };
  }, [list]);

  // Hide the per-status chips if everyone is in the same bucket — chips
  // that always equal "All" add no information.
  const showStatusChips = counts.ran > 0 && counts.draft > 0;

  const filtered = useMemo(() => {
    let r = list;
    if (filter !== "ALL") r = r.filter((x) => deriveStatus(x) === filter);
    const q = query.trim().toLowerCase();
    if (q) {
      r = r.filter((x) =>
        x.label.toLowerCase().includes(q)
        || (x.latest_primary_dx ?? "").toLowerCase().includes(q),
      );
    }
    r = [...r].sort((a, b) => {
      if (sort === "label")      return a.label.localeCompare(b.label);
      if (sort === "runs")       return (b.run_count ?? 0) - (a.run_count ?? 0);
      if (sort === "confidence") return (b.latest_primary_confidence ?? 0) - (a.latest_primary_confidence ?? 0);
      if (sort === "created")    return +new Date(b.created_at) - +new Date(a.created_at);
      const aT = a.last_run_at ? +new Date(a.last_run_at) : 0;
      const bT = b.last_run_at ? +new Date(b.last_run_at) : 0;
      return bT - aT;
    });
    return r;
  }, [list, filter, query, sort]);

  const isEmpty = rows !== null && rows.length === 0;

  return (
    <div className="tests-view">
      <header className="tests-view__header">
        <div className="tests-view__heading">
          <h2 className="tests-view__title">My test patients</h2>
          <div className="tests-view__sub">Past custom patient runs · Researcher</div>
        </div>
        <button onClick={onNew} className="tests-view__cta">+ New patient</button>
      </header>

      {isEmpty ? (
        <div className="tests-empty">
          <FlaskConical size={36} strokeWidth={1.2} className="tests-empty__icon" />
          <h3 className="tests-empty__title">No test patients yet.</h3>
          <p className="tests-empty__sub">
            Build one from scratch or clone a Synthea patient to get started.
          </p>
          <button onClick={onNew} className="tests-view__cta tests-empty__cta">+ New patient</button>
        </div>
      ) : (
        <>
          <StatStrip s={summary} />

          <Toolbar
            filter={filter} setFilter={setFilter}
            query={query}   setQuery={setQuery}
            sort={sort}     setSort={setSort}
            counts={counts} showStatusChips={showStatusChips}
          />

          <ul className="tests-list">
            {filtered.map((r, i) => (
              <ListRow
                key={r.test_uuid}
                r={r}
                last={i === filtered.length - 1}
                busy={runFor?.test_uuid === r.test_uuid}
                onRun={() => setRunFor(r)}
                onView={r.last_run_at ? () => onView(r.test_uuid) : undefined}
                onEdit={() => onEdit(r.test_uuid)}
                onRemove={() => remove(r.test_uuid)}
              />
            ))}
            {filtered.length === 0 && (
              <li className="tests-list__none">
                No patients match the current filter.
              </li>
            )}
          </ul>
        </>
      )}

      <AnimatePresence>
        {runFor && (
          <TestRunConfigModal
            key={runFor.test_uuid}
            patient={runFor}
            onClose={() => setRunFor(null)}
            onStarted={(taskId) => {
              setRunFor(null);
              // Let the parent know a run kicked off (refresh list, etc.)
              // before we navigate away. The parent unmounts when the URL
              // flips, so its bookkeeping needs to happen now.
              onRun(taskId);
              // Hand the task off to the Doctor runtime workspace — same
              // running view + result view the normal Run flow uses. The
              // helper stashes the task and pushes ?mode=runtime; RuntimeMode
              // picks it up on its mount effect and subscribes to SSE.
              handoffToRuntimeRun(taskId);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Stat strip ─────────────────────────────────────────────────────── */
function StatStrip({ s }: {
  s: { patients: number; runs: number; ran: number; drafts: number; lastRun?: string };
}) {
  return (
    <div className="tests-strip">
      <Stat label="Patients"      value={String(s.patients)} hint={`${s.ran} ran · ${s.drafts} draft${s.drafts === 1 ? "" : "s"}`} />
      <Stat label="Total runs"    value={String(s.runs)}     hint={s.runs ? "across all patients" : "no runs yet"} tone={s.runs ? undefined : "muted"} />
      <Stat label="Last activity" value={s.lastRun ? relative(s.lastRun) : "—"}
                                  hint={s.lastRun ? "most recent run" : "no runs yet"}
                                  tone={s.lastRun ? undefined : "muted"} last />
    </div>
  );
}

function Stat({ label, value, hint, tone, last }: {
  label: string;
  value: string;
  hint?: string;
  tone?: "success" | "muted";
  last?: boolean;
}) {
  return (
    <div className={`tests-strip__cell${last ? " is-last" : ""}`}>
      <div className="tests-strip__label">{label}</div>
      <div className={`tests-strip__value${tone ? ` tests-strip__value--${tone}` : ""}`}>{value}</div>
      {hint && <div className="tests-strip__hint">{hint}</div>}
    </div>
  );
}

/* ── Toolbar ────────────────────────────────────────────────────────── */
function Toolbar({
  filter, setFilter, query, setQuery, sort, setSort, counts, showStatusChips,
}: {
  filter:    FilterKey;
  setFilter: (f: FilterKey) => void;
  query:     string;
  setQuery:  (q: string) => void;
  sort:      "recent" | "created" | "runs" | "confidence" | "label";
  setSort:   (s: "recent" | "created" | "runs" | "confidence" | "label") => void;
  counts:    Record<FilterKey, number>;
  showStatusChips: boolean;
}) {
  type Chip = { key: FilterKey; label: string; tone: "muted" | "success" };
  const chips: Chip[] = [
    { key: "ALL", label: "All", tone: "muted" },
    ...(showStatusChips ? ([
      { key: "ran",   label: "Ran",    tone: "success" },
      { key: "draft", label: "Drafts", tone: "muted"   },
    ] satisfies Chip[]) : []),
  ];
  return (
    <div className="tests-toolbar">
      <div className="tests-search">
        <Search size={12} strokeWidth={1.8} className="tests-search__icon" />
        <input
          type="text"
          className="tests-search__input"
          placeholder="Search label or diagnosis…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="tests-chips">
        {chips.map((c) => {
          const active = filter === c.key;
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => setFilter(c.key)}
              className={`tests-chip tests-chip--${c.tone}${active ? " is-active" : ""}`}
              aria-pressed={active}
            >
              <span className={`tests-chip__dot tests-chip__dot--${c.tone}`} aria-hidden="true" />
              {c.label}
              <span className="tests-chip__count mono">{counts[c.key]}</span>
            </button>
          );
        })}
      </div>
      <div className="tests-sort">
        <span className="tests-sort__label">Sort</span>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          className="tests-sort__select"
        >
          <option value="recent">Last run</option>
          <option value="created">Created</option>
          <option value="runs">Run count</option>
          <option value="confidence">Confidence</option>
          <option value="label">Label A–Z</option>
        </select>
      </div>
    </div>
  );
}

/* ── Single row ─────────────────────────────────────────────────────── */
function ListRow({ r, last, busy, onRun, onView, onEdit, onRemove }: {
  r:        TestPatientSummary;
  last:     boolean;
  busy:     boolean;
  onRun:    () => void;
  /** Optional — only provided when the patient has a `last_run_at`. Opens
   *  the most recent completed run in the Doctor runtime view (read-only
   *  result; doesn't re-trigger the pipeline). */
  onView?:  () => void;
  onEdit:   () => void;
  onRemove: () => void;
}) {
  const status = deriveStatus(r);
  const meta   = STATUS_META[status];
  return (
    <li className={`tests-row${last ? " is-last" : ""} tests-row--${meta.tone}${status === "draft" ? " tests-row--draft" : ""}`}>
      <span className={`tests-row__accent tests-row__accent--${meta.tone}`} aria-hidden="true" />
      <div className="tests-row__meta">
        <div className="tests-row__meta-top">
          <span className="tests-row__label">{r.label}</span>
          <StatusPill status={status} />
        </div>
        <div className="tests-row__meta-bottom mono">
          created {relative(r.created_at)}
          {r.last_run_at && (
            <>{" "}· {r.run_count} run{r.run_count === 1 ? "" : "s"} · last {relative(r.last_run_at)}</>
          )}
          {r.last_duration_s != null && (
            <>{" "}· {Math.round(r.last_duration_s)}s</>
          )}
        </div>
      </div>

      <OutcomeLine r={r} status={status} />

      <div className="tests-row__when mono">
        {r.last_run_at
          ? relative(r.last_run_at)
          : <span className="tests-row__never">never</span>}
      </div>

      <div className="tests-row__actions">
        {onView && (
          <button
            type="button"
            onClick={onView}
            className="tests-btn tests-btn--ghost"
            title="View the most recent run in the runtime workspace"
          >
            <Eye size={11} strokeWidth={1.8} />
            View
          </button>
        )}
        <button
          type="button"
          onClick={onRun}
          disabled={busy}
          className="tests-btn tests-btn--primary"
          title={r.last_run_at ? "Re-run pipeline on this patient" : "Run pipeline on this patient"}
        >
          <Play size={11} strokeWidth={2} />
          {r.last_run_at ? "Re-run" : "Run"}
        </button>
        <button
          type="button"
          onClick={onEdit}
          className="tests-btn tests-btn--ghost"
          title="Edit patient"
        >
          <Pencil size={11} strokeWidth={1.8} />
          Edit
        </button>
        <button
          type="button"
          onClick={onRemove}
          className="tests-btn tests-btn--ghost tests-btn--danger"
          aria-label={`Delete ${r.label}`}
          title="Delete"
        >
          <Trash2 size={12} strokeWidth={1.7} />
        </button>
      </div>
    </li>
  );
}

/* ── StatusPill ─────────────────────────────────────────────────────── */
function StatusPill({ status }: { status: Status }) {
  const meta = STATUS_META[status];
  return (
    <span className={`tests-pill tests-pill--${meta.tone} mono`}>
      <span className="tests-pill__glyph" aria-hidden="true">{meta.glyph}</span>
      {meta.label}
    </span>
  );
}

/* ── OutcomeLine ────────────────────────────────────────────────────── */
function OutcomeLine({ r, status }: {
  r:      TestPatientSummary;
  status: Status;
}) {
  if (status === "draft") {
    return (
      <span className="tests-outcome tests-outcome--draft">
        Not yet run · save first or run from scratch
      </span>
    );
  }
  // "ran" — surface the top diagnosis + confidence so the user can see the
  // agents' actual answer without opening the run detail view.
  const conf = r.latest_primary_confidence ?? 0;
  const dx   = r.latest_primary_dx ?? "—";
  return (
    <div className="tests-outcome">
      <div className="tests-outcome__top">
        <span className="tests-outcome__eyebrow mono">Top diagnosis</span>
        <span className="tests-outcome__dx">{dx}</span>
        <span className="tests-outcome__bar" role="presentation">
          <span
            className="tests-outcome__bar-fill tests-outcome__bar-fill--success"
            style={{ width: `${Math.max(0, Math.min(100, conf))}%` }}
          />
        </span>
        <span className="tests-outcome__pct mono tests-outcome__pct--success">
          {Math.round(conf)}%
        </span>
      </div>
    </div>
  );
}

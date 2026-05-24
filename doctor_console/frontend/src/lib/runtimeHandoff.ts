/**
 * Runtime hand-off helpers.
 *
 * Lets non-runtime surfaces (the Researcher → My-test-patients list, in
 * particular) push a run into the Doctor-runtime workspace so the user
 * sees the same running view + result view they get from a normal Run.
 *
 * Two intents are supported:
 *
 *   1. `handoffToRuntimeRun(taskId)` — the caller just fired a new run via
 *      startTestRun / startRun and has a taskId; the runtime view picks it
 *      up on mount (via RuntimeMode's existing localStorage-rehydrate path)
 *      and subscribes to SSE for the live agent flow.
 *
 *   2. `handoffToRuntimeView({ patientUuid, resultSet })` — the caller wants
 *      to *view* an already-completed past run without re-running it. The
 *      runtime view reads this on mount, calls getResult, and jumps
 *      straight to phase="completed" with a synthetic task.
 *
 * Both helpers stash the intent in localStorage *then* flip the URL to
 * `?mode=runtime` so App.tsx unmounts the current workspace and mounts
 * RuntimeMode, which reads the stash on mount. We can't share state via
 * React context here because the two workspaces don't share a mount tree.
 */

export const RUN_TASK_STORAGE_KEY    = "cmads.runtime.activeTaskId";
export const VIEW_INTENT_STORAGE_KEY = "cmads.runtime.viewIntent";

export interface RuntimeViewIntent {
  patientUuid: string;
  resultSet:   string;
}

/* ── Active-task storage ────────────────────────────────────────────── */
export function getRuntimeTask(): string | null {
  try { return window.localStorage.getItem(RUN_TASK_STORAGE_KEY); }
  catch { return null; }
}
export function setRuntimeTask(taskId: string | null): void {
  try {
    if (taskId) window.localStorage.setItem(RUN_TASK_STORAGE_KEY, taskId);
    else        window.localStorage.removeItem(RUN_TASK_STORAGE_KEY);
  } catch { /* ignore */ }
}

/* ── View-intent storage ────────────────────────────────────────────── */
export function getViewIntent(): RuntimeViewIntent | null {
  try {
    const raw = window.localStorage.getItem(VIEW_INTENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.patientUuid === "string" && typeof parsed.resultSet === "string") {
      return parsed as RuntimeViewIntent;
    }
    return null;
  } catch { return null; }
}
export function setViewIntent(v: RuntimeViewIntent | null): void {
  try {
    if (v) window.localStorage.setItem(VIEW_INTENT_STORAGE_KEY, JSON.stringify(v));
    else   window.localStorage.removeItem(VIEW_INTENT_STORAGE_KEY);
  } catch { /* ignore */ }
}

/* ── URL flip ───────────────────────────────────────────────────────── */
function flipToRuntime(): void {
  const params = new URLSearchParams(window.location.search);
  // Clear leftover deep-link params from the previous workspace so the user
  // lands on the natural runtime entry rather than e.g. ?tab=patients.
  ["tab", "p", "a", "r"].forEach((k) => params.delete(k));
  params.set("mode", "runtime");
  const url = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
  window.history.pushState(null, "", url);
  // useUrlState hooks listen for popstate, so dispatch one to trigger
  // re-renders without a full reload.
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/* ── Public hand-off API ────────────────────────────────────────────── */
export function handoffToRuntimeRun(taskId: string): void {
  setRuntimeTask(taskId);
  setViewIntent(null);
  flipToRuntime();
}

export function handoffToRuntimeView(intent: RuntimeViewIntent): void {
  // View-intent supersedes any stale task — clear it so RuntimeMode
  // doesn't try to subscribe to an unrelated run on mount.
  setRuntimeTask(null);
  setViewIntent(intent);
  flipToRuntime();
}

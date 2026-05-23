import type {
  Annotation, CohortBrowseRow, CohortComparisonResponse, ComparisonResult,
  DashboardSummary, ExtractResponse, MemoryAbComparison, ModelPreset,
  PatientListItem, PatientResult, ResultSet, RunTask, SimilarCasesResponse,
  StatsOverview, TestPatientDoc, TestPatientPayload, TestPatientSummary,
  VocabularyItem,
} from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (parsed.detail) {
        message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
      }
    } catch {
      // The API may return plain text from middleware or development proxies.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function getResultSets(
  options: { includeRuntime?: boolean } = {}
): Promise<ResultSet[]> {
  const params = new URLSearchParams();
  if (options.includeRuntime) params.set("include_runtime", "true");
  const qs = params.toString();
  return request<ResultSet[]>(`/api/result-sets${qs ? `?${qs}` : ""}`);
}

export function getDashboard(resultSet: string): Promise<DashboardSummary> {
  const params = new URLSearchParams({ result_set: resultSet });
  return request<DashboardSummary>(`/api/dashboard?${params.toString()}`);
}

export type AgentPrompt = {
  agentId: string;
  path: string;
  text: string;
  lineCount: number;
  byteSize: number;
};

export function getAgentPrompt(agentId: string): Promise<AgentPrompt> {
  return request<AgentPrompt>(`/api/agents/${encodeURIComponent(agentId)}/prompt`);
}

export function getStatsOverview(resultSet: string): Promise<StatsOverview> {
  const params = new URLSearchParams({ result_set: resultSet });
  return request<StatsOverview>(`/api/stats/overview?${params.toString()}`);
}

export function getCohortComparison(
  options: { includeRuntime?: boolean } = {}
): Promise<CohortComparisonResponse> {
  const params = new URLSearchParams();
  if (options.includeRuntime) params.set("include_runtime", "true");
  const qs = params.toString();
  return request<CohortComparisonResponse>(
    `/api/stats/cohort-comparison${qs ? `?${qs}` : ""}`
  );
}

export function getMemoryAbComparison(): Promise<MemoryAbComparison> {
  return request<MemoryAbComparison>("/api/comparisons/memory-ab");
}

export function getModelComparison(
  baseline: string,
  candidate: string
): Promise<ComparisonResult> {
  const params = new URLSearchParams({ baseline, candidate });
  return request<ComparisonResult>(`/api/comparisons/model?${params.toString()}`);
}

export function getMasVsSingleLlmComparison(): Promise<ComparisonResult> {
  return request<ComparisonResult>("/api/comparisons/mas-vs-single-llm");
}

export function getPatients(
  resultSet: string,
  query: string,
  options: { unseenOnly?: boolean; verifiedOnly?: boolean } = {},
): Promise<PatientListItem[]> {
  const params = new URLSearchParams({ result_set: resultSet, query, limit: "500" });
  if (options.unseenOnly)   params.set("unseen_only", "true");
  if (options.verifiedOnly) params.set("verified_only", "true");
  return request<PatientListItem[]>(`/api/patients?${params.toString()}`);
}

export function getResult(resultSet: string, patientUuid: string): Promise<PatientResult> {
  return request<PatientResult>(`/api/results/${resultSet}/${patientUuid}`);
}

/**
 * Load the Gold-layer case bundle for a patient (EHR + Lab + demographics).
 * Used during a live run so the doctor can see what data is being read
 * before the full PatientResult is available.
 */
export type CaseBundle = {
  patient: PatientResult["patient"];
  ehrCase: Record<string, unknown>;
  labCase: Record<string, unknown>;
  groundTruth: Record<string, unknown>;
  caseStats: Record<string, number>;
};

export function getPatientCase(patientUuid: string): Promise<CaseBundle> {
  return request<CaseBundle>(`/api/patients/${patientUuid}/case`);
}

export function getSimilarCases(
  patientUuid: string,
  options: {
    topK?: number;
    matchFilter?: string[];
    excludeSelf?: boolean;
    resultSet?: string;
    mode?: "researcher" | "runtime";
  } = {}
): Promise<SimilarCasesResponse> {
  const params = new URLSearchParams({
    top_k: String(options.topK ?? 5),
    match_filter: (options.matchFilter ?? []).join(","),
    exclude_self: String(options.excludeSelf ?? true),
    result_set: options.resultSet ?? "mas_results",
    mode: options.mode ?? "researcher",
  });
  return request<SimilarCasesResponse>(`/api/patients/${patientUuid}/similar?${params.toString()}`);
}

export function startRun(
  patientUuid: string,
  options: {
    presetId?: string; provider?: string; model?: string;
    topK?: number;
  } = {},
): Promise<RunTask> {
  const body: Record<string, unknown> = { patient_uuid: patientUuid };
  if (options.presetId) body.preset_id = options.presetId;
  if (options.provider) body.provider = options.provider;
  if (options.model)    body.model    = options.model;
  if (typeof options.topK === "number") body.top_k = options.topK;
  return request<RunTask>("/api/runs", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(body),
  });
}

export function getModelPresets(): Promise<ModelPreset[]> {
  return request<ModelPreset[]>("/api/model-presets");
}

export function getRun(taskId: string): Promise<RunTask> {
  return request<RunTask>(`/api/runs/${taskId}`);
}

export { getRun as getRunStatus };

export function cancelRun(
  taskId: string
): Promise<{ cancelled: boolean; reason?: string }> {
  return request<{ cancelled: boolean; reason?: string }>(
    `/api/runs/${encodeURIComponent(taskId)}/cancel`,
    { method: "POST" }
  );
}

export function getAnnotation(patientUuid: string): Promise<Annotation> {
  return request<Annotation>(`/api/annotations/${patientUuid}`);
}

export function saveAnnotation(
  patientUuid: string,
  payload: Pick<Annotation, "agreement" | "notes" | "reviewer"> & { reviewed?: boolean }
): Promise<Annotation> {
  return request<Annotation>(`/api/annotations/${patientUuid}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ reviewed: true, ...payload }),
  });
}

export function deleteAnnotation(patientUuid: string): Promise<Annotation> {
  return request<Annotation>(`/api/annotations/${patientUuid}`, { method: "DELETE" });
}

/**
 * Subscribe to a live run with SSE + polling fallback.
 *
 * The backend streams task updates over a long-lived ``EventSource``. In
 * practice that connection can drop for benign reasons mid-run — proxy
 * idle timeout, dev-server HMR reconnect, brief Wi-Fi blip — even though
 * the pipeline is still happily executing on the server. The old version
 * surfaced "stream disconnected" the instant SSE errored and the doctor
 * thought the run had failed.
 *
 * This version is robust:
 *   1. Use SSE while it works.
 *   2. If SSE errors, switch to polling ``GET /api/runs/{id}`` every 3 s.
 *   3. Reuse the same ``onTask`` callback for both — UI doesn't know the
 *      difference.
 *   4. Only surface ``onError`` if the task itself reports ``status:error``
 *      or if polling fails for 5 consecutive attempts (~15 s).
 *   5. Stop on terminal status (``completed`` / ``error``).
 */
// ── Tester journey API ──────────────────────────────────────────

export function getVocabulary(
  kind: "condition" | "medication" | "lab",
  q: string,
): Promise<VocabularyItem[]> {
  const params = new URLSearchParams({ kind, q });
  return request<VocabularyItem[]>(`/api/tests/vocabulary?${params}`);
}

export function getDiseaseCounts(): Promise<Record<string, number>> {
  return request<Record<string, number>>("/api/tests/cohort/disease-counts");
}

export function browseCohort(filters: {
  disease?: string;
  age_min?: number;
  age_max?: number;
  gender?: string;
  limit?: number;
}): Promise<CohortBrowseRow[]> {
  const params = new URLSearchParams();
  if (filters.disease) params.set("disease", filters.disease);
  if (filters.age_min != null) params.set("age_min", String(filters.age_min));
  if (filters.age_max != null) params.set("age_max", String(filters.age_max));
  if (filters.gender) params.set("gender", filters.gender);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  return request<CohortBrowseRow[]>(`/api/tests/cohort?${params}`);
}

export function getCohortTemplate(uuid: string): Promise<TestPatientPayload> {
  return request<TestPatientPayload>(`/api/tests/cohort/${encodeURIComponent(uuid)}`);
}

export function createTestPatient(payload: TestPatientPayload):
    Promise<{ test_uuid: string; label: string; created_at: string }> {
  return request<{ test_uuid: string; label: string; created_at: string }>(
    "/api/tests/patients",
    {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    },
  );
}

export function listTestPatients(): Promise<TestPatientSummary[]> {
  return request<TestPatientSummary[]>("/api/tests/patients");
}

export function getTestPatient(testUuid: string): Promise<TestPatientDoc> {
  return request<TestPatientDoc>(`/api/tests/patients/${encodeURIComponent(testUuid)}`);
}

export function updateTestPatient(testUuid: string, payload: TestPatientPayload):
    Promise<TestPatientDoc> {
  return request<TestPatientDoc>(
    `/api/tests/patients/${encodeURIComponent(testUuid)}`,
    {
      method:  "PUT",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    },
  );
}

export function deleteTestPatient(testUuid: string, withRuns = false):
    Promise<{ deleted: true }> {
  return request<{ deleted: true }>(
    `/api/tests/patients/${encodeURIComponent(testUuid)}?with_runs=${withRuns}`,
    { method: "DELETE" },
  );
}

/**
 * Build a CaseBundle from a TestPatientDoc so that the RuntimeRunningView
 * can render the same patient-context panel for Tester runs that it shows
 * for Known-patient runs.  The shapes are equivalent; we just re-map field
 * names to match what CaseBundle / PatientResult["patient"] expect.
 */
export async function getTestPatientAsCase(testUuid: string): Promise<CaseBundle> {
  const doc = await getTestPatient(testUuid);
  const demographics = doc.demographics as Record<string, unknown> | undefined;
  // PatientEvidence (the runtime renderer) keys lab rows on Synthea's
  // {lab_name, value, units, date} shape. TestPatient docs store the
  // canonical {test_name, value, unit, …} shape. Without this remap,
  // every lab in a custom-patient run shows "Lab" (the fallback string)
  // because lab_name is missing — exactly what the bug report describes.
  const rawLabs = (doc.labs ?? {}) as Record<string, unknown>;
  const rawRows = (rawLabs.latest_labs as unknown[] | undefined) ?? [];
  const labCase: Record<string, unknown> = {
    ...rawLabs,
    latest_labs: rawRows.map((row) => {
      const r = (row ?? {}) as Record<string, unknown>;
      return {
        lab_name: r.test_name ?? r.lab_name ?? "",
        value:    r.value     ?? "",
        units:    r.unit      ?? r.units    ?? "",
        date:     r.date      ?? "",
        reference_range: r.reference_range,
        flag:     r.flag,
      };
    }),
  };
  return {
    patient: {
      uuid: doc._id,
      age:  demographics?.age  as number  | undefined,
      gender: demographics?.gender as string | undefined,
      race:   demographics?.race   as string | undefined,
      ethnicity: demographics?.ethnicity as string | undefined,
      cutoffDate: doc.cutoff_date,
      targetCondition: (doc.ground_truth as Record<string, unknown> | undefined)
        ?.target_condition
        ? ((doc.ground_truth as Record<string, Record<string, unknown>>)
            .target_condition?.name as string | undefined)
        : undefined,
    },
    ehrCase: {
      patient_uuid: doc._id,
      cutoff_date:  doc.cutoff_date,
      demographics: doc.demographics,
      conditions:   doc.conditions,
      medications:  doc.medications,
      visits:       doc.visits,
      comorbidity:  (doc as unknown as Record<string, unknown>).comorbidity,
      risk_scores:  (doc as unknown as Record<string, unknown>).risk_scores,
    },
    labCase,
    groundTruth: (doc.ground_truth ?? {}) as Record<string, unknown>,
    caseStats: {
      activeConditions:
        ((doc.conditions as { active?: unknown[] } | undefined)?.active ?? []).length,
      activeMedications:
        ((doc.medications as { active?: unknown[] } | undefined)?.active ?? []).length,
      labTrends:
        ((doc.labs as { latest_labs?: unknown[] } | undefined)?.latest_labs ?? []).length,
      criticalFlags: 0,
    },
  };
}

export function extractText(text: string): Promise<ExtractResponse> {
  const fd = new FormData();
  fd.append("kind", "text");
  fd.append("text", text);
  return request<ExtractResponse>("/api/tests/extract", {
    method: "POST",
    // Do NOT set Content-Type here — the browser sets it with the multipart
    // boundary automatically when body is a FormData instance.
    body: fd,
  });
}

export function extractFile(file: File): Promise<ExtractResponse> {
  const fd = new FormData();
  fd.append("kind", "file");
  fd.append("file", file);
  return request<ExtractResponse>("/api/tests/extract", {
    method: "POST",
    body: fd,
  });
}

export function extractImage(image: File): Promise<ExtractResponse> {
  const fd = new FormData();
  fd.append("kind", "image");
  fd.append("file", image);
  return request<ExtractResponse>("/api/tests/extract", { method: "POST", body: fd });
}

export function startTestRun(testUuid: string, opts: {
  topK?: number; accuracyMode?: "recommended" | "fast"; presetId?: string;
} = {}): Promise<RunTask> {
  return request<RunTask>("/api/tests/runs", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      test_uuid:     testUuid,
      top_k:         opts.topK ?? 5,
      accuracy_mode: opts.accuracyMode ?? "recommended",
      preset_id:     opts.presetId,
    }),
  });
}

export function subscribeRun(
  taskId: string,
  onTask: (task: RunTask) => void,
  onError: (message: string) => void
): () => void {
  let cancelled = false;
  let pollTimer: number | null = null;
  let failuresInARow = 0;

  const stopPolling = () => {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  };

  const isTerminal = (status: string) =>
    status === "completed" || status === "error" || status === "cancelled";

  const poll = async () => {
    if (cancelled) return;
    try {
      const task = await getRun(taskId);
      failuresInARow = 0;
      onTask(task);
      if (isTerminal(task.status)) {
        stopPolling();
        return;
      }
    } catch {
      failuresInARow += 1;
      if (failuresInARow >= 5) {
        onError("Live run stream disconnected. The run may still be processing.");
        stopPolling();
        return;
      }
    }
    if (!cancelled) {
      pollTimer = window.setTimeout(poll, 3000);
    }
  };

  const source = new EventSource(`/api/runs/${taskId}/stream`);
  source.onmessage = (event) => {
    try {
      const task = JSON.parse(event.data) as RunTask;
      onTask(task);
      if (isTerminal(task.status)) {
        source.close();
        stopPolling();
      }
    } catch { /* malformed payload — ignore one frame */ }
  };
  source.onerror = () => {
    // Don't surface an error — the SSE connection just dropped. Switch to
    // polling to keep the run alive in the UI.
    source.close();
    if (!cancelled && pollTimer === null) {
      pollTimer = window.setTimeout(poll, 1000);
    }
  };

  return () => {
    cancelled = true;
    source.close();
    stopPolling();
  };
}

import type { DashboardSummary, PatientListItem, PatientResult, ResultSet, RunTask, SimilarCasesResponse } from "./types";

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

export function getResultSets(): Promise<ResultSet[]> {
  return request<ResultSet[]>("/api/result-sets");
}

export function getDashboard(resultSet: string): Promise<DashboardSummary> {
  const params = new URLSearchParams({ result_set: resultSet });
  return request<DashboardSummary>(`/api/dashboard?${params.toString()}`);
}

export function getPatients(resultSet: string, query: string): Promise<PatientListItem[]> {
  const params = new URLSearchParams({ result_set: resultSet, query, limit: "500" });
  return request<PatientListItem[]>(`/api/patients?${params.toString()}`);
}

export function getResult(resultSet: string, patientUuid: string): Promise<PatientResult> {
  return request<PatientResult>(`/api/results/${resultSet}/${patientUuid}`);
}

export function getSimilarCases(
  patientUuid: string,
  options: { topK?: number; matchFilter?: string[]; excludeSelf?: boolean; resultSet?: string } = {}
): Promise<SimilarCasesResponse> {
  const params = new URLSearchParams({
    top_k: String(options.topK ?? 5),
    match_filter: (options.matchFilter ?? []).join(","),
    exclude_self: String(options.excludeSelf ?? true),
    result_set: options.resultSet ?? "mas_results",
  });
  return request<SimilarCasesResponse>(`/api/patients/${patientUuid}/similar?${params.toString()}`);
}

export function startRun(patientUuid: string): Promise<RunTask> {
  return request<RunTask>("/api/runs", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ patient_uuid: patientUuid })
  });
}

export function getRun(taskId: string): Promise<RunTask> {
  return request<RunTask>(`/api/runs/${taskId}`);
}

export function subscribeRun(
  taskId: string,
  onTask: (task: RunTask) => void,
  onError: (message: string) => void
): () => void {
  const source = new EventSource(`/api/runs/${taskId}/stream`);
  source.onmessage = (event) => {
    onTask(JSON.parse(event.data) as RunTask);
  };
  source.onerror = () => {
    onError("Live run stream disconnected. The run may still be processing.");
    source.close();
  };
  return () => source.close();
}

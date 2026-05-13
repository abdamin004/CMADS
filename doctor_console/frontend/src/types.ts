export type ResultSet = {
  id: string;
  label: string;
  path: string;
  patientCount: number;
};

export type PatientListItem = {
  uuid: string;
  age?: number;
  gender?: string;
  race?: string;
  hasRun: boolean;
  matchType?: string;
  primaryDiagnosis?: string;
  durationS?: number;
};

export type DashboardSummary = {
  resultSet: ResultSet;
  totalGoldPatients: number;
  savedRuns: number;
  directMatches: number;
  indirectMatches: number;
  misses: number;
  unevaluated: number;
  directRate: number;
  usefulRate: number;
  averageDurationS?: number | null;
  matchDistribution: Array<{
    label: string;
    count: number;
    rate: number;
  }>;
  agentCompletion: Array<{
    agentId: string;
    label: string;
    completed: number;
    rate: number;
  }>;
  topDiagnoses: Array<{
    diagnosis: string;
    count: number;
  }>;
  memoryStore: {
    path: string;
    exists: boolean;
    semanticEntries: number;
    updatedAt?: number | null;
  };
};

export type AgentCard = {
  id: string;
  label: string;
  status: string;
  executionMs?: number;
  error?: string | null;
  summary: string;
  hasOutput: boolean;
};

export type AgentNarrative = {
  agentId: string;
  title: string;
  summary: string;
  metrics: Array<{
    label: string;
    value: string | number;
  }>;
  callouts: string[];
  sections: Array<{
    title: string;
    items: string[];
    empty?: string;
  }>;
};

export type SessionEvent = {
  event_type: string;
  agent_id: string;
  timestamp?: string;
  summary: string;
  payload?: Record<string, unknown>;
  tags?: string[];
};

export type PatientResult = {
  patient: {
    uuid: string;
    age?: number;
    gender?: string;
    race?: string;
    ethnicity?: string;
    cutoffDate?: string;
    targetCondition?: string;
  };
  resultSet: ResultSet;
  case: {
    caseStats: Record<string, number>;
    ehrCase: Record<string, unknown>;
    labCase: Record<string, unknown>;
    groundTruth: Record<string, unknown>;
  };
  evaluation: Record<string, unknown>;
  finalDiagnosis: Record<string, unknown>;
  treatment: Record<string, unknown>;
  agents: AgentCard[];
  agentOutputs: Record<string, unknown>;
  agentNarratives: Record<string, AgentNarrative>;
  trace: Record<string, unknown>;
  sessionMemory: SessionEvent[];
  semanticMemory: Record<string, unknown>[];
  sharedMemory: {
    patientContext: string;
    agentOutputKeys: string[];
    sessionEvents: number;
    traceEntries: number;
    notes: string[];
  };
};

export type RunTask = {
  taskId: string;
  patientUuid: string;
  status: "queued" | "running" | "completed" | "error";
  startedAt?: number;
  finishedAt?: number;
  error?: string | null;
  resultSet: string;
  activeAgentId?: string | null;
  agents?: AgentCard[];
  agentNarratives?: Record<string, AgentNarrative>;
  events?: RunEvent[];
};

export type RunEvent = {
  timestamp: number;
  agentId?: string | null;
  title: string;
  message: string;
};

export type SimilarCase = {
  patientUuid: string;
  similarity: number;
  matchedDiagnosis?: string | null;
  rawDiagnosis?: string | null;
  canonicalFamily?: string | null;
  matchType?: string | null;
  rankWhenFound?: number | null;
  primaryConfidence?: number | null;
  caseText?: string;
  evidencePatterns?: string[];
  indexedAt?: string | null;
};

export type SimilarCasesResponse = {
  patientUuid: string;
  collection: string;
  totalIndexed: number;
  isPatientIndexed: boolean;
  queryText: string;
  error?: string | null;
  results: SimilarCase[];
};

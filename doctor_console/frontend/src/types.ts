export type ResultSet = {
  id: string;
  label: string;
  path: string;
  patientCount: number;
  /** Experimental category (e.g. "Multi-level memory", "Model comparison"). */
  category?: string;
  /** LLM backend the cohort was produced with. */
  model?: string;
  /** True for cohorts that hold live doctor runs (mas_results_runtime). */
  runtime?: boolean;
};

/**
 * One row in the cohort-comparison table. Mirrors what /api/stats/cohort-comparison
 * returns — the Streamlit master table moved behind a single endpoint.
 */
export type CohortRow = {
  id: string;
  label: string;
  category: string;
  model: string;
  n: number;
  direct: number;
  indirect: number;
  miss: number;
  found: number;
  rank1: number;
  directPct: number;
  indirectPct: number;
  missPct: number;
  foundPct: number;
  rank1PctOfFound: number;
  avgTimeS: number;
  medianTimeS: number;
};

export type CohortComparisonResponse = { rows: CohortRow[] };

export type RankBucket = { label: string; count: number };

export type PerDiseaseRow = {
  disease: string;
  n: number;
  direct: number;
  indirect: number;
  miss: number;
  foundPct: number;
  avgRank: number | null;
};

export type CohortAggregates = {
  n: number;
  direct: number;
  indirect: number;
  miss: number;
  found: number;
  rank1: number;
  directPct: number;
  indirectPct: number;
  missPct: number;
  foundPct: number;
  rank1PctOfFound: number;
  avgTimeS: number;
  medianTimeS: number;
};

export type StatsOverview = {
  resultSet: ResultSet;
  aggregates: CohortAggregates;
  rankDistribution: RankBucket[];
  perDisease: PerDiseaseRow[];
  topDiagnoses: Array<{ diagnosis: string; count: number }>;
};

export type DiscordantPatient = {
  patientUuid: string;
  target: string;
  baselineMatchType?: string;
  candidateMatchType?: string;
  baselineRank?: number | null;
  candidateRank?: number | null;
  offDirect?: boolean;
  onDirect?: boolean;
};

export type ComparisonArm = {
  resultSet: ResultSet;
  label: string;
  aggregates: CohortAggregates;
  perDisease: PerDiseaseRow[];
};

export type ComparisonResult = {
  baseline: ComparisonArm;
  candidate: ComparisonArm;
  pairedN: number;
  restrictedToIntersection: boolean;
  discordant: DiscordantPatient[];
  discordantCount: number;
};

export type MemoryAbComparison = {
  label: string;
  armA: { key: string; label: string };
  armB: { key: string; label: string };
  nPaired: number;
  nDropped: number;
  offDirectRate: number;
  onDirectRate: number;
  /** Found rate (DIRECT + INDIRECT) — the headline metric in the UI. */
  offFoundRate?: number;
  onFoundRate?: number;
  offFoundCount?: number;
  onFoundCount?: number;
  offAggregates?: CohortAggregates;
  onAggregates?: CohortAggregates;
  offRankDistribution?: RankBucket[];
  onRankDistribution?: RankBucket[];
  offPerDisease?: PerDiseaseRow[];
  onPerDisease?: PerDiseaseRow[];
  contingency: {
    both_DIRECT?: number;
    only_OFF_DIRECT?: number;
    only_ON_DIRECT?: number;
    neither_DIRECT?: number;
  };
  mcnemar: {
    discordant_pairs?: number;
    p_value_two_sided?: number;
    method?: string;
  };
  discordant: DiscordantPatient[];
  discordantCount: number;
  artefactPath?: string | null;
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
  reviewed?: boolean;
  agreement?: "agree" | "disagree" | "uncertain" | null;
};

export type Annotation = {
  patientUuid: string;
  exists: boolean;
  reviewed?: boolean;
  agreement?: "agree" | "disagree" | "uncertain";
  notes?: string;
  reviewer?: string;
  updatedAt?: string;
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

/**
 * Per-run system-accuracy preset.
 * - "recommended" enables multi-level memory (principal headline
 *   configuration: 76.9% DIRECT).
 * - "fast" runs the single-level baseline — ~30 s faster per run
 *   but lower accuracy (53.8% DIRECT on the paired-160 cohort).
 */
export type AccuracyMode = "recommended" | "fast";

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
  modelOverride?: ModelOverrideEcho | null;
  accuracyMode?: AccuracyMode;
};

export type ModelPreset = {
  id: string;
  label: string;
  provider: string;
  model: string;
  location: "cloud" | "local";
  vendor: string;
  default?: boolean;
  /** Typical median wall-clock for one patient through the 7-agent pipeline. */
  runtimeSeconds?: number | null;
  /** Typical USD spend for one patient. 0 for local models. */
  costUsdPerPatient?: number | null;
  /** True if the backend has verified the preset is actually configured. */
  available?: boolean;
  /** Why the preset isn't available (missing API key, Ollama not running, etc.). */
  unavailableReason?: string | null;
};

export type ModelOverrideEcho = {
  presetId?: string | null;
  provider?: string | null;
  model?: string | null;
  label?: string | null;
  vendor?: string | null;
  location?: "cloud" | "local" | null;
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
  /** Runtime mode: confirmed clinical diagnosis from the neighbour's ground truth. */
  groundTruthDiagnosis?: string | null;
  groundTruthCode?: string | null;
  groundTruthDate?: string | null;
  /** "system_output" (researcher) or "ground_truth" (runtime). */
  source?: "system_output" | "ground_truth";
};

export type SimilarCasesResponse = {
  patientUuid: string;
  collection: string;
  totalIndexed: number;
  isPatientIndexed: boolean;
  queryText: string;
  mode?: "researcher" | "runtime";
  error?: string | null;
  results: SimilarCase[];
};

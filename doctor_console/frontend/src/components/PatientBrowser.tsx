import { useMemo, useState } from "react";
import { Activity, ChevronLeft, Filter, Play, RefreshCw, Search } from "lucide-react";
import type { PatientListItem, RunTask } from "../types";

type Props = {
  patients: PatientListItem[];
  selectedUuid?: string;
  query: string;
  loading: boolean;
  runTask?: RunTask | null;
  collapsed?: boolean;
  onQueryChange: (query: string) => void;
  onSelectPatient: (uuid: string) => void;
  onRefresh: () => void;
  onRun: () => void;
  onCollapseChange?: (collapsed: boolean) => void;
  onGoOverview?: () => void;
};

type MatchKey = "DIRECT" | "INDIRECT" | "MISS" | "NORUN";
const MATCH_OPTIONS: { key: MatchKey; label: string }[] = [
  { key: "DIRECT", label: "Direct" },
  { key: "INDIRECT", label: "Indirect" },
  { key: "MISS", label: "Miss" },
  { key: "NORUN", label: "No run" },
];

export function PatientBrowser({
  patients,
  selectedUuid,
  query,
  loading,
  runTask,
  collapsed = false,
  onQueryChange,
  onSelectPatient,
  onRefresh,
  onRun,
  onCollapseChange,
  onGoOverview,
}: Props) {
  const [matchFilters, setMatchFilters] = useState<Set<MatchKey>>(
    new Set(["DIRECT", "INDIRECT", "MISS", "NORUN"]),
  );
  const [genderFilter, setGenderFilter] = useState<"" | "M" | "F">("");
  const [ageMin, setAgeMin] = useState<string>("");
  const [ageMax, setAgeMax] = useState<string>("");
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);

  const filtered = useMemo(() => {
    return patients.filter((p) => {
      const m: MatchKey = p.hasRun
        ? ((p.matchType || "MISS").toUpperCase() as MatchKey)
        : "NORUN";
      if (!matchFilters.has(m)) return false;
      if (genderFilter && (p.gender || "").toUpperCase() !== genderFilter) return false;
      if (ageMin && (p.age ?? -1) < Number(ageMin)) return false;
      if (ageMax && (p.age ?? 1e9) > Number(ageMax)) return false;
      return true;
    });
  }, [patients, matchFilters, genderFilter, ageMin, ageMax]);

  const selected = patients.find((p) => p.uuid === selectedUuid);
  const canRun = Boolean(selectedUuid) && runTask?.status !== "running" && runTask?.status !== "queued";

  const toggleMatch = (k: MatchKey) => {
    setMatchFilters((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  const activeFilterCount =
    (matchFilters.size < 4 ? 1 : 0) +
    (genderFilter ? 1 : 0) +
    (ageMin ? 1 : 0) +
    (ageMax ? 1 : 0);

  if (collapsed) {
    return (
      <aside className="sidebar-collapsed" aria-label="Sidebar collapsed">
        <button
          type="button"
          className="icon-button"
          onClick={() => onCollapseChange?.(false)}
          title="Open patient roster"
        >
          <Activity size={18} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark">
          <Activity size={20} />
        </div>
        <button
          type="button"
          className="brand-link"
          onClick={onGoOverview}
          title="Back to overview"
          disabled={!onGoOverview}
        >
          <div className="brand-title">CMADS</div>
          <div className="brand-subtitle">Doctor Console</div>
        </button>
        {onCollapseChange ? (
          <button
            type="button"
            className="icon-button"
            onClick={() => onCollapseChange(true)}
            title="Hide patient roster"
            style={{ minHeight: 32, width: 32 }}
          >
            <ChevronLeft size={16} />
          </button>
        ) : null}
      </div>

      <div className="search-row">
        <Search size={16} />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search UUID, name, condition…"
        />
      </div>

      <div className="sidebar-actions">
        <button
          className={`icon-button ${activeFilterCount ? "icon-button-active" : ""}`}
          type="button"
          onClick={() => setFilterPanelOpen((s) => !s)}
          title="Toggle filters"
        >
          <Filter size={15} />
          {activeFilterCount ? <span className="filter-dot" /> : null}
        </button>
        <button className="icon-button" type="button" onClick={onRefresh} title="Refresh">
          <RefreshCw size={16} />
        </button>
        <button className="run-button" type="button" onClick={onRun} disabled={!canRun}>
          <Play size={15} />
          Run
        </button>
      </div>

      {filterPanelOpen ? (
        <div className="filter-panel">
          <div className="filter-section">
            <div className="field-label">Match status</div>
            <div className="filter-chips">
              {MATCH_OPTIONS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  className={`filter-chip filter-chip-${key.toLowerCase()} ${matchFilters.has(key) ? "active" : ""}`}
                  onClick={() => toggleMatch(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-section">
            <div className="field-label">Gender</div>
            <div className="filter-chips">
              {(["", "M", "F"] as const).map((g) => (
                <button
                  key={g || "all"}
                  type="button"
                  className={`filter-chip ${genderFilter === g ? "active" : ""}`}
                  onClick={() => setGenderFilter(g)}
                >
                  {g === "" ? "All" : g === "M" ? "Male" : "Female"}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-section">
            <div className="field-label">Age range</div>
            <div className="filter-range">
              <input
                type="number"
                placeholder="Min"
                value={ageMin}
                onChange={(e) => setAgeMin(e.target.value)}
                min={0}
                max={120}
              />
              <span style={{ color: "var(--ink-muted)", fontFamily: "JetBrains Mono, monospace" }}>—</span>
              <input
                type="number"
                placeholder="Max"
                value={ageMax}
                onChange={(e) => setAgeMax(e.target.value)}
                min={0}
                max={120}
              />
            </div>
          </div>

          {activeFilterCount > 0 ? (
            <button
              type="button"
              className="ghost-button"
              style={{ marginTop: "0.4rem", justifyContent: "flex-start" }}
              onClick={() => {
                setMatchFilters(new Set(["DIRECT", "INDIRECT", "MISS", "NORUN"]));
                setGenderFilter("");
                setAgeMin("");
                setAgeMax("");
              }}
            >
              Clear filters
            </button>
          ) : null}
        </div>
      ) : null}

      {runTask && (
        <div className={`run-status status-${runTask.status}`}>
          Live run: {runTask.status}
          {runTask.error ? <span>{runTask.error}</span> : null}
        </div>
      )}

      <div className="patient-count">
        {loading
          ? "Loading patients…"
          : `${filtered.length} of ${patients.length} patients`}
      </div>

      <div className="patient-list">
        {filtered.map((patient) => (
          <button
            key={patient.uuid}
            data-patient-uuid={patient.uuid}
            data-demo-anchor="patient-row"
            className={`patient-row ${patient.uuid === selectedUuid ? "selected" : ""}`}
            type="button"
            onClick={() => onSelectPatient(patient.uuid)}
          >
            <span className="patient-main">
              <span className="mono">
                {patient.uuid.slice(0, 12)}
                {patient.reviewed ? (
                  <span
                    className={`reviewed-dot reviewed-${patient.agreement ?? "uncertain"}`}
                    title={`Reviewed: ${patient.agreement ?? "uncertain"}`}
                  />
                ) : null}
              </span>
              <span>
                {patient.age ?? "?"}y {patient.gender ?? ""} {patient.race ?? ""}
              </span>
              {patient.primaryDiagnosis ? (
                <span style={{ fontSize: "0.72rem", color: "var(--ink-muted)" }}>
                  {patient.primaryDiagnosis.slice(0, 32)}
                </span>
              ) : null}
            </span>
            <span className={`match-pill match-${(patient.matchType || "none").toLowerCase()}`}>
              {patient.hasRun ? patient.matchType || "run" : "no run"}
            </span>
          </button>
        ))}
        {!loading && filtered.length === 0 ? (
          <div className="empty-state compact">No patients match the current filters.</div>
        ) : null}
      </div>

      {selected && (
        <div className="sidebar-footer">
          <div className="footer-label">Selected primary</div>
          <div>{selected.primaryDiagnosis || "No saved diagnosis"}</div>
        </div>
      )}
    </aside>
  );
}

import { useMemo, useState } from "react";
import { Activity, ChevronLeft, Filter, Play, RefreshCw, Search } from "lucide-react";
import type { PatientListItem, RunTask } from "../types";
import { matchGlyph } from "../lib/matchType";
import { useUrlState } from "../useUrlState";

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
  /** Optional — only Doctor (runtime) mode passes a handler; researcher mode
   *  hides the run button since researchers never trigger live patient runs. */
  onRun?: () => void;
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
  // Doctor (runtime) mode shows the "Run" button — in that mode the browser
  // defaults to NO-RUN patients only so the doctor picks from cases the
  // system hasn't seen yet. Researcher mode defaults to all match types.
  const isRuntime = Boolean(onRun);
  const defaultMatchKey = isRuntime ? "NORUN" : "DIRECT,INDIRECT,MISS,NORUN";

  // Filter state is mirrored into the URL so PatientBrowser deep-links
  // survive a refresh and the user can share a filtered view by URL.
  // Keys: mt=DIRECT,INDIRECT  g=M|F  ageMin=  ageMax=
  const [matchParam, setMatchParam] = useUrlState("mt", defaultMatchKey, { replace: true });
  const [genderFilter, setGenderFilterRaw] = useUrlState("g", "", { replace: true });
  const [ageMin, setAgeMin] = useUrlState("ageMin", "", { replace: true });
  const [ageMax, setAgeMax] = useUrlState("ageMax", "", { replace: true });
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);

  // Adapt URL string ↔ Set<MatchKey> at the boundaries; the rest of the
  // component continues to think in terms of a Set.
  const matchFilters: Set<MatchKey> = useMemo(() => {
    const valid: MatchKey[] = ["DIRECT", "INDIRECT", "MISS", "NORUN"];
    const keys = matchParam.split(",").map((s) => s.trim().toUpperCase() as MatchKey).filter((k) => valid.includes(k));
    return new Set(keys);
  }, [matchParam]);
  const setMatchFilters = (next: Set<MatchKey>) => {
    setMatchParam(Array.from(next).join(","));
  };
  const setGenderFilter = (g: "" | "M" | "F") => setGenderFilterRaw(g);

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
    const next = new Set(matchFilters);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setMatchFilters(next);
  };

  // A match filter is "active" only when it deviates from the mode-default
  // (Doctor → NORUN only; Researcher → all four). Otherwise the filter dot
  // would always be lit in Doctor mode just because we default-filter to NORUN.
  const defaultMatchSize = isRuntime ? 1 : 4;
  const matchFilterIsActive = matchFilters.size !== defaultMatchSize
    || (isRuntime && !matchFilters.has("NORUN"));
  const activeFilterCount =
    (matchFilterIsActive ? 1 : 0) +
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
          aria-label="Open patient roster"
        >
          <Activity size={18} aria-hidden />
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
            className="icon-button icon-button--sm"
            onClick={() => onCollapseChange(true)}
            title="Hide patient roster"
            aria-label="Hide patient roster"
          >
            <ChevronLeft size={16} aria-hidden />
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
          aria-label={activeFilterCount ? `Filters (${activeFilterCount} active)` : "Toggle filters"}
          aria-expanded={filterPanelOpen}
        >
          <Filter size={15} aria-hidden />
          {activeFilterCount ? <span className="filter-dot" aria-hidden /> : null}
        </button>
        <button
          className="icon-button"
          type="button"
          onClick={onRefresh}
          title="Refresh patient list"
          aria-label="Refresh patient list"
        >
          <RefreshCw size={16} aria-hidden />
        </button>
        {onRun ? (
          <button className="run-button" type="button" onClick={onRun} disabled={!canRun}>
            <Play size={15} />
            Run
          </button>
        ) : null}
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
                setMatchFilters(
                  new Set(isRuntime ? ["NORUN"] : ["DIRECT", "INDIRECT", "MISS", "NORUN"]),
                );
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
            {(() => {
              const mt = patient.hasRun ? (patient.matchType || "") : "NORUN";
              const cls = patient.hasRun ? (mt.toLowerCase() || "none") : "none";
              const Glyph = matchGlyph(mt);
              return (
                <span className={`match-pill match-${cls}`}>
                  <Glyph size={11} strokeWidth={2} aria-hidden />
                  {patient.hasRun ? patient.matchType || "run" : "no run"}
                </span>
              );
            })()}
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

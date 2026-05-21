import { useMemo } from "react";
import { ChartLine, Home, Layers, Microscope, ScatterChart, Users } from "lucide-react";
import type { ReactNode } from "react";
import { ModeSwitcher } from "./ModeSwitcher";
import { PatientExplorer } from "./PatientExplorer";
import { StatsOverview } from "./StatsOverview";
import { MemoryAbTab } from "./MemoryAbTab";
import { ModelComparisonTab } from "./ModelComparisonTab";
import { MasVsSingleLlmTab } from "./MasVsSingleLlmTab";
import { useUrlState } from "../useUrlState";
import type { Mode } from "../useMode";

type Props = {
  mode: Mode;
  onModeChange: (next: Mode) => void;
  onHome: () => void;
};

type ResearcherTabId =
  | "overview"
  | "memory-ab"
  | "model"
  | "mas-vs-single"
  | "patients";

type TabDef = {
  id: ResearcherTabId;
  label: string;
  hint: string;
  icon: ReactNode;
  render: () => ReactNode;
};

/**
 * Researcher workspace. Tab strip across the top:
 *   Overview · Memory A/B · Model · MAS vs single-LLM · Patients
 *
 * Tab selection is URL-driven via ?tab= so views are deep-linkable.
 */
export function ResearcherMode({ mode, onModeChange, onHome }: Props) {
  const [activeUrl, setActive] = useUrlState("tab", "overview");
  const active = (activeUrl || "overview") as ResearcherTabId;

  const tabs: TabDef[] = useMemo(() => [
    {
      id: "overview",
      label: "Overview",
      hint: "System accuracy across cohorts at a glance.",
      icon: <ChartLine size={14} strokeWidth={1.7} />,
      render: () => <StatsOverview onOpenPatient={(uuid) => openInPatients(uuid)} />,
    },
    {
      id: "mas-vs-single",
      label: "MAS vs single-LLM",
      hint: "Does coordinating seven agents beat a single LLM call? Same patients on both sides.",
      icon: <Microscope size={14} strokeWidth={1.7} />,
      render: () => <MasVsSingleLlmTab onOpenPatient={(uuid) => openInPatients(uuid)} />,
    },
    {
      id: "model",
      label: "Model",
      hint: "Controlled 20-patient comparison: GPT-OSS 120B vs Med42 70B on the same cohort, both with memory off.",
      icon: <ScatterChart size={14} strokeWidth={1.7} />,
      render: () => <ModelComparisonTab onOpenPatient={(uuid) => openInPatients(uuid)} />,
    },
    {
      id: "memory-ab",
      label: "Memory A/B",
      hint: "Paired-160 multi-level memory vs single-level with exact McNemar.",
      icon: <Layers size={14} strokeWidth={1.7} />,
      render: () => <MemoryAbTab onOpenPatient={(uuid) => openInPatients(uuid)} />,
    },
    {
      id: "patients",
      label: "Patients",
      hint: "Per-patient drill-down — agent narratives, differential, treatment plan.",
      icon: <Users size={14} strokeWidth={1.7} />,
      render: () => <PatientExplorer mode="researcher" />,
    },
  ], []);

  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];

  function openInPatients(uuid: string) {
    // Deep-link into the Patients tab with the chosen UUID preselected.
    const params = new URLSearchParams(window.location.search);
    params.set("tab", "patients");
    params.set("p", uuid);
    params.delete("a");
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.pushState(null, "", next);
    setActive("patients");
  }

  if (active === "patients") {
    return (
      <PatientExplorer
        mode="researcher"
        ribbon={
          <ResearcherRibbon
            tabs={tabs}
            active={active}
            onSelect={(id) => setActive(id)}
            mode={mode}
            onModeChange={onModeChange}
            onHome={onHome}
          />
        }
      />
    );
  }

  return (
    <div className="researcher-mode">
      <ResearcherRibbon
        tabs={tabs}
        active={active}
        onSelect={(id) => setActive(id)}
        mode={mode}
        onModeChange={onModeChange}
        onHome={onHome}
      />
      <main className="researcher-mode__workspace">
        <header className="researcher-mode__head">
          <div className="eyebrow">Researcher · {activeTab.label}</div>
          <h1>{activeTab.label === "Overview" ? "System performance" : activeTab.label}</h1>
          <p className="researcher-mode__hint">{activeTab.hint}</p>
        </header>
        {activeTab.render()}
      </main>
    </div>
  );
}

function ResearcherRibbon({
  tabs, active, onSelect, mode, onModeChange, onHome,
}: {
  tabs: TabDef[];
  active: ResearcherTabId;
  onSelect: (id: ResearcherTabId) => void;
  mode: Mode;
  onModeChange: (next: Mode) => void;
  onHome: () => void;
}) {
  return (
    <div className="mode-ribbon mode-ribbon--researcher">
      <button type="button" className="mode-ribbon__brand mode-ribbon__brand--button" onClick={onHome} title="Back to home">
        <Home size={15} strokeWidth={1.7} />
        <strong>Researcher</strong>
        <span className="mono mode-ribbon__sep">·</span>
        <span className="mono">statistics &amp; comparisons</span>
      </button>
      <nav className="researcher-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`researcher-tab${tab.id === active ? " is-active" : ""}`}
            onClick={() => onSelect(tab.id)}
            title={tab.hint}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
      <ModeSwitcher mode={mode} onChange={onModeChange} />
    </div>
  );
}

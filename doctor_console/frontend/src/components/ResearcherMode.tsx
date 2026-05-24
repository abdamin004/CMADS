import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChartLine,
  ChevronDown,
  FlaskConical,
  FolderSearch,
  History,
  Home,
  Layers,
  Microscope,
  Scale,
  ScatterChart,
  Users,
} from "lucide-react";
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

const COMPARISON_IDS: ResearcherTabId[] = ["mas-vs-single", "model", "memory-ab"];

/**
 * Researcher workspace. Top ribbon collapses the five flat tabs of the
 * previous design into three controls:
 *
 *   Overview              · flat tab — single landing
 *   Comparisons ▼         · dropdown of MAS-vs-single / Model / Memory A/B
 *   Patients ▼            · dropdown of Explore / Create / My test patients
 *
 * Each dropdown's trigger lights up when any of its sub-items is active,
 * so the user always knows which group they are inside. The underlying
 * URL contract (?tab=…) is unchanged — comparison tabs still own their
 * own ``tab`` value and the Patients tab still owns ``view=`` for its
 * sub-flow — so deep-links from the old ribbon keep working.
 */
export function ResearcherMode({ mode, onModeChange, onHome }: Props) {
  const [activeUrl, setActive] = useUrlState("tab", "overview");
  const active = (activeUrl || "overview") as ResearcherTabId;
  // Subscribe to ?view= so the Patients-dropdown active-item indicator
  // re-renders when the user switches between Explore / Create / My
  // test patients (or anywhere else that calls setView).
  const [viewUrl, setViewUrl] = useUrlState("view", "");

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
    params.delete("view"); // ensure we land on explore, not create / my-tests
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.pushState(null, "", next);
    window.dispatchEvent(new PopStateEvent("popstate"));
    setActive("patients");
  }

  /** Patients-dropdown picks: set tab=patients and view=<sub>, then announce. */
  function openPatientsView(view: "" | "create" | "my-tests") {
    // Drop the patient/agent deep-link params; setting them via the
    // dedicated hooks below keeps every useUrlState consumer in sync.
    const params = new URLSearchParams(window.location.search);
    params.delete("p");
    params.delete("a");
    const next = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
    window.history.replaceState(null, "", next);
    setActive("patients");
    setViewUrl(view);
  }

  const ribbon = (
    <ResearcherRibbon
      tabs={tabs}
      active={active}
      patientsView={viewUrl}
      onSelect={(id) => setActive(id)}
      onOpenPatientsView={openPatientsView}
      mode={mode}
      onModeChange={onModeChange}
      onHome={onHome}
    />
  );

  if (active === "patients") {
    return <PatientExplorer mode="researcher" ribbon={ribbon} />;
  }

  return (
    <div className="researcher-mode">
      {ribbon}
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

// ────────────────────────────────────────────────────────────────────────────
// Ribbon — Overview · Comparisons ▼ · Patients ▼ · (mode switcher)
// ────────────────────────────────────────────────────────────────────────────

function ResearcherRibbon({
  tabs,
  active,
  patientsView,
  onSelect,
  onOpenPatientsView,
  mode,
  onModeChange,
  onHome,
}: {
  tabs: TabDef[];
  active: ResearcherTabId;
  patientsView: string;
  onSelect: (id: ResearcherTabId) => void;
  onOpenPatientsView: (view: "" | "create" | "my-tests") => void;
  mode: Mode;
  onModeChange: (next: Mode) => void;
  onHome: () => void;
}) {
  const overview = tabs.find((t) => t.id === "overview")!;
  const comparisonItems = COMPARISON_IDS.map((id) => tabs.find((t) => t.id === id)!).filter(Boolean);

  // The Patients dropdown's "active sub-item" is the current ?view= value
  // when the Patients tab is active. ``viewUrl`` flows in from the
  // useUrlState hook in ResearcherMode so this re-renders on every
  // sub-view switch — without that, the active dot would freeze on
  // whichever sub-view the ribbon was first rendered for.
  const patientsActiveChild = (() => {
    if (active !== "patients") return null;
    if (patientsView === "create" || patientsView === "my-tests") return patientsView;
    return "explore";
  })();

  return (
    <div className="mode-ribbon mode-ribbon--researcher">
      <button type="button" className="mode-ribbon__brand mode-ribbon__brand--button" onClick={onHome} title="Back to home">
        <Home size={15} strokeWidth={1.7} />
        <strong>Researcher</strong>
        <span className="mono mode-ribbon__sep">·</span>
        <span className="mono">statistics &amp; comparisons</span>
      </button>

      <nav className="researcher-tabs">
        {/* Flat tab — Overview */}
        <button
          type="button"
          className={`researcher-tab${active === "overview" ? " is-active" : ""}`}
          onClick={() => onSelect("overview")}
          title={overview.hint}
        >
          {overview.icon}
          <span>{overview.label}</span>
        </button>

        {/* Dropdown — Comparisons */}
        <RibbonDropdown
          label="Comparisons"
          icon={<Scale size={14} strokeWidth={1.7} />}
          isActive={COMPARISON_IDS.includes(active)}
          activeChildId={COMPARISON_IDS.includes(active) ? active : null}
          items={comparisonItems.map((t) => ({
            id: t.id,
            label: t.label,
            hint: t.hint,
            icon: t.icon,
            onClick: () => onSelect(t.id),
          }))}
        />

        {/* Dropdown — Patients */}
        <RibbonDropdown
          label="Patients"
          icon={<Users size={14} strokeWidth={1.7} />}
          isActive={active === "patients"}
          activeChildId={patientsActiveChild}
          items={[
            {
              id: "explore",
              label: "Explore patients",
              hint: "Browse the cohort roster — read every agent's reasoning for any past patient.",
              icon: <FolderSearch size={14} strokeWidth={1.7} />,
              onClick: () => onOpenPatientsView(""),
            },
            {
              id: "create",
              label: "Create patients",
              hint: "Clone a cohort patient and edit, or build a chart from scratch.",
              icon: <FlaskConical size={14} strokeWidth={1.7} />,
              onClick: () => onOpenPatientsView("create"),
            },
            {
              id: "my-tests",
              label: "My test patients",
              hint: "Custom patients you've built and runs you've launched.",
              icon: <History size={14} strokeWidth={1.7} />,
              onClick: () => onOpenPatientsView("my-tests"),
            },
          ]}
        />
      </nav>

      <ModeSwitcher mode={mode} onChange={onModeChange} />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Reusable dropdown for the ribbon. Anchored to its trigger, dismissed by
// click-outside and Escape. Trigger lights up when any child is active.
// ────────────────────────────────────────────────────────────────────────────

type DropdownItem = {
  id: string;
  label: string;
  hint: string;
  icon: ReactNode;
  onClick: () => void;
};

/**
 * Production-grade ribbon dropdown — accessible (ARIA menu semantics,
 * keyboard navigation, focus restoration), portalled to document.body so
 * the menu escapes any ancestor's overflow (the researcher ribbon clips
 * its overflow-y to keep the tab strip clean), repositioned on scroll
 * and resize, and animated with a single restrained Framer Motion fade
 * + lift. Highlight follows both mouse hover and arrow keys.
 */
function RibbonDropdown({
  label,
  icon,
  isActive,
  activeChildId,
  items,
}: {
  label: string;
  icon: ReactNode;
  isActive: boolean;
  activeChildId: string | null;
  items: DropdownItem[];
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // Anchor the menu to the trigger. Runs synchronously after layout so the
  // first paint of the menu is already in the right spot.
  const recalc = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const MIN_W = 300;
    setPos({
      left: rect.left,
      top: rect.bottom + 8,
      width: Math.max(rect.width, MIN_W),
    });
  };
  useLayoutEffect(() => {
    if (open) recalc();
  }, [open]);

  // Seed the keyboard highlight with the currently-active sub-item when
  // the menu opens so the user can press Enter to re-confirm or arrows
  // to move from a known position.
  useEffect(() => {
    if (!open) {
      setHighlightIdx(-1);
      return;
    }
    const seed = items.findIndex((it) => it.id === activeChildId);
    setHighlightIdx(seed >= 0 ? seed : 0);
  }, [open, items, activeChildId]);

  // Global listeners when open: click-outside, Escape, arrow-key nav,
  // and reposition on scroll/resize so the portalled menu tracks its
  // anchor.
  useEffect(() => {
    if (!open) return;
    const onScroll = () => recalc();
    const onResize = () => recalc();
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightIdx((i) => (i + 1) % items.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightIdx((i) => (i - 1 + items.length) % items.length);
        return;
      }
      if (e.key === "Home") {
        e.preventDefault();
        setHighlightIdx(0);
        return;
      }
      if (e.key === "End") {
        e.preventDefault();
        setHighlightIdx(items.length - 1);
        return;
      }
      if (e.key === "Enter" || e.key === " ") {
        if (highlightIdx < 0) return;
        e.preventDefault();
        items[highlightIdx].onClick();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    window.addEventListener("mousedown", onMouseDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, items, highlightIdx]);

  // Move DOM focus to the highlighted item so screen readers and the
  // visible focus ring stay in lockstep.
  useEffect(() => {
    if (!open) return;
    if (highlightIdx < 0) return;
    itemRefs.current[highlightIdx]?.focus();
  }, [open, highlightIdx]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`researcher-tab ribbon-dd__trigger${isActive ? " is-active" : ""}${open ? " is-open" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {icon}
        <span>{label}</span>
        <ChevronDown
          size={12}
          strokeWidth={2}
          className={`ribbon-dd__caret${open ? " is-open" : ""}`}
        />
      </button>
      {createPortal(
        <AnimatePresence>
          {open && pos ? (
            <>
              {/* Backdrop scrim — recedes the page behind the menu so the
                  open dropdown reads as a proper surface, not a floating
                  tag on top of full-opacity content. A click on the
                  scrim closes the menu (the mousedown listener already
                  handles this, but the scrim makes the dismiss target
                  explicit). */}
              <motion.div
                className="ribbon-dd__scrim"
                aria-hidden
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              />
              <motion.div
                ref={menuRef}
                className="ribbon-dd__menu"
                role="menu"
                aria-label={label}
                style={{ left: pos.left, top: pos.top, minWidth: pos.width }}
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.98 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
              >
              <span className="ribbon-dd__menu-rule" aria-hidden />
              {items.map((item, idx) => {
                const isActiveChild = item.id === activeChildId;
                const isHighlighted = idx === highlightIdx;
                return (
                  <button
                    key={item.id}
                    ref={(el) => { itemRefs.current[idx] = el; }}
                    type="button"
                    role="menuitem"
                    tabIndex={isHighlighted ? 0 : -1}
                    className={`ribbon-dd__item${isActiveChild ? " is-active" : ""}${isHighlighted ? " is-highlighted" : ""}`}
                    onMouseEnter={() => setHighlightIdx(idx)}
                    onClick={() => {
                      item.onClick();
                      setOpen(false);
                      triggerRef.current?.focus();
                    }}
                  >
                    <span className="ribbon-dd__item-icon" aria-hidden>
                      {item.icon}
                    </span>
                    <span className="ribbon-dd__item-body">
                      <span className="ribbon-dd__item-label">
                        {item.label}
                        {isActiveChild ? (
                          <span className="ribbon-dd__item-dot" aria-hidden />
                        ) : null}
                      </span>
                      <span className="ribbon-dd__item-hint">{item.hint}</span>
                    </span>
                  </button>
                );
              })}
              </motion.div>
            </>
          ) : null}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}

import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { springSnappy } from "../lib/motion";

export type TabApi = {
  /** Switch the tab strip programmatically — used for "see full
   *  differential" buttons or clickable cards that jump elsewhere. */
  setActive: (id: string) => void;
};

export type TabDef = {
  id: string;
  label: string;
  hint?: string;
  badge?: string | number;
  render: (api: TabApi) => ReactNode;
};

type Props = {
  tabs: TabDef[];
  defaultActive?: string;
  /** Persist active tab across patient changes when true. */
  preserveAcrossPatients?: boolean;
};

/**
 * Tabbed patient detail. Renders a horizontal tab strip with an animated
 * underline indicator (shared layoutId), and a fade/translate transition
 * for the active panel body. One panel visible at a time — addresses the
 * doctor's feedback that the old stacked layout dumped too much detail
 * onto the page at once.
 */
export function PatientDetailTabs({ tabs, defaultActive }: Props) {
  const [active, setActive] = useState<string>(defaultActive ?? tabs[0]?.id ?? "");
  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];
  const stripRef = useRef<HTMLDivElement | null>(null);
  const userInitiatedRef = useRef(false);

  // After a tab change initiated by a user click, scroll the strip into
  // view so the new body appears at the top of the visible area. We skip
  // the initial mount (userInitiatedRef stays false until the first click)
  // so loading a patient with a default tab doesn't yank the page.
  useEffect(() => {
    if (!userInitiatedRef.current) return;
    const el = stripRef.current;
    if (!el) return;
    // Wait a frame so the new body has rendered before scrolling.
    requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [active]);

  const handleSelect = (id: string) => {
    userInitiatedRef.current = true;
    setActive(id);
  };

  // Keyboard navigation per WAI-ARIA tabs pattern: Left/Right move and
  // activate, Home/End jump to first/last. We use roving tabindex on the
  // <button> elements via tabIndex below.
  const handleTabKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const ids = tabs.map((t) => t.id);
    const idx = ids.indexOf(active);
    let next: number;
    if (e.key === "ArrowRight")      next = (idx + 1) % ids.length;
    else if (e.key === "ArrowLeft")  next = (idx - 1 + ids.length) % ids.length;
    else if (e.key === "Home")       next = 0;
    else                              next = ids.length - 1;
    handleSelect(ids[next]);
    // Move focus to the newly-active tab so the user can keep pressing arrows.
    requestAnimationFrame(() => {
      const root = stripRef.current;
      if (!root) return;
      const btn = root.querySelector<HTMLButtonElement>(`[data-tab-id="${ids[next]}"]`);
      btn?.focus();
    });
  };

  return (
    <section className="patient-tabs" ref={stripRef}>
      <div
        className="patient-tabs__strip"
        role="tablist"
        aria-label="Patient detail sections"
        data-demo-anchor="patient-tabs"
        onKeyDown={handleTabKey}
      >
        {tabs.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={`patient-tab-panel-${t.id}`}
              id={`patient-tab-${t.id}`}
              tabIndex={isActive ? 0 : -1}
              data-active={isActive ? "true" : undefined}
              data-tab-id={t.id}
              data-demo-anchor={`tab-${t.id}`}
              className="patient-tabs__tab"
              onClick={() => handleSelect(t.id)}
            >
              <span className="patient-tabs__label">{t.label}</span>
              {t.badge !== undefined && t.badge !== "" ? (
                <span className="patient-tabs__badge">{t.badge}</span>
              ) : null}
              {isActive ? (
                <motion.span
                  className="patient-tabs__indicator"
                  layoutId="patientTabsIndicator"
                  transition={springSnappy}
                />
              ) : null}
            </button>
          );
        })}
      </div>

      {activeTab?.hint ? (
        <div className="patient-tabs__hint">{activeTab.hint}</div>
      ) : null}

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={active}
          role="tabpanel"
          id={`patient-tab-panel-${active}`}
          aria-labelledby={`patient-tab-${active}`}
          tabIndex={0}
          className="patient-tabs__body"
          data-demo-anchor={`tab-body-${active}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
        >
          {activeTab?.render({ setActive: handleSelect })}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

import { useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";

export type TabDef = {
  id: string;
  label: string;
  hint?: string;
  badge?: string | number;
  render: () => ReactNode;
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

  return (
    <section className="patient-tabs">
      <div
        className="patient-tabs__strip"
        role="tablist"
        aria-label="Patient detail sections"
        data-demo-anchor="patient-tabs"
      >
        {tabs.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              data-active={isActive ? "true" : undefined}
              data-tab-id={t.id}
              data-demo-anchor={`tab-${t.id}`}
              className="patient-tabs__tab"
              onClick={() => setActive(t.id)}
            >
              <span className="patient-tabs__label">{t.label}</span>
              {t.badge !== undefined && t.badge !== "" ? (
                <span className="patient-tabs__badge">{t.badge}</span>
              ) : null}
              {isActive ? (
                <motion.span
                  className="patient-tabs__indicator"
                  layoutId="patientTabsIndicator"
                  transition={{ type: "spring", stiffness: 420, damping: 38 }}
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
          className="patient-tabs__body"
          data-demo-anchor={`tab-body-${active}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.22, ease: [0.22, 0.65, 0.3, 0.96] }}
        >
          {activeTab?.render()}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

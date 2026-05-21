import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

type Props = {
  /** Title shown in the summary row. */
  title: ReactNode;
  /** Optional supplementary info displayed to the right of the title. */
  badge?: ReactNode;
  /** Optional one-line hint below the summary when closed. */
  hint?: ReactNode;
  /** Default open state. */
  defaultOpen?: boolean;
  /** Visual variant: 'default' subtle, 'callout' tinted for highlights. */
  tone?: "default" | "callout" | "muted";
  /** Stable DOM attribute for Playwright/demo targeting. */
  demoAnchor?: string;
  children: ReactNode;
};

/**
 * A single accessible collapse-disclosure. Refined editorial aesthetic:
 * thin border, generous padding, animated chevron + height. Used by
 * AgentInspector for highlights, narrative sections, and raw output.
 */
export function Disclosure({
  title,
  badge,
  hint,
  defaultOpen = false,
  tone = "default",
  demoAnchor,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      className={`disclosure disclosure--${tone}`}
      data-open={open ? "true" : "false"}
      data-demo-anchor={demoAnchor}
    >
      <button
        type="button"
        className="disclosure__summary"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronDown
          size={15}
          className="disclosure__chevron"
          style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}
        />
        <span className="disclosure__title">{title}</span>
        {badge !== undefined && badge !== "" && badge !== 0 ? (
          <span className="disclosure__badge">{badge}</span>
        ) : null}
      </button>
      {!open && hint ? (
        <div className="disclosure__hint">{hint}</div>
      ) : null}
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="content"
            className="disclosure__content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 0.65, 0.3, 0.96] }}
          >
            <div className="disclosure__body">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

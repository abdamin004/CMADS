import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

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
          aria-hidden
        />
        <span className="disclosure__title">{title}</span>
        {badge !== undefined && badge !== "" && badge !== 0 ? (
          <span className="disclosure__badge">{badge}</span>
        ) : null}
      </button>
      {!open && hint ? (
        <div className="disclosure__hint">{hint}</div>
      ) : null}
      {/* The expand/collapse uses the CSS grid-template-rows 0fr→1fr trick
          (driven by [data-open]) instead of animating `height: auto`. That
          keeps the animation off the layout properties Framer Motion was
          previously reflowing on each frame. */}
      <div className="disclosure__content" aria-hidden={!open}>
        <div className="disclosure__body">{children}</div>
      </div>
    </div>
  );
}

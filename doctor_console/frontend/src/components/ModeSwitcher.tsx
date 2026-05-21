import { ChartLine, Stethoscope } from "lucide-react";
import type { Mode } from "../useMode";

type Props = {
  mode: Mode;
  onChange: (next: Mode) => void;
};

/**
 * Compact pill switcher for the topbar. Visible in both modes so the user can
 * flip between Doctor runtime and Researcher statistics without going back to
 * the splash. Keyboard-accessible (radio-group semantics).
 */
export function ModeSwitcher({ mode, onChange }: Props) {
  return (
    <div className="mode-switcher" role="radiogroup" aria-label="Workspace mode">
      <button
        type="button"
        role="radio"
        aria-checked={mode === "runtime"}
        className={`mode-switcher__chip${mode === "runtime" ? " is-active" : ""}`}
        onClick={() => onChange("runtime")}
      >
        <Stethoscope size={14} strokeWidth={1.7} />
        <span>Doctor</span>
        <span className="mode-switcher__sub mono">assistant</span>
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={mode === "researcher"}
        className={`mode-switcher__chip${mode === "researcher" ? " is-active" : ""}`}
        onClick={() => onChange("researcher")}
      >
        <ChartLine size={14} strokeWidth={1.7} />
        <span>Researcher</span>
        <span className="mode-switcher__sub mono">statistics</span>
      </button>
    </div>
  );
}

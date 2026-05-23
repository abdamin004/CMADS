import { useCallback } from "react";
import { useUrlState } from "./useUrlState";

/**
 * Two-mode entry: Doctor runtime vs Researcher statistics.
 *
 * The ModeChooser splash is shown every time the user lands on the bare
 * URL (no ?mode= param). We deliberately do NOT remember the previous
 * choice — the home page is the chooser, the URL is the source of truth.
 * Shareable links with ?mode=runtime or ?mode=researcher still take the
 * user directly to that mode.
 */
export type Mode = "runtime" | "researcher" | "tester";

export function useMode(): {
  mode: Mode | undefined;
  setMode: (next: Mode) => void;
  clearMode: () => void;
} {
  // replace=false so picking a mode pushes a new history entry; pressing
  // Back from a mode returns the user to the chooser.
  const [urlMode, setUrlMode] = useUrlState("mode", "");

  const setMode = useCallback((next: Mode) => {
    // Picking a mode from the chooser (or via the switcher) is a fresh
    // entry point. Clear any leftover ?tab=, ?p=, ?a= from the previous
    // mode so the user always lands on the natural starting view for the
    // chosen workspace (Overview for Researcher, hero for Doctor).
    const params = new URLSearchParams(window.location.search);
    ["tab", "p", "a", "r"].forEach((k) => params.delete(k));
    params.set("mode", next);
    const url = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
    window.history.pushState(null, "", url);
    // Trigger React updates for any other useUrlState subscribers.
    window.dispatchEvent(new PopStateEvent("popstate"));
    setUrlMode(next);
  }, [setUrlMode]);

  const clearMode = useCallback(() => {
    setUrlMode("");
  }, [setUrlMode]);

  const mode: Mode | undefined =
    urlMode === "runtime" || urlMode === "researcher" || urlMode === "tester"
      ? urlMode
      : undefined;

  return { mode, setMode, clearMode };
}

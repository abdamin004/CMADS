import { useEffect, useState } from "react";

/**
 * Two-way bind a `URLSearchParams` key to React state.
 *
 * - Initial value: read from the URL on mount, falling back to `initial`.
 * - On state change: pushes a new history entry with the updated query string.
 * - On `popstate` (back/forward): re-reads the URL and updates state.
 *
 * Designed to be drop-in for `useState<string>`. Multiple instances on the same
 * page share the URL safely because each one only touches its own key.
 */
export function useUrlState(
  key: string,
  initial: string,
  options: { replace?: boolean } = {}
): [string, (value: string) => void] {
  const replace = options.replace ?? false;
  const [value, setValueState] = useState<string>(() => readFromUrl(key, initial));

  useEffect(() => {
    const handler = () => setValueState(readFromUrl(key, initial));
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [key, initial]);

  function setValue(next: string) {
    setValueState(next);
    const params = new URLSearchParams(window.location.search);
    if (next === initial || next === "") {
      params.delete(key);
    } else {
      params.set(key, next);
    }
    const search = params.toString();
    const newUrl = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
    if (replace) {
      window.history.replaceState(null, "", newUrl);
    } else {
      window.history.pushState(null, "", newUrl);
    }
    // Broadcast a popstate so every other useUrlState instance (and
    // any other component subscribing to history changes) re-reads the
    // URL. Without this, only the React component that owns *this*
    // hook re-renders — sibling consumers of the same key (e.g. the
    // ribbon and the explorer both reading "view") stay stale until
    // the user navigates with back/forward.
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  return [value, setValue];
}

function readFromUrl(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const params = new URLSearchParams(window.location.search);
  return params.get(key) ?? fallback;
}

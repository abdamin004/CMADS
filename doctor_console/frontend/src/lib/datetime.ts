/**
 * Date parsing helpers.
 *
 * The backend writes timestamps with Python's `datetime.utcnow().isoformat()`
 * which yields a naïve string like `2026-05-23T22:52:50.373000` — no
 * timezone suffix. JavaScript's `new Date(naiveIso)` then parses such
 * strings as LOCAL time (per the ECMAScript spec for "date-time" without
 * a TZ designator), so the displayed clock is off by the user's UTC
 * offset.
 *
 * `parseBackendDate` normalises that: if the string already carries an
 * explicit offset (Z, +hh:mm, -hh:mm) the parse is unchanged; otherwise
 * the string is treated as UTC (Z appended). Use this everywhere we read
 * a timestamp emitted by the FastAPI backend.
 */
const TZ_RE = /Z|[+-]\d{2}:?\d{2}$/;

export function parseBackendDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const hasTz = TZ_RE.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "3h ago" — local-clock-correct relative string from a backend ISO. */
export function relativeBackend(iso?: string | null): string {
  const d = parseBackendDate(iso);
  if (!d) return "—";
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60)        return `${Math.round(s)}s ago`;
  if (s < 3600)      return `${Math.round(s / 60)}m ago`;
  if (s < 86400)     return `${Math.round(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)}d ago`;
  return `${Math.round(s / (86400 * 7))}w ago`;
}

/** Full local-TZ display, e.g. "May 25, 2026, 4:18 PM". */
export function formatBackendDate(iso?: string | null): string {
  const d = parseBackendDate(iso);
  if (!d) return "—";
  return d.toLocaleString();
}

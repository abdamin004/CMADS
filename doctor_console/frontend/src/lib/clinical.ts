/* Small clinical-display helpers shared by the past-patients + detail
 * views. All UI-only; no external dependencies. */

/** Two-character initials extracted from a UUID for the avatar tile. */
export function initials(uuid: string): string {
  if (!uuid) return "··";
  const cleaned = uuid.replace(/-/g, "");
  return (cleaned[0] + cleaned[Math.min(3, cleaned.length - 1)]).toUpperCase();
}

/** Compact UUID for the secondary chip — first 8 chars. */
export function shortId(uuid: string): string {
  return (uuid || "").slice(0, 8);
}

/** "67F · white" — clinician-readable demographic line. */
export function demoLine(p: {
  age: number | null; gender: string | null; race: string | null;
}): string {
  const head = [
    p.age != null ? `${p.age}${(p.gender ?? "").toUpperCase().charAt(0)}` : (p.gender ?? "Patient"),
  ];
  if (p.race) head.push(p.race);
  return head.join(" · ");
}

/** Full clinician-friendly demographic line for the detail hero. */
export function demoLineLong(p: {
  age: number | null; gender: string | null; race: string | null;
}): string {
  const sex = p.gender === "F" ? "female"
            : p.gender === "M" ? "male"
            : p.gender || "patient";
  const age = p.age != null ? `${p.age}-year-old` : "Adult";
  const parts = [`${age} ${sex}`];
  if (p.race) parts.push(p.race);
  return parts.join(" · ");
}

/** Confidence band class for the small pill — green / amber / rose. */
export function confClass(c: number | null | undefined): string {
  if (c == null) return "is-muted";
  if (c >= 70) return "is-success";
  if (c >= 50) return "is-warning";
  return "is-critical";
}

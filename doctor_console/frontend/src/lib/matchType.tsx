import { CheckCircle2, CircleDashed, XCircle, CircleSlash } from "lucide-react";

export type MatchType = "DIRECT" | "INDIRECT" | "MISS" | "NORUN" | "" | string;

type GlyphProps = { size?: number; strokeWidth?: number };

/**
 * Returns the glyph component paired with a match-type verdict.
 *
 * Match type was previously signalled by color alone (green pill / amber pill
 * / red pill), which fails for colorblind users and on monochrome printouts.
 * A glyph carries the verdict on its own; the color stays as reinforcement.
 */
export function matchGlyph(matchType: MatchType): React.ComponentType<GlyphProps> {
  const mt = String(matchType || "").toUpperCase();
  if (mt === "DIRECT")   return CheckCircle2;
  if (mt === "INDIRECT") return CircleDashed;
  if (mt === "MISS")     return XCircle;
  if (mt === "NORUN")    return CircleSlash;
  return CircleSlash;
}

export function matchLabel(matchType: MatchType): string {
  const mt = String(matchType || "").toUpperCase();
  if (mt === "DIRECT")   return "Direct match";
  if (mt === "INDIRECT") return "Indirect match";
  if (mt === "MISS")     return "Missed";
  if (mt === "NORUN")    return "Not run";
  return "Not evaluated";
}

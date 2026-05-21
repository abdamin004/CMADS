import type { Variants, Transition } from "framer-motion";

/**
 * Shared motion tokens for the doctor console.
 *
 * Single source of truth for the editorial easing curves and stagger
 * timings used across the app, so every cascade reads with the same
 * rhythm. The vocabulary is small on purpose: a page-level cascade
 * container, two child variants (full section and tight list item),
 * and a handful of easing curves keyed to the CSS --ease-* tokens in
 * styles.css.
 *
 * Inspired by the refined motion vocabulary used in Emil Kowalski /
 * Vercel-style interfaces: a single coordinated wave of entrance
 * motion rather than scattered per-component fades.
 */

// ─── Easing curves ────────────────────────────────────────────────
// Mirror the --ease-* tokens declared in styles.css so JS-driven and
// CSS-driven motion share the same feel.
export const easeOut    = [0.23, 1, 0.32, 1]    as const; // enter / hover
export const easeInOut  = [0.77, 0, 0.175, 1]   as const; // layout / morph
export const easeDrawer = [0.32, 0.72, 0, 1]    as const; // drawers, large surfaces

// ─── Cascade container ────────────────────────────────────────────
// Use at the outermost element of a page. Its `visible` state
// orchestrates the rest of the page through staggerChildren —
// children declare their own keyframes via cascadeItem / cascadeRow.
export const cascade: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      // delayChildren gives the page a brief "settle" before the
      // sequence begins so the cascade reads as deliberate, not anxious.
      delayChildren: 0.08,
      staggerChildren: 0.07,
    },
  },
};

// ─── Section item ─────────────────────────────────────────────────
// Each major section / panel on a page (headline block, KPI grid,
// precision card, rank histogram, per-disease table). Rises 14 px
// with a softened ease so the wave feels smooth, not snappy.
export const cascadeItem: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: easeOut },
  },
};

// ─── Tight row item ───────────────────────────────────────────────
// Use for rows inside a list (differential rows, delta-table rows,
// KPI tiles when the tile itself is the staggered child). Rises
// 8 px with a quicker duration so a list of N items doesn't take
// forever to fully resolve.
export const cascadeRow: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: easeOut },
  },
};

// ─── Inner-list orchestrator ──────────────────────────────────────
// For tight inner lists nested inside a cascadeItem. Tighter stagger
// so the inner sequence reads as one beat of the outer cascade rather
// than a second separate wave.
export const innerList: Variants = {
  hidden: {},
  visible: {
    transition: {
      delayChildren: 0.04,
      staggerChildren: 0.035,
    },
  },
};

// ─── List container ───────────────────────────────────────────────
// Combines cascadeItem (rise as a section) with innerList (stagger
// children). Use on a container that itself participates in the
// page cascade AND holds staggered children (KPI grid, differential
// list, delta-table tbody).
export const cascadeListContainer: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: easeOut,
      delayChildren: 0.06,
      staggerChildren: 0.04,
    },
  },
};

// ─── Soft page enter ──────────────────────────────────────────────
// When a top-level route mounts (e.g. arriving at a tab). Slight
// upward slide so the content settles in rather than appearing.
export const pageEnter: Transition = {
  duration: 0.45,
  ease: easeOut,
};

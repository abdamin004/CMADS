/**
 * Seven crew personas, each rendered as a polished SVG robot bust with
 * mouse-tracking eyes.
 *
 * Each robot:
 *   • Has its own SVG ref so it computes the look-direction relative
 *     to its own bounding box (each robot looks toward the cursor from
 *     where it sits on the page).
 *   • Uses Framer Motion springs so the eye motion is smoothly damped
 *     instead of snapping with every mousemove event.
 *   • Idle-floats; intensified when `active` is true.
 *
 * The seven silhouettes stay distinct (filing cabinet, test tube,
 * humanoid, angular, refined, blocky, capsule) so the crew reads as a
 * team of specialists rather than seven recolourings of one model.
 */
import { useEffect, useId, useRef } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  type MotionValue,
} from "framer-motion";

type RobotProps = { active?: boolean };

/* ──────────────────────────────────────────────────────────────────
   Mouse tracker — returns a ref to attach to the SVG and two
   spring-smoothed motion values for the eye-translate transform.
   ────────────────────────────────────────────────────────────────── */
function useEyeTracker(maxOffset = 3) {
  const ref = useRef<SVGSVGElement | null>(null);
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const x = useSpring(rx, { stiffness: 220, damping: 22 });
  const y = useSpring(ry, { stiffness: 220, damping: 22 });

  useEffect(() => {
    function onMove(e: MouseEvent) {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      // Normalise distance — 240 px is the "follow radius"; beyond that
      // the eyes stay locked at their maximum offset.
      const dx = (e.clientX - cx) / 240;
      const dy = (e.clientY - cy) / 240;
      rx.set(Math.max(-1, Math.min(1, dx)) * maxOffset);
      ry.set(Math.max(-1, Math.min(1, dy)) * maxOffset);
    }
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => window.removeEventListener("mousemove", onMove);
  }, [maxOffset, rx, ry]);

  return { ref, x, y };
}

const float = (active?: boolean) => ({
  animate: { y: active ? [0, -5, 0] : [0, -3, 0] },
  transition: {
    duration: active ? 1.6 : 3,
    repeat: Infinity,
    ease: "easeInOut" as const,
  },
});

const floorShadow = (active?: boolean) => ({
  animate: {
    rx: active ? [30, 34, 30] : [30, 27, 30],
    opacity: active ? [0.22, 0.4, 0.22] : [0.28, 0.18, 0.28],
  },
  transition: {
    duration: active ? 1.6 : 3,
    repeat: Infinity,
    ease: "easeInOut" as const,
  },
});

/* Shared SVG defs — body gradient, sheen, visor glow, soft shadow. */
function RobotDefs({ id, tint }: { id: string; tint: string }) {
  return (
    <defs>
      <linearGradient id={`body-${id}`} x1="50%" y1="0%" x2="50%" y2="100%">
        <stop offset="0%" stopColor="#2a3147" />
        <stop offset="55%" stopColor="#1a1f2e" />
        <stop offset="100%" stopColor="#0c0f17" />
      </linearGradient>
      <linearGradient id={`sheen-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stopColor="white" stopOpacity="0.22" />
        <stop offset="100%" stopColor="white" stopOpacity="0" />
      </linearGradient>
      <linearGradient id={`visor-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stopColor={tint} stopOpacity="1" />
        <stop offset="55%" stopColor={tint} stopOpacity="0.75" />
        <stop offset="100%" stopColor={tint} stopOpacity="0.35" />
      </linearGradient>
      <radialGradient id={`shadow-${id}`} cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor={tint} stopOpacity="0.55" />
        <stop offset="100%" stopColor={tint} stopOpacity="0" />
      </radialGradient>
      <filter id={`glow-${id}`} x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="1.6" />
      </filter>
      <filter id={`soft-${id}`} x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="0.6" />
      </filter>
    </defs>
  );
}

function Floor({ id, active }: { id: string; active?: boolean }) {
  return (
    <motion.ellipse
      cx="60"
      cy="126"
      rx="30"
      ry="3"
      fill={`url(#shadow-${id})`}
      {...floorShadow(active)}
    />
  );
}

/* Eye group wrapper — applies the tracker spring values as a transform. */
function Eyes({
  x,
  y,
  children,
}: {
  x: MotionValue<number>;
  y: MotionValue<number>;
  children: React.ReactNode;
}) {
  return <motion.g style={{ x, y }}>{children}</motion.g>;
}

/* ──────────────────────────────────────────────────────────────────
   1. EHR Analyst — The Archivist (filing-cabinet silhouette)
   ────────────────────────────────────────────────────────────────── */
export function ArchivistRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#6ea0ff";
  const t = useEyeTracker(2.5);
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Scanner antenna */}
        <line x1="60" y1="22" x2="60" y2="14" stroke={tint} strokeWidth="1.4" strokeLinecap="round" />
        <motion.circle
          cx="60" cy="11" r="2.2"
          fill={tint}
          filter={`url(#glow-${id})`}
          animate={{ opacity: active ? [0.5, 1, 0.5] : [0.6, 1, 0.6] }}
          transition={{ duration: active ? 0.9 : 1.8, repeat: Infinity }}
        />

        {/* Head — rectangular cabinet with rounded top */}
        <rect x="22" y="22" width="76" height="46" rx="6" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.06" strokeWidth="0.6" />
        <rect x="22" y="22" width="76" height="14" rx="6" fill={`url(#sheen-${id})`} />

        {/* Visor — wide horizontal slot */}
        <rect x="28" y="38" width="64" height="16" rx="3" fill="#05070d" />
        <rect x="28.6" y="38.6" width="62.8" height="14.8" rx="2.4" fill={`url(#visor-${id})`} filter={`url(#soft-${id})`} />

        {/* Pupils that follow the mouse — Archivist's eyes inside the data visor */}
        <Eyes x={t.x} y={t.y}>
          <circle cx="46" cy="46" r="2.4" fill="white" fillOpacity="0.9" />
          <circle cx="46" cy="46" r="1.1" fill="#0c0f17" />
          <circle cx="74" cy="46" r="2.4" fill="white" fillOpacity="0.9" />
          <circle cx="74" cy="46" r="1.1" fill="#0c0f17" />
        </Eyes>

        {/* Neck */}
        <rect x="48" y="68" width="24" height="6" rx="1" fill={`url(#body-${id})`} />
        <rect x="48" y="68" width="24" height="2" fill={`url(#sheen-${id})`} />

        {/* Body — filing-cabinet bust */}
        <path
          d="M 22 76 Q 22 72 26 72 L 94 72 Q 98 72 98 76 L 96 120 Q 96 124 92 124 L 28 124 Q 24 124 24 120 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.06" strokeWidth="0.6"
        />
        <path d="M 22 76 Q 22 72 26 72 L 94 72 Q 98 72 98 76 L 97 84 L 23 84 Z" fill={`url(#sheen-${id})`} />

        {/* Drawer dividers + handles */}
        <line x1="26" y1="93" x2="94" y2="93" stroke="white" strokeOpacity="0.10" strokeWidth="0.6" />
        <line x1="26" y1="107" x2="94" y2="107" stroke="white" strokeOpacity="0.10" strokeWidth="0.6" />
        <g filter={`url(#glow-${id})`}>
          <rect x="56" y="86" width="8" height="2" rx="1" fill={tint} />
          <rect x="56" y="100" width="8" height="2" rx="1" fill={tint} fillOpacity="0.7" />
          <rect x="56" y="114" width="8" height="2" rx="1" fill={tint} fillOpacity="0.5" />
        </g>
      </motion.g>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   2. Lab Interpreter — The Chemist (glass dome + test-tube body)
   ────────────────────────────────────────────────────────────────── */
export function ChemistRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#4ed68b";
  const t = useEyeTracker(2.5);
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Beaker antenna */}
        <path d="M 56 6 L 56 16 L 64 16 L 64 6 Z" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.1" strokeWidth="0.6" />
        <line x1="57" y1="10" x2="63" y2="10" stroke={tint} strokeWidth="0.6" strokeOpacity="0.7" />
        <line x1="60" y1="16" x2="60" y2="22" stroke={tint} strokeWidth="1.4" strokeLinecap="round" />

        {/* Glass dome head */}
        <circle cx="60" cy="42" r="22" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.08" strokeWidth="0.6" />
        <path d="M 42 32 Q 60 22 78 32" fill={`url(#sheen-${id})`} />

        {/* Visor slot */}
        <rect x="42" y="40" width="36" height="8" rx="3" fill="#05070d" />
        <rect x="42.6" y="40.6" width="34.8" height="6.8" rx="2.5" fill={`url(#visor-${id})`} filter={`url(#soft-${id})`} />

        {/* Droplet pupils tracking the mouse */}
        <Eyes x={t.x} y={t.y}>
          <path d="M 50 44 Q 48 47 50 47 Q 52 47 50 44 Z" fill="white" fillOpacity="0.95" />
          <path d="M 70 44 Q 68 47 70 47 Q 72 47 70 44 Z" fill="white" fillOpacity="0.95" />
        </Eyes>

        {/* Inner dome reflection */}
        <ellipse cx="50" cy="32" rx="6" ry="2" fill="white" fillOpacity="0.18" />

        {/* Neck */}
        <rect x="50" y="62" width="20" height="6" rx="1" fill={`url(#body-${id})`} />

        {/* Test-tube body */}
        <path
          d="M 38 70 L 38 112 Q 38 124 60 124 Q 82 124 82 112 L 82 70 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.08" strokeWidth="0.6"
        />
        <path d="M 38 70 L 82 70 L 82 80 L 38 80 Z" fill={`url(#sheen-${id})`} />

        {/* Liquid line + glow */}
        <path d="M 38 96 L 82 96 L 82 112 Q 82 124 60 124 Q 38 124 38 112 Z" fill={tint} fillOpacity="0.18" />
        <line x1="38" y1="96" x2="82" y2="96" stroke={tint} strokeWidth="0.8" strokeOpacity="0.85" filter={`url(#glow-${id})`} />

        {/* Rising bubbles */}
        <motion.circle cx="48" r="1.8" fill={tint} fillOpacity="0.7"
          animate={{ cy: [114, 98, 114], opacity: [0, 1, 0] }}
          transition={{ duration: active ? 1.6 : 2.8, repeat: Infinity, ease: "easeOut" }}
        />
        <motion.circle cx="60" r="1.3" fill={tint} fillOpacity="0.7"
          animate={{ cy: [118, 100, 118], opacity: [0, 1, 0] }}
          transition={{ duration: active ? 1.8 : 3.2, repeat: Infinity, ease: "easeOut", delay: 0.8 }}
        />
        <motion.circle cx="70" r="1.1" fill={tint} fillOpacity="0.7"
          animate={{ cy: [115, 102, 115], opacity: [0, 1, 0] }}
          transition={{ duration: active ? 1.5 : 3, repeat: Infinity, ease: "easeOut", delay: 1.4 }}
        />

        {/* Side reflection */}
        <line x1="44" y1="84" x2="44" y2="106" stroke="white" strokeOpacity="0.18" strokeWidth="1.6" strokeLinecap="round" />
      </motion.g>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   3. Diagnostic Reasoning — The Strategist (humanoid + rotating gear)
   ────────────────────────────────────────────────────────────────── */
export function StrategistRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#f3b95a";
  const t = useEyeTracker(3);
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Rotating gear */}
        <motion.g
          animate={{ rotate: 360 }}
          transition={{ duration: active ? 3 : 8, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: "60px 14px" }}
        >
          <circle cx="60" cy="14" r="6.5" fill="none" stroke={tint} strokeWidth="1.2" filter={`url(#glow-${id})`} />
          <circle cx="60" cy="14" r="2" fill={tint} />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((d) => (
            <rect key={d} x="59" y="6" width="2" height="3" fill={tint} transform={`rotate(${d} 60 14)`} />
          ))}
        </motion.g>
        <line x1="60" y1="20" x2="60" y2="26" stroke={tint} strokeWidth="1.2" strokeLinecap="round" />

        {/* Rounded humanoid head */}
        <rect x="24" y="26" width="72" height="46" rx="18" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.08" strokeWidth="0.6" />
        <rect x="24" y="26" width="72" height="16" rx="18" fill={`url(#sheen-${id})`} />

        {/* Twin eyes — pupils track the mouse */}
        <circle cx="44" cy="48" r="3.5" fill="#05070d" />
        <circle cx="76" cy="48" r="3.5" fill="#05070d" />
        <Eyes x={t.x} y={t.y}>
          <circle cx="44" cy="48" r="2.4" fill={tint} filter={`url(#soft-${id})`} />
          <circle cx="44" cy="48" r="1" fill="white" fillOpacity="0.9" />
          <circle cx="76" cy="48" r="2.4" fill={tint} filter={`url(#soft-${id})`} />
          <circle cx="76" cy="48" r="1" fill="white" fillOpacity="0.9" />
        </Eyes>

        {/* Chin / mouth indicator */}
        <line x1="50" y1="62" x2="70" y2="62" stroke="white" strokeOpacity="0.15" strokeWidth="0.8" strokeLinecap="round" />

        {/* Neck */}
        <rect x="50" y="72" width="20" height="6" rx="1" fill={`url(#body-${id})`} />

        {/* Body — humanoid bust */}
        <path
          d="M 26 80 Q 26 76 30 76 L 90 76 Q 94 76 94 80 L 92 122 Q 92 126 88 126 L 32 126 Q 28 126 28 122 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.06" strokeWidth="0.6"
        />
        <path d="M 26 80 Q 26 76 30 76 L 90 76 Q 94 76 94 80 L 93 88 L 27 88 Z" fill={`url(#sheen-${id})`} />

        {/* Chest core */}
        <motion.g
          animate={{ opacity: active ? [0.5, 1, 0.5] : [0.6, 0.9, 0.6] }}
          transition={{ duration: active ? 0.9 : 1.8, repeat: Infinity }}
        >
          <circle cx="60" cy="104" r="6" fill="#05070d" />
          <circle cx="60" cy="104" r="4.5" fill={tint} filter={`url(#soft-${id})`} />
        </motion.g>
        <circle cx="34" cy="96" r="1" fill={tint} fillOpacity="0.55" />
        <circle cx="86" cy="96" r="1" fill={tint} fillOpacity="0.55" />
        <circle cx="34" cy="118" r="1" fill={tint} fillOpacity="0.55" />
        <circle cx="86" cy="118" r="1" fill={tint} fillOpacity="0.55" />
      </motion.g>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   4. Clinical Reviewer — The Inspector (helmet + magnifier follows mouse)
   ────────────────────────────────────────────────────────────────── */
export function InspectorRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#b794f6";
  const t = useEyeTracker(5); // bigger range — the magnifier sweeps further
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Question-mark antenna */}
        <path d="M 56 18 Q 56 10 62 10 Q 68 10 68 16 Q 68 20 63 22 Q 60 24 60 27" fill="none" stroke={tint} strokeWidth="1.4" strokeLinecap="round" />
        <circle cx="60" cy="30" r="1.4" fill={tint} filter={`url(#glow-${id})`} />

        {/* Angular hexagonal helmet */}
        <path
          d="M 30 38 L 42 28 L 78 28 L 90 38 L 90 64 L 78 74 L 42 74 L 30 64 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.08" strokeWidth="0.6"
        />
        <path d="M 30 38 L 42 28 L 78 28 L 90 38 L 86 44 L 34 44 Z" fill={`url(#sheen-${id})`} />

        {/* Narrowed slit eye on the left */}
        <rect x="40" y="49" width="14" height="3" rx="1.5" fill="#05070d" />
        <rect x="40.6" y="49.6" width="12.8" height="1.8" rx="0.9" fill={tint} filter={`url(#soft-${id})`} />

        {/* Magnifier follows the mouse */}
        <Eyes x={t.x} y={t.y}>
          <circle cx="70" cy="50" r="8" fill="#05070d" />
          <circle cx="70" cy="50" r="6.8" fill={`url(#visor-${id})`} filter={`url(#soft-${id})`} />
          <circle cx="70" cy="50" r="2.4" fill={tint} />
          <line x1="76" y1="56" x2="84" y2="64" stroke={tint} strokeWidth="2" strokeLinecap="round" />
          <ellipse cx="66" cy="46" rx="2.4" ry="1.4" fill="white" fillOpacity="0.4" />
        </Eyes>

        {/* Neck */}
        <rect x="50" y="74" width="20" height="5" rx="1" fill={`url(#body-${id})`} />

        {/* Body — sharp angular shoulders */}
        <path
          d="M 18 84 L 60 76 L 102 84 L 96 126 L 24 126 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.08" strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <path d="M 18 84 L 60 76 L 102 84 L 100 90 L 20 90 Z" fill={`url(#sheen-${id})`} />

        {/* Badge */}
        <g filter={`url(#glow-${id})`}>
          <path d="M 54 100 L 60 94 L 66 100 L 66 112 L 60 118 L 54 112 Z" fill="none" stroke={tint} strokeWidth="1.4" />
          <path d="M 56 104 L 60 100 L 64 104" fill="none" stroke={tint} strokeWidth="1.2" />
        </g>
      </motion.g>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   5. Diagnostic Refiner — The Editor (sleek + sparkles, eyes track)
   ────────────────────────────────────────────────────────────────── */
export function EditorRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#c8a4ff";
  const t = useEyeTracker(2.5);
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Pen-nib antenna */}
        <path d="M 60 6 L 54 20 L 66 20 Z" fill={`url(#visor-${id})`} filter={`url(#soft-${id})`} />
        <path d="M 60 6 L 54 20 L 66 20 Z" fill="none" stroke="white" strokeOpacity="0.2" strokeWidth="0.5" />
        <line x1="60" y1="16" x2="60" y2="20" stroke="#05070d" strokeWidth="1" />

        {/* Sparkles */}
        <motion.g
          animate={{ opacity: active ? [0.3, 1, 0.3] : [0.25, 0.8, 0.25], rotate: 360 }}
          transition={{ duration: active ? 2.4 : 5, repeat: Infinity, ease: "easeInOut" }}
          style={{ transformOrigin: "60px 44px" }}
        >
          <path d="M 22 32 L 24 34 L 22 36 L 20 34 Z" fill={tint} filter={`url(#soft-${id})`} />
          <path d="M 98 30 L 100 32 L 98 34 L 96 32 Z" fill={tint} filter={`url(#soft-${id})`} />
          <path d="M 18 60 L 20 62 L 18 64 L 16 62 Z" fill={tint} filter={`url(#soft-${id})`} />
          <path d="M 100 58 L 102 60 L 100 62 L 98 60 Z" fill={tint} filter={`url(#soft-${id})`} />
        </motion.g>

        {/* Refined oval head */}
        <ellipse cx="60" cy="48" rx="30" ry="24" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.08" strokeWidth="0.6" />
        <path d="M 30 36 Q 60 26 90 36 L 90 44 L 30 44 Z" fill={`url(#sheen-${id})`} />

        {/* Eyes with pupils that track */}
        <ellipse cx="46" cy="50" rx="5" ry="4" fill="#05070d" />
        <ellipse cx="74" cy="50" rx="5" ry="4" fill="#05070d" />
        <Eyes x={t.x} y={t.y}>
          <circle cx="46" cy="50" r="2.4" fill={tint} filter={`url(#soft-${id})`} />
          <circle cx="46" cy="50" r="1" fill="white" fillOpacity="0.95" />
          <circle cx="74" cy="50" r="2.4" fill={tint} filter={`url(#soft-${id})`} />
          <circle cx="74" cy="50" r="1" fill="white" fillOpacity="0.95" />
        </Eyes>

        {/* Neck */}
        <rect x="50" y="72" width="20" height="6" rx="1" fill={`url(#body-${id})`} />

        {/* Body */}
        <path
          d="M 30 80 Q 30 76 34 76 L 86 76 Q 90 76 90 80 L 86 124 Q 86 126 84 126 L 36 126 Q 34 126 34 124 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.08" strokeWidth="0.6"
        />
        <path d="M 30 80 Q 30 76 34 76 L 86 76 Q 90 76 90 80 L 88 88 L 32 88 Z" fill={`url(#sheen-${id})`} />

        {/* Diff lines + markers */}
        <line x1="40" y1="98" x2="78" y2="98" stroke="white" strokeOpacity="0.15" strokeWidth="0.6" />
        <line x1="40" y1="104" x2="72" y2="104" stroke="white" strokeOpacity="0.15" strokeWidth="0.6" />
        <line x1="40" y1="110" x2="80" y2="110" stroke="white" strokeOpacity="0.15" strokeWidth="0.6" />
        <g filter={`url(#glow-${id})`}>
          <rect x="43" y="97" width="3" height="1" fill={tint} />
          <rect x="44" y="96" width="1" height="3" fill={tint} />
          <rect x="43" y="103" width="3" height="1" fill={tint} fillOpacity="0.7" />
          <circle cx="44.5" cy="110" r="0.8" fill={tint} fillOpacity="0.5" />
        </g>
      </motion.g>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   6. LLM Evaluator — The Judge (blocky stoic + tilting scales)
   ────────────────────────────────────────────────────────────────── */
export function JudgeRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#7ed7d0";
  const t = useEyeTracker(2);
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Scales antenna */}
        <line x1="60" y1="22" x2="60" y2="14" stroke={tint} strokeWidth="1.2" strokeLinecap="round" />
        <motion.g
          animate={{ rotate: active ? [-5, 5, -5] : [-2, 2, -2] }}
          transition={{ duration: active ? 1.6 : 3.4, repeat: Infinity, ease: "easeInOut" }}
          style={{ transformOrigin: "60px 14px" }}
        >
          <line x1="46" y1="14" x2="74" y2="14" stroke={tint} strokeWidth="1.2" strokeLinecap="round" />
          <path d="M 42 14 L 46 18 L 50 14 Z" fill="none" stroke={tint} strokeWidth="1" strokeLinejoin="round" filter={`url(#soft-${id})`} />
          <path d="M 70 14 L 74 18 L 78 14 Z" fill="none" stroke={tint} strokeWidth="1" strokeLinejoin="round" filter={`url(#soft-${id})`} />
        </motion.g>

        {/* Blocky head */}
        <rect x="22" y="24" width="76" height="44" rx="6" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.08" strokeWidth="0.6" />
        <rect x="22" y="24" width="76" height="14" rx="6" fill={`url(#sheen-${id})`} />

        {/* Visor */}
        <rect x="28" y="44" width="64" height="6" rx="2" fill="#05070d" />
        <rect x="28.6" y="44.6" width="62.8" height="4.8" rx="1.5" fill={`url(#visor-${id})`} filter={`url(#soft-${id})`} />

        {/* Pupils inside the visor tracking the mouse */}
        <Eyes x={t.x} y={t.y}>
          <circle cx="44" cy="47" r="1.4" fill="white" fillOpacity="0.95" />
          <circle cx="76" cy="47" r="1.4" fill="white" fillOpacity="0.95" />
        </Eyes>

        {/* Verdict-strength indicator dots */}
        <circle cx="34" cy="58" r="1.5" fill={tint} filter={`url(#glow-${id})`} />
        <circle cx="44" cy="58" r="1.5" fill={tint} fillOpacity="0.7" />
        <circle cx="54" cy="58" r="1.5" fill={tint} fillOpacity="0.5" />
        <circle cx="64" cy="58" r="1.5" fill={tint} fillOpacity="0.35" />
        <circle cx="74" cy="58" r="1.5" fill={tint} fillOpacity="0.25" />

        {/* Neck */}
        <rect x="50" y="68" width="20" height="6" rx="1" fill={`url(#body-${id})`} />

        {/* Body */}
        <path
          d="M 22 76 Q 22 72 26 72 L 94 72 Q 98 72 98 76 L 98 126 L 22 126 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.08" strokeWidth="0.6"
        />
        <path d="M 22 76 Q 22 72 26 72 L 94 72 Q 98 72 98 76 L 96 84 L 24 84 Z" fill={`url(#sheen-${id})`} />

        <line x1="22" y1="90" x2="98" y2="90" stroke="white" strokeOpacity="0.12" strokeWidth="0.6" />
        <g filter={`url(#glow-${id})`}>
          <path d="M 38 104 L 46 98 L 54 104 L 62 98 L 70 104 L 78 98" fill="none" stroke={tint} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M 38 116 L 46 110 L 54 116 L 62 110 L 70 116 L 78 110" fill="none" stroke={tint} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.55" />
        </g>
      </motion.g>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   7. Treatment Planner — The Pharmacist (capsule body, red cross)
   ────────────────────────────────────────────────────────────────── */
export function PharmacistRobot({ active }: RobotProps) {
  const id = useId();
  const tint = "#f5a0a0";
  const t = useEyeTracker(2.5);
  return (
    <svg ref={t.ref} viewBox="0 0 120 130" width="100%" height="100%" aria-hidden>
      <RobotDefs id={id} tint={tint} />
      <Floor id={id} active={active} />

      <motion.g {...float(active)}>
        {/* Prescription bottle antenna */}
        <rect x="52" y="6" width="16" height="14" rx="2" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.1" strokeWidth="0.6" />
        <rect x="54" y="9" width="12" height="1.4" rx="0.4" fill={tint} fillOpacity="0.7" />
        <rect x="54" y="13" width="12" height="1.4" rx="0.4" fill={tint} fillOpacity="0.7" />
        <line x1="60" y1="20" x2="60" y2="26" stroke={tint} strokeWidth="1.4" strokeLinecap="round" />

        {/* Spherical head */}
        <circle cx="60" cy="46" r="22" fill={`url(#body-${id})`} stroke="white" strokeOpacity="0.08" strokeWidth="0.6" />
        <path d="M 40 36 Q 60 26 80 36" fill={`url(#sheen-${id})`} />

        {/* Eye sockets */}
        <ellipse cx="50" cy="49" rx="5" ry="4" fill="#05070d" />
        <ellipse cx="70" cy="49" rx="5" ry="4" fill="#05070d" />
        {/* Warm pupils that track */}
        <Eyes x={t.x} y={t.y}>
          <circle cx="50" cy="49" r="2.2" fill={tint} filter={`url(#soft-${id})`} />
          <circle cx="50" cy="49" r="1" fill="white" fillOpacity="0.95" />
          <circle cx="70" cy="49" r="2.2" fill={tint} filter={`url(#soft-${id})`} />
          <circle cx="70" cy="49" r="1" fill="white" fillOpacity="0.95" />
        </Eyes>

        {/* Red cross emblem on forehead */}
        <motion.g
          animate={{ opacity: active ? [0.55, 1, 0.55] : [0.6, 0.9, 0.6] }}
          transition={{ duration: active ? 1.2 : 2.4, repeat: Infinity }}
          filter={`url(#glow-${id})`}
        >
          <rect x="57" y="32" width="6" height="14" rx="0.8" fill={tint} />
          <rect x="53" y="36" width="14" height="6" rx="0.8" fill={tint} />
        </motion.g>

        {/* Smile hint */}
        <path d="M 50 60 Q 60 64 70 60" fill="none" stroke="white" strokeOpacity="0.18" strokeWidth="0.8" strokeLinecap="round" />

        {/* Neck */}
        <rect x="50" y="68" width="20" height="6" rx="1" fill={`url(#body-${id})`} />

        {/* Pill body */}
        <path
          d="M 32 80 Q 32 74 38 74 L 82 74 Q 88 74 88 80 L 88 100 L 32 100 Z"
          fill={`url(#body-${id})`}
          stroke="white" strokeOpacity="0.08" strokeWidth="0.6"
        />
        <path d="M 32 80 Q 32 74 38 74 L 82 74 Q 88 74 88 80 L 87 88 L 33 88 Z" fill={`url(#sheen-${id})`} />

        <path
          d="M 32 100 L 88 100 L 88 120 Q 88 126 82 126 L 38 126 Q 32 126 32 120 Z"
          fill={`url(#visor-${id})`}
          stroke="white" strokeOpacity="0.1" strokeWidth="0.6"
        />
        <path d="M 32 100 L 88 100 L 88 106 L 32 106 Z" fill="white" fillOpacity="0.1" />

        <line x1="32" y1="100" x2="88" y2="100" stroke="white" strokeOpacity="0.25" strokeWidth="0.8" />
        <line x1="38" y1="82" x2="38" y2="96" stroke="white" strokeOpacity="0.2" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="38" y1="108" x2="38" y2="120" stroke="white" strokeOpacity="0.35" strokeWidth="1.4" strokeLinecap="round" />
      </motion.g>
    </svg>
  );
}

/* Dispatcher — pick the robot for a given agent id. */
export function AgentRobot({
  agentId,
  active,
}: {
  agentId: string;
  active?: boolean;
}) {
  switch (agentId) {
    case "ehr_analyst":
      return <ArchivistRobot active={active} />;
    case "lab_interpreter":
      return <ChemistRobot active={active} />;
    case "diagnostic_reasoning":
      return <StrategistRobot active={active} />;
    case "clinical_reviewer":
      return <InspectorRobot active={active} />;
    case "final_diagnosis":
      return <EditorRobot active={active} />;
    case "evaluation":
      return <JudgeRobot active={active} />;
    case "treatment_planning":
      return <PharmacistRobot active={active} />;
    default:
      return <ArchivistRobot active={active} />;
  }
}

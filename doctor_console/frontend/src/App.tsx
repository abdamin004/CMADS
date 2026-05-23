import { AnimatePresence, motion } from "framer-motion";
import { ModeChooser } from "./components/ModeChooser";
import { ResearcherMode } from "./components/ResearcherMode";
import { RuntimeMode } from "./components/RuntimeMode";
import { useMode } from "./useMode";

/**
 * Thin top-level mode router.
 *
 * Source-of-truth for "which workspace" is ?mode= in the URL, persisted via
 * localStorage. First-visit users see the ModeChooser splash. Existing patient
 * deep-links (?p=…&a=…) continue to work in both modes.
 */
export default function App() {
  const { mode, setMode, clearMode } = useMode();

  return (
    <AnimatePresence mode="wait">
      {!mode ? (
        <motion.div
          key="chooser"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }}
        >
          <ModeChooser onChoose={setMode} />
        </motion.div>
      ) : mode === "runtime" ? (
        <motion.div
          key="runtime"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
        >
          <RuntimeMode mode={mode} onModeChange={setMode} onHome={clearMode} />
        </motion.div>
      ) : (
        <motion.div
          key="researcher"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
        >
          <ResearcherMode mode={mode} onModeChange={setMode} onHome={clearMode} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

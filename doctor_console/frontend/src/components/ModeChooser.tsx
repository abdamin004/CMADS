import { motion } from "framer-motion";
import { Activity, HeartHandshake, Stethoscope } from "lucide-react";
import type { Mode } from "../useMode";

type Props = {
  onChoose: (mode: Mode) => void;
};

/**
 * Landing splash shown on the first visit (no stored mode) and as a /-route
 * fallback. Two cards: a clinician-facing "Run a patient" path and a
 * researcher-facing "Explore the results" path. The splash also carries the
 * trust signal that live clinician runs are stored in a separate cohort so
 * the research statistics stay reproducible.
 */
export function ModeChooser({ onChoose }: Props) {
  return (
    <div className="mode-chooser">
      <div className="mode-chooser__grain" aria-hidden />
      <div className="mode-chooser__rule mode-chooser__rule--top" aria-hidden />
      <div className="mode-chooser__rule mode-chooser__rule--bottom" aria-hidden />

      <motion.header
        className="mode-chooser__brand"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
      >
        <div className="mode-chooser__eyebrow mono">
          CMADS · A clinical second opinion
        </div>
      </motion.header>

      <div className="mode-chooser__cards">
        <motion.button
          type="button"
          className="mode-chooser__card mode-chooser__card--doctor"
          onClick={() => onChoose("runtime")}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.08, ease: [0.23, 1, 0.32, 1] }}
          whileHover={{ y: -4 }}
          whileTap={{ scale: 0.985 }}
        >
          <div className="mode-chooser__card-head">
            <div className="mode-chooser__card-icon">
              <Stethoscope size={28} strokeWidth={1.4} />
            </div>
            <span className="mode-chooser__card-eyebrow mono">When you have a patient in front of you</span>
          </div>
          <h2 className="mode-chooser__card-title">Assist me.</h2>
          <p className="mode-chooser__card-body">
            Bring up a patient and a careful second opinion will walk through
            their chart and lab work with you. You'll see what looks most likely,
            what's worth checking next, and a management plan to consider —
            always there for you to take, change, or set aside.
          </p>
          <ul className="mode-chooser__card-points">
            <li><Activity size={14} strokeWidth={1.6} /> A second opinion in about two minutes</li>
            <li><Stethoscope size={14} strokeWidth={1.6} /> You stay in charge of every decision</li>
          </ul>
          <span className="mode-chooser__card-cta">Let's look at a patient →</span>
        </motion.button>

        <motion.button
          type="button"
          className="mode-chooser__card mode-chooser__card--researcher"
          onClick={() => onChoose("researcher")}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.18, ease: [0.23, 1, 0.32, 1] }}
          whileHover={{ y: -4 }}
          whileTap={{ scale: 0.985 }}
        >
          <span className="mode-chooser__card-suggest mono" aria-hidden>
            Start here
          </span>
          <div className="mode-chooser__card-head">
            <div className="mode-chooser__card-icon">
              <HeartHandshake size={28} strokeWidth={1.4} />
            </div>
            <span className="mode-chooser__card-eyebrow mono">Before you lean on it</span>
          </div>
          <h2 className="mode-chooser__card-title">Build trust.</h2>
          <p className="mode-chooser__card-body">
            See how often the system is right on patients whose diagnoses we
            already know. Read through real past cases, watch how it thought
            through each one, and decide for yourself whether its second opinion
            is worth listening to next time.
          </p>
          <ul className="mode-chooser__card-points">
            <li><HeartHandshake size={14} strokeWidth={1.6} /> See how often it gets the right answer</li>
            <li><Activity size={14} strokeWidth={1.6} /> Look through real past patients in detail</li>
          </ul>
          <span className="mode-chooser__card-cta">Show me what it can do →</span>
        </motion.button>

      </div>

      <motion.section
        className="mode-chooser__howto"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.28, ease: [0.23, 1, 0.32, 1] }}
      >
        <div className="mode-chooser__howto-head">
          <span className="mode-chooser__howto-eyebrow mono">How to use the system</span>
          <h2 className="mode-chooser__howto-title">
            Two ways in, and an order worth following.
          </h2>
        </div>
        <ol className="mode-chooser__howto-steps">
          <li>
            <span className="mode-chooser__howto-num">1</span>
            <div>
              <strong>Start with Build trust.</strong> See how often the system
              is right on patients whose diagnoses we already know, read through
              past cases, and watch how it thought through each one.
            </div>
          </li>
          <li>
            <span className="mode-chooser__howto-num">2</span>
            <div>
              <strong>Switch to Assist me</strong> once it has earned your
              confidence. Bring up a new patient and the system will walk through
              the chart and lab work with you — every decision stays yours.
            </div>
          </li>
        </ol>
        <div className="mode-chooser__meta mono">
          Bachelor thesis · Faculty of Media Engineering and Technology · German University in Cairo
        </div>
      </motion.section>
    </div>
  );
}

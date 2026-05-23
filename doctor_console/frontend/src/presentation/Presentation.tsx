import FlowArt, { FlowSection } from "../components/ui/story-scroll";
import { SplineScene } from "../components/ui/splite";
import { Spotlight } from "../components/ui/spotlight";

const NAVY = "#0a1838";
const PAPER = "#f5f0e8";
const BLUE = "#1a3de8";
const AMBER = "#fd5200";
const TEAL = "#0d8267";
const INK_DARK = "#0d1220";
const INK_LIGHT = "#f7f9fc";

export default function Presentation() {
  return (
    <FlowArt aria-label="CMADS final presentation">

      {/* ───────────── Slide 1 — Hero (matches DashboardHero pattern) ───────────── */}
      <FlowSection
        aria-label="Title"
        style={{ backgroundColor: "rgba(0,0,0,0.96)", color: INK_LIGHT }}
      >
        <Spotlight
          className="-top-40 left-0 md:left-60 md:-top-20"
          fill="white"
        />

        <p className="relative z-10 text-xs font-bold uppercase tracking-[0.25em] opacity-80 font-mono">
          Bachelor Thesis · German University in Cairo · May 2026
        </p>

        <div className="relative z-10 flex flex-1 flex-col gap-[3vw] md:flex-row md:items-center">
          <div className="flex-1">
            <p className="text-xs uppercase tracking-[0.18em] text-neutral-400 mb-3 font-mono">
              Clinical Multi-Agent Decisioning
            </p>
            <h1 className="text-[clamp(3rem,9vw,9rem)] font-bold uppercase leading-[0.9] tracking-tight bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 to-neutral-400">
              CMADS
            </h1>
            <p className="mt-[2vw] text-[clamp(1.3rem,2.4vw,2.4rem)] font-normal leading-snug text-neutral-200 max-w-[40ch]">
              Diagnosis you can audit.
            </p>
            <p className="mt-[2vw] max-w-[55ch] text-[clamp(1rem,1.6vw,1.4rem)] font-normal leading-relaxed text-neutral-300">
              Seven specialised agents reason over the patient record, a
              clinical reviewer challenges the primary diagnosis, and the full
              chain --- evidence, memory, retrieved guidelines, and final
              ranked differential --- is exposed for inspection.
            </p>
            <div className="mt-[3vw] flex flex-wrap items-baseline gap-[3vw]">
              <p className="text-[clamp(1rem,1.6vw,1.4rem)] font-semibold text-neutral-100">
                Abdelrahman Mohamed Amin
              </p>
              <p className="text-[clamp(0.85rem,1.2vw,1rem)] text-neutral-400">
                Supervisor · Dr. Shereen Moataz Afifi
              </p>
            </div>
          </div>

          <div className="hidden md:block flex-1 h-[60vh]">
            <SplineScene
              scene="https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"
              className="w-full h-full"
            />
          </div>
        </div>

        <p className="relative z-10 mt-auto text-[clamp(0.85rem,1.2vw,1.05rem)] text-neutral-400 font-mono">
          Scroll to begin · 11 slides · ~8 min
        </p>
      </FlowSection>

      {/* ───────────── Slide 2 — Where the field is today ───────────── */}
      <FlowSection
        aria-label="Where the field is today"
        style={{ backgroundColor: PAPER, color: INK_DARK }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-70">
          02 — Where the field is
        </p>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Five papers,
          <br />
          one pattern.
        </h2>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <div className="grid grid-cols-1 gap-[2.5vw] md:grid-cols-2 lg:grid-cols-3">
          {[
            ["MDAgents (2024)", "10 MCQ benchmarks", "Best on 7 of 10"],
            ["ZODIAC (2024)", "Real cardiology, 8 metrics", "Cardiologist-level on 7/8"],
            ["ClinicalLab (2024)", "1,500 real cases, 11 depts", "Within 5% of senior physicians"],
            ["MAC Framework (2025)", "302 rare-disease cases", "Outperforms self-consistency"],
            ["RareAgents (2024)", "RareBench + MIMIC-Ext", "Open backbone > GPT-4o"],
          ].map(([name, cohort, headline]) => (
            <div key={name} className="min-w-[200px]">
              <p className="mb-2 text-sm font-bold uppercase tracking-wider">{name}</p>
              <p className="mb-1 text-[clamp(0.85rem,1.2vw,1rem)] opacity-70">{cohort}</p>
              <p className="text-[clamp(0.95rem,1.3vw,1.1rem)] font-medium leading-snug">
                {headline}
              </p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <p className="mt-auto max-w-[60ch] text-[clamp(1rem,1.8vw,1.6rem)] font-normal leading-relaxed">
          Three things repeat: closed frontier models, multiple-choice
          benchmarks, no doctor-facing loop. That is the shape of the gap.
        </p>
      </FlowSection>

      {/* ───────────── Slide 3 — The gap CMADS targets ───────────── */}
      <FlowSection
        aria-label="The gap CMADS targets"
        style={{ backgroundColor: AMBER, color: INK_LIGHT }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em]">03 — The gap</p>
        <hr className="my-[2vw] border-none border-t border-white/60" />
        <h2 className="text-[clamp(2.5rem,9vw,9rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Four gaps.
          <br />
          One system.
        </h2>
        <hr className="my-[2vw] border-none border-t border-white/60" />
        <div className="grid grid-cols-1 gap-[3vw] md:grid-cols-2">
          {[
            ["01 — End-to-end pipeline", "Synthea → medallion data lake → 7 agents → ranked differential → NICE treatment plan → doctor review. Most papers stop at \"did the model pick the right answer\"."],
            ["02 — Open-source backbone", "GPT-OSS-120B reasoning, Qwen3-32B judge. Whole pipeline reproduces under ~$30 per 1,000 patients."],
            ["03 — Inspectable memory subsystem", "Four CoALA-inspired tiers (working / episodic / semantic / case-based). Each persisted and addressable. Tested with a controlled A/B."],
            ["04 — Doctor-facing console", "Every agent output inspectable. Similar past cases surfaced. Treatment plan exposes its assumptions and missing-data warnings. Reviewer verdict persisted."],
          ].map(([title, body]) => (
            <div key={title} className="min-w-[220px]">
              <p className="mb-2 text-sm font-bold uppercase tracking-wider">{title}</p>
              <p className="text-[clamp(0.95rem,1.4vw,1.2rem)] leading-relaxed opacity-90">
                {body}
              </p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-white/60" />
        <p className="mt-auto max-w-[60ch] text-[clamp(1rem,1.8vw,1.6rem)] font-normal leading-relaxed">
          Each individual piece exists in some prior paper. The composition is
          the contribution.
        </p>
      </FlowSection>

      {/* ───────────── Slide 4 — Seven-agent pipeline ───────────── */}
      <FlowSection
        aria-label="Seven-agent pipeline"
        style={{ backgroundColor: PAPER, color: INK_DARK }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-70">
          04 — Pipeline
        </p>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Seven agents.
          <br />
          Six stages.
        </h2>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <div className="grid grid-cols-1 gap-[2vw] md:grid-cols-2 lg:grid-cols-3">
          {[
            ["Stage 1 (parallel)", "EHR Analyst Agent + Lab Interpreter Agent"],
            ["Stage 2", "Diagnostic Reasoning, adaptive critique loop (≤3 rounds)"],
            ["Stage 3", "Clinical Reviewer, adversarial, non-destructive"],
            ["Stage 4", "Diagnostic Refiner, merges reasoning + review"],
            ["Stage 5", "LLM Evaluator (DIRECT / INDIRECT / MISS vs ground truth)"],
            ["Stage 6", "Treatment Planning, NICE guidelines, DIRECT-gated"],
            ["Stage 7", "Memory consolidation, non-LLM, writes T2/T3/T4"],
          ].map(([stage, body]) => (
            <div key={stage} className="min-w-[200px]">
              <p className="mb-2 text-sm font-bold uppercase tracking-wider text-[var(--accent,#1a3de8)]">
                {stage}
              </p>
              <p className="text-[clamp(0.95rem,1.3vw,1.1rem)] leading-relaxed opacity-90">
                {body}
              </p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <p className="mt-auto max-w-[65ch] text-[clamp(1rem,1.8vw,1.6rem)] font-normal leading-relaxed">
          Stage 2 is the only loop. Stages 3 and 4 form a non-destructive
          review — the Refiner can change the primary but the original
          Diagnostic output stays in the trace.
        </p>
      </FlowSection>

      {/* ───────────── Slide 5 — Multi-level memory ───────────── */}
      <FlowSection
        aria-label="Multi-level memory architecture"
        style={{ backgroundColor: TEAL, color: INK_LIGHT }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em]">05 — Memory</p>
        <hr className="my-[2vw] border-none border-t border-white/50" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Four tiers.
          <br />
          Inspectable.
        </h2>
        <hr className="my-[2vw] border-none border-t border-white/50" />
        <div className="grid grid-cols-1 gap-[3vw] md:grid-cols-2">
          {[
            ["T1 — Working", "Per-agent scratchpad inside one run. Lives in PipelineState. Volatile."],
            ["T2 — Episodic", "Run-level event timeline — what each agent did, in what order. Persisted to session_memory.json."],
            ["T3 — Semantic", "Disease-level statistics across runs. JSON store, addressable by canonical disease name."],
            ["T4 — Case-based", "Past patient cases embedded with BioLORD-2023, stored in Qdrant. The Bayesian-style prior for new cases."],
          ].map(([t, body]) => (
            <div key={t} className="min-w-[220px]">
              <p className="mb-2 text-sm font-bold uppercase tracking-wider">{t}</p>
              <p className="text-[clamp(0.95rem,1.4vw,1.2rem)] leading-relaxed opacity-90">
                {body}
              </p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-white/50" />
        <p className="mt-auto max-w-[65ch] text-[clamp(1rem,1.8vw,1.6rem)] font-normal leading-relaxed">
          When T4 returns a strong past case, the Diagnostic agent runs a
          three-phase split: prior visible, clean room, synthesise. Explicit
          anti-anchoring.
        </p>
      </FlowSection>

      {/* ───────────── Slide 6 — Memory A/B on 100 patients ───────────── */}
      <FlowSection
        aria-label="Memory A/B on 100 patients"
        style={{ backgroundColor: INK_DARK, color: INK_LIGHT }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] text-[#fd5200]">
          06 — Memory A/B · 100 patients
        </p>
        <hr className="my-[2vw] border-none border-t border-white/40" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Broader,
          <br />
          not sharper.
        </h2>
        <hr className="my-[2vw] border-none border-t border-white/40" />
        <div className="grid grid-cols-2 gap-[2vw] md:grid-cols-4">
          {[
            ["67.8%", "Single-level DIRECT", "n=205"],
            ["49.0%", "Multi-level DIRECT", "n=100"],
            ["95.0%", "Multi-level Found", "vs 88.3% single"],
            ["p = 1.0", "Paired McNemar", "n=20 paired"],
          ].map(([val, label, sub]) => (
            <div key={label}>
              <p className="text-[clamp(2rem,5vw,4.5rem)] font-bold leading-none tracking-tight text-[#fd5200]">
                {val}
              </p>
              <p className="mt-2 text-sm font-bold uppercase tracking-wider">{label}</p>
              <p className="text-[clamp(0.8rem,1.1vw,0.95rem)] opacity-70">{sub}</p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-white/40" />
        <p className="max-w-[65ch] text-[clamp(1rem,1.6vw,1.5rem)] font-normal leading-relaxed opacity-90">
          MISS rate falls by more than half. Found rate climbs to 95%. But
          primary-diagnosis accuracy drops on the unpaired aggregate, and the
          paired 20-patient test is underpowered to settle it.
        </p>
        <hr className="my-[2vw] border-none border-t border-white/40" />
        <p className="mt-auto max-w-[65ch] text-[clamp(1rem,1.6vw,1.5rem)] font-medium leading-relaxed">
          Reported as a preliminary pattern, not a confirmed empirical
          contribution.
        </p>
      </FlowSection>

      {/* ───────────── Slide 7 — What the data say ───────────── */}
      <FlowSection
        aria-label="What the data say"
        style={{ backgroundColor: PAPER, color: INK_DARK }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-70">
          07 — The reading
        </p>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          It is a
          <br />
          trade.
        </h2>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <div className="grid grid-cols-1 gap-[3vw] md:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-bold uppercase tracking-wider text-[#0d8267]">
              The benefit
            </p>
            <p className="text-[clamp(1rem,1.5vw,1.3rem)] leading-relaxed opacity-90">
              Case-based retrieval surfaces disease-family priors the
              no-memory configuration missed. Found rate up by ~7 percentage
              points (88.3% → 95.0%).
            </p>
          </div>
          <div>
            <p className="mb-2 text-sm font-bold uppercase tracking-wider text-[#c0392b]">
              The cost
            </p>
            <p className="text-[clamp(1rem,1.5vw,1.3rem)] leading-relaxed opacity-90">
              Broader recall, less confident top-1 pick. DIRECT rate down on
              the unpaired aggregate. The Reviewer–Refiner step does not
              fully remove the broadening because the Reviewer sees outputs
              already influenced by the prior.
            </p>
          </div>
        </div>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <p className="mt-auto max-w-[65ch] text-[clamp(1rem,1.8vw,1.6rem)] font-normal leading-relaxed">
          Whether broader recall at the cost of a less confident top-1 pick is
          worth it depends on what the doctor will do with the differential.
        </p>
      </FlowSection>

      {/* ───────────── Slide 8 — Doctor console ───────────── */}
      <FlowSection
        aria-label="Doctor console"
        style={{ backgroundColor: BLUE, color: INK_LIGHT }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em]">
          08 — Doctor console
        </p>
        <hr className="my-[2vw] border-none border-t border-white/50" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Human
          <br />
          in the loop.
        </h2>
        <hr className="my-[2vw] border-none border-t border-white/50" />
        <div className="grid grid-cols-1 gap-[3vw] md:grid-cols-2">
          {[
            ["Agent workflow inline", "Each agent output one click away with a doctor-readable narrative generated from the schema."],
            ["Treatment safety review", "Medications, drug interactions, contraindications, and the LLM's missing-data warnings (\"eGFR unknown — assumed normal for ACE-I\")."],
            ["Similar past cases", "Top-K Tier-4 neighbours with their evaluator match type. One click switches to that patient."],
            ["Reviewer note (new)", "Three-way verdict, free-text, reviewer initials. Persisted to data/gold/annotations/<uuid>.json. Sidebar shows a coloured dot."],
            ["URL-driven state", "?r=<set>&p=<uuid>&a=<agent> — every view shareable, refresh-safe."],
          ].map(([title, body]) => (
            <div key={title} className="min-w-[240px]">
              <p className="mb-2 text-sm font-bold uppercase tracking-wider">{title}</p>
              <p className="text-[clamp(0.95rem,1.3vw,1.15rem)] leading-relaxed opacity-90">
                {body}
              </p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-white/50" />
        <p className="mt-auto max-w-[65ch] text-[clamp(1rem,1.6vw,1.5rem)] font-normal leading-relaxed">
          The console is what turns the system answered into the doctor
          reviewed the answer and recorded their verdict.
        </p>
      </FlowSection>

      {/* ───────────── Slide 9 — Literature comparison ───────────── */}
      <FlowSection
        aria-label="Literature comparison"
        style={{ backgroundColor: PAPER, color: INK_DARK }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-70">
          09 — Side by side
        </p>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Different
          <br />
          metric.
          <br />
          Different
          <br />
          ambition.
        </h2>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <div className="grid grid-cols-1 gap-[2.5vw]">
          {[
            ["MDAgents", "10 MCQ benchmarks", "Best on 7 of 10", "Real EHR-shaped records · treatment plan · doctor UI"],
            ["ZODIAC", "Real cardiology, 8 metrics", "Cardiologist-level on 7 of 8", "8 disease families, not 1 · full pipeline, not consult"],
            ["ClinicalLab", "1,500 real cases, 11 depts", "Within 5% of senior physicians", "Open-source backbone · explicit memory subsystem"],
            ["MAC Framework", "302 rare-disease cases", "Outperforms self-consistency, fewer LLM calls", "Same critique–refine + T4 case recall + doctor UI"],
            ["RareAgents", "RareBench + MIMIC-IV-Ext-Rare", "Open backbone beats GPT-4o on rare disease", "Generalist 8 families · treatment plan · clinician annotation"],
            ["CMADS (this work)", "160 Synthea patients, 8 families", "76.9% DIRECT · 94.4% Found · 64.5% Rank-1 in found", "End-to-end + open-source + memory subsystem + doctor UI"],
          ].map(([name, cohort, headline, gap], i, arr) => (
            <div
              key={name}
              className={
                "grid grid-cols-1 gap-[1vw] md:grid-cols-[1.4fr_2fr_3fr_3fr] " +
                (i === arr.length - 1 ? "border-t-2 border-black pt-[2vw]" : "")
              }
            >
              <p className={"text-[clamp(0.95rem,1.3vw,1.15rem)] font-bold uppercase tracking-wider " + (i === arr.length - 1 ? "" : "")}>
                {name}
              </p>
              <p className="text-[clamp(0.9rem,1.2vw,1.05rem)] opacity-75">{cohort}</p>
              <p className="text-[clamp(0.95rem,1.3vw,1.15rem)] font-medium">{headline}</p>
              <p className="text-[clamp(0.9rem,1.2vw,1.05rem)] opacity-90 leading-snug">{gap}</p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <p className="mt-auto max-w-[70ch] text-[clamp(1rem,1.8vw,1.6rem)] font-normal leading-relaxed italic">
          The point is not that CMADS beats them on the same metric.
          It is what those papers chose to leave out, and what CMADS chose to
          put in.
        </p>
      </FlowSection>

      {/* ───────────── Slide 10 — Gap as a sentence ───────────── */}
      <FlowSection
        aria-label="The gap, as one sentence"
        style={{ backgroundColor: NAVY, color: INK_LIGHT }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-70">
          10 — The thesis sentence
        </p>
        <hr className="my-[2vw] border-none border-t border-white/40" />
        <div className="my-auto max-w-[28ch]">
          <p className="text-[clamp(2rem,5vw,4.5rem)] font-normal leading-tight">
            Most papers prove
            <br />
            that coordination
            <br />
            helps on a
            <br />
            benchmark.
          </p>
          <p className="mt-[3vw] text-[clamp(2rem,5vw,4.5rem)] font-bold leading-tight text-[#fd5200]">
            None ship an
            <br />
            end-to-end
            <br />
            open-source
            <br />
            pipeline with
            <br />
            inspectable memory,
            <br />
            a doctor-facing
            <br />
            console, and
            <br />
            a controlled A/B —
            <br />
            in one reproducible
            <br />
            system.
          </p>
        </div>
        <hr className="my-[2vw] border-none border-t border-white/40" />
        <p className="mt-auto text-[clamp(0.9rem,1.4vw,1.2rem)] italic opacity-75">
          That sentence is what the thesis defends.
        </p>
      </FlowSection>

      {/* ───────────── Slide 11 — Limitations ───────────── */}
      <FlowSection
        aria-label="Limitations and next steps"
        style={{ backgroundColor: PAPER, color: INK_DARK }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-70">
          11 — Limits and next steps
        </p>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <h2 className="text-[clamp(2.5rem,8vw,8rem)] font-bold uppercase leading-[0.9] tracking-tight">
          Honest about
          <br />
          what is open.
        </h2>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <div className="grid grid-cols-1 gap-[3vw] md:grid-cols-2">
          {[
            ["Synthetic-only cohort", "Real EHR validation is future work."],
            ["No clinician review yet", "Annotation system exists; controlled review protocol planned."],
            ["Memory A/B underpowered", "n=20 paired, p=1.0. Target n≥80 for a settled result."],
            ["No token instrumentation", "Cost estimated (~$0.03/patient). 30-line adapter change away from measured."],
            ["Gate and judge share a model", "Disclosed in methodology, bounded by sensitivity analysis."],
          ].map(([limit, fix]) => (
            <div key={limit} className="min-w-[240px]">
              <p className="mb-2 text-sm font-bold uppercase tracking-wider text-[#c0392b]">
                {limit}
              </p>
              <p className="text-[clamp(0.95rem,1.3vw,1.15rem)] leading-relaxed opacity-90">
                {fix}
              </p>
            </div>
          ))}
        </div>
        <hr className="my-[2vw] border-none border-t border-black/30" />
        <p className="mt-auto max-w-[60ch] text-[clamp(1.2rem,2vw,1.8rem)] font-semibold leading-relaxed">
          Each limitation is a concrete next step. Thank you.
        </p>
      </FlowSection>

    </FlowArt>
  );
}

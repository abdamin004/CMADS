export function DashboardHero() {
  return (
    <section className="dashboard-hero">
      <div className="dashboard-hero__glow" aria-hidden="true" />
      <div className="dashboard-hero__body">
        <p className="eyebrow">A clinical second opinion</p>
        <h1 className="dashboard-hero__title">
          Read the patient the way you would.
        </h1>
        <p className="dashboard-hero__lede">
          We walk through the chart, weigh what's most likely going on,
          push back on the leading guess, and end up with a short list
          of diagnoses and a plan to consider, with every step laid out
          so you can decide whether to trust it.
        </p>
        <p className="dashboard-hero__hint mono">
          Pick a patient on the left to look through one.
        </p>
      </div>
    </section>
  );
}

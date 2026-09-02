// The public landing page.
//
// The single most important thing here is that the dashboard below the fold
// is not a screenshot or a mockup -- it is the real component reading real
// data from the public API. A visitor scrolling past the hero is already
// using the product, which is a far stronger claim than a picture of it.

import DecayExplainer from "./DecayExplainer";

export default function Landing({ status, children, onTrack }) {
  const commits = status?.total_commits;
  const skills = status?.distinct_skills;

  return (
    <>
      <header className="hero shell">
        <span className="pill">
          <span className="dot" />
          {commits
            ? `${commits.toLocaleString()} commits classified · updated twice daily`
            : "live data · updated twice daily"}
        </span>

        <h1>
          Your skills are <span className="decay">decaying</span> right now
        </h1>

        <p>
          Every skill you stop using fades, quietly and without telling you.
          Undrift reads your real commit history, works out which skill each
          commit exercised, and scores every one of them on a decay curve — so
          the fading is something you can see instead of something you find out
          in an interview.
        </p>

        <div className="hero-actions">
          <button onClick={onTrack}>Track your GitHub</button>
          <a href="#live">
            <button className="ghost">See it on real data ↓</button>
          </a>
        </div>
      </header>

      <section className="block shell">
        <div className="steps">
          <div className="step">
            <div className="step-num">1</div>
            <h3>Pull the commits</h3>
            <p>
              GitHub&rsquo;s API, on a schedule. Only metadata — commit
              messages and the paths of changed files. Never your source code.
            </p>
          </div>
          <div className="step">
            <div className="step-num">2</div>
            <h3>Claude labels each one</h3>
            <p>
              One skill per commit, chosen from a fixed vocabulary of{" "}
              {skills ? `${skills} seen so far` : "32"}. The model picks the
              label and explains why — it never decides what&rsquo;s stale.
            </p>
          </div>
          <div className="step">
            <div className="step-num">3</div>
            <h3>Plain arithmetic scores it</h3>
            <p>
              Exponential decay, no AI. Reproducible, inspectable, and the same
              answer every time you run it. That part is below.
            </p>
          </div>
        </div>
      </section>

      <section className="block shell" id="live">
        <p className="eyebrow">Live, not a screenshot</p>
        <h2 className="section-title">Real profiles, scored right now</h2>
        <p className="section-sub">
          These are public GitHub accounts, ingested and scored by the running
          deployment. Click any skill to see the commits behind the number and
          the classifier&rsquo;s own reasoning.
        </p>
        {children}
      </section>

      <section className="block shell">
        <p className="eyebrow">The part worth reading</p>
        <h2 className="section-title">How the decay actually works</h2>
        <p className="section-sub">
          No model decides whether a skill is stale. That is arithmetic, and
          this is all of it.
        </p>
        <DecayExplainer defaultHalfLife={status?.half_life_days ?? 60} />
      </section>
    </>
  );
}

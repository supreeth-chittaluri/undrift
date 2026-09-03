import { useCallback, useEffect, useState } from "react";
import {
  AuthError,
  getHistory,
  getProfiles,
  getSession,
  getSkills,
  getStatus,
  triggerRefresh,
} from "./api";
import { clearCredentials, getCredentials } from "./auth";
import Audit from "./components/Audit";
import Landing from "./components/Landing";
import Login from "./components/Login";
import ProfileSwitcher from "./components/ProfileSwitcher";
import SkillBars from "./components/SkillBars";
import StatusBar from "./components/StatusBar";
import SummaryTiles from "./components/SummaryTiles";
import TrendChart from "./components/TrendChart";

// Three views, and which one you get depends on whether you signed in:
//
//   landing  anonymous. The marketing page, with a real dashboard embedded in
//            it reading the public sample profiles.
//   app      signed in. The same dashboard, defaulting to the owner's data.
//   audit    the resume auditor, run against whichever profile is selected.
//
// The API decides what an anonymous caller may see, not this component. The
// frontend asks for data and renders whatever comes back; it never holds a
// list of "private" profiles it is supposed to hide, because a check that
// lives only in the browser is not a check at all.

function Nav({ authed, onSignOut, onSignIn, onAudit, onHome }) {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <a className="wordmark" href="#" onClick={onHome}>
          <span className="mark" aria-hidden="true">
            <i /><i /><i />
          </span>
          Undrift
        </a>
        <div className="nav-actions">
          <button className="ghost" onClick={onAudit}>
            Audit a résumé
          </button>
          {authed ? (
            <button className="ghost" onClick={onSignOut}>
              Sign out
            </button>
          ) : (
            <button className="ghost" onClick={onSignIn}>
              Sign in
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}

function Loading() {
  return (
    <div className="skill-list">
      {[0, 1, 2, 3].map((i) => (
        <div className="skeleton" key={i} />
      ))}
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(false);
  // "landing" | "track" | "login". The dashboard is not a view of its own --
  // it renders inside the landing page when anonymous, and on its own when
  // signed in.
  const [view, setView] = useState(() =>
    new URLSearchParams(window.location.search).has("audit") ? "audit" : "landing",
  );

  const [profiles, setProfiles] = useState([]);
  // null means "whichever profile the API considers the default" -- we don't
  // hardcode the owner's username in the frontend.
  const [selected, setSelected] = useState(null);
  const [skills, setSkills] = useState([]);
  const [history, setHistory] = useState([]);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Stored credentials might be stale, so ask the one endpoint that still
  // 401s rather than assuming they work. Runs once, before any data loads.
  useEffect(() => {
    if (!getCredentials()) return;
    getSession()
      .then(() => setAuthed(true))
      .catch(() => {
        clearCredentials();
        setAuthed(false);
      });
  }, []);

  const load = useCallback(async () => {
    try {
      const [p, s, h, st] = await Promise.all([
        getProfiles(),
        getSkills(selected),
        getHistory(selected),
        getStatus(),
      ]);
      setProfiles(p);
      // On first load the API picked the default profile for us; record which
      // one that was so the switcher can highlight it.
      if (selected === null && p.length) {
        setSelected(p.find((x) => !x.is_sample)?.username ?? p[0].username);
      }
      setSkills(s);
      setHistory(h);
      setStatus(st);
      setError(null);
    } catch (err) {
      if (err instanceof AuthError) {
        // Signing out mid-session, or a profile that turned out to be
        // private. Drop to anonymous rather than showing a dead screen --
        // the public data is still there to look at.
        setAuthed(false);
        setSelected(null);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [authed, load]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await triggerRefresh();
      await load();
    } catch (err) {
      if (err instanceof AuthError) setAuthed(false);
      else setError(err.message);
    } finally {
      setRefreshing(false);
    }
  }

  function handleSignOut() {
    clearCredentials();
    setAuthed(false);
    setSelected(null);
    setView("landing");
  }

  function handleSignedIn() {
    setAuthed(true);
    setSelected(null);
    setView("landing");
  }

  const activeProfile = profiles.find((p) => p.username === selected);

  // The dashboard proper. Rendered inside the landing page when anonymous and
  // on its own once signed in, so there is exactly one of it.
  const dashboard = (
    <>
      {profiles.length > 1 && (
        <div style={{ marginBottom: "1rem" }}>
          <ProfileSwitcher
            profiles={profiles}
            selected={selected}
            onSelect={setSelected}
          />
        </div>
      )}

      <StatusBar
        status={status}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        canRefresh={authed}
      />

      {error && <p className="error" style={{ marginTop: "1rem" }}>{error}</p>}

      {loading ? (
        <div style={{ marginTop: "1.25rem" }}>
          <Loading />
        </div>
      ) : (
        <>
          <SummaryTiles skills={skills} />

          <SkillBars skills={skills} profile={selected} history={history} />

          <div style={{ marginTop: "2.5rem" }}>
            <h2 className="section-title">Drift over time</h2>
            <p className="section-sub">
              Freshness replayed weekly over the past six months, so the trend
              is real history rather than a line that starts today.
            </p>
            <TrendChart history={history} />
          </div>
        </>
      )}
    </>
  );

  let body;
  if (view === "audit") {
    body = <Audit profile={selected} profileLabel={selected} />;
  } else if (view === "login") {
    body = (
      <Login onSuccess={handleSignedIn} onCancel={() => setView("landing")} />
    );
  } else if (authed) {
    body = (
      <main className="shell" style={{ paddingTop: "2.25rem" }}>
        <p className="eyebrow">Signed in</p>
        <h1 className="section-title" style={{ fontSize: "1.6rem" }}>
          {activeProfile?.is_sample
            ? `${activeProfile.username} — sample data`
            : "Your skills"}
        </h1>
        <p className="section-sub">
          Which of your skills are staying sharp, and which are quietly going
          stale.
        </p>
        {dashboard}
      </main>
    );
  } else {
    body = (
      <Landing status={status} onAudit={() => setView("audit")}>
        {dashboard}
      </Landing>
    );
  }

  return (
    <>
      <Nav
        authed={authed}
        onSignOut={handleSignOut}
        onSignIn={() => setView("login")}
        onAudit={() => setView("audit")}
        onHome={(e) => {
          e.preventDefault();
          setView("landing");
        }}
      />
      {body}
      <footer>
        <div className="shell">
          <span>
            freshness = 100 × w / (w + 3), where w sums each commit&rsquo;s
            decay weight of 0.5 ^ (age in days / {status?.half_life_days ?? 60})
          </span>
          <a
            href="https://github.com/supreeth-chittaluri/undrift"
            target="_blank"
            rel="noreferrer"
          >
            Source on GitHub
          </a>
        </div>
      </footer>
    </>
  );
}

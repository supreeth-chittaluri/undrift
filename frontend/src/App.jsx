import { useCallback, useEffect, useState } from "react";
import {
  AuthError,
  getHistory,
  getProfiles,
  getSkills,
  getStatus,
  triggerRefresh,
} from "./api";
import { clearCredentials, getCredentials } from "./auth";
import Login from "./components/Login";
import ProfileSwitcher from "./components/ProfileSwitcher";
import SkillBars from "./components/SkillBars";
import StatusBar from "./components/StatusBar";
import TrendChart from "./components/TrendChart";

export default function App() {
  // We can't know whether stored credentials are still valid until a request
  // is made, so this starts as "we have something to try" and the first
  // failing load flips it back to false.
  const [authed, setAuthed] = useState(() => Boolean(getCredentials()));
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

  // One loader for all three endpoints, reused on mount and after a refresh.
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
        setAuthed(false);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    if (authed) {
      setLoading(true);
      load();
    }
  }, [authed, load]);

  // The manual button is for demos. Real refreshes come from the scheduler
  // and the GitHub Actions cron -- see the README.
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
  }

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  const activeProfile = profiles.find((p) => p.username === selected);

  return (
    <div className="app">
      <header>
        <div className="header-row">
          <h1>Undrift</h1>
          <button className="ghost" onClick={handleSignOut}>Sign out</button>
        </div>
        <p className="tagline">
          Which of my skills are staying sharp, and which are quietly going stale.
        </p>
      </header>

      <ProfileSwitcher
        profiles={profiles}
        selected={selected}
        onSelect={setSelected}
      />

      <StatusBar status={status} onRefresh={handleRefresh} refreshing={refreshing} />

      {error && <p className="error">Could not reach the API: {error}</p>}
      {loading ? (
        <p className="empty">Loading…</p>
      ) : (
        <>
          <section>
            <h2>
              Freshness now
              {activeProfile?.is_sample && (
                <span className="section-note">
                  public sample data from @{activeProfile.username}
                </span>
              )}
            </h2>
            <SkillBars skills={skills} />
          </section>

          <section>
            <h2>Drift over time</h2>
            <TrendChart history={history} />
          </section>
        </>
      )}

      <footer>
        Freshness = 100 * w / (w + 3), where w sums each commit's decay
        weight of 0.5 ^ (age in days / {status?.half_life_days ?? 60}).
      </footer>
    </div>
  );
}

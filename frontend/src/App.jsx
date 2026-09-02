import { useCallback, useEffect, useState } from "react";
import { AuthError, getHistory, getSkills, getStatus, triggerRefresh } from "./api";
import { clearCredentials, getCredentials } from "./auth";
import Login from "./components/Login";
import SkillBars from "./components/SkillBars";
import StatusBar from "./components/StatusBar";
import TrendChart from "./components/TrendChart";

export default function App() {
  // We can't know whether stored credentials are still valid until a request
  // is made, so this starts as "we have something to try" and the first
  // failing load flips it back to false.
  const [authed, setAuthed] = useState(() => Boolean(getCredentials()));
  const [skills, setSkills] = useState([]);
  const [history, setHistory] = useState([]);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // One loader for all three endpoints, reused on mount and after a refresh.
  const load = useCallback(async () => {
    try {
      const [s, h, st] = await Promise.all([getSkills(), getHistory(), getStatus()]);
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
  }, []);

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

      <StatusBar status={status} onRefresh={handleRefresh} refreshing={refreshing} />

      {error && <p className="error">Could not reach the API: {error}</p>}
      {loading ? (
        <p className="empty">Loading…</p>
      ) : (
        <>
          <section>
            <h2>Freshness now</h2>
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

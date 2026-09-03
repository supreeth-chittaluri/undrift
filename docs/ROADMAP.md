# Undrift — what to do next

Handoff notes. Written after the revamp that took the project from a private
single-column dashboard to a public product with an evidence view, a résumé
auditor and a live README card.

Ordered by impact on the actual goal: **a recruiter opens the link, believes a
real engineer built this, and can tell why in ninety seconds.**

---

## 0. Where things stand

Deployed and working:

- Public read-only demo (sample profiles); owner's own profile behind Basic auth
- Skills scored on three axes — freshness (decays), depth (doesn't), momentum
- Forecast: "goes stale in 41 days" via inverting the decay curve
- Evidence drill-down: the commits behind each score, with the classifier's own
  reason and confidence, deep-linkable at `#skill=Python`
- Résumé / job-description auditor with an explicit "Not tracked" verdict,
  deep-linkable at `?audit=Python,React,AWS`
- Live SVG card at `/api/card.svg`, embedded in the README
- Batched classification on Haiku: 302 commits for ~$0.09 (was ~$1.70)

Known-unfinished, in priority order below.

---

## 1. The credibility gaps a recruiter checks first

These are cheap and they are the difference between "side project" and
"engineer who ships".

### 1.1 There are no tests — this is the biggest single gap

There are 22 doctests in `scoring.py` / `config.py` and nothing else. No
`backend/tests/`, no frontend tests, no CI. A recruiter who opens the repo
looking for engineering signal finds none.

Add `pytest` with a real suite. The highest-value targets, because they are
where the logic actually lives:

- `scoring.py` — decay/depth/momentum edge cases: empty history, a single
  commit, commits dated in the future (clock skew), `days_until_freshness`
  returning `None` when already below target, momentum's `MOMENTUM_MIN_COMMITS`
  gate.
- `skill_tagger.py` — batch response handling with a **mocked** Anthropic
  client: a short response (fewer tags than commits), duplicate indices,
  out-of-range indices, a refusal, an `APIError`. Assert the per-index fallback
  rather than whole-batch fallback. This is the most interesting code in the
  repo and it is completely untested.
- `auth.py` / `api.py` — the public/private matrix via FastAPI's `TestClient`:
  anonymous sees samples, 401s on the owner, 401s on POST, `PUBLIC_DEMO=false`
  closes everything. Table-driven.
- `audit.py` — `assess()` and `match_percentage()` with a fake session; assert
  untracked skills are excluded from the denominator.

Aim for meaningful coverage of `scoring`, `audit` and `auth`, not a percentage
target. Use `pytest` + `httpx`/`TestClient`; both are already dependencies.

### 1.2 No CI

`.github/workflows/` has only `refresh.yml` (the cron). Add `ci.yml` running on
push and PR: `ruff` (or `oxlint` equivalent for Python), `pytest`, `npm run
lint`, `npm run build`. Put the badge at the top of the README.

A green CI badge is one of the few signals a recruiter reads in under a second.

### 1.3 No LICENSE

Add MIT. A repo with no license is technically un-usable by anyone, and its
absence reads as unfinished.

### 1.4 No link preview

`frontend/index.html` has `og:title` and `og:description` but **no `og:image`**.
Paste the link into LinkedIn, Slack or a DM today and you get a bare grey box.

Fix: generate a 1200×630 PNG and reference it as `og:image` +
`twitter:card=summary_large_image`. Either commit a static one under
`frontend/public/og.png`, or serve it from the API the way `card.svg` is served
(note: most social scrapers will not render SVG, so this one needs to be a
raster).

This is a five-minute change with outsized visibility — every share of the link
is currently worse-looking than it needs to be.

### 1.5 The favicon is from the old design

`frontend/public/favicon.svg` is a purple `#863bff` mark left over from the dark
theme. It clashes with the warm palette the site now uses. Redraw it as the
three-bar decay mark (the same glyph as `.mark` in `index.css` and the header of
`card.py`) in `--fresh` / `--fading` / `--stale`.

---

## 2. The product problem: the showcase is someone else's work

**This is the most important item in this document.**

| Profile | Commits | Repos |
|---|---|---|
| tiangolo | 120 | 6 |
| sindresorhus | 107 | 6 |
| simonw | 62 | 5 |
| **supreeth-chittaluri** | **13** | **2** |

A recruiter opening the live link sees a beautifully-scored breakdown of
**Sebastián Ramírez's** skills. Yours is private, and even if it weren't, 13
commits across 2 repos would not fill the page.

Two things to fix, in order:

**2.1 Ingest your own history properly.** `MAX_REPOS=6` and
`MAX_COMMITS_PER_REPO=20` cap you at 120 commits, and you're at 13 — so the
limits aren't even the binding constraint; ingestion isn't reaching your repos.
Check `GITHUB_REPOS` and the auto-discovery path in `ingest.py`, and confirm the
token can see everything you want counted. Then raise the caps for a one-off
backfill: at Haiku prices, 500 commits is about 18 cents.

**2.2 Make your own profile publicly readable.** Right now `is_sample` does
double duty — it means both "demo data" *and* "publicly visible". Split it:

- add `is_public` to `Profile`
- `resolve_profile` gates on `is_public`, not on `is_sample`
- `is_sample` keeps its current job: labelling data as not-yours in the UI

Then set your own profile `is_public=True, is_sample=False`. Writes
(`POST /api/refresh`) stay private; only reads open up. The demo becomes *your*
skill profile, with the sample accounts as supporting comparison — which is the
right way round for a portfolio piece.

This single change does more for the "impressive to recruiters" goal than any
new feature.

---

## 3. The cold start will cost you visitors

Render's free tier sleeps after ~15 minutes idle and takes **30–60 seconds** to
wake. A recruiter clicking your link at a random hour hits a spinner for most of
a minute, and many will leave.

Options, cheapest first:

1. **Honest loading state.** The landing page currently shows shimmer
   skeletons with no explanation. Detect a slow first response (>3s) and say
   "waking the API — the free tier sleeps after 15 minutes". Visible effort
   beats a silent hang.
2. **Keep it warm.** Add a GitHub Actions cron pinging `/health` every 10
   minutes. Free, ~4,300 runs/month, well inside the free tier's 2,000 *minutes*
   if each run is a few seconds. Not elegant, and worth a comment saying so.
3. **Serve a static snapshot.** Have the refresh job write the latest scores to
   a JSON file committed to the repo; the frontend reads that instantly and
   upgrades to live data when the API responds. Best experience, most work.
4. **Pay for Render Starter ($7/mo).** Removes the problem entirely.

Pick one deliberately and say which in the README — "I know about this and here
is the tradeoff I chose" reads better than a slow site.

---

## 4. Features worth building

### 4.1 "What should I work on next" — this was planned and never built

The original plan had a ranked recommendation feed as a Tier-1 item and it did
not get built. `SummaryTiles` has a mini-version (`mostAtRisk`), but there is no
answer to "so what do I do about it".

Build it deterministically, then let Claude phrase it — the numbers stay
arithmetic:

```
regret(skill) = depth × (1 − freshness/100)
```

High depth and low freshness means you are losing something you paid for; that
is the thing worth reviving. Rank by it, take the top three, and render each as
a concrete action ("containerise one of your Python services" for Docker). One
cached Claude call per snapshot turns the ranking into sentences — the same
split the rest of the app uses.

The auditor already accepts a job description and reports a match percentage,
but produces no "highest-impact preparation" list. This closes that loop too.

### 4.2 Compare two profiles

The data is already there and multi-profile is already modelled. A side-by-side
or radar of you vs. `tiangolo` is a genuinely good visual and costs zero API
calls. Deep-link it (`?compare=a,b`) like the other views.

### 4.3 Real routing

Views are `useState` strings with two ad-hoc URL params bolted on. The browser
Back button doesn't work between the landing page, the auditor and sign-in.
Adding `react-router` (or a small hash router) fixes that and gives you
`/u/<username>` profile pages — shareable, and the natural home for the OG image
above.

### 4.4 Drop Chart.js

The bundle is 388 KB raw / 128 KB gzipped, and `chart.js` + `react-chartjs-2` is
most of it. You already hand-rolled `Sparkline.jsx`; the trend chart is the same
problem with axes and a legend. Removing the dependency would cut the bundle by
roughly two thirds and demonstrate you can draw an SVG chart rather than reach
for a library — which is the more interesting thing to show.

---

## 5. Correctness and craft

### 5.1 Momentum reads +100 on almost every sample skill

An artifact of ingestion pulling only the most recent N commits per repo, which
leaves the prior 30-day comparison window nearly empty. The maths is right and
the low-evidence gate works, but the *displayed* result is misleading on the
data actually shown.

Either ingest a longer continuous history (see §2.1), or suppress momentum when
the ingestion window can't support the comparison — the tool currently can't
tell "no activity in the prior window" from "no *data* for the prior window",
and those are the same distinction the auditor gets right with "Not tracked".

### 5.2 The rate limiter is per-process and in-memory

`_AUDIT_CALLS` in `api.py` resets on every deploy and would not hold across
replicas. Fine for one free-tier instance and documented as such, but if the
audit endpoint ever gets real traffic, move it to Redis or Postgres.

### 5.3 `audit.py` imports a private helper

`from .skill_tagger import Skill, _request_options` — reaching across a module
boundary for an underscore-prefixed function. Promote `_request_options` to a
public helper, or move it to a shared `llm.py` that both modules use.

### 5.4 Lint warning still open

`src/App.jsx:138` — `setState` called synchronously inside an effect. It's the
data-loading effect, so it's defensible, but either restructure it or add a
scoped disable with a comment explaining why. An unexplained warning in a lint
run is a small credibility leak.

### 5.5 No security headers

`frontend/vercel.json` sets rewrites only. Add `X-Content-Type-Options`,
`Referrer-Policy`, `X-Frame-Options` and a basic CSP. Cheap, and it's the kind of
thing a security-minded reviewer looks for.

### 5.6 Accessibility — colour is fixed, the rest is not

Writing this document turned up two real contrast failures introduced by the
redesign, since fixed:

| Token | Was | Now |
|---|---|---|
| `--text-faint` | `#9a9186` — **2.85:1, fails** | `#766c5e` — 4.74:1 |
| `--fading` | `#b07d16` — 3.33:1, large text only | `#8a6212` — 5.03:1 |

All six semantic/text tokens now clear 4.5:1 against `--bg`. `--text-faint`
carries real content (axis labels, SHAs, confidence percentages), so
decorative-grade contrast was not defensible.

Still outstanding, and not yet checked:

- Keyboard-only pass over the whole app — especially the skill cards (which are
  `<button>`s, so they should work) and the audit form.
- `aria-live` on the audit results, so a screen reader announces findings when
  they arrive rather than leaving them silent.
- Focus-visible styles exist on `button` but have not been verified against
  every interactive element.
- Contrast of text *on coloured chips* (`.ev-strong` etc., coloured text on a
  tinted background) — measured against `--bg`, not against the chip fill.

### 5.7 No TypeScript

The frontend is plain JSX. Converting is a day of work and is a strong signal
for frontend-leaning roles; skip it if you're targeting backend/ML.

---

## 6. Infrastructure

### 6.1 Vercel has no Git integration — deploys are manual

The project was created by CLI upload and has **no repository connected**, so
pushing to `main` does not deploy. Every release currently needs
`vercel --prod` from `frontend/`.

Fix:

```bash
cd frontend && vercel git connect
```

**Important:** the project's Root Directory is `.` because it was linked from
inside `frontend/`. Git-triggered builds run from the repo root, where there is
no `package.json`, so they will fail until you also set Root Directory to
`frontend` in Settings → General.

### 6.2 Deployment Protection

Still enabled at time of writing — every URL 302s to Vercel SSO, so the public
demo is invisible to everyone but you. Settings → Deployment Protection →
Vercel Authentication → Disabled.

### 6.3 No error tracking

No Sentry, no structured logging, no request IDs. When something breaks in
production the only signal is Render's log stream. Sentry's free tier is
generous and wiring it up is twenty minutes.

---

## 7. Deliberately not done, and why

Keep these decisions — being able to explain a *non*-feature is worth more in an
interview than another half-built one.

- **Goals and email notifications.** Both need real user accounts, which means
  real auth, which is a different project.
- **"Run it on any GitHub username."** The headline feature, deliberately cut:
  it costs roughly 4¢ per new visitor in classification and needs OAuth, a
  queue and a global spend ceiling before it can face the open internet. Worth
  building when you're willing to spend a few dollars a month.
- **Alembic migrations.** The database is a rebuildable cache of GitHub;
  `init_db()` patches in additive columns and anything larger is answered by
  dropping it. Correct call at this size.
- **Lines-changed weighting.** One commit vendoring a dependency would outweigh
  a month of real work.

---

## Suggested order

1. §2 — make your own profile the public one, with real history *(highest impact)*
2. §1.1 + §1.2 — tests and CI *(highest credibility per hour)*
3. §1.3–1.5 — LICENSE, OG image, favicon *(under an hour, all of it visible)*
4. §6.1 — reconnect Git so deploys stop being manual
5. §3 — pick a cold-start answer and document it
6. §4.1 — the recommendation feed, the one planned feature still missing
7. Everything else as time allows

# Undrift

A skill decay tracker. It pulls GitHub commit history automatically, uses
Claude to tag which skill each commit exercises, and computes a
recency-weighted freshness score per skill — so you can see which skills are
staying sharp and which are quietly going stale.

It tracks several people at once. Each tracked person is a **profile** (just a
GitHub username), and the dashboard has a switcher to move between them.
Profiles listed in `SAMPLE_PROFILES` are public accounts seeded as demo data;
they read only public information, and the UI labels them as samples so their
work is never presented as yours.

**[ARCHITECTURE.md](ARCHITECTURE.md) explains the data flow in five steps.**

```
FastAPI + SQLAlchemy + Postgres  ·  Claude API  ·  React + Vite + Chart.js
APScheduler + GitHub Actions cron  ·  Render + Vercel
```

---

## The decay formula

This is the part worth understanding, and it is deliberately plain Python —
no LLM decides whether a skill is stale.

**Step 1 — every commit decays exponentially with age.**

```
weight(commit) = 0.5 ** (age_in_days / HALF_LIFE)
```

Same shape as radioactive half-life. A commit made today counts 1.0; one made
`HALF_LIFE` days ago counts 0.5; twice that age, 0.25. It approaches zero but
never reaches it, so skills fade smoothly instead of falling off a cliff on an
arbitrary cutoff date.

`HALF_LIFE` is 60 days by default. That's a judgement call: short enough that
a skill dropped last quarter visibly fades, long enough that a two-week
holiday doesn't tank the score.

| Commit age | Weight |
|---|---|
| today | 1.000 |
| 30 days | 0.707 |
| 60 days | 0.500 |
| 180 days | 0.125 |
| 1 year | 0.015 |

**Step 2 — a skill's raw weight is the sum of its commits' weights.**

```
raw_weight(skill) = Σ weight(commit) for every commit tagged with that skill
```

Summing is what folds in **frequency** as well as **recency**. One commit last
week scores lower than ten commits last week, because ten near-1.0 weights add
up. Both factors fall out of a single sum rather than needing two terms bolted
together.

**Step 3 — squash it onto a 0–100 scale.**

```
freshness(skill) = 100 * raw_weight / (raw_weight + 3.0)
```

`raw_weight` is unbounded but a progress bar needs 0–100. This curve rises
steeply at first and flattens as it approaches 100, so the gap between "never"
and "occasionally" shows up strongly while the gap between "a lot" and "a
whole lot" barely moves the bar — which is what you actually want, since past
a point more commits don't make you sharper.

The constant `3.0` is what gives the score its meaning: **a skill whose
decayed weight equals 3.0 — roughly three commits in the last few days — sits
at exactly 50/100.**

The scale is **absolute, not a ranking**. Scores aren't normalised against the
best skill, so if I stop coding entirely every bar drops toward zero together.
Normalising would always pin something at 100 and hide the very drift this
exists to show.

Deliberately *not* included: lines changed. Weighting by diff size would let
one commit that vendored a dependency outweigh a month of real work.

The formula lives in [`backend/app/scoring.py`](backend/app/scoring.py) with
doctests covering the curve.

---

## Running it locally

**Prerequisites:** Python 3.12+, Node 20+.

```bash
git clone https://github.com/supreeth-chittaluri/undrift.git
cd undrift
cp .env.example .env     # then fill it in — see below
```

Set up the backend:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
```

Fill in `.env`. The four that matter:

| Variable | What to put there |
|---|---|
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |
| `GITHUB_TOKEN` | A **fine-grained** token — see the security note below |
| `APP_USERNAME` / `APP_PASSWORD` | Anything; the API refuses to serve without them |
| `SAMPLE_PROFILES` | Optional. Public GitHub usernames to seed as demo profiles |

Run the API:

```bash
./.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

And the dashboard, in a second terminal:

```bash
npm --prefix frontend install && npm --prefix frontend run dev
```

Open http://localhost:5173 and sign in with `APP_USERNAME` / `APP_PASSWORD`.
The first refresh pulls your commits, tags them, and backfills six months of
history so the trend chart has something to draw.

To run the pipeline once from the command line instead:

```bash
PYTHONPATH=backend ./.venv/bin/python -c "from app.db import SessionLocal, init_db; from app.pipeline import run_refresh; init_db(); print(run_refresh(SessionLocal(), 'manual'))"
```

---

## API

Every route requires HTTP Basic auth except `/health`.

Endpoints that report on a person take an optional `?profile=<username>`.
Omitting it falls back to the owner profile — the first non-sample one.

| Route | Returns |
|---|---|
| `GET /health` | Liveness — the only public route, so Render can probe it |
| `GET /api/profiles` | Everyone being tracked, with commit counts and sample flags |
| `GET /api/skills?profile=` | Current freshness per skill, with the change since the last snapshot |
| `GET /api/skills/history?weeks=26&profile=` | Freshness over time, for the trend chart |
| `GET /api/commits?limit=50&profile=` | Recent commits and how each was tagged |
| `GET /api/status` | Row counts and the last sync run |
| `POST /api/refresh?trigger=cron` | Runs ingest → tag → score |

Interactive docs at `/docs` (also behind auth).

---

## How it stays up to date

Two mechanisms, because one isn't enough:

- **APScheduler** runs inside the API process every `REFRESH_INTERVAL_HOURS`.
  Clean, but it only works while the process is awake.
- **A GitHub Actions cron** ([`.github/workflows/refresh.yml`](.github/workflows/refresh.yml))
  POSTs to `/api/refresh` at 06:00 and 18:00 UTC.

Render's free tier sleeps after ~15 minutes idle, and a sleeping process can't
fire its own timer — so in production `ENABLE_SCHEDULER=false` and the cron is
what actually drives ingestion. The pipeline is idempotent, so an extra run
costs almost nothing: ingestion skips SHAs it already has and tagging skips
commits it already tagged.

---

## Deploying it privately

Three free accounts, roughly 20 minutes. Do them in this order — each step
produces a value the next one needs.

### 1. Database — Neon

Create a project at [neon.tech](https://neon.tech) and copy the connection
string. `postgres://` and `postgresql://` both work; the app rewrites either
to `postgresql+psycopg://` itself, so paste it unchanged. That rewrite is not
cosmetic — SQLAlchemy resolves a bare `postgresql://` to psycopg2, which this
project doesn't install, so without it the app dies at startup.

Use the **pooled** endpoint (the one with `-pooler` in the host). Neon runs
PgBouncer in transaction mode, which historically broke Python drivers that
use protocol-level prepared statements — but Neon's PgBouncer is 1.22+ and
psycopg 3.2+ handles it, so no `prepare_threshold` workaround is needed. If
you ever see `prepared statement "..." already exists`, that assumption has
broken; the fix is `connect_args={"prepare_threshold": None}` in `db.py`.

The schema is created by `create_all()` on startup, so there is no separate
migration step to point at a direct connection.

### 2. Backend — Render

1. **New → Web Service**, connect this repo. Render reads `render.yaml`.
2. Fill in the secrets it prompts for:
   `DATABASE_URL` (from step 1), `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`,
   `APP_USERNAME`, `APP_PASSWORD`, and `SAMPLE_PROFILES`.
   Leave `ALLOWED_ORIGINS` blank for now — you get that value in step 3.
3. Wait for the first deploy, then confirm it's alive:
   `curl https://<your-service>.onrender.com/health`

The first refresh classifies every ingested commit, so expect it to take a
few minutes and cost a couple of dollars in Claude calls. Every run after
that only touches genuinely new commits.

### 3. Frontend — Vercel

1. **Add New → Project**, import this repo, set **Root Directory** to
   `frontend`.
2. Add environment variable `VITE_API_URL` = your Render URL (no trailing
   slash).
3. Deploy. Vercel gives you a URL like `undrift.vercel.app`.

### 4. Close the loop

- Back on Render, set `ALLOWED_ORIGINS` to your exact Vercel URL and redeploy.
  Without this the browser blocks every API call as a CORS violation.
- In this repo: **Settings → Secrets and variables → Actions**, add
  `UNDRIFT_API_URL`, `UNDRIFT_USERNAME`, `UNDRIFT_PASSWORD` so the cron can
  authenticate. Trigger it once by hand from the **Actions** tab to prove it
  works.

### What "private" actually means here

Verified against the live deployment, not just read off the docs:

| URL | Unauthenticated result |
|---|---|
| `undrift-<hash>-<team>.vercel.app` (immutable deployment) | `302` → Vercel SSO |
| `undrift-<team>.vercel.app` (production alias) | `302` → Vercel SSO |

So on the Hobby plan, with **no custom domain attached**, every URL this
project has is gated behind Vercel Authentication — only your own Vercel
account gets through. Vercel's docs describe Standard Protection as leaving
"production domains" public, and that is true, but it means *custom* domains
you attach yourself. The auto-generated `.vercel.app` production alias counts
as a generated deployment URL and is protected.

The practical consequence: **don't add a custom domain** unless you upgrade to
Pro. Attaching one is exactly the step that would make the dashboard publicly
reachable.

Defence in depth is still worth having, because Vercel protection only guards
the static page:

| Layer | Protection | Cost |
|---|---|---|
| Vercel (all generated URLs) | Vercel Authentication — your account only | free |
| Render API | HTTP Basic on every route except `/health` | free |
| Search engines | `noindex` meta + `robots.txt` disallow | free |

Even if the page were reachable, it renders only a login form — every byte of
data comes from the Render API, which rejects unauthenticated requests.

For the demo video, sign in to Vercel in your browser first, then open the
production alias; you will pass straight through.

## Security notes

**Use a fine-grained GitHub token.** Undrift only ever issues `GET` requests
against the commits API. Give it a fine-grained token with **Contents:
Read-only** and **Metadata: Read-only** and nothing else. A classic token with
full `repo` scope — let alone `admin:org` or `delete_repo` — hands far more
authority to an environment variable than this app has any use for.

**Credentials in the browser.** HTTP Basic means the dashboard has to hold the
username and password to replay them on each request; they're kept in
`sessionStorage`, so they're dropped when the tab closes. Anything the browser
can replay is readable by scripts on the page — an acceptable tradeoff for a
single-user private dashboard, but not the design a multi-user product should
use. That would want real tokens and a session cookie.

**Schema changes mean drop and re-ingest.** There is no migration tooling
here, deliberately: the database is a cache, not the source of truth.
Everything in it can be rebuilt from GitHub by deleting it and running a
refresh. That's a real tradeoff — a production multi-tenant app would want
Alembic — but for this the simpler answer is the honest one.

**A first sync costs real money.** Each newly ingested commit is one Claude
call. Seeding three prolific sample profiles (~300 commits) cost roughly
$1.70 on `claude-opus-5`. Later runs are nearly free, since only genuinely
new commits get classified. `MAX_REPOS` and `MAX_COMMITS_PER_REPO` are the
levers if you want to spend less.

**Nothing secret is committed.** `.env` is gitignored, `.env.example` ships
with empty values, and `render.yaml` marks every secret `sync: false` so
Render prompts for it instead of reading it from the repo.

---

## Project layout

```
backend/app/
  config.py         settings from environment variables
  models.py         profiles, repos, commits, skill_scores, sync_runs
  github_client.py  the four GitHub calls the app needs
  ingest.py         pull commits, skip SHAs already stored
  skill_tagger.py   Claude call, schema-validated, with a fallback
  scoring.py        the decay formula
  pipeline.py       ingest → tag → score, logged to sync_runs
  scheduler.py      the in-process timer
  auth.py           HTTP Basic middleware
  api.py            the endpoints
frontend/src/
  App.jsx           layout and data loading
  api.js            every backend call, in one place
  components/       Login, ProfileSwitcher, SkillBars, TrendChart, StatusBar
```

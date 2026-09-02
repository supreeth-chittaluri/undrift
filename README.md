# Undrift

A skill decay tracker. It pulls my GitHub commit history automatically, uses
Claude to tag which skill each commit exercises, and computes a
recency-weighted freshness score per skill — so I can see which skills are
staying sharp and which are quietly going stale.

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

| Route | Returns |
|---|---|
| `GET /health` | Liveness — the only public route, so Render can probe it |
| `GET /api/skills` | Current freshness per skill, with the change since the last snapshot |
| `GET /api/skills/history?weeks=26` | Freshness over time, for the trend chart |
| `GET /api/commits?limit=50` | Recent commits and how each was tagged |
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

The goal is that only I can reach it. The two halves are protected differently
because they're different kinds of target.

### Backend → Render

1. New → Web Service → connect this repo. Render reads `render.yaml`.
2. Create a free Postgres database ([Neon](https://neon.tech) or
   [Supabase](https://supabase.com)) and copy its connection string. Both
   `postgres://` and `postgresql://` URLs work — the app rewrites them to the
   psycopg driver itself.
3. Set the secrets Render prompts for: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`,
   `DATABASE_URL`, `APP_USERNAME`, `APP_PASSWORD`, and `ALLOWED_ORIGINS`
   (your Vercel URL, once you have it).

The backend is public on the internet but every route except `/health` sits
behind HTTP Basic, enforced by middleware rather than per-route decorators —
so a new endpoint is protected the moment it's added, instead of being
silently public if the decorator is forgotten. It fails closed: with no
credentials configured it returns 503 rather than serving openly.

### Frontend → Vercel

1. New Project → import this repo → set **Root Directory** to `frontend`.
2. Set `VITE_API_URL` to the Render URL.
3. Leave **Deployment Protection** on its default (Standard Protection). On
   the free plan this restricts access to my own logged-in Vercel account,
   which is what keeps the dashboard from being found by anyone else. No paid
   password-protection add-on is needed.

Then add three repository secrets under **Settings → Secrets and variables →
Actions** so the cron can authenticate: `UNDRIFT_API_URL`,
`UNDRIFT_USERNAME`, `UNDRIFT_PASSWORD`.

Because Vercel's protection gates the dashboard to my own account, the plan is
to show this to people via a screen recording rather than a live link.

---

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

**Nothing secret is committed.** `.env` is gitignored, `.env.example` ships
with empty values, and `render.yaml` marks every secret `sync: false` so
Render prompts for it instead of reading it from the repo.

---

## Project layout

```
backend/app/
  config.py         settings from environment variables
  models.py         repos, commits, skill_scores, sync_runs
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
  components/       Login, SkillBars, TrendChart, StatusBar
```

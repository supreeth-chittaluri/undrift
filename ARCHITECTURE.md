# How Undrift works

## The five steps

**1. Commits come in from GitHub.**
Undrift tracks a list of people — each one is a *profile*, which is just a
GitHub username. For every profile, a scheduled job asks the GitHub API for
the commits that person authored in the last two years, discovering their
repositories itself rather than reading a hand-maintained list. Each commit is
stored with its message, its changed files, and which profile wrote it.
Commits are keyed by their SHA, so running this again only picks up what's new.

**2. Claude labels each commit with one skill.**
For every commit that doesn't have a label yet, the app sends the commit
message and the changed filenames to the Claude API and asks: which single
skill does this commit primarily exercise? The answer has to come back as
JSON matching a fixed schema, and the skill has to be one of about thirty
allowed values. The label, the model's confidence, and its one-line reason
all get written back onto the commit row — the reason is what lets the
dashboard show *why* a commit counted toward a skill.

Commits go up in batches of twenty-five rather than one at a time. A single
commit is a few dozen tokens of message and filenames wrapped in a system
prompt several times that size, so one call per commit spends most of its
money re-sending the same instructions.

**3. Plain Python computes the freshness scores.**
This is arithmetic, not AI. Every commit decays exponentially with age: worth
1.0 the day it's made, 0.5 after sixty days, 0.25 after a hundred and twenty.
A skill's score is the sum of its commits' decayed weights, squashed onto a
0–100 scale. Commit often and recently, and a skill stays near the top. Stop
touching it, and it slides toward zero on its own.

**4. Postgres stores the commits and a history of scores.**
Scores aren't overwritten. Every scoring run appends a new dated snapshot of
every skill for every profile, so the database accumulates a record of how
each skill's freshness moved over time — which is what the trend chart draws.
Scoring is always scoped to one profile, so two people's commits never get
summed into the same curve.

**5. The dashboard reads it, and a cron keeps it current.**
A React app fetches the latest snapshot for the selected profile and renders a
bar per skill, faded in proportion to how stale it is, plus a line chart of the
history. A switcher at the top swaps between profiles. Nobody has to press
anything: a GitHub Actions cron hits the refresh endpoint twice a day, which
runs steps 1 through 4 again.

---

## The one-sentence version

GitHub gives me commits for each tracked person, Claude labels each one with a
skill, exponential decay math turns those labels into a freshness score per
person, Postgres keeps every snapshot so I can see the trend, and a cron runs
the whole thing twice a day.

---

## Why some of the choices were made

**Why the LLM only labels, and never scores.**
The obvious shortcut would be to ask Claude "does this skill seem stale?" That
would be unreproducible — the same data could give different answers on
different days, and I couldn't explain any individual number. Splitting the
work means the model does the part that genuinely needs judgement (reading a
diff and naming the skill) and Python does the part that needs to be exact.

**Why the skill vocabulary is a fixed list.**
If the model could answer freely, it would return "Python", "python3" and
"Py" on different commits. Those would become three separate skills, each
with a third of the evidence, and every decay curve would be wrong. The
allowed values are baked into the JSON schema as an enum, so the API itself
rejects anything else, and the app re-checks the value before storing it.

**Why the score is absolute, not a ranking.**
Scores aren't normalised against my best skill. If they were, something would
always sit at 100 even if I hadn't written code in a year. On an absolute
scale every bar can fall at once — which is exactly the drift the app exists
to show.

**Why there are two scheduling mechanisms.**
APScheduler runs inside the API process on a timer. That works anywhere the
process stays awake, but the free hosting tier puts the service to sleep after
about fifteen minutes idle, and a sleeping process can't fire its own timer.
The GitHub Actions cron calls the service from outside, which wakes it. The
scheduler is the clean answer; the cron is the one that survives free hosting.

**Why sample profiles exist, and why they're labelled.**
My own account has very few commits, so my curves alone would be a flat line
near zero — technically correct and useless as a demonstration. Undrift also
tracks a few prolific *public* GitHub accounts, which gives real multi-language
decay curves to look at. They only ever read public data, they're flagged
`is_sample` in the database, and the dashboard prints "public sample data from
@username" above their scores so their work is never presented as mine.

**Why history can be drawn on day one.**
A score for any date is a pure function of the commits that existed by then,
so on a fresh database the app replays the same formula at weekly intervals
over the past six months. That's reconstructed from real commit dates, not
invented — and where a skill didn't exist yet, the chart leaves a gap rather
than drawing a zero.

---

## The pieces

```
GitHub API ──▶ ingest.py ──▶ ┌──────────┐   (one row per profile
                             │  commits │    per commit)
Claude API ──▶ skill_tagger ▶└──────────┘
                                   │
                             scoring.py  (exponential decay)
                                   │
                             ┌──────────────┐
                             │ skill_scores │  one snapshot per run
                             └──────────────┘
                                   │
                              api.py (FastAPI)
                                   │
                          React dashboard (Vercel)

    pipeline.py runs all of the above, triggered by
    APScheduler (in-process) or GitHub Actions cron (external)
```

| File | What it does |
|---|---|
| `config.py` | Reads every setting from environment variables |
| `models.py` | Five tables: profiles, repos, commits, skill_scores, sync_runs |
| `github_client.py` | The four GitHub API calls the app needs |
| `ingest.py` | Pulls commits, skipping SHAs already stored |
| `skill_tagger.py` | Claude call, schema-validated, with a fallback tagger |
| `scoring.py` | The decay formula — the interesting file |
| `pipeline.py` | Runs ingest → tag → score, logs the run |
| `scheduler.py` | The in-process timer |
| `auth.py` | HTTP Basic across every route except `/health` |
| `api.py` | The endpoints the dashboard calls |

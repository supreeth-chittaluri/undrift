# Undrift

A full-stack skill decay tracker: pulls my GitHub commit history automatically,
uses an LLM to tag which skill each commit touches, and computes a
recency-weighted "freshness" score per skill so I can see what's staying
sharp vs. going stale.

Status: scaffolding only — the actual build happens in a Claude Code session
using the project prompt.

See `.env.example` for the environment variables you'll need before running
anything (Anthropic API key, GitHub token, database URL).

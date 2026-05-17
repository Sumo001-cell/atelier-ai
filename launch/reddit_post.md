# Reddit r/SaaS + r/sideproject + r/programming launch

## Title (60–80 chars)
Atelier AI: 7-agent autonomous income pipeline (open source, Claude Code)

## Body

Spent 6 hours wiring together the "one-person AI agency" concept: scout leads → score → build deliverable → pitch → audit → draft PR → check → report — all running 24/7 inside Claude Code through a SQLite state machine.

Why this exists: most agent demos stop at "LLM calls a tool." Real income-generating pipelines need crash-safe state, stealth scraping (Cloudflare-protected sources), security gates before anything leaves the box, and rate-limited outreach.

**Stack:**

- Orchestrator: SQLite WAL + BEGIN IMMEDIATE for race-free counters
- Scraping: CloakBrowser (drop-in Playwright with source-level fingerprint patches)
- Security scanners: bandit + semgrep + slither + mythril
- API surface: FastAPI (Scrape API + Landing Generator)
- Outreach: Gmail SMTP + Telegram + draft fallback when creds missing
- Code reviewed 5x — closed 4 CRITICAL + 7 HIGH

**What's included:**

1. Smart Contract Auditor — Code4rena-format markdown report, allow-listed clone hosts
2. Scrape API — per-key daily quota, SSRF block on private/loopback/link-local IPs
3. Landing Generator — editorial template, four themes, HTML-escaped customer input, webhook-secret protected /paid endpoint

**All credentials via env** — bank account, PayPal handle, email, phone are env-driven. Nothing committed.

Repo: https://github.com/Sumo001-cell/atelier-ai (MIT)

Looking for feedback on:
- Where does the orchestrator pattern break down at scale?
- Anyone running a similar pipeline through Cursor/Codex instead of Claude Code?
- Best practices for filtering bandit/semgrep false positives?

Open to PRs.

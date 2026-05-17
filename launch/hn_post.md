# Show HN launch post

## Title (max 80 chars)
Show HN: Atelier AI – 7-agent autonomous income pipeline (Claude Code, MIT)

## URL
https://github.com/Sumo001-cell/atelier-ai

## Text (HN body)
Most agent demos stop at "LLM calls one tool." Real income-generating pipelines need crash-safe state, stealth scraping, security gates, rate-limited outreach, and quality control. Atelier wires those concerns together in ~2.5k lines of Python.

7 cooperating agents through a SQLite state machine:

  Scout (public + JS-rendered + regional feeds) → Diagnoser (scoring + pitch) → Builder (template render) → Pitcher (Gmail/Telegram multi-channel) → Auditor (bandit/semgrep/slither) → PR-drafter (gh CLI fork+branch+draft) → Checker (secret scan + size guard) → SupportBot (heartbeat).

Three production services come with the harness:

- Smart Contract Auditor — slither + mythril wrapper, Code4rena-format markdown, allow-listed clone hosts, path-resolved local files
- Scrape API (FastAPI) — per-key daily quota with BEGIN IMMEDIATE atomic counter; SSRF block validates scheme + DNS-resolved IP (rejects private/loopback/link-local/reserved/multicast/unspecified)
- Landing Generator (FastAPI) — editorial template, four themes, html.escape on every customer field, /paid endpoint protected by constant-time webhook secret comparison

Five rounds of code review caught and closed 4 CRITICAL (XSS, /paid auth, SSRF, hardcoded credentials) + 7 HIGH (SQLite race, path traversal, clone allow-list, stage transition ignoring failure, duplicate-send on retry, log handle leak, theme injection latent surface). All env-driven config; no credential hardcoded.

Built with Claude Opus 4.7 in ~6 hours. Looking for feedback on:

- agent boundary design (one orchestrator + small agents vs. one big agent + sub-tools)
- false-positive filter heuristics (currently regex over source — naive)
- cross-harness portability (does this hold up under Cursor/Codex/OpenCode?)

Repo: https://github.com/Sumo001-cell/atelier-ai (MIT)
Architecture diagram + env table in README.

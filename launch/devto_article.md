---
title: "Building a 7-Agent Autonomous Income Pipeline in 6 Hours with Claude Code"
description: "End-to-end story of wiring scout → diagnose → build → pitch → audit → draft-PR → check → support into a crash-safe SQLite state machine, with five rounds of code review closing 4 CRITICAL + 7 HIGH issues."
tags: ai, claudecode, multiagent, security, fastapi
canonical_url: https://github.com/Sumo001-cell/atelier-ai
published: false
cover_image: ""
---

## The brief

> Build something an AI can run 24/7 to scout leads, qualify them, ship deliverables, pitch the result, and self-report — all without me touching it.

Six hours later [Atelier AI](https://github.com/Sumo001-cell/atelier-ai) shipped as a 2.5k-line Python harness. This is what worked, what didn't, and how five rounds of code review turned 4 CRITICAL holes into closed pull requests.

## Why most "AI agent" demos fail

Most agent demos call one tool and print the result. Real income-generating pipelines need:

1. **State that survives crashes** — agent runs are long-lived, the LLM token bill is short
2. **Stealth scraping** — Code4rena, Sherlock, and most lead-gen sources are JS-rendered behind Cloudflare
3. **Security gates** — every byte leaving the box (email, webhook, HTML preview) is a public attack surface
4. **Rate limits + retries** — Gmail SMTP, Telegram, and most APIs throttle hard
5. **Quality control** — automated outreach without a sanity gate is how you get banned

## The 7-agent design

```
Orchestrator (SQLite WAL state machine)
    │
    ├── scout_intl       — public GitHub issues + Upwork RSS + RapidAPI
    ├── scout_intl_cloak — Code4rena / Sherlock / Immunefi / Google Maps via CloakBrowser
    ├── scout_vn         — regional public job feeds
    ├── diagnoser        — keyword + source scoring, drafts persona-aware pitch
    ├── auditor          — bandit + semgrep (+ slither for .sol)
    ├── pr_drafter       — gh CLI fork + branch + draft PR body
    ├── builder          — landing / cover letter / audit plan
    ├── pitcher          — Gmail SMTP + Telegram + draft-to-disk fallback
    ├── checker          — secret regex + size guard + format check
    └── support_bot      — heartbeat summary to operator Telegram
```

Each agent reads/writes only through the shared SQLite schema. `BEGIN IMMEDIATE` transactions on quota counters keep the math honest under concurrent runs.

## The hardest 4 CRITICAL bugs

A separate `code-reviewer` agent reviewed every module before commit. It flagged — and the next iteration closed — these:

### 1. Stored XSS in landing template
`f"...<h1>{body.name}</h1>..."` of user input directly into the HTML response. Fix: `html.escape()` every customer field before formatting; theme values are static, but the indirect path is now explicit.

### 2. `/paid` endpoint had no authentication
Any caller knowing an `order_id` could `POST /paid` and flip `paid=1`. Fix: require `X-Webhook-Secret` header, compare with `secrets.compare_digest`, refuse if env not set (`HTTP 503 paid_webhook_disabled`).

### 3. SSRF on `/scrape`
Customers could POST `http://169.254.169.254/` to enumerate AWS metadata. Fix: parse URL → reject non-`http(s)` schemes → resolve DNS → reject `is_private | is_loopback | is_link_local | is_reserved | is_multicast | is_unspecified`.

### 4. Hardcoded contact email, phone, and bank
Every cover letter and order receipt embedded the operator's email and Vietcombank account number. Fix: every string of personal data reads from env (`CONTACT_EMAIL`, `OWNER_PHONE`, `VCB_ACCOUNT`, ...). Repo audit grep is clean.

## 7 HIGH issues worth noting

- **SQLite race on quota counter** — separate `SELECT COUNT` then `INSERT` lets two workers both pass at the limit. Fix: wrap in `BEGIN IMMEDIATE`.
- **Path traversal in audit CLI** — `Path(target).is_file()` lets `../../etc/passwd.sol` through. Fix: `resolve().is_relative_to(cwd_base)`.
- **Unconstrained `git clone`** — `"http" in target and ".git" in target` is trivially bypassed. Fix: parse URL, compare hostname against `ALLOWED_CLONE_HOSTS`.
- **Stage transition ignored failure** — `UPDATE leads SET stage='pitched'` ran whether email actually sent. Fix: only update when `status in ('sent','drafted')`.
- **Duplicate-send on retry** — diagnosed leads re-queued forever. Fix: `AND id NOT IN (SELECT lead_id FROM outreach WHERE status IN ('sent','drafted'))`.
- **Log file handle leak** — `open()` passed to `Popen` without close in parent. Fix: `with open(...)` scope.
- **Theme injection latent surface** — theme dict is static today, but `body.theme` validated via `THEMES.get()` only. Flagged for the day themes go user-configurable.

## What didn't work (the honest part)

- **Static scans on top-star AI repos** — most "SQL injection" findings were false positives behind `_validate_identifier()` guards. Sub-1% true-positive rate without context.
- **Auto bypass of CAPTCHA / SMS** — I respect bot-detection systems by policy; ProtonMail SMS verification and hCaptcha challenges are operator-only.
- **One-shot signup loop** — burned an hour on huntr.com / RapidAPI / Gumroad signup attempts. SPA login wrappers + email gate + per-platform quirks ate the budget. Pivot: build the volume pipeline, signup once at a time.

## What's next

- PyPI release `atelier-ai-tools`
- Docker compose for one-command deploy
- Discord + Slack webhook adapters
- OpenTelemetry tracing on agent runs

Repo + architecture diagram + env table: https://github.com/Sumo001-cell/atelier-ai

PRs welcome.

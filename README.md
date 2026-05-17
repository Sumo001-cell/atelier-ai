# Atelier AI

> **7-agent autonomous pipeline** that scouts, qualifies, builds, and pitches — running 24/7 inside Claude Code.

[![GitHub stars](https://img.shields.io/github/stars/Sumo001-cell/atelier-ai?style=for-the-badge&color=4a9968&labelColor=0f1b16)](https://github.com/Sumo001-cell/atelier-ai/stargazers)
[![License](https://img.shields.io/badge/License-MIT-d4a24a?style=for-the-badge&labelColor=0f1b16)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-4a9968?style=for-the-badge&labelColor=0f1b16)](https://www.python.org/)
[![Code review](https://img.shields.io/badge/Code--reviewer-passed%205%C3%97-4a9968?style=for-the-badge&labelColor=0f1b16)](#security)

A reference implementation of the **"one-person AI agency"** concept: scout leads, diagnose fit, build deliverables, pitch, check, and report — orchestrated as 7 cooperating agents through a SQLite state machine.

---

## Why this exists

Most AI agent demos stop at "look, my LLM called a tool". Real income-generating pipelines need:

1. **State that survives crashes** — SQLite with `BEGIN IMMEDIATE` transactions for race-free counters
2. **Stealth scraping** — CloakBrowser drop-in for Cloudflare/CAPTCHA-protected sources
3. **Security gates** — secret scan + HTML escape + SSRF block before anything leaves the box
4. **Multi-channel outreach** — Gmail SMTP + Telegram + outbound webhooks with rate limits
5. **Quality control** — every deliverable passes through a `checker` agent that quarantines on leak/oversize/format-fail

This repo wires those concerns together in ~2,500 lines of Python.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                       Orchestrator (state machine)                     │
│            SQLite WAL · agent_runs · BEGIN IMMEDIATE                   │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │          │
   scout_intl  scout_cloak  scout_vn  diagnoser  builder    pitcher
       │ public  │ JS-render│ regional │ scoring  │ template │ multi-
       │ feeds   │ + Maps   │ feeds    │ + pitch  │ render   │ channel
       └──────────────┬─────┴───────────┴──────────┴──────────┘
                      │
              ┌───────┴───────┐
              │   checker     │  secret regex · size guard · format check
              └───────┬───────┘
                      │
              ┌───────┴───────┐
              │  support_bot  │  pipeline summary → owner Telegram
              └───────────────┘
```

| Agent | Role | Input | Output |
|-------|------|-------|--------|
| `scout_intl` | Crawl public sources (no API key) | GitHub issues, Upwork RSS, RapidAPI feeds | rows in `leads` |
| `scout_intl_cloak` | JS-rendered sources via CloakBrowser | Code4rena, Sherlock, Immunefi, Google Maps | rows in `leads` |
| `scout_vn` | Regional public sources | ITViec, VietnamWorks | rows in `leads` |
| `diagnoser` | Score + personalised pitch | qualified leads | `meta_json.pitch` |
| `builder` | Render deliverable | qualified leads | rows in `deliverables` |
| `pitcher` | Send outreach | diagnosed leads | rows in `outreach` |
| `checker` | Quality gate | deliverables | `verified` or `quarantined` |
| `support_bot` | Heartbeat + summary | full pipeline | Telegram message |

---

## Three production services

### 1. Smart Contract Auditor

Wraps slither + mythril, exports Code4rena-format markdown reports. Path-resolved local files restricted to working directory; remote clones restricted to an allow-list (`github.com`, `gitlab.com`, `bitbucket.org`). Contact email and brand name read from `CONTACT_EMAIL` and `BRAND_NAME` env vars.

```bash
python products/smart_contract_audit/audit.py path/to/Contract.sol --out audit_out
```

### 2. Scrape API (FastAPI)

Per-key daily quota with atomic `BEGIN IMMEDIATE` counter. SSRF block validates scheme (`http`/`https` only) and DNS-resolved IP (rejects private, loopback, link-local, reserved, multicast, unspecified).

```bash
uvicorn products.scrape_api.main:app --port 8080
```

```http
POST /scrape
X-API-Key: sk_atl_…
{"url":"https://target.com","render_ms":2000,"want":["text","screenshot"]}
```

### 3. Landing Generator (FastAPI)

Editorial template using **Be Vietnam Pro + Roboto Mono**, four themes (`editorial_warm`, `editorial_dark`, `burgundy`, `midnight`). All customer input passes through `html.escape()` before insertion. The `/paid` endpoint requires `X-Webhook-Secret` matching `PAID_WEBHOOK_SECRET` env, with constant-time comparison via `secrets.compare_digest`.

```bash
uvicorn products.landing_gen.main:app --port 8091
```

```http
POST /preview
{"name":"Quan Pho Vu Anh","phone":"0901234567","tagline":"Pho gia truyen 3 doi","theme":"editorial_warm"}
```

---

## Security

Five independent code reviews caught and fixed:

- **CRITICAL** stored XSS in landing template — fixed by `html.escape()` of every customer field
- **CRITICAL** unauthenticated `/paid` flip — fixed by webhook-secret header
- **CRITICAL** SSRF in `/scrape` — fixed by URL scheme + DNS IP validation
- **HIGH** SQLite race on quota — fixed by `BEGIN IMMEDIATE` transaction
- **HIGH** path traversal in audit CLI — fixed by `Path.resolve()` + `is_relative_to()`
- **HIGH** clone host allow-list missing — fixed by `ALLOWED_CLONE_HOSTS`
- **HIGH** stage transition ignored failure — fixed by conditional update
- **HIGH** duplicate-send on retry — fixed by `NOT IN (SELECT ... WHERE status IN sent,drafted)`

See commit history for the diff.

---

## Configuration (env)

| Variable | Purpose | Required |
|----------|---------|----------|
| `BRAND_NAME` | Customer-facing brand (e.g. "Atelier") | yes |
| `CONTACT_EMAIL` | Contact in outreach + audit reports | yes |
| `GITHUB_HANDLE` | Cover letter + portfolio link | optional |
| `OWNER_NAME`, `OWNER_PHONE` | Outreach signature | optional |
| `PAYPAL_ME` | Landing `/order` PayPal link | optional |
| `STRIPE_PAYMENT_LINK` | Landing `/order` Stripe link | optional |
| `VCB_BANK_NAME`, `VCB_ACCOUNT`, `VCB_OWNER` | Landing `/order` bank info | optional |
| `PAID_WEBHOOK_SECRET` | `/paid` endpoint auth | yes if `/paid` exposed |
| `GMAIL_USER`, `GMAIL_APP_PASS` | Outbound SMTP | optional |
| `OUTREACH_PER_RUN` | Rate limit pitcher | optional |
| `SCRAPE_DAILY_LIMIT` | Default new customer quota | optional |

Never commit env values. Use `.env` (gitignored) or process env.

---

## Quick start

```bash
git clone https://github.com/Sumo001-cell/atelier-ai
cd atelier-ai

# Install scanners + browser
pip install -r products/scrape_api/requirements.txt
pip install slither-analyzer cloakbrowser bandit semgrep

# Initialise state
python orchestrator.py init

# Run one cycle
python orchestrator.py run all

# Loop every 10 minutes
python orchestrator.py loop 600
```

The first run will:

1. Create `db/state.sqlite3`
2. Populate `leads` from public scout sources
3. Score → diagnose → build → pitch (drafts saved if SMTP creds not set)
4. Ping owner Telegram with a summary

---

## Stack synergy

Atelier composes well with public skills + agents:

- [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code) — 60 agents + 230 skills + 75 commands
- [`nexu-io/html-anything`](https://github.com/nexu-io/html-anything) — 75 HTML skills, zero API key
- [`xai-org/x-algorithm`](https://github.com/xai-org/x-algorithm) — reference For-You ranking
- [`CloakHQ/CloakBrowser`](https://github.com/CloakHQ/CloakBrowser) — stealth Playwright drop-in
- [`mattpocock/skills`](https://github.com/mattpocock/skills) — engineering workflow skills

Drop them into `repos/` and reference the skill markdown from your agent runner.

---

## Roadmap

- [ ] PyPI release `atelier-ai-tools` (CLI wrapper)
- [ ] Docker compose for one-command deploy
- [ ] Webhook adapters for Discord + Slack notifications
- [ ] OpenTelemetry tracing on agent runs
- [ ] LangChain / LlamaIndex tool wrappers

---

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Built with Claude Code (Opus 4.7) — and a lot of code review feedback that made every CRITICAL into a closed pull request.

If this saves you a week of plumbing, drop a ⭐ — it's the only currency the project takes.

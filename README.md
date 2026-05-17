# Atelier AI — Autonomous Income Pipeline

> 7-agent autonomous pipeline for income generation. Cross-harness (Claude Code, Cursor, Codex, OpenCode).

## Stack

- **Orchestrator** (Python 3.12) coordinates 7 agents through a SQLite state machine.
- **CloakBrowser** for stealth scraping (Cloudflare/CAPTCHA bypass).
- **slither + mythril** for Solidity auditing.
- **FastAPI** for customer-facing services (Scrape API, Landing Generator).
- **Cloudflare Tunnel** for zero-trust public exposure.

## 7 Agents

| Agent | Role |
|-------|------|
| `scout_intl` | Crawls GitHub issues, Upwork RSS, public job feeds. |
| `scout_intl_cloak` | Code4rena / Sherlock / Immunefi / Google Maps via CloakBrowser. |
| `scout_vn` | ITViec / VietnamWorks. |
| `diagnoser` | Scores leads, drafts personalised pitches. |
| `builder` | Generates deliverables (landings, audit plans, cover letters). |
| `pitcher` | Multi-channel outreach (Gmail SMTP, Telegram drafts). |
| `checker` | Secret scan + size guard before send. |
| `support_bot` | Pipeline heartbeat to owner Telegram. |

## Three production services

### 1. Smart Contract Auditor

Wraps slither + mythril, exports Code4rena-format markdown report.

```bash
python products/smart_contract_audit/audit.py path/to/Contract.sol --out audit_out
```

### 2. Scrape API (FastAPI)

Per-key daily quota, SSRF block (private/loopback/link-local), atomic counter via `BEGIN IMMEDIATE`.

```bash
uvicorn products.scrape_api.main:app --port 8080
```

### 3. Landing Generator (FastAPI)

Editorial template (Be Vietnam Pro + Roboto Mono), four themes, HTML-escaped customer input, webhook-secret protected `/paid`.

```bash
uvicorn products.landing_gen.main:app --port 8091
```

## Security hardening (passed 5 code reviews)

- HTML escape on every customer string before template insertion.
- `BEGIN IMMEDIATE` SQLite transaction on quota counter.
- SSRF block: scheme + host + DNS-resolved IP (private / loopback / link-local / multicast / unspecified).
- Webhook secret comparison via `secrets.compare_digest`.
- Owner credentials read from env (`VCB_ACCOUNT`, `PAYPAL_ME`, `BRAND_NAME`, `CONTACT_EMAIL`, `GMAIL_APP_PASS`, `PAID_WEBHOOK_SECRET`).
- Solidity clone restricted to allow-listed hosts.
- Local `.sol` file copy restricted to current working directory.

## Run the full pipeline

```bash
python orchestrator.py init                   # create DB
python orchestrator.py run scout_intl          # one agent
python orchestrator.py run all                 # all registered agents once
python orchestrator.py loop 600                # run every 600 seconds
```

## License

MIT — see LICENSE.

## Author

Bao Nguyen Gia — [github.com/Sumo001-cell](https://github.com/Sumo001-cell)

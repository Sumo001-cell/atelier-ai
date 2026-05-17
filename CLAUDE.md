# Atelier — AI Workspace dự án kiếm tiền

> **Workspace tách biệt** với các project cũ. Mọi reference đến project cũ KHÔNG được nhắc trong code, output, hay báo cáo của workspace này.

## Phạm vi

- Dự án kiếm tiền tự động (Atelier AI brand mặc định, có thể đổi qua env `BRAND_NAME`)
- Khách hàng: SMB Việt Nam + freelance quốc tế (Code4rena, RapidAPI, Upwork, ProductHunt)
- Mọi sản phẩm trong `products/` đều hướng tới doanh thu trực tiếp

## Cấu trúc workspace

```
_kiem_tien_v2/
├── orchestrator.py            # điều phối 7 agent (scout/diagnoser/builder/pitcher/checker/support)
├── agents/                    # các agent rời
│   ├── scout_intl.py          # cào GitHub issues + Upwork RSS
│   ├── scout_intl_cloak.py    # Code4rena/Sherlock/Immunefi + Google Maps qua CloakBrowser
│   ├── scout_vn.py            # ITViec / VietnamWorks
│   ├── diagnoser.py           # chấm điểm lead, soạn pitch
│   ├── builder.py             # gen deliverable (landing / audit plan / cover letter)
│   ├── pitcher.py             # outreach email + Telegram notify owner
│   ├── checker.py             # quét secret + size + format
│   └── support_bot.py         # heartbeat pipeline tới Telegram owner
├── products/                  # MVP customer-facing
│   ├── scrape_api/            # FastAPI scrape SaaS (port 8080)
│   ├── landing_gen/           # FastAPI landing gen (port 8091)
│   └── smart_contract_audit/  # slither + mythril wrapper
├── repos/                     # third-party repos đã clone
│   ├── ecc-v2/                # affaan-m/everything-claude-code
│   ├── html-anything/         # nexu-io/html-anything
│   ├── x-algorithm/           # xai-org/x-algorithm
│   └── mattpocock-skills/     # mattpocock/skills
├── db/state.sqlite3           # lead pipeline state
├── deliverables/              # output đã build cho từng lead
├── logs/                      # log + outreach drafts
└── boot_all.py                # khởi 2 API + tail log
```

## Quy tắc kỹ thuật

1. **Không hardcode brand cũ.** Mọi nhãn tên dùng `os.getenv("BRAND_NAME", "Atelier")`.
2. **Tiếng Việt CÓ DẤU 100%** cho mọi nội dung khách Việt (landing, email, Zalo).
3. **html.escape()** mọi input của khách trước khi vào HTML template.
4. **Webhook secret** cho mọi endpoint payment (env `PAID_WEBHOOK_SECRET`).
5. **Không hardcode** số tài khoản, email cá nhân, handle GitHub trong source. Dùng env:
   - `VCB_BANK_NAME`, `VCB_ACCOUNT`, `VCB_OWNER`
   - `PAYPAL_ME`, `STRIPE_PAYMENT_LINK`
   - `CONTACT_EMAIL`, `BRAND_NAME`
6. **CloakBrowser** mọi scrape có khả năng bị Cloudflare/CAPTCHA chặn.
7. **SSRF block**: parse URL → reject scheme ≠ https/http → reject private/loopback/link-local IP.
8. **Atomic SQLite transaction** (`BEGIN IMMEDIATE`) cho mọi quota counter để chặn race.

## Quy tắc giao tiếp

1. **Telegram FIRST**: trước mọi câu hỏi/báo cáo, `sendMessage` cho chat owner.
2. **Báo cáo kèm screenshot**: mọi UI deliverable phải gửi ảnh qua Telegram (anh không ngồi máy).
3. **Tiếng Việt có dấu** trong mọi tin Telegram (python -X utf8).
4. **Anh chốt → hành động ngay**, không hỏi A/B/C/D.

## Quy trình kiếm tiền

### Quốc tế (USD)

- Code4rena / Sherlock / Immunefi: pipeline `smart_contract_audit/audit.py` → submit finding
- Upwork / Fiverr (qua `viecremote-bot` ở thư mục Kiem Tien): apply auto
- RapidAPI: publish Scrape API ở https://shine-surfing-learning-productivity.trycloudflare.com
- ProductHunt + IndieHackers + HN: launch organic

### Việt Nam (VND)

- SMB Việt Nam không có web: scrape Google Maps qua `scout_intl_cloak.smb_vn` → gen landing demo qua `landing_gen` API → outreach Zalo / FB Messenger
- KiotViet / Misa / Sapo: chuẩn bị unified API SaaS (chưa build)

## Thanh toán

| Loại | Kênh | Status |
|---|---|---|
| VND | Chuyển khoản VCB → env VCB_ACCOUNT | ✅ sẵn sàng |
| USD | PayPal.me + USDT BEP20 / TRC20 | ⚠️ chờ verify PayPal handle |
| USD | Stripe Payment Link | ⚠️ chờ owner tự signup (Chrome MCP cấm financial site) |

## Public URL hiện tại

- Scrape API: https://shine-surfing-learning-productivity.trycloudflare.com
- Landing Gen: https://offerings-rich-indexes-sampling.trycloudflare.com
- Demo landing (mẫu Phở Vũ Anh): https://offerings-rich-indexes-sampling.trycloudflare.com/preview/ph-v-anh-51t3xA

## Brand defaults

- `BRAND_NAME=Atelier`
- `CONTACT_EMAIL=` (set khi cần)
- Tone: editorial + bento + magazine + AI-native synthesis (Instrument Serif + Inter Tight + JetBrains Mono)

## Tooling đã cài

- Python 3.12, Node.js, pnpm, gh CLI (đã login), git
- slither-analyzer 0.11.5, solc-select 1.2.0
- cloakbrowser 0.3.28 (Chromium drop-in Playwright)
- cloudflared 2026.5.0 (free tunnel)
- ECC v2 (60 agents + 230 skills + 75 commands + 34 rules + 14 MCP)
- html-anything (75 skills × 9 surfaces, ZERO API key)
- mattpocock skills, x-algorithm (reference)

## Định nghĩa “tự kiếm tiền” (cho workspace này)

1. Em tự research, tự build, tự deploy.
2. Em tự outreach, tự fulfill, tự thu tiền.
3. Owner CHỈ: đọc OTP/2FA khi setup, duyệt T4 edge case 3% ticket.

## Cấm tuyệt đối

- Nhắc dự án cũ trong source, output, hoặc báo cáo workspace này.
- Hardcode credentials, bank account, hoặc email cá nhân.
- Bỏ dấu tiếng Việt trong nội dung cho khách Việt.
- Bỏ dấu tiếng Việt trong tin Telegram cho owner.
- Tự ý gửi email/Zalo/FB outreach mà chưa qua `checker.py`.

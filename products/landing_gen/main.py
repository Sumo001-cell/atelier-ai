"""
AI LANDING GEN — buyer-facing API.
Endpoints:
  POST /preview  {name, phone, tagline, address, email, theme} -> {preview_url}
  GET  /preview/{slug}                                          -> rendered HTML
  POST /order    {preview_id, email}                             -> {payment_options}
  POST /paid     {order_id, tx, paid_via}    (requires X-Webhook-Secret) -> mark paid

Template: Editorial / Magazine + Internal, áp dụng html-anything web-proto-editorial +
ui-ux-pro-max-skill design tokens (Instrument Serif / Inter Tight / JetBrains Mono).
Tiếng Việt có dấu cho khách Việt.

Security:
  - html.escape() mọi input của khách trước khi đưa vào HTML (chặn stored XSS).
  - /paid yêu cầu X-Webhook-Secret khớp env PAID_WEBHOOK_SECRET (chặn flip-order-paid).
  - Số tài khoản VCB + tên chủ tài khoản đọc từ env (không hardcode).

Run: uvicorn products.landing_gen.main:app --host 0.0.0.0 --port 8091
"""
import html
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
PREVIEW_DIR = ROOT / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
DB = ROOT / "landing.sqlite3"

STRIPE_PAYMENT_LINK = os.getenv("STRIPE_PAYMENT_LINK", "")
PAYPAL_ME = os.getenv("PAYPAL_ME", "")
BRAND_NAME = os.getenv("BRAND_NAME", "Atelier")
PRICE_USD = float(os.getenv("PRICE_USD", "99"))
PRICE_VND = int(os.getenv("PRICE_VND", "500000"))
VCB_BANK_NAME = os.getenv("VCB_BANK_NAME", "Vietcombank")
VCB_ACCOUNT = os.getenv("VCB_ACCOUNT", "")
VCB_OWNER = os.getenv("VCB_OWNER", "")
PAID_WEBHOOK_SECRET = os.getenv("PAID_WEBHOOK_SECRET", "")


THEMES = {
    "editorial_warm": {
        "canvas": "#FBFBFA",
        "surface": "#FFFFFF",
        "ink": "#1A1A19",
        "muted": "#787774",
        "hairline": "#EAEAEA",
        "accent": "#346538",
        "accent_bg": "#EDF3EC",
    },
    "editorial_dark": {
        "canvas": "#0F1B16",
        "surface": "#1A2E25",
        "ink": "#F5F4EF",
        "muted": "#A5B1AA",
        "hairline": "#2D4A3E",
        "accent": "#D4A24A",
        "accent_bg": "rgba(212,162,74,0.12)",
    },
    "burgundy": {
        "canvas": "#FAF4F2",
        "surface": "#FFFFFF",
        "ink": "#1A0F12",
        "muted": "#7E5C5C",
        "hairline": "#EADCD8",
        "accent": "#9D2C3A",
        "accent_bg": "#FDEBEC",
    },
    "midnight": {
        "canvas": "#0A0F1A",
        "surface": "#101A30",
        "ink": "#E6ECF7",
        "muted": "#8C9AB6",
        "hairline": "#1F2B45",
        "accent": "#5A7CFF",
        "accent_bg": "rgba(90,124,255,0.12)",
    },
}


def _render_template(ctx: dict) -> str:
    """Render landing HTML. ctx values must be pre-escaped."""
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{ctx['name']} — Trang giới thiệu</title>
<meta name="description" content="{ctx['name']} · {ctx['tagline']}">
<meta property="og:title" content="{ctx['name']}">
<meta property="og:description" content="{ctx['tagline']}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:ital,wght@0,400;0,500;0,600;0,700;1,500;1,700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --canvas:{ctx['t_canvas']};--surface:{ctx['t_surface']};--ink:{ctx['t_ink']};
  --muted:{ctx['t_muted']};--hairline:{ctx['t_hairline']};--accent:{ctx['t_accent']};--accent-bg:{ctx['t_accent_bg']};
  --display:'Be Vietnam Pro','SF Pro Display',system-ui,sans-serif;
  --sans:'Be Vietnam Pro','Inter Tight','SF Pro Display',system-ui,sans-serif;
  --mono:'Roboto Mono','Be Vietnam Pro',ui-monospace,monospace;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{margin:0;padding:0}}
body{{background:var(--canvas);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 24px}}
.nav{{position:sticky;top:16px;z-index:50;margin:16px auto 0;display:flex;align-items:center;justify-content:space-between;max-width:920px;padding:10px 14px 10px 20px;background:color-mix(in srgb,var(--canvas) 80%, transparent);backdrop-filter:saturate(140%) blur(16px);border:1px solid var(--hairline);border-radius:999px}}
.nav .brand{{font-family:var(--display);font-size:20px;letter-spacing:-0.01em;color:var(--ink)}}
.nav .brand em{{font-style:italic;color:var(--muted)}}
.nav ul{{list-style:none;display:flex;gap:22px;margin:0;padding:0}}
.nav ul a{{color:var(--ink);text-decoration:none;font-size:13.5px;font-weight:500}}
.nav ul a:hover{{color:var(--muted)}}
.nav .cta{{font:500 13px/1 var(--sans);padding:10px 16px;border-radius:999px;background:var(--accent);color:var(--canvas);border:1px solid var(--accent);text-decoration:none;transition:transform .2s cubic-bezier(.16,1,.3,1)}}
.nav .cta:hover{{transform:translateY(-1px)}}
.hero{{padding:96px 0 80px}}
.eyebrow{{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);padding:5px 12px;border:1px solid var(--hairline);border-radius:999px;background:var(--surface)}}
.eyebrow .dot{{width:6px;height:6px;border-radius:999px;background:var(--accent)}}
.hero h1{{font-family:var(--display);font-size:clamp(36px,5.8vw,76px);line-height:1.08;letter-spacing:-0.025em;margin:22px 0 0;max-width:20ch;font-weight:700}}
.hero h1 em{{font-style:italic;font-weight:500;color:var(--muted)}}
.hero .lede{{font-size:18.5px;color:var(--muted);max-width:54ch;margin:24px 0 36px;line-height:1.55}}
.hero .actions{{display:flex;flex-wrap:wrap;gap:12px;align-items:center}}
.btn{{font:500 14px/1 var(--sans);padding:13px 22px;border-radius:8px;cursor:pointer;text-decoration:none;transition:transform .2s cubic-bezier(.16,1,.3,1)}}
.btn-primary{{background:var(--accent);color:var(--canvas);border:1px solid var(--accent)}}
.btn-primary:hover{{transform:translateY(-1px)}}
.btn-ghost{{background:transparent;color:var(--ink);border:1px solid var(--hairline)}}
.bento{{padding:72px 0;border-top:1px solid var(--hairline)}}
.bento h2{{font-family:var(--sans);font-size:clamp(28px,3.6vw,42px);font-weight:600;letter-spacing:-0.02em;margin-bottom:28px;max-width:18ch}}
.bento-grid{{display:grid;grid-template-columns:repeat(6,1fr);grid-auto-rows:minmax(160px,auto);gap:0;border:1px solid var(--hairline);background:var(--hairline)}}
.bento-grid>.cell{{background:var(--surface);padding:24px 26px}}
.cell--hero{{grid-column:span 4;grid-row:span 2;padding:32px 36px}}
.cell--tall{{grid-column:span 2;grid-row:span 2}}
.cell--wide{{grid-column:span 4}}
.cell--small{{grid-column:span 2}}
.cell h3{{font-family:var(--sans);font-size:20px;font-weight:600;letter-spacing:-0.01em;margin:0 0 8px;line-height:1.3}}
.cell h4{{font-size:14px;font-weight:600;margin:0 0 6px;letter-spacing:-0.005em}}
.cell p{{font-size:14px;color:var(--muted);margin:0;line-height:1.6;max-width:42ch}}
.cell .num{{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:18px}}
.chip{{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:999px;background:var(--accent-bg);color:var(--accent);margin-bottom:10px}}
.contact{{padding:88px 0;border-top:1px solid var(--hairline)}}
.contact-grid{{display:grid;grid-template-columns:1fr 1fr;gap:64px;align-items:start}}
.contact h2{{font-family:var(--sans);font-size:clamp(32px,4.4vw,52px);line-height:1.05;letter-spacing:-0.02em;margin:0;max-width:14ch;font-weight:600}}
.contact-info{{font-size:15px;line-height:1.9}}
.contact-info .row{{display:grid;grid-template-columns:140px 1fr;padding:14px 0;border-bottom:1px solid var(--hairline);align-items:baseline}}
.contact-info .row:last-child{{border-bottom:none}}
.contact-info .label{{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}}
.contact-info a{{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--hairline)}}
.contact-info a:hover{{border-color:var(--accent);color:var(--accent)}}
.cta-band{{padding:72px 0;border-top:1px solid var(--hairline);text-align:center}}
.cta-band h2{{font-family:var(--sans);font-size:clamp(28px,3.6vw,44px);max-width:24ch;margin:0 auto 24px;font-weight:600;letter-spacing:-0.02em}}
.cta-band .actions{{display:inline-flex;flex-wrap:wrap;gap:12px;justify-content:center}}
footer{{border-top:1px solid var(--hairline);padding:32px 0;font-family:var(--mono);font-size:11.5px;color:var(--muted);letter-spacing:.04em}}
footer .row{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center}}
@media (max-width:880px){{
  .nav ul{{display:none}}
  .bento-grid{{grid-template-columns:1fr}}
  .cell--hero,.cell--tall,.cell--wide,.cell--small{{grid-column:span 1;grid-row:auto}}
  .contact-grid{{grid-template-columns:1fr;gap:24px}}
  .contact-info .row{{grid-template-columns:1fr}}
  .contact-info .label{{margin-bottom:4px}}
}}
.reveal{{opacity:0;transform:translateY(12px);transition:opacity .6s cubic-bezier(.16,1,.3,1),transform .6s cubic-bezier(.16,1,.3,1)}}
.reveal.is-in{{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){{.reveal{{opacity:1;transform:none;transition:none}}}}
</style></head>
<body>
<header class="nav">
  <span class="brand">{ctx['name']}<em> · giới thiệu</em></span>
  <ul>
    <li><a href="#menu">Thực đơn</a></li>
    <li><a href="#contact">Liên hệ</a></li>
    <li><a href="#book">Đặt bàn</a></li>
  </ul>
  <a class="cta" href="tel:{ctx['phone_tel']}">Gọi ngay</a>
</header>

<main>
  <section class="wrap hero reveal">
    <span class="eyebrow"><span class="dot"></span>Quán Việt · Khu vực {ctx['region']}</span>
    <h1>{ctx['name']} — <em>nơi quen của khách quen</em>.</h1>
    <p class="lede">{ctx['tagline']}</p>
    <div class="actions">
      <a class="btn btn-primary" href="tel:{ctx['phone_tel']}">Gọi {ctx['phone']}</a>
      <a class="btn btn-ghost" href="https://zalo.me/{ctx['phone_zalo']}">Nhắn Zalo đặt bàn</a>
    </div>
  </section>

  <section class="wrap bento reveal" id="menu">
    <h2>Thực đơn nổi bật</h2>
    <div class="bento-grid">
      <div class="cell cell--hero">
        <span class="num">01 / Đặc trưng</span>
        <span class="chip">Bán chạy</span>
        <h3>Món tủ của quán — giữ trọn hương vị truyền thống.</h3>
        <p>Công thức gia truyền, nguyên liệu tươi mỗi sáng. Anh/chị chủ quán cập nhật ảnh + mô tả chi tiết sau khi nhận bản chính thức.</p>
      </div>
      <div class="cell cell--tall">
        <span class="num">02 / Combo</span>
        <span class="chip">Tiết kiệm</span>
        <h4 style="margin-top:14px">Combo đôi hợp lý</h4>
        <p>Bộ combo dành cho 2 người, cân bằng món chính, món phụ và đồ uống.</p>
      </div>
      <div class="cell cell--small">
        <span class="num">03 / Mới</span>
        <h4>Món theo mùa</h4>
        <p>Cập nhật theo nguyên liệu chợ phiên trong tuần.</p>
      </div>
      <div class="cell cell--small">
        <span class="num">04 / Tráng miệng</span>
        <span class="chip">Hand-made</span>
        <h4 style="margin-top:8px">Chè & nước mát</h4>
        <p>Tự nấu mỗi ngày, không phẩm màu, không phụ gia.</p>
      </div>
      <div class="cell cell--wide">
        <span class="num">05 / Ưu đãi</span>
        <h4 style="margin-top:14px">Khách quen — giảm 10% mỗi tuần</h4>
        <p>Lưu số quán vào danh bạ + nhắn Zalo "khách quen" để nhận mã giảm giá hàng tuần. Áp dụng cả ăn tại quán và mang đi.</p>
      </div>
    </div>
  </section>

  <section class="wrap contact reveal" id="contact">
    <div class="contact-grid">
      <h2>Đặt bàn & ghé quán hôm nay.</h2>
      <div class="contact-info">
        <div class="row"><span class="label">Địa chỉ</span><span>{ctx['address']}</span></div>
        <div class="row"><span class="label">Điện thoại</span><a href="tel:{ctx['phone_tel']}">{ctx['phone']}</a></div>
        <div class="row"><span class="label">Email</span><a href="mailto:{ctx['email']}">{ctx['email']}</a></div>
        <div class="row"><span class="label">Giờ mở cửa</span><span>07:00 – 22:00 hằng ngày</span></div>
        <div class="row"><span class="label">Đặt qua</span><a href="https://zalo.me/{ctx['phone_zalo']}">Zalo · {ctx['phone']}</a></div>
      </div>
    </div>
  </section>

  <section class="wrap cta-band reveal" id="book">
    <h2>Ghé quán hoặc gọi món mang đi — đều ngon.</h2>
    <div class="actions">
      <a class="btn btn-primary" href="tel:{ctx['phone_tel']}">Gọi đặt món · {ctx['phone']}</a>
      <a class="btn btn-ghost" href="https://maps.google.com/?q={ctx['address']}">Xem đường tới quán</a>
    </div>
  </section>
</main>

<footer class="wrap">
  <div class="row">
    <span>© 2026 {ctx['name']} · {ctx['region']}</span>
    <span>Trang giới thiệu tạo bởi {ctx['brand']} {ctx['watermark']}</span>
  </div>
</footer>

<script>
  const io=new IntersectionObserver((es)=>es.forEach(e=>{{if(e.isIntersecting){{e.target.classList.add('is-in');io.unobserve(e.target)}}}}),{{threshold:.12}});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
</script>
</body>
</html>
"""


def db_init() -> None:
    with sqlite3.connect(DB) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS previews (
                id TEXT PRIMARY KEY,
                slug TEXT UNIQUE,
                input_json TEXT,
                html_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                preview_id TEXT,
                email TEXT,
                amount_usd REAL,
                amount_vnd INTEGER,
                paid INTEGER DEFAULT 0,
                paid_via TEXT,
                tx TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT
            );
            """
        )


@contextmanager
def conn():
    c = sqlite3.connect(DB)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _slugify(s: str) -> str:
    out = []
    for ch in s.lower().strip():
        if ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    slug = "".join(out).strip("-")[:48]
    return slug or "lead"


def _e164(phone: str) -> str:
    p = phone.replace(" ", "").replace("-", "").lstrip("+")
    return ("84" + p[1:]) if p.startswith("0") else p


class PreviewBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    tagline: str = Field(default="Quán quen của khu phố — món ngon, giá hợp lý, phục vụ nhanh.", max_length=240)
    address: str = Field(default="", max_length=200)
    region: str = Field(default="TP. Hồ Chí Minh", max_length=80)
    email: str = Field(default="contact@example.com", max_length=120)
    theme: str = Field(default="editorial_warm")


class OrderBody(BaseModel):
    preview_id: str
    email: str


class PaidBody(BaseModel):
    order_id: str
    tx: str
    paid_via: str = "manual"


app = FastAPI(title=f"{BRAND_NAME} Landing Gen", version="0.2.0")
db_init()


@app.get("/health")
def health():
    return {"ok": True, "version": app.version}


@app.post("/preview")
def create_preview(body: PreviewBody):
    theme = THEMES.get(body.theme, THEMES["editorial_warm"])
    safe = {k: html.escape(getattr(body, k) if getattr(body, k) else "") for k in ("name", "phone", "tagline", "address", "region", "email")}
    if not safe["address"]:
        safe["address"] = "Đang cập nhật"
    phone_tel = html.escape("+" + _e164(body.phone))
    phone_zalo = html.escape(_e164(body.phone))
    ctx = dict(safe)
    ctx.update(
        phone_tel=phone_tel,
        phone_zalo=phone_zalo,
        brand=html.escape(BRAND_NAME) + " AI",
        watermark="(bản preview — thanh toán để gỡ watermark)",
        t_canvas=theme["canvas"],
        t_surface=theme["surface"],
        t_ink=theme["ink"],
        t_muted=theme["muted"],
        t_hairline=theme["hairline"],
        t_accent=theme["accent"],
        t_accent_bg=theme["accent_bg"],
    )
    html_out = _render_template(ctx)
    pid = secrets.token_urlsafe(10)
    slug = _slugify(body.name) + "-" + secrets.token_urlsafe(4)
    out_path = PREVIEW_DIR / f"{slug}.html"
    out_path.write_text(html_out, encoding="utf-8")
    with conn() as c:
        c.execute(
            "INSERT INTO previews(id, slug, input_json, html_path) VALUES (?,?,?,?)",
            (pid, slug, body.model_dump_json(), str(out_path)),
        )
    return {
        "preview_id": pid,
        "slug": slug,
        "preview_url": f"/preview/{slug}",
        "price_usd": PRICE_USD,
        "price_vnd": PRICE_VND,
    }


@app.get("/preview/{slug}", response_class=HTMLResponse)
def get_preview(slug: str):
    with conn() as c:
        row = c.execute("SELECT html_path FROM previews WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise HTTPException(404, "not_found")
    return HTMLResponse(Path(row[0]).read_text(encoding="utf-8"))


@app.post("/order")
def create_order(body: OrderBody):
    with conn() as c:
        row = c.execute("SELECT id FROM previews WHERE id=?", (body.preview_id,)).fetchone()
        if not row:
            raise HTTPException(404, "preview_not_found")
        oid = secrets.token_urlsafe(12)
        c.execute(
            "INSERT INTO orders(id, preview_id, email, amount_usd, amount_vnd) VALUES (?,?,?,?,?)",
            (oid, body.preview_id, body.email, PRICE_USD, PRICE_VND),
        )
    pay: dict = {
        "order_id": oid,
        "amount_usd": PRICE_USD,
        "amount_vnd": PRICE_VND,
        "stripe_url": STRIPE_PAYMENT_LINK or None,
        "paypal_url": f"{PAYPAL_ME}/{int(PRICE_USD)}" if PAYPAL_ME else None,
    }
    if VCB_ACCOUNT and VCB_OWNER:
        pay["bank_vn"] = {
            "bank": VCB_BANK_NAME,
            "account": VCB_ACCOUNT,
            "name": VCB_OWNER,
            "note": f"ATL-{oid[:6]}",
        }
    return pay


@app.post("/paid")
def mark_paid(body: PaidBody, x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret")):
    if not PAID_WEBHOOK_SECRET:
        raise HTTPException(503, "paid_webhook_disabled")
    if not x_webhook_secret or not secrets.compare_digest(x_webhook_secret, PAID_WEBHOOK_SECRET):
        raise HTTPException(401, "invalid_webhook_secret")
    with conn() as c:
        cur = c.execute(
            "UPDATE orders SET paid=1, paid_via=?, tx=?, paid_at=datetime('now') WHERE id=? AND paid=0",
            (body.paid_via, body.tx, body.order_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "order_not_found_or_already_paid")
    return {"ok": True, "order_id": body.order_id}


if __name__ == "__main__":
    print("usage: uvicorn products.landing_gen.main:app --port 8091")

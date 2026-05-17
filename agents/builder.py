"""
BUILDER — generate deliverables for qualified leads.
Modes:
  smart_contract_audit -> stub finding template (rendered via Claude Code in human loop)
  landing_gen_vn -> html landing page from template + lead-specific data
  freelance_dev -> CV cover letter (reuses viecremote-bot generator if available)
  bug_bounty -> issue triage note
"""
import json
import re
from datetime import datetime

from orchestrator import register, db_conn, ROOT

LANDING_TEMPLATE = ROOT / "agents" / "templates" / "landing_vn.html"
DELIV_DIR = ROOT / "deliverables"
DELIV_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_LANDING_HTML = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} — Website demo</title>
<style>
  :root{{--bg:#0f1b16;--surface:#1a2e25;--accent:#4a9968;--gold:#d4a24a;--text:#f5f4ef;font-family:'Playfair Display', Georgia, serif}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:linear-gradient(180deg,#0f1b16,#1a2e25,#2d4a3e);color:var(--text);font-family:'IBM Plex Sans',system-ui,sans-serif;line-height:1.6}}
  .hero{{min-height:80vh;display:grid;place-items:center;padding:40px 20px;text-align:center}}
  .hero h1{{font-family:'Playfair Display',Georgia,serif;font-weight:600;font-size:clamp(2rem,5vw,4rem);color:var(--gold);margin-bottom:12px}}
  .hero p{{max-width:640px;color:#cfd5d1;font-size:1.1rem}}
  .cta{{display:inline-flex;gap:16px;margin-top:24px}}
  .btn{{padding:14px 28px;border-radius:999px;background:var(--accent);color:#0f1b16;font-weight:600;text-decoration:none}}
  .btn.ghost{{background:transparent;border:1px solid var(--accent);color:var(--accent)}}
  section{{padding:60px 24px;max-width:1080px;margin:0 auto}}
  h2{{font-family:'Playfair Display',Georgia,serif;color:var(--gold);font-size:2rem;margin-bottom:24px}}
  .menu{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}}
  .item{{background:rgba(255,255,255,0.04);padding:18px;border-radius:14px;border:1px solid rgba(255,255,255,0.08)}}
  footer{{padding:32px 20px;text-align:center;color:#a5b1aa;font-size:.9rem}}
</style>
</head>
<body>
<header class="hero">
  <h1>{name}</h1>
  <p>{tagline}</p>
  <div class="cta">
    <a class="btn" href="tel:{phone}">Goi {phone}</a>
    <a class="btn ghost" href="https://zalo.me/{phone}">Chat Zalo</a>
  </div>
</header>
<section>
  <h2>Mon noi bat</h2>
  <div class="menu">
    <div class="item"><b>Mon dac biet 1</b><p>Mo ta ngan — anh chi cap nhat sau</p></div>
    <div class="item"><b>Mon dac biet 2</b><p>Mo ta ngan — anh chi cap nhat sau</p></div>
    <div class="item"><b>Mon dac biet 3</b><p>Mo ta ngan — anh chi cap nhat sau</p></div>
  </div>
</section>
<section>
  <h2>Lien he</h2>
  <p>Dia chi: {address}<br>Dien thoai: {phone}<br>Gio mo cua: 07:00 - 22:00</p>
</section>
<footer>© 2026 {name} · landing gen by SUMO AI</footer>
</body>
</html>
"""


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", s.strip()).strip("-").lower()
    return s[:60] or "lead"


def build_landing(lead_id: int, name: str, meta: dict) -> dict:
    import os
    phone = meta.get("phone") or os.getenv("OWNER_PHONE", "")
    address = meta.get("address", "Cap nhat sau")
    tagline = "Quan ngon — gia hop ly — phuc vu nhanh"
    html = DEFAULT_LANDING_HTML.format(
        name=name[:80] or "Cua hang",
        tagline=tagline,
        phone=phone or "(liên hệ)",
        address=address[:120],
    )
    folder = DELIV_DIR / f"landing_{lead_id}_{_slug(name)}"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "index.html"
    out.write_text(html, encoding="utf-8")
    return {"kind": "landing", "path": str(out)}


def build_audit_stub(lead_id: int, title: str, url: str) -> dict:
    folder = DELIV_DIR / f"audit_{lead_id}_{_slug(title)}"
    folder.mkdir(parents=True, exist_ok=True)
    fp = folder / "audit_plan.md"
    fp.write_text(
        f"""# Smart Contract Audit Plan
Target: {title}
URL: {url}
Date: {datetime.utcnow().isoformat()}

## Pipeline
1. clone target repo
2. run slither --json -
3. run mythril analyze
4. manual review with ECC defi-amm-security skill
5. write findings with PoC + severity (Code4rena format)
6. submit
""",
        encoding="utf-8",
    )
    return {"kind": "audit_plan", "path": str(fp)}


def build_cover_letter(lead_id: int, title: str, url: str) -> dict:
    folder = DELIV_DIR / f"cover_{lead_id}_{_slug(title)}"
    folder.mkdir(parents=True, exist_ok=True)
    body = f"""# Cover Letter — {title[:120]}

Hi,

I'm applying for: {title}.
Source: {url}

Background: 8+ years sales operations and Python/FastAPI/Next.js automation.
Recent: shipped AI agent pipelines (Scout/Diagnoser/Builder/Pitcher/Checker) with ECC v2, html-anything, CloakBrowser. Built smart-contract audit pipeline using slither + mythril.
{github_line}

Available within 7 days. Open to part-time or contract.

Best,
Bao Nguyen
${CONTACT_EMAIL}
"""
    fp = folder / "cover.md"
    fp.write_text(body, encoding="utf-8")
    return {"kind": "cover_letter", "path": str(fp)}


@register("builder")
def run() -> dict:
    built = {"landing": 0, "audit_plan": 0, "cover_letter": 0, "skipped": 0}
    with db_conn() as c:
        rows = c.execute(
            "SELECT id, title, url, source, meta_json FROM leads WHERE stage='diagnosed' LIMIT 50"
        ).fetchall()
        for lead_id, title, url, source, meta_json in rows:
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            pitch = meta.get("pitch", {})
            product = pitch.get("product", "generic")
            res = None
            if product == "landing_gen_vn":
                res = build_landing(lead_id, title or "Khach hang", meta)
            elif product == "smart_contract_audit":
                res = build_audit_stub(lead_id, title or "", url or "")
            elif product == "freelance_dev":
                res = build_cover_letter(lead_id, title or "", url or "")
            else:
                built["skipped"] += 1
                continue
            if res:
                c.execute(
                    "INSERT INTO deliverables(lead_id, kind, path, status) VALUES (?,?,?,?)",
                    (lead_id, res["kind"], res["path"], "ready"),
                )
                built[res["kind"]] = built.get(res["kind"], 0) + 1
    return built


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

"""
DIAGNOSER — score leads + generate per-lead pitch hooks.
No external Claude API call (anh khong co API key) — uses heuristics + template hooks.
Stage transitions:
  scouted -> diagnosed (if score >= threshold)
  scouted -> dead (if score below threshold)
Outputs personalised pitch payload stored in meta_json.
"""
import json
import re
from datetime import datetime

from orchestrator import register, db_conn

# scoring rules (lightweight, no LLM cost)
KEYWORDS_HIGH = re.compile(
    r"(audit|smart contract|solidity|defi|security|landing|saas|next\.?js|fastapi|automation|scraping|ai agent|claude|llm|rag|telegram bot|integration|chatbot|whatsapp)",
    re.I,
)
KEYWORDS_LOW = re.compile(r"(intern|fresher|junior trainee|3 month internship)", re.I)
KEYWORDS_VN_SMB = re.compile(r"(quan an|cafe|spa|tiem nail|shop|nha hang|tiem)", re.I)

PRODUCT_FIT = {
    "code4rena": "smart_contract_audit",
    "sherlock": "smart_contract_audit",
    "immunefi": "smart_contract_audit",
    "github": "bug_bounty",
    "upwork": "freelance_dev",
    "itviec": "freelance_dev",
    "vnworks": "freelance_dev",
    "topcv": "freelance_dev",
    "google_maps": "landing_gen_vn",
}


def score_lead(title: str, source: str) -> float:
    s = 1.0
    if KEYWORDS_HIGH.search(title or ""):
        s += 3
    if KEYWORDS_LOW.search(title or ""):
        s -= 2
    if KEYWORDS_VN_SMB.search(title or ""):
        s += 2
    if source in {"code4rena", "sherlock", "immunefi"}:
        s += 2  # high ticket
    if source == "google_maps":
        s += 1
    return round(s, 2)


def make_pitch(title: str, source: str, meta: dict) -> dict:
    import os
    contact = os.getenv("CONTACT_EMAIL", "")
    handle_tg = os.getenv("CONTACT_TELEGRAM", "")
    owner_phone = os.getenv("OWNER_PHONE", "")
    github = os.getenv("GITHUB_HANDLE", "")
    product = PRODUCT_FIT.get(source, "generic")
    if product == "smart_contract_audit":
        contact_line = " / ".join([s for s in (contact, f"Telegram {handle_tg}" if handle_tg else "") if s])
        body = (
            f"Hi team, I noticed your audit contest '{title[:80]}'. "
            "I'm an independent security researcher running automated Slither + Mythril + manual review pipeline. "
            "I'll submit high-quality findings with reproducible PoC. "
            f"Direct contact: {contact_line}"
        )
    elif product == "landing_gen_vn":
        phone = meta.get("phone") or owner_phone
        contact_line = " / ".join([s for s in (f"Zalo {phone}" if phone else "", contact) if s])
        body = (
            f"Chao anh/chi quan '{title[:80]}'. "
            "Em nhan thay quan minh chua co website rieng. "
            "Em xay landing page chuyen nghiep cho quan (menu + hinh anh + dat ban + Zalo). "
            "Em co the gui demo trong 2 gio. "
            f"Lien he: {contact_line}"
        )
    elif product == "freelance_dev":
        cv_line = f"CV: github.com/{github}" if github else ""
        body = (
            f"Hi, I'm applying for: {title[:100]}. "
            "8+ years sales operations + Python/FastAPI/Next.js automation. "
            "Built AI agent pipelines, scraping, dashboards. "
            f"{cv_line} Available 7 days."
        )
    elif product == "bug_bounty":
        body = (
            f"Hi maintainer, I'd like to take this issue: {title[:100]}. "
            "I run a Claude Code automation pipeline that can produce a PR with tests. "
            "If a bounty applies, please confirm via the issue comments."
        )
    else:
        body = f"Re: {title[:120]}. Lien he {contact}."
    return {"product": product, "body": body, "drafted_at": datetime.utcnow().isoformat()}


@register("diagnoser")
def run() -> dict:
    qualified = 0
    dead = 0
    with db_conn() as c:
        rows = c.execute(
            "SELECT id, title, source, meta_json FROM leads WHERE stage='scouted' LIMIT 500"
        ).fetchall()
        for lead_id, title, source, meta_json in rows:
            meta = {}
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            score = score_lead(title or "", source)
            new_stage = "diagnosed" if score >= 2 else "dead"
            if new_stage == "diagnosed":
                pitch = make_pitch(title or "", source, meta)
                meta["pitch"] = pitch
                qualified += 1
            else:
                dead += 1
            c.execute(
                "UPDATE leads SET stage=?, score=?, meta_json=? WHERE id=?",
                (new_stage, score, json.dumps(meta, ensure_ascii=False), lead_id),
            )
    return {"qualified": qualified, "dead": dead}


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

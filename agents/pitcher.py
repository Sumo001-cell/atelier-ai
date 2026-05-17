"""
PITCHER — multi-channel outreach engine.
Channels:
  - Email (Gmail SMTP via app password, fallback dry-run if no creds)
  - Telegram (SUMO bot for owner notifications, separate outreach bot for cold contacts)
  - Save outreach drafts to disk for manual review when channel not configured
Transitions:
  diagnosed -> pitched (after first attempt)
  pitched -> closed_won / closed_lost (manual or response-driven)
Rate limit: max OUTREACH_PER_RUN per agent invocation.
"""
import json
import os
import smtplib
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from orchestrator import register, db_conn, log, ROOT

OUTREACH_PER_RUN = int(os.getenv("OUTREACH_PER_RUN", "30"))
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")  # set after generated
TG_BOT_TOKEN = None
TG_OWNER_CHAT = None
try:
    cfg = json.loads(Path("C:/AI_Pipeline/sumo_bot_config.json").read_text(encoding="utf-8"))
    TG_BOT_TOKEN = cfg.get("bot_token")
    TG_OWNER_CHAT = cfg.get("admin_chat_id")
except Exception:
    pass

DRAFT_DIR = ROOT / "logs" / "outreach_drafts"
DRAFT_DIR.mkdir(parents=True, exist_ok=True)


def send_email(to_addr: str, subject: str, body: str) -> dict:
    if not (GMAIL_USER and GMAIL_APP_PASS):
        return {"ok": False, "reason": "no_creds", "dry": True}
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("Bao Nguyen", GMAIL_USER))
        msg["To"] = to_addr
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as srv:
            srv.login(GMAIL_USER, GMAIL_APP_PASS)
            srv.sendmail(GMAIL_USER, [to_addr], msg.as_string())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


def tg_notify(text: str) -> bool:
    if not (TG_BOT_TOKEN and TG_OWNER_CHAT):
        return False
    if len(text) > 4000:
        log.warning("tg_notify truncated %d->4000 chars", len(text))
    try:
        data = urllib.parse.urlencode({"chat_id": TG_OWNER_CHAT, "text": text[:4000]}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", data=data
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        log.warning("tg_notify err: %s", e)
        return False


def save_draft(lead_id: int, channel: str, payload: str) -> Path:
    fp = DRAFT_DIR / f"lead_{lead_id}_{channel}_{int(time.time())}.txt"
    fp.write_text(payload, encoding="utf-8")
    return fp


def pitch_email(lead_id: int, title: str, url: str, source: str, pitch: dict) -> dict:
    subject = pitch.get("subject") or f"[Sumo] {title[:80]}"
    body = pitch.get("body", "")
    body += f"\n\nReference: {url}"
    target_email = pitch.get("target_email")
    if target_email:
        return send_email(target_email, subject, body)
    draft = save_draft(lead_id, "email", f"SUBJECT: {subject}\nTO: <unknown>\n\n{body}")
    return {"ok": True, "dry": True, "draft": str(draft), "reason": "no_target_email"}


@register("pitcher")
def run() -> dict:
    sent_email = 0
    drafted = 0
    failed = 0
    with db_conn() as c:
        rows = c.execute(
            "SELECT id, title, url, source, meta_json FROM leads "
            "WHERE stage='diagnosed' "
            "AND id NOT IN (SELECT lead_id FROM outreach WHERE status IN ('sent','drafted')) "
            "ORDER BY score DESC LIMIT ?",
            (OUTREACH_PER_RUN,),
        ).fetchall()
        for lead_id, title, url, source, meta_json in rows:
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            pitch = meta.get("pitch", {})
            if not pitch:
                continue
            res = pitch_email(lead_id, title or "", url or "", source, pitch)
            channel = "email"
            status = "sent" if res.get("ok") and not res.get("dry") else "drafted"
            if status == "sent":
                sent_email += 1
            elif res.get("dry"):
                drafted += 1
            else:
                failed += 1
                status = "failed"
            c.execute(
                "INSERT INTO outreach(lead_id, channel, payload_path, response, sent_at, status) VALUES (?,?,?,?,?,?)",
                (
                    lead_id,
                    channel,
                    res.get("draft"),
                    json.dumps(res, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                    status,
                ),
            )
            if status in ("sent", "drafted"):
                c.execute("UPDATE leads SET stage='pitched' WHERE id=?", (lead_id,))
    if sent_email or drafted:
        tg_notify(f"📤 Pitcher: {sent_email} sent, {drafted} drafted, {failed} failed.")
    return {"sent_email": sent_email, "drafted": drafted, "failed": failed}


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

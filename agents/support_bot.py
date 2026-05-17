"""
SUPPORT — minimal heartbeat + summary push.
Real support bot (Crisp/Telegram inbound) wired in a separate process when service signups done.
This module just summarises pipeline state and pings the operator chat.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from orchestrator import register, db_conn, log

CFG_PATH = Path(os.getenv("SUMO_BOT_CONFIG", "C:/AI_Pipeline/sumo_bot_config.json"))
CFG = {}
if CFG_PATH.is_file():
    try:
        CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("support_bot: cannot parse %s: %s", CFG_PATH, e)
else:
    log.warning("support_bot: config missing at %s — heartbeat will not send", CFG_PATH)

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")


def tg_send(text: str) -> bool:
    tok = CFG.get("bot_token")
    chat = CFG.get("admin_chat_id")
    if not (tok and chat):
        return False
    if not _TOKEN_RE.match(tok):
        log.warning("support_bot: invalid token format, skip send")
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage", data=data
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        log.warning("tg_send err: %s", e)
        return False


@register("support")
def run() -> dict:
    with db_conn() as c:
        leads_by_stage = dict(
            c.execute("SELECT stage, COUNT(*) FROM leads GROUP BY stage").fetchall()
        )
        leads_total = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        outreach_today = c.execute(
            "SELECT status, COUNT(*) FROM outreach WHERE date(sent_at)=date('now') GROUP BY status"
        ).fetchall()
        sales_today = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount_usd),0), COALESCE(SUM(amount_vnd),0) "
            "FROM sales WHERE date(paid_at)=date('now')"
        ).fetchone()
        deliv_by_status = dict(
            c.execute("SELECT status, COUNT(*) FROM deliverables GROUP BY status").fetchall()
        )

    summary = {
        "leads_total": leads_total,
        "leads_by_stage": leads_by_stage,
        "outreach_today": dict(outreach_today),
        "sales_today": {
            "count": sales_today[0],
            "usd": sales_today[1],
            "vnd": sales_today[2],
        },
        "deliverables": deliv_by_status,
    }
    text_lines = [
        "📈 Pipeline summary",
        f"Leads total: {leads_total}",
        f"By stage: {leads_by_stage}",
        f"Outreach today: {dict(outreach_today)}",
        f"Sales today: {summary['sales_today']}",
        f"Deliverables: {deliv_by_status}",
    ]
    tg_send("\n".join(text_lines))
    return summary


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

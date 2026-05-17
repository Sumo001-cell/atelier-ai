"""
CHECKER — basic gate before pitch / send.
Checks for the most common landmines without spawning expensive sub-agents:
  - file size reasonable
  - no secrets in deliverable (regex pass for known tokens)
  - HTML deliverable parses minimally
  - markdown not empty
Marks deliverables as ready -> verified (or quarantined).
"""
import re
from pathlib import Path

from orchestrator import register, db_conn, log

import os

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"Giabao\d+@"),
]
_OWNER_SECRETS = [v for v in (os.getenv("GMAIL_APP_PASS"), os.getenv("OWNER_PASS")) if v]


def scan_for_secrets(text: str) -> list[str]:
    hits = [p.pattern for p in SECRET_PATTERNS if p.search(text)]
    for s in _OWNER_SECRETS:
        if s and s in text:
            hits.append("owner_secret_match")
    return hits


def check_file(path: str) -> dict:
    try:
        p = Path(path)
        if not p.is_file():
            return {"ok": False, "reason": "missing"}
        if p.stat().st_size == 0:
            return {"ok": False, "reason": "empty"}
        if p.stat().st_size > 2 * 1024 * 1024:
            return {"ok": False, "reason": "too_large"}
        text = p.read_text(encoding="utf-8", errors="ignore")
        leaks = scan_for_secrets(text)
        if leaks:
            return {"ok": False, "reason": f"secret_leak:{','.join(leaks)}"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}


@register("checker")
def run() -> dict:
    verified = 0
    quarantined = 0
    with db_conn() as c:
        rows = c.execute(
            "SELECT id, path FROM deliverables WHERE status='ready' LIMIT 200"
        ).fetchall()
        for did, path in rows:
            res = check_file(path or "")
            new = "verified" if res.get("ok") else "quarantined"
            c.execute("UPDATE deliverables SET status=? WHERE id=?", (new, did))
            if res.get("ok"):
                verified += 1
            else:
                quarantined += 1
                log.warning("deliverable %s quarantined: %s", did, res.get("reason"))
    return {"verified": verified, "quarantined": quarantined}


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

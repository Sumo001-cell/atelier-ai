"""
CloakBrowser Scrape API — passive recurring revenue MVP.
Endpoints:
  POST /scrape    {url, render_ms?, return: ["html","text","screenshot"]}
  GET  /health
  GET  /usage     (auth via X-API-Key)
Auth: simple X-API-Key per customer in SQLite.
Rate limit: per-key requests/day.
Stripe integration is left to a separate webhook process (out of scope MVP).

Run: uvicorn products.scrape_api.main:app --host 0.0.0.0 --port 8080
"""
import base64
import ipaddress
import os
import socket
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


def _validate_target_url(raw: str) -> str:
    try:
        u = urlparse(raw)
    except Exception as e:
        raise HTTPException(400, f"bad_url:{e}")
    if u.scheme not in ("http", "https"):
        raise HTTPException(400, "scheme_not_allowed")
    if not u.hostname:
        raise HTTPException(400, "missing_host")
    host = u.hostname
    if host in {"localhost", "metadata.google.internal", "metadata"}:
        raise HTTPException(400, "blocked_host")
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except Exception as e:
        raise HTTPException(400, f"dns_failed:{e}")
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(400, f"blocked_ip:{ip}")
    return raw


ROOT = Path(__file__).parent
DB = ROOT / "scrape_api.sqlite3"
DAILY_LIMIT_DEFAULT = int(os.getenv("SCRAPE_DAILY_LIMIT", "200"))


def db_init() -> None:
    with sqlite3.connect(DB) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT UNIQUE NOT NULL,
                email TEXT,
                plan TEXT DEFAULT 'free',
                daily_limit INTEGER DEFAULT 200,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                url TEXT,
                ok INTEGER,
                duration_ms INTEGER,
                bytes_out INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_usage_key_ts ON usage(api_key, ts);
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


def get_customer(api_key: str) -> Optional[dict]:
    if not api_key:
        return None
    with conn() as c:
        r = c.execute(
            "SELECT id, api_key, email, plan, daily_limit, active FROM customers WHERE api_key=?",
            (api_key,),
        ).fetchone()
        if not r:
            return None
        return {"id": r[0], "api_key": r[1], "email": r[2], "plan": r[3], "daily_limit": r[4], "active": r[5]}


def today_usage(api_key: str) -> int:
    with conn() as c:
        r = c.execute(
            "SELECT COUNT(*) FROM usage WHERE api_key=? AND date(ts)=date('now')", (api_key,)
        ).fetchone()
    return r[0] if r else 0


class ScrapeBody(BaseModel):
    url: str
    render_ms: int = 2000
    want: list[str] = ["text"]  # any of: html, text, screenshot


app = FastAPI(title="SUMO Scrape API", version="0.1.0")
db_init()


@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time())}


@app.get("/usage")
def usage(x_api_key: str = Header(default="")):
    cust = get_customer(x_api_key)
    if not cust:
        raise HTTPException(401, "invalid_api_key")
    return {"customer": cust, "today": today_usage(x_api_key)}


@app.post("/scrape")
def scrape(body: ScrapeBody, x_api_key: str = Header(default="")):
    cust = get_customer(x_api_key)
    if not cust:
        raise HTTPException(401, "invalid_api_key")
    if not cust["active"]:
        raise HTTPException(403, "customer_inactive")
    target = _validate_target_url(body.url)
    # Atomic check-and-reserve to prevent over-limit under concurrency
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        used = c.execute(
            "SELECT COUNT(*) FROM usage WHERE api_key=? AND date(ts)=date('now')", (x_api_key,)
        ).fetchone()[0]
        if used >= cust["daily_limit"]:
            c.execute("ROLLBACK")
            raise HTTPException(429, f"daily_limit_reached:{cust['daily_limit']}")
        c.execute(
            "INSERT INTO usage(api_key, url, ok, duration_ms, bytes_out) VALUES (?,?,0,0,0)",
            (x_api_key, target),
        )
        usage_row_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("COMMIT")
    try:
        from cloakbrowser import launch
    except Exception as e:
        raise HTTPException(500, f"cloakbrowser_unavailable:{e}")
    start = time.time()
    result: dict = {"url": target, "ok": False}
    browser = None
    try:
        browser = launch()
        page = browser.new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=20000)
        if body.render_ms > 0:
            time.sleep(min(body.render_ms, 8000) / 1000)
        html = page.content()
        if "html" in body.want:
            result["html"] = html
        if "text" in body.want:
            try:
                result["text"] = page.inner_text("body")[:200000]
            except Exception:
                result["text"] = ""
        if "screenshot" in body.want:
            shot = page.screenshot(type="png")
            result["screenshot_b64"] = base64.b64encode(shot).decode("ascii")
        result["ok"] = True
    except Exception as e:
        result["error"] = str(e)[:300]
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
    dur = int((time.time() - start) * 1000)
    out_bytes = sum(len(str(v)) for v in result.values() if isinstance(v, (str, bytes)))
    with conn() as c:
        c.execute(
            "UPDATE usage SET ok=?, duration_ms=?, bytes_out=? WHERE id=?",
            (1 if result.get("ok") else 0, dur, out_bytes, usage_row_id),
        )
    result["duration_ms"] = dur
    return result


def create_customer_cli(email: str, plan: str = "free", limit: int = DAILY_LIMIT_DEFAULT) -> str:
    import secrets

    key = f"sk_sumo_{secrets.token_urlsafe(24)}"
    with conn() as c:
        c.execute(
            "INSERT INTO customers(api_key, email, plan, daily_limit) VALUES (?,?,?,?)",
            (key, email, plan, limit),
        )
    print(f"API key: {key} | email: {email} | plan: {plan} | limit: {limit}/day")
    return key


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "create":
        create_customer_cli(sys.argv[2] if len(sys.argv) > 2 else "test@example.com")
    else:
        print("usage: python main.py create <email> | or run with uvicorn")

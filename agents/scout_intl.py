"""
SCOUT INTL — scrape lead sources public, KHONG can API key.
Sources:
  - Code4rena audit opportunities (audits page)
  - Sherlock contests
  - Immunefi bug bounties
  - Upwork RSS public jobs
  - Fiverr buyer requests (public)
  - GitHub repos with open issues tagged "help wanted" / "bug" / "security"
Output: insert rows into leads(source, channel, ext_id, title, url, meta_json).
"""
import json
import re
import time
from urllib.parse import urljoin

import urllib.request

from orchestrator import register, db_conn, log

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36"


def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def upsert_lead(source: str, channel: str, ext_id: str, title: str, url: str, meta: dict) -> bool:
    with db_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO leads(source, channel, ext_id, title, url, meta_json) VALUES (?,?,?,?,?,?)",
            (source, channel, ext_id, title, url, json.dumps(meta, ensure_ascii=False)),
        )
        return cur.rowcount > 0


def scout_code4rena() -> int:
    """Code4rena public audits list."""
    n = 0
    try:
        html = http_get("https://code4rena.com/audits")
        # extract anchors to /audits/2026-... contests
        for m in re.finditer(r'href="(/audits/[^"]+)"[^>]*>([^<]{4,120})</a>', html):
            url = urljoin("https://code4rena.com", m.group(1))
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            ext_id = m.group(1)
            if upsert_lead("code4rena", "audit", ext_id, title, url, {}):
                n += 1
    except Exception as e:
        log.warning("scout_code4rena err: %s", e)
    return n


def scout_sherlock() -> int:
    n = 0
    try:
        html = http_get("https://audits.sherlock.xyz/contests")
        for m in re.finditer(r'href="(/contests/[^"]+)"[^>]*>([^<]{4,120})</a>', html):
            url = urljoin("https://audits.sherlock.xyz", m.group(1))
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            ext_id = m.group(1)
            if upsert_lead("sherlock", "audit", ext_id, title, url, {}):
                n += 1
    except Exception as e:
        log.warning("scout_sherlock err: %s", e)
    return n


def scout_immunefi() -> int:
    n = 0
    try:
        html = http_get("https://immunefi.com/bug-bounty/")
        for m in re.finditer(r'href="(/bug-bounty/[a-z0-9\-]+/?)"[^>]*>', html):
            url = urljoin("https://immunefi.com", m.group(1))
            ext_id = m.group(1)
            title = ext_id.replace("/bug-bounty/", "").strip("/")
            if upsert_lead("immunefi", "bounty", ext_id, title, url, {}):
                n += 1
    except Exception as e:
        log.warning("scout_immunefi err: %s", e)
    return n


def scout_upwork_rss() -> int:
    """Upwork public RSS for AI/security/web dev keywords."""
    n = 0
    queries = [
        "smart+contract+audit",
        "ai+agent+development",
        "scraping+api",
        "next.js+landing",
        "fastapi+python+saas",
    ]
    for q in queries:
        url = f"https://www.upwork.com/ab/feed/jobs/rss?q={q}&sort=recency&paging=0;10"
        try:
            xml = http_get(url)
            for m in re.finditer(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<guid[^>]*>(.*?)</guid>", xml, re.S):
                title = re.sub(r"<.*?>", "", m.group(1)).strip()
                link = m.group(2).strip()
                guid = m.group(3).strip()
                if upsert_lead("upwork", q, guid, title[:200], link, {}):
                    n += 1
        except Exception as e:
            log.warning("scout_upwork %s err: %s", q, e)
    return n


def scout_github_issues() -> int:
    """GitHub issues for bug-bounty hunting eligible repos."""
    n = 0
    try:
        for label in ["help+wanted", "good+first+issue", "bug", "security"]:
            url = f"https://api.github.com/search/issues?q=label:%22{label}%22+state:open+language:python&sort=created&order=desc&per_page=30"
            data = json.loads(http_get(url))
            for item in data.get("items", []):
                if upsert_lead(
                    "github",
                    label.replace("+", " "),
                    str(item["id"]),
                    item.get("title", "")[:200],
                    item.get("html_url", ""),
                    {"repo": item.get("repository_url"), "comments": item.get("comments")},
                ):
                    n += 1
            time.sleep(2)
    except Exception as e:
        log.warning("scout_github err: %s", e)
    return n


@register("scout_intl")
def run() -> dict:
    stats = {
        "code4rena": scout_code4rena(),
        "sherlock": scout_sherlock(),
        "immunefi": scout_immunefi(),
        "upwork": scout_upwork_rss(),
        "github": scout_github_issues(),
    }
    stats["total"] = sum(stats.values())
    return stats


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

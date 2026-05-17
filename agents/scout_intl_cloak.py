"""
SCOUT INTL CLOAK — JS-rendered sources via CloakBrowser.
Targets: Code4rena audits, Sherlock contests, Immunefi bug-bounties.
Output: leads(source, channel='audit'|'bounty', ext_id, title, url, meta_json).
"""
import json
import re
import time
import urllib.parse

from orchestrator import register, db_conn, log


def _upsert(source: str, channel: str, ext_id: str, title: str, url: str, meta: dict) -> bool:
    with db_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO leads(source, channel, ext_id, title, url, meta_json) "
            "VALUES (?,?,?,?,?,?)",
            (source, channel, ext_id, title, url, json.dumps(meta, ensure_ascii=False)),
        )
        return cur.rowcount > 0


def _open_browser():
    try:
        from cloakbrowser import launch
    except Exception as e:
        log.warning("cloakbrowser unavailable: %s", e)
        return None, None
    browser = launch()
    page = browser.new_page()
    return browser, page


def scrape_code4rena(page) -> int:
    n = 0
    try:
        page.goto("https://code4rena.com/audits", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        html = page.content()
        seen = set()
        for m in re.finditer(r'href="(/audits/[^"#?]+)"[^>]*>(?:[^<]*<[^>]+>)*([^<]{4,140})', html):
            slug = m.group(1)
            if slug in seen or slug.endswith("/leaderboard"):
                continue
            seen.add(slug)
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            if not title or title.lower() in {"audit", "audits"}:
                continue
            url = "https://code4rena.com" + slug
            if _upsert("code4rena", "audit", slug, title[:200], url, {}):
                n += 1
    except Exception as e:
        log.warning("scrape_code4rena err: %s", e)
    return n


def scrape_sherlock(page) -> int:
    n = 0
    try:
        page.goto("https://audits.sherlock.xyz/contests", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        html = page.content()
        seen = set()
        for m in re.finditer(r'href="(/contests/[0-9]+[^"#?]*)"[^>]*>([^<]{4,160})', html):
            slug = m.group(1)
            if slug in seen:
                continue
            seen.add(slug)
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            url = "https://audits.sherlock.xyz" + slug
            if _upsert("sherlock", "audit", slug, title[:200], url, {}):
                n += 1
    except Exception as e:
        log.warning("scrape_sherlock err: %s", e)
    return n


def scrape_immunefi(page) -> int:
    n = 0
    try:
        page.goto("https://immunefi.com/bug-bounty/", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        html = page.content()
        seen = set()
        for m in re.finditer(r'href="(/bug-bounty/[a-z0-9\-]+/?)"', html):
            slug = m.group(1).rstrip("/")
            if slug in seen:
                continue
            seen.add(slug)
            title = slug.replace("/bug-bounty/", "").replace("-", " ").title()
            url = "https://immunefi.com" + slug
            if _upsert("immunefi", "bounty", slug, title[:200], url, {}):
                n += 1
    except Exception as e:
        log.warning("scrape_immunefi err: %s", e)
    return n


def scrape_google_maps_smb(page, queries: list[str]) -> int:
    """Find Vietnamese SMB without website attribute on Google Maps."""
    n = 0
    for q in queries:
        try:
            url = f"https://www.google.com/maps/search/{urllib.parse.quote(q)}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            html = page.content()
            names = re.findall(r'aria-label="([^"]{6,80})"\s+jsaction', html)
            phones = re.findall(r"\+84[\s\-]?[0-9 \-]{8,12}|0\d{9,10}", html)
            for i, name in enumerate(names[:20]):
                phone = phones[i] if i < len(phones) else ""
                if not phone:
                    continue
                ext = f"{q}|{name}|{phone}"
                if _upsert(
                    "google_maps",
                    q.split()[0],
                    ext,
                    name,
                    url,
                    {"phone": phone, "query": q, "needs_web": True},
                ):
                    n += 1
            time.sleep(2)
        except Exception as e:
            log.warning("smb %s err: %s", q, e)
    return n


@register("scout_intl_cloak")
def run() -> dict:
    stats = {"code4rena": 0, "sherlock": 0, "immunefi": 0, "smb_vn": 0}
    browser, page = _open_browser()
    if not browser:
        return {**stats, "error": "no_browser"}
    try:
        stats["code4rena"] = scrape_code4rena(page)
        stats["sherlock"] = scrape_sherlock(page)
        stats["immunefi"] = scrape_immunefi(page)
        stats["smb_vn"] = scrape_google_maps_smb(
            page,
            [
                "quan an Quan 1 Ho Chi Minh",
                "cafe Quan 3 Ho Chi Minh",
                "tiem nail Ha Noi",
            ],
        )
    finally:
        try:
            browser.close()
        except Exception:
            pass
    stats["total"] = sum(v for v in stats.values() if isinstance(v, int))
    return stats


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

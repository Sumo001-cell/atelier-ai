"""
SCOUT VN — scrape lead source Viet Nam.
Sources:
  - TopCV public jobs (no API)
  - ITViec public jobs
  - VietnamWorks
  - Google Maps Places (SMB) via CloakBrowser (anti-bot)
  - FB Marketplace public listings (via CloakBrowser if logged in)
"""
import json
import re
import time
import urllib.request

from orchestrator import register, db_conn, log

UA = "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36"


def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "vi,en;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def upsert(source: str, channel: str, ext_id: str, title: str, url: str, meta: dict) -> bool:
    with db_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO leads(source, channel, ext_id, title, url, meta_json) VALUES (?,?,?,?,?,?)",
            (source, channel, ext_id, title, url, json.dumps(meta, ensure_ascii=False)),
        )
        return cur.rowcount > 0


def scout_topcv() -> int:
    """TopCV public job feed — fallback to CloakBrowser if 403."""
    n = 0
    try:
        from cloakbrowser import launch
    except Exception:
        log.warning("cloakbrowser not available")
        return 0
    queries = ["AI", "Python", "FastAPI", "Next.js", "Smart Contract", "Solidity", "Data Analyst"]
    browser = None
    try:
        browser = launch()
        page = browser.new_page()
        for q in queries:
            url = f"https://www.topcv.vn/tim-viec-lam-{q.replace(' ', '-').lower()}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                html = page.content()
                for m in re.finditer(r'href="(https?://www\.topcv\.vn/viec-lam/[^"]+)"[^>]*>([^<]{8,140})</a>', html):
                    link = m.group(1)
                    title = re.sub(r"\s+", " ", m.group(2)).strip()
                    if upsert("topcv", q, link, title[:200], link, {}):
                        n += 1
                time.sleep(2)
            except Exception as e:
                log.warning("topcv %s err: %s", q, e)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
    return n


def scout_itviec() -> int:
    n = 0
    queries = ["python", "ai", "fastapi", "nextjs", "solidity", "rust", "data-analyst"]
    for q in queries:
        try:
            html = http_get(f"https://itviec.com/it-jobs/{q}")
            for m in re.finditer(r'href="(/it-jobs/[a-z0-9\-]{8,})"[^>]*>', html):
                link = "https://itviec.com" + m.group(1)
                ext = m.group(1)
                title = ext.split("/")[-1].replace("-", " ").title()
                if upsert("itviec", q, ext, title[:200], link, {}):
                    n += 1
        except Exception as e:
            log.warning("itviec %s err: %s", q, e)
    return n


def scout_vnworks() -> int:
    n = 0
    try:
        html = http_get("https://www.vietnamworks.com/viec-lam-it-phan-mem-c10")
        for m in re.finditer(r'href="(https?://www\.vietnamworks\.com/[^"]+jv\.html)"', html):
            link = m.group(1)
            if upsert("vnworks", "it", link, link.rsplit("/", 1)[-1][:120], link, {}):
                n += 1
    except Exception as e:
        log.warning("vnworks err: %s", e)
    return n


def scout_smb_no_web() -> int:
    """
    Scrape Google Maps for SMB without website (high-value lead for Landing Gen SaaS).
    Uses CloakBrowser to evade rate limits.
    Strategy: search business category in HCM/HN, mark those without 'website' attribute.
    """
    n = 0
    try:
        from cloakbrowser import launch
    except Exception:
        log.warning("cloakbrowser unavailable, skip smb_no_web")
        return 0
    queries = [
        "quan an Quan 1 Ho Chi Minh",
        "cafe Quan 3 Ho Chi Minh",
        "spa Quan 7 Ho Chi Minh",
        "tiem nail Ha Noi",
        "shop quan ao Da Nang",
    ]
    browser = None
    try:
        browser = launch()
        page = browser.new_page()
        for q in queries:
            url = f"https://www.google.com/maps/search/{urllib.request.quote(q)}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(3)
                html = page.content()
                # Crude pass: collect business names + phone numbers from Maps DOM
                names = re.findall(r'aria-label="([^"]{6,80})"\s+jsaction', html)
                phones = re.findall(r"\+84[\s\-\d]{8,12}|0\d{9,10}", html)
                for i, name in enumerate(names[:20]):
                    phone = phones[i] if i < len(phones) else ""
                    if not phone:
                        continue
                    ext = f"{q}|{name}|{phone}"
                    if upsert(
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
                log.warning("smb_no_web %s err: %s", q, e)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
    return n


@register("scout_vn")
def run() -> dict:
    stats = {
        "itviec": scout_itviec(),
        "vnworks": scout_vnworks(),
        # heavy ops kept optional; un-skip when proven stable
        # "topcv": scout_topcv(),
        # "smb_no_web": scout_smb_no_web(),
    }
    stats["total"] = sum(v for v in stats.values() if isinstance(v, int))
    return stats


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

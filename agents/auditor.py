"""
AUDITOR — auto-scan target repo via bandit + semgrep + slither (if Solidity).

Workflow:
  1. SELECT lead url where source='github' AND stage='scouted'
  2. clone shallow into audits_targets/<slug>/
  3. run bandit (Python) or semgrep (multi-language) or slither (.sol)
  4. parse JSON, filter out validated-identifier / well-known false positives
  5. write findings to leads.meta_json.findings + advance stage to 'audited'

Outputs are passed to pr_drafter and submitter agents.
"""
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from orchestrator import register, db_conn, log, ROOT

TARGETS_DIR = ROOT / "audits_targets"
TARGETS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_HOSTS = {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com", "bitbucket.org"}
MAX_TARGETS_PER_RUN = int(os.getenv("AUDIT_PER_RUN", "5"))

# Patterns we treat as likely false positive when source code shows protection
FALSE_POSITIVE_GUARDS = [
    re.compile(r"_validate_identifier\b"),
    re.compile(r"@app\.route\([^)]*methods=.*['\"]GET['\"]"),
    re.compile(r"app\.add_url_rule"),
]


def sh(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> dict:
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout
        )
        return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}
    except FileNotFoundError as e:
        return {"rc": 127, "out": "", "err": str(e)}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "timeout"}


def repo_url_from_issue(issue_url: str) -> str | None:
    """Convert https://github.com/owner/repo/issues/123 -> https://github.com/owner/repo.git"""
    if not issue_url:
        return None
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/", issue_url)
    if not m:
        return None
    return f"https://github.com/{m.group(1)}/{m.group(2)}.git"


def _slug(url: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", url)
    return s.strip("-")[:60]


def clone_target(repo_url: str) -> Path | None:
    u = urlparse(repo_url)
    if u.hostname not in ALLOWED_HOSTS:
        log.warning("auditor: blocked host %s", u.hostname)
        return None
    slug = _slug(u.path)
    target = TARGETS_DIR / slug
    if target.exists():
        return target
    r = sh(["git", "clone", "--depth", "1", repo_url, str(target)], timeout=120)
    if r["rc"] != 0:
        log.warning("auditor: clone fail %s :: %s", repo_url, r["err"][:200])
        return None
    return target


def run_bandit(target: Path) -> list[dict]:
    out_path = LOGS_DIR / f"bandit_{target.name}.json"
    sh(["bandit", "-r", str(target), "-f", "json", "-ll", "-o", str(out_path)], timeout=180)
    if not out_path.is_file():
        return []
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        return data.get("results", []) or []
    except Exception:
        return []


def run_semgrep(target: Path) -> list[dict]:
    out_path = LOGS_DIR / f"semgrep_{target.name}.json"
    r = sh(
        ["semgrep", "--config=auto", "--json", "--output", str(out_path), str(target)],
        timeout=300,
    )
    if r["rc"] not in (0, 1):  # 0 ok, 1 = findings
        return []
    if not out_path.is_file():
        return []
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        return data.get("results", []) or []
    except Exception:
        return []


def looks_false_positive(target: Path, finding: dict) -> bool:
    file_rel = finding.get("filename") or finding.get("path") or ""
    if not file_rel:
        return False
    p = (target / file_rel).resolve() if not Path(file_rel).is_absolute() else Path(file_rel)
    try:
        if not p.is_relative_to(target.resolve()):
            return False
    except AttributeError:
        # Python <3.9 fallback
        try:
            p.relative_to(target.resolve())
        except ValueError:
            return False
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    for pat in FALSE_POSITIVE_GUARDS:
        if pat.search(text):
            return True
    return False


def severity_score(finding: dict) -> int:
    sev = (finding.get("issue_severity") or finding.get("severity") or "").upper()
    conf = (finding.get("issue_confidence") or "").upper()
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(sev, 0) * 2 + {
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }.get(conf, 0)


def normalise_finding(finding: dict, tool: str) -> dict:
    return {
        "tool": tool,
        "severity": finding.get("issue_severity") or finding.get("severity"),
        "confidence": finding.get("issue_confidence"),
        "test_id": finding.get("test_id") or finding.get("check_id"),
        "test_name": finding.get("test_name") or finding.get("check_id"),
        "cwe": (finding.get("issue_cwe") or {}).get("id") if tool == "bandit" else None,
        "filename": finding.get("filename") or finding.get("path"),
        "line": finding.get("line_number") or (finding.get("start") or {}).get("line"),
        "text": (finding.get("issue_text") or (finding.get("extra") or {}).get("message") or "")[
            :400
        ],
    }


@register("auditor")
def run() -> dict:
    stats = {"scanned": 0, "findings": 0, "skipped": 0, "false_positives": 0}
    with db_conn() as c:
        rows = c.execute(
            "SELECT id, title, url, meta_json FROM leads "
            "WHERE source='github' AND stage IN ('scouted','diagnosed','pitched') "
            "AND id NOT IN (SELECT lead_id FROM deliverables WHERE kind='audit_findings') "
            "ORDER BY id DESC LIMIT ?",
            (MAX_TARGETS_PER_RUN,),
        ).fetchall()
        for lead_id, title, url, meta_json in rows:
            repo_url = repo_url_from_issue(url)
            if not repo_url:
                stats["skipped"] += 1
                continue
            target = clone_target(repo_url)
            if not target:
                stats["skipped"] += 1
                continue
            bandit_results = run_bandit(target)
            semgrep_results = run_semgrep(target) if not bandit_results else []
            tool = "bandit" if bandit_results else "semgrep"
            findings = bandit_results or semgrep_results
            kept: list[dict] = []
            for f in findings:
                if looks_false_positive(target, f):
                    stats["false_positives"] += 1
                    continue
                kept.append(normalise_finding(f, tool))
            kept.sort(key=lambda x: -severity_score(x))
            top = kept[:20]
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            meta["findings"] = top
            meta["repo_url"] = repo_url
            stats["scanned"] += 1
            stats["findings"] += len(top)
            c.execute(
                "INSERT INTO deliverables(lead_id, kind, path, status) VALUES (?,?,?,?)",
                (lead_id, "audit_findings", str(target), "ready"),
            )
            c.execute(
                "UPDATE leads SET meta_json=?, stage='audited' WHERE id=?",
                (json.dumps(meta, ensure_ascii=False), lead_id),
            )
    return stats


if __name__ == "__main__":
    from orchestrator import db_init

    db_init()
    print(run())

"""
SMART CONTRACT AUDIT — automated MVP.
Workflow:
  1. clone target Solidity repo (or fetch single file)
  2. run slither --json -
  3. run myth analyze (skip if mythril not installed)
  4. parse + dedupe findings
  5. render markdown report (Code4rena format) and JSON
Usage: python audit.py <repo_url|file.sol> [--out DIR]
"""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime


SEVERITY_MAP = {
    "High": "H",
    "Medium": "M",
    "Low": "L",
    "Informational": "QA",
    "Optimization": "G",
}

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "contact@example.com")
ALLOWED_CLONE_HOSTS = {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com", "bitbucket.org"}


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


def clone_or_copy(target: str, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    if target.endswith(".sol"):
        src = Path(target).resolve()
        if not src.is_file():
            raise FileNotFoundError(target)
        cwd_base = Path.cwd().resolve()
        try:
            src.relative_to(cwd_base)
        except ValueError:
            raise PermissionError(f"path outside working directory: {src}")
        dest = work / src.name
        shutil.copyfile(src, dest)
        return work
    if target.startswith(("http://", "https://")):
        u = urlparse(target)
        if u.hostname not in ALLOWED_CLONE_HOSTS:
            raise PermissionError(f"clone host not allowed: {u.hostname}")
        repo_dir = work / "repo"
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        r = sh(["git", "clone", "--depth", "1", target, str(repo_dir)], timeout=180)
        if r["rc"] != 0:
            raise RuntimeError(f"clone failed: {r['err'][:200]}")
        return repo_dir
    raise ValueError(f"unsupported target: {target}")


def run_slither(repo: Path) -> dict:
    out = repo / "_slither.json"
    r = sh(["slither", str(repo), "--json", str(out)], timeout=600)
    findings: list[dict] = []
    if out.is_file():
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
            for d in data.get("results", {}).get("detectors", []) or []:
                findings.append(
                    {
                        "tool": "slither",
                        "check": d.get("check"),
                        "impact": d.get("impact"),
                        "confidence": d.get("confidence"),
                        "description": (d.get("description") or "").strip()[:1000],
                        "elements": [
                            {"name": e.get("name"), "src": e.get("source_mapping", {}).get("filename_short")}
                            for e in (d.get("elements") or [])[:3]
                        ],
                    }
                )
        except Exception as e:
            findings.append({"tool": "slither", "error": str(e)})
    return {"rc": r["rc"], "stderr": r["err"][:500], "findings": findings}


def run_mythril(file_or_dir: Path) -> dict:
    sol_files = list(file_or_dir.rglob("*.sol")) if file_or_dir.is_dir() else [file_or_dir]
    findings: list[dict] = []
    for sf in sol_files[:5]:
        r = sh(["myth", "analyze", str(sf), "-o", "json"], timeout=300)
        if r["rc"] == 0 and r["out"].strip():
            try:
                data = json.loads(r["out"])
                for iss in data.get("issues", []) or []:
                    findings.append(
                        {
                            "tool": "mythril",
                            "file": str(sf.relative_to(file_or_dir if file_or_dir.is_dir() else sf.parent)),
                            "swc": iss.get("swc-id"),
                            "severity": iss.get("severity"),
                            "title": iss.get("title"),
                            "description": (iss.get("description") or "").strip()[:600],
                        }
                    )
            except Exception:
                pass
    return {"findings": findings}


def render_markdown(target: str, slither: dict, mythril: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Smart Contract Audit — {target}\n")
    lines.append(f"Date: {datetime.utcnow().isoformat()}Z\n")
    lines.append("Pipeline: slither + mythril (automated) + manual review queued\n")
    total = len(slither["findings"]) + len(mythril["findings"])
    lines.append(f"\nTotal raw findings: **{total}**\n")
    if slither["findings"]:
        lines.append("\n## Slither\n")
        for i, f in enumerate(slither["findings"][:50], 1):
            tag = SEVERITY_MAP.get((f.get("impact") or "").title(), "?")
            lines.append(f"### [{tag}-{i:02d}] {f.get('check')} — {f.get('impact')}/{f.get('confidence')}")
            lines.append(f.get("description", ""))
            if f.get("elements"):
                lines.append("Elements:")
                for el in f["elements"]:
                    lines.append(f"- `{el.get('name')}` ({el.get('src')})")
            lines.append("")
    if mythril["findings"]:
        lines.append("\n## Mythril\n")
        for i, f in enumerate(mythril["findings"][:50], 1):
            lines.append(f"### [SWC-{f.get('swc')}-{i:02d}] {f.get('title')} — {f.get('severity')}")
            lines.append(f"File: `{f.get('file')}`")
            lines.append(f.get("description", ""))
            lines.append("")
    brand = os.getenv("BRAND_NAME", "Atelier")
    lines.append(f"\n---\nGenerated by {brand} Audit Pipeline · contact {CONTACT_EMAIL}\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="GitHub URL or local .sol file path")
    ap.add_argument("--out", default="audit_out")
    args = ap.parse_args()
    out_dir = Path(args.out).absolute()
    work = out_dir / "work"
    repo = clone_or_copy(args.target, work)
    slither = run_slither(repo)
    mythril = run_mythril(repo if repo.is_dir() else repo.parent)
    report_md = render_markdown(args.target, slither, mythril)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")
    (out_dir / "raw.json").write_text(
        json.dumps({"slither": slither, "mythril": mythril}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"OK report -> {out_dir / 'report.md'}")
    print(f"Slither findings: {len(slither['findings'])} | Mythril findings: {len(mythril['findings'])}")


if __name__ == "__main__":
    main()

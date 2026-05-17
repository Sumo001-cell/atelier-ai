"""
Boot all 3 product APIs on different ports + optional cloudflared tunnels.
Usage: python boot_all.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

SERVICES = [
    {
        "name": "scrape_api",
        "module": "products.scrape_api.main:app",
        "port": 8080,
        "env": {},
    },
    {
        "name": "landing_gen",
        "module": "products.landing_gen.main:app",
        "port": 8091,
        "env": {
            "PRICE_USD": os.getenv("PRICE_USD", "99"),
            "PRICE_VND": os.getenv("PRICE_VND", "500000"),
            "PAYPAL_ME": os.getenv("PAYPAL_ME", "https://paypal.me/atelier-ai"),
        },
    },
]


def launch(svc: dict) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(svc["env"])
    log = LOG_DIR / f"{svc['name']}.log"
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        svc["module"],
        "--host",
        "0.0.0.0",
        "--port",
        str(svc["port"]),
        "--log-level",
        "info",
    ]
    print(f"launching {svc['name']} on :{svc['port']} -> {log}")
    with open(log, "a", encoding="utf-8") as f:
        return subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=f, stderr=f)


def main() -> None:
    procs = [launch(s) for s in SERVICES]
    print(f"started {len(procs)} services")
    print("press Ctrl+C to stop")
    try:
        while True:
            time.sleep(5)
            for s, p in zip(SERVICES, procs):
                if p.poll() is not None:
                    print(f"!! {s['name']} exited rc={p.returncode}")
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()

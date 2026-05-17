"""
ORCHESTRATOR — Task 16/5.9 AI 1 nguoi 7 agent
Concept: FB#2 4AIVN — Scout / Diagnoser / Builder / Filmer / Pitcher / Checker / Support
Stack: Claude Code + ECC v2 + html-anything + CloakBrowser + viecremote-bot + mattpocock skills
"""
import sys
import time
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
DB = ROOT / "db" / "state.sqlite3"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
(ROOT / "db").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "orchestrator.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("orch")


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def db_init() -> None:
    with db_conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                channel TEXT NOT NULL,
                ext_id TEXT,
                title TEXT,
                url TEXT,
                meta_json TEXT,
                score REAL DEFAULT 0,
                stage TEXT DEFAULT 'scouted',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, ext_id)
            );
            CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
            CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);

            CREATE TABLE IF NOT EXISTS deliverables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER REFERENCES leads(id),
                kind TEXT NOT NULL,
                path TEXT,
                url TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS outreach (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER REFERENCES leads(id),
                channel TEXT NOT NULL,
                payload_path TEXT,
                response TEXT,
                sent_at TEXT,
                reply_at TEXT,
                status TEXT DEFAULT 'queued'
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER REFERENCES leads(id),
                product TEXT NOT NULL,
                amount_usd REAL,
                amount_vnd REAL,
                paid_via TEXT,
                payout_to TEXT,
                tx_id TEXT,
                paid_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                ok INTEGER,
                stats_json TEXT
            );
            """
        )
    log.info("db_init ok: %s", DB)


AGENT_REGISTRY: dict[str, callable] = {}


def register(name: str):
    def wrap(fn):
        AGENT_REGISTRY[name] = fn
        return fn

    return wrap


def run_agent(name: str) -> dict:
    fn = AGENT_REGISTRY.get(name)
    if not fn:
        log.error("unknown agent: %s", name)
        return {"ok": False, "error": "unknown_agent"}
    start = time.time()
    stats: dict = {}
    ok = True
    try:
        result = fn() or {}
        stats = result if isinstance(result, dict) else {}
    except Exception as e:
        ok = False
        stats = {"error": str(e)}
        log.exception("agent %s failed", name)
    dur = round(time.time() - start, 2)
    stats["duration_s"] = dur
    with db_conn() as c:
        c.execute(
            "INSERT INTO agent_runs(agent, ended_at, ok, stats_json) VALUES (?,?,?,?)",
            (name, datetime.utcnow().isoformat(), 1 if ok else 0, json.dumps(stats, ensure_ascii=False)),
        )
    log.info("agent %s ok=%s dur=%ss stats=%s", name, ok, dur, stats)
    return {"ok": ok, "stats": stats}


def schedule_loop(interval_s: int = 600) -> None:
    """Main orchestrator loop. Run 7 agent sequentially each cycle."""
    pipeline = ["scout_intl", "scout_vn", "diagnoser", "builder", "pitcher", "checker", "support"]
    cycle = 0
    while True:
        cycle += 1
        log.info("=== cycle %d ===", cycle)
        for ag in pipeline:
            if ag in AGENT_REGISTRY:
                run_agent(ag)
        log.info("cycle %d done, sleep %ds", cycle, interval_s)
        time.sleep(interval_s)


def import_agents() -> None:
    """Import agent modules to populate AGENT_REGISTRY."""
    sys.path.insert(0, str(ROOT))
    for mod in [
        "agents.scout_intl",
        "agents.scout_intl_cloak",
        "agents.scout_vn",
        "agents.diagnoser",
        "agents.builder",
        "agents.pitcher",
        "agents.checker",
        "agents.support_bot",
    ]:
        try:
            __import__(mod)
        except Exception as e:
            log.warning("skip import %s: %s", mod, e)


def main() -> None:
    if __name__ == "__main__":
        sys.modules["orchestrator"] = sys.modules["__main__"]
    db_init()
    import_agents()
    log.info("registered agents: %s", list(AGENT_REGISTRY))
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "init":
            return
        if cmd == "run":
            ag = sys.argv[2] if len(sys.argv) > 2 else None
            if ag and ag != "all":
                run_agent(ag)
                return
            for a in AGENT_REGISTRY:
                run_agent(a)
            return
        if cmd == "loop":
            schedule_loop(int(sys.argv[2]) if len(sys.argv) > 2 else 600)
            return
    print("usage: orchestrator.py {init|run [agent|all]|loop [interval_s]}")


if __name__ == "__main__":
    main()

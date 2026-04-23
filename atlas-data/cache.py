import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

# Default to /tmp so Vercel Lambda (read-only filesystem except /tmp) works without config.
# CACHE_DB env var overrides for local dev or custom deployments.
DB = Path(os.getenv("CACHE_DB") or str(Path(tempfile.gettempdir()) / "atlas-cache.db"))


def _conn():
    c = sqlite3.connect(str(DB), timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, exp REAL)")
    return c


def get(key: str):
    try:
        with _conn() as c:
            row = c.execute("SELECT v, exp FROM cache WHERE k=?", (key,)).fetchone()
        if not row or row[1] < time.time():
            return None
        return json.loads(row[0])
    except Exception:
        return None


def get_stale(key: str):
    try:
        with _conn() as c:
            row = c.execute("SELECT v FROM cache WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        return json.loads(row[0])
    except Exception:
        return None


def put(key: str, value, ttl_sec: int):
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                (key, json.dumps(value), time.time() + ttl_sec),
            )
    except Exception:
        pass

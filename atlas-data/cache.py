import json
import os
import sqlite3
import time
from pathlib import Path

DB = Path(os.getenv("CACHE_DB", Path(__file__).parent / "cache.db"))


def _conn():
    c = sqlite3.connect(DB, timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, exp REAL)")
    return c


def get(key: str):
    with _conn() as c:
        row = c.execute("SELECT v, exp FROM cache WHERE k=?", (key,)).fetchone()
    if not row or row[1] < time.time():
        return None
    return json.loads(row[0])


def get_stale(key: str):
    with _conn() as c:
        row = c.execute("SELECT v FROM cache WHERE k=?", (key,)).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def put(key: str, value, ttl_sec: int):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            (key, json.dumps(value), time.time() + ttl_sec),
        )

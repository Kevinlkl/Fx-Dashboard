"""SQLite connection + upsert helpers.

SQLite keeps the repo zero-setup: the database is one file, no server. Every
statement here is plain SQL, so swapping to Postgres later means changing this
module and nothing else.
"""
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH, SCHEMA_PATH


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_fx(conn, rows):
    """rows: list of (date, currency, session, unit, buying, selling, middle, source)"""
    ts = now()
    conn.executemany(
        """INSERT INTO fx_rates
             (date, currency, session, unit, buying, selling, middle, source, ingested_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(date, currency, session) DO UPDATE SET
             unit=excluded.unit, buying=excluded.buying,
             selling=excluded.selling, middle=excluded.middle,
             source=excluded.source, ingested_at=excluded.ingested_at""",
        [tuple(r) + (ts,) for r in rows],
    )
    conn.commit()
    return len(rows)


def upsert_interest(conn, rows):
    """rows: list of (date, country, series, tenor, rate, source)"""
    ts = now()
    conn.executemany(
        """INSERT INTO interest_rates
             (date, country, series, tenor, rate, source, ingested_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(date, country, series, tenor) DO UPDATE SET
             rate=excluded.rate, source=excluded.source,
             ingested_at=excluded.ingested_at""",
        [tuple(r) + (ts,) for r in rows],
    )
    conn.commit()
    return len(rows)


def log_ingest(conn, source, scope, rows, status):
    conn.execute(
        "INSERT INTO ingest_log (ts, source, scope, rows, status) VALUES (?,?,?,?,?)",
        (now(), source, scope, rows, status),
    )
    conn.commit()


def months_present(conn, table, where_sql, params=()):
    """Return {'YYYY-MM'} already stored, used to skip completed months."""
    cur = conn.execute(
        f"SELECT DISTINCT substr(date,1,7) AS ym FROM {table} WHERE {where_sql}", params
    )
    return {r["ym"] for r in cur}

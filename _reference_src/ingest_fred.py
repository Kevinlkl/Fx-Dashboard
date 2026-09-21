"""Ingestion of US interest rates from FRED.

Uses FRED's CSV download endpoint, which needs no API key. The registered API
would also work; this keeps the repo runnable by anyone who clones it.

DTB3 (3-month T-bill) is the USD leg used for covered interest parity at the
3-month tenor. SOFR is pulled as an overnight cross-check.

    python src/ingest_fred.py
"""
import csv
import io
import sys

import requests

from config import FRED_CSV, FRED_SERIES, START_YEAR
from db import connect, init_db, log_ingest, upsert_interest

TIMEOUT = 60
TENOR_OF = {"DTB3": "3_month", "SOFR": "overnight"}


def fetch_series(series_id):
    r = requests.get(
        FRED_CSV,
        params={"id": series_id, "cosd": f"{START_YEAR}-01-01"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    rows = []
    for rec in reader:
        d = rec.get("observation_date") or rec.get("DATE")
        raw = rec.get(series_id, "").strip()
        if not d or raw in ("", "."):   # '.' is FRED's missing-value marker
            continue
        rows.append((d, "US", series_id, TENOR_OF[series_id], float(raw), "FRED"))
    return rows


def main():
    conn = connect()
    init_db(conn)
    for series_id, label in FRED_SERIES.items():
        try:
            rows = fetch_series(series_id)
        except Exception as e:                      # noqa: BLE001 - log and continue
            print(f"  ! {series_id}: {e}", file=sys.stderr)
            log_ingest(conn, "fred", series_id, 0, f"error: {e}")
            continue
        n = upsert_interest(conn, rows) if rows else 0
        log_ingest(conn, "fred", series_id, n, "ok" if n else "empty")
        print(f"  {series_id} ({label}): {n} rows")
    conn.close()
    print("done")


if __name__ == "__main__":
    main()

"""US interest rates from FRED.

Uses FRED's CSV download endpoint, which needs no API key, so the repo stays
runnable by anyone who clones it.

DTB4WK (4-week T-bill) is the USD leg for a 1-month hedge; DTB3 is kept for a
3-month robustness check, SOFR as an overnight cross-check.

    python ingest_fred.py
"""
import csv
import io
import sys

import requests

from config import FRED_CSV, FRED_SERIES, START_YEAR, TENOR_OF
from db import connect, init_db, log_ingest, upsert_interest

TIMEOUT = 60


def fetch_series(series_id):
    r = requests.get(FRED_CSV,
                     params={"id": series_id, "cosd": f"{START_YEAR}-01-01"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    rows = []
    for rec in reader:
        d = rec.get("observation_date") or rec.get("DATE")
        raw = rec.get(series_id, "").strip()
        if not d or raw in ("", "."):      # '.' is FRED's missing-value marker
            continue
        rows.append((d, "US", series_id, TENOR_OF[series_id], float(raw), "FRED"))
    return rows


def main():
    conn = connect()
    init_db(conn)
    for series_id, label in FRED_SERIES.items():
        try:
            rows = fetch_series(series_id)
        except Exception as e:
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
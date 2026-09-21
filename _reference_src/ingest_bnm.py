"""Incremental ingestion from the Bank Negara Malaysia Open API.

Pulls three series into SQLite:
  * daily USD/MYR exchange rates (buying / selling / middle)
  * daily interbank money-market rates by tenor
  * Overnight Policy Rate decisions

Incremental rule: a month already present in the database is skipped unless it
is the current month, which is always refetched because it is still filling up.
Re-running the script is therefore cheap and safe.

    python src/ingest_bnm.py            # backfill from START_YEAR to today
    python src/ingest_bnm.py --full     # ignore what is stored, refetch all
"""
import argparse
import sys
import time
from datetime import date

import requests

from config import BNM_BASE, BNM_HEADERS, CURRENCY, FX_SESSION, START_YEAR
from db import connect, init_db, log_ingest, months_present, upsert_fx, upsert_interest

SLEEP = 0.3          # be polite to a free public API
TIMEOUT = 30
TENORS = ["overnight", "1_week", "1_month", "3_month", "6_month", "1_year"]


def get(path, **params):
    """GET one BNM endpoint, returning the 'data' payload (or None on failure)."""
    url = f"{BNM_BASE}/{path}"
    try:
        r = requests.get(url, headers=BNM_HEADERS, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        print(f"  ! {path}: {e}", file=sys.stderr)
        return None
    if r.status_code != 200:
        print(f"  ! {path}: HTTP {r.status_code}", file=sys.stderr)
        return None
    return r.json().get("data")


def month_range(start_year):
    """Yield (year, month) from January of start_year through the current month."""
    today = date.today()
    for y in range(start_year, today.year + 1):
        for m in range(1, 13):
            if (y, m) > (today.year, today.month):
                return
            yield y, m


def ingest_fx(conn, full=False):
    have = set() if full else months_present(
        conn, "fx_rates", "currency=? AND session=?", (CURRENCY, FX_SESSION)
    )
    current = date.today().strftime("%Y-%m")
    total = 0
    for y, m in month_range(START_YEAR):
        ym = f"{y}-{m:02d}"
        if ym in have and ym != current:
            continue
        data = get(
            f"exchange-rate/{CURRENCY.lower()}/year/{y}/month/{m}",
            session=FX_SESSION, quote="rm",
        )
        time.sleep(SLEEP)
        if not data:
            log_ingest(conn, "bnm_fx", ym, 0, "empty")
            continue
        unit = data.get("unit", 1)
        quotes = data.get("rate", [])
        if isinstance(quotes, dict):        # single-day payloads are not wrapped
            quotes = [quotes]
        rows = [
            (q["date"], CURRENCY, FX_SESSION, unit,
             q.get("buying_rate"), q.get("selling_rate"), q.get("middle_rate"),
             "BNM")
            for q in quotes if q.get("date")
        ]
        n = upsert_fx(conn, rows) if rows else 0
        log_ingest(conn, "bnm_fx", ym, n, "ok" if n else "empty")
        total += n
        print(f"  fx {ym}: {n} rows")
    return total


def ingest_interbank(conn, full=False):
    """Interbank money-market rates. Longer tenors are quoted only on days when
    a trade actually happened, so nulls here are genuine absences, not errors."""
    have = set() if full else months_present(
        conn, "interest_rates", "country='MY' AND series='interbank'"
    )
    current = date.today().strftime("%Y-%m")
    total = 0
    for y, m in month_range(START_YEAR):
        ym = f"{y}-{m:02d}"
        if ym in have and ym != current:
            continue
        data = get(f"interest-rate/year/{y}/month/{m}", quote="rm", product="interbank")
        time.sleep(SLEEP)
        if not data:
            log_ingest(conn, "bnm_interbank", ym, 0, "empty")
            continue
        rows = [
            (d["date"], "MY", "interbank", t, d[t], "BNM")
            for d in data for t in TENORS
            if d.get(t) is not None
        ]
        n = upsert_interest(conn, rows) if rows else 0
        log_ingest(conn, "bnm_interbank", ym, n, "ok" if n else "empty")
        total += n
        print(f"  interbank {ym}: {n} quotes")
    return total


def ingest_opr(conn, full=False):
    """OPR decisions. Only ~6 rows a year, so we always refetch the whole span."""
    total = 0
    for y in range(START_YEAR, date.today().year + 1):
        data = get(f"opr/year/{y}")
        time.sleep(SLEEP)
        if not data:
            log_ingest(conn, "bnm_opr", str(y), 0, "empty")
            continue
        rows = [
            (d["date"], "MY", "opr", "policy", d["new_opr_level"], "BNM")
            for d in data if d.get("date")
        ]
        n = upsert_interest(conn, rows) if rows else 0
        log_ingest(conn, "bnm_opr", str(y), n, "ok" if n else "empty")
        total += n
    print(f"  opr: {total} decisions")
    return total


def main():
    ap = argparse.ArgumentParser(description="Ingest BNM data into SQLite.")
    ap.add_argument("--full", action="store_true", help="refetch everything")
    args = ap.parse_args()

    conn = connect()
    init_db(conn)
    print(f"BNM ingest -> {conn.execute('PRAGMA database_list').fetchone()['file']}")
    ingest_fx(conn, args.full)
    ingest_interbank(conn, args.full)
    ingest_opr(conn, args.full)
    conn.close()
    print("done")


if __name__ == "__main__":
    main()

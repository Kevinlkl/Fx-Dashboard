"""
Urm, basically make it regen every fig quoted in docs/data_cleaning.md, then assert the 
invariants that the pipeline must satisfy

2 kinds of output:
    REPORT - descriptive numbers, printed for comparison against the doc
    CHECK - invariants that must hold; any failure exits non-zero
"""

import sys
import numpy as np
import pandas as pd
from db import connect

TENORS = ["1_month", "3_month", "6_month", "1_year"]

def fx_calender(conn):
    return pd.read_sql(
        """
        SELECT DISTINCT date
        FROM fx_rates
        ORDER BY date
        """,
        conn, parse_dates=["date"]
    )

def staleness(conn, cal, series, tenor):
    """
    How old the most recent quote is on each FX trading day.

    Measured against every published quote, including those falling on days
    with no FX quote at all. Walking only the FX calendar misses ~400 of the
    1-month quotes and overstates staleness.
    """
    r = pd.read_sql(
        """SELECT date, rate FROM interest_rates WHERE series=? AND tenor=? ORDER BY date""",
        conn, params=(series, tenor), parse_dates=["date"]
    )

    if r.empty:
        return None
    m = pd.merge_asof(cal, r.assign(quote_date=r["date"]), on="date", direction="backward")
    age = (m["date"] - m["quote_date"]).dt.days
    return dict(quoted=len(r), median=age.median(), p90=age.quantile(.9), worst=age.max(), over30=int((age > 30).sum()))

def report_coverage(conn):
    print("== source coverage ==")
    print(pd.read_sql("""
        SELECT 'fx_rates' AS tbl, COUNT(*) n, MIN(date) lo, MAX(date) hi FROM fx_rates
        UNION ALL
        SELECT country||' '||series, COUNT(*), MIN(date), MAX(date)
        FROM interest_rates GROUP BY country, series
    """, conn).to_string(index=False))


def report_staleness(conn, cal):
    print("\n== interbank coverage and forward-fill staleness ==")
    rows = []
    for t in TENORS:
        s = staleness(conn, cal, "interbank", t)
        if s:
            rows.append({"tenor": t, "quoted": s["quoted"],
                         "pct": f"{100*s['quoted']/len(cal):.0f}%",
                         "median": s["median"], "p90": s["p90"],
                         "worst": s["worst"], "over30d": s["over30"]})
    print(pd.DataFrame(rows).to_string(index=False))


def report_opr_spread(conn):
    """Is the interbank-minus-OPR gap stable enough to reconstruct a missing
    quote? Yes at 1-month, no at 3-month."""
    opr = pd.read_sql(
        "SELECT date, rate opr FROM interest_rates WHERE series='opr' ORDER BY date",
        conn, parse_dates=["date"])
    print("\n== interbank minus OPR, bps (stability of the fallback) ==")
    for t in ["1_month", "3_month"]:
        r = pd.read_sql(
            "SELECT date, rate FROM interest_rates WHERE series='interbank' "
            "AND tenor=? ORDER BY date", conn, params=(t,), parse_dates=["date"])
        d = pd.merge_asof(r, opr, on="date")
        s = (d["rate"] - d["opr"]) * 100
        yr = s.groupby(d["date"].dt.year).std()
        print(f"  {t}: mean {s.mean():+.0f}  sd {s.std():.0f}  "
              f"within-year sd {yr.min():.0f}-{yr.max():.0f}")


def report_fx_quality(conn):
    fx = pd.read_sql("SELECT date, buying, selling, middle FROM fx_rates ORDER BY date",
                     conn, parse_dates=["date"])
    sp = (fx["selling"] - fx["buying"]) / fx["middle"] * 100
    gaps = fx["date"].diff().dt.days
    ret = np.log(fx["middle"]).diff()
    print("\n== FX series quality ==")
    print(f"  raw spread % of mid : mean {sp.mean():.4f}  min {sp.min():.4f}  max {sp.max():.4f}")
    print(f"  gaps                : max {gaps.max():.0f}d | 4+ days {(gaps>=4).sum()} | 3 days {(gaps==3).sum()}")
    print(f"  daily log return    : sd {ret.std()*100:.3f}%  min {ret.min()*100:+.2f}%  max {ret.max()*100:+.2f}%")
    print(f"  moves beyond 3sd    : {(ret.abs() > 3*ret.std()).sum()}")


def report_premium(conn):
    p = pd.read_sql("SELECT * FROM daily_panel", conn,
                    parse_dates=["date"]).dropna(subset=["myr_1m", "usd_1m"])
    t = 1 / 12
    F = p["spot_mid"] * (1 + p["myr_1m"] / 100 * t) / (1 + p["usd_1m"] / 100 * t)
    prem = (F - p["spot_mid"]) * 100
    print("\n== 1-month forward premium, sen ==")
    print(f"  overall mean {prem.mean():+.2f}")
    yr = prem.groupby(p["date"].dt.year).mean()
    print("  " + "  ".join(f"{y}:{v:+.2f}" for y, v in yr.items()))


def checks(conn, cal):
    fails = []
    p = pd.read_sql("SELECT * FROM daily_panel", conn, parse_dates=["date"])

    n_fx = pd.read_sql("SELECT COUNT(*) n FROM fx_rates", conn)["n"][0]
    if len(p) != n_fx:
        fails.append(f"daily_panel has {len(p)} rows, fx_rates has {n_fx}")
    if not (p["cost_rate"] > p["spot_sell"]).all():
        fails.append("cost_rate not above spot_sell on every row")
    n_nan = int(p["log_ret"].isna().sum())
    if n_nan != 1:
        fails.append(f"log_ret has {n_nan} NaNs, expected exactly 1")
    for col in ["myr_1m_age", "usd_1m_age"]:
        bad = int((p[col] < 0).sum())
        if bad:
            fails.append(f"{col} negative on {bad} rows - as-of join looked forward")
    dupes = pd.read_sql("""SELECT COUNT(*) n FROM (
            SELECT date, currency, session FROM fx_rates
            GROUP BY 1,2,3 HAVING COUNT(*)>1)""", conn)["n"][0]
    if dupes:
        fails.append(f"{dupes} duplicate rows in fx_rates")
    pay = set(pd.read_sql("SELECT payment_date FROM payments", conn)["payment_date"])
    off = sorted(pay - set(cal["date"].dt.strftime("%Y-%m-%d")))
    if off:
        fails.append(f"{len(off)} payment dates are not FX trading days: {off[:3]}")
    return fails


def main():
    conn = connect()
    cal = fx_calender(conn)
    report_coverage(conn)
    report_staleness(conn, cal)
    report_opr_spread(conn)
    report_fx_quality(conn)
    report_premium(conn)

    fails = checks(conn, cal)
    print("\n== invariant checks ==")
    if fails:
        for f in fails:
            print("  FAIL:", f)
        conn.close()
        sys.exit(1)
    print("  all passed")
    conn.close()


if __name__ == "__main__":
    main()

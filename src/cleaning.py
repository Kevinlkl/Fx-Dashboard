"""Build the analysis-ready daily panel from the raw tables.

Rebuilt from scratch each run. At ~2,900 rows this takes milliseconds, and a
full rebuild is far easier to reason about than incremental patching.

    python clean.py                 # default 0.3% bank spread
    python clean.py --spread 0.005  # sweep a different assumption
"""
import argparse
import numpy as np
import pandas as pd

from config import CURRENCY, FX_SESSION
from db import connect, init_db

DEFAULT_SPREAD = 0.003 # SME markup over BNM's interbank selling rate

def load_fx(conn):
    return pd.read_sql(
        """SELECT date, selling as spot_sell, middle AS spot_mid
           FROM fx_rates WHERE currency=? and session=? ORDER BY date""",
        conn, params=(CURRENCY, FX_SESSION), parse_dates=["date"]
    )

def load_rate(conn, series, tenor):
    """One rate series, nulls already excluded from the tenor. """
    df = pd.read_sql(
        """SELECT date, rate from interest_rates
        WHERE series=? and tenor=? ORDER BY date""",
        conn, params=(series, tenor), parse_dates=["date"]
    )
    df["quote_date"] = df["date"]
    return df

def asof(panel, rates, name):
    """Attach the most recent rate published on or before each panel date.

    direction='backward' is mandatory. 'nearest' would happily pull a rate
    published *after* the date and silently create look-ahead bias.
    """
    out = pd.merge_asof(
        panel, rates.rename(columns={"rate": name}),
        on="date", direction="backward",
    )
    out[f"{name}_age"] = (out["date"] - out["quote_date"]).dt.days
    return out.drop(columns=["quote_date"])

def build_panel(conn, spread=DEFAULT_SPREAD):
    panel = load_fx(conn)

    # What the importer actually pays: BNM's selling rate plus a bank markup.
    panel["cost_rate"] = panel["spot_sell"] * (1 + spread)

    # Returns off the mid, not the selling rate: bid-ask bounce would show up
    # as volatility that never happened. Consecutive trading days only, no
    # calendar fill.
    panel["log_ret"] = np.log(panel["spot_mid"]).diff()

    panel = asof(panel, load_rate(conn, "interbank", "1_month"), "myr_1m")
    panel = asof(panel, load_rate(conn, "DTB4WK", "1_month"), "usd_1m")
    return panel


def write_panel(conn, panel):
    out = panel.assign(date=panel["date"].dt.strftime("%Y-%m-%d"))
    out.to_sql("daily_panel", conn, index=False, if_exists="replace")
    conn.commit()


def main():
    ap = argparse.ArgumentParser(description="Build daily_panel.")
    ap.add_argument("--spread", type=float, default=DEFAULT_SPREAD,
                    help="bank spread over BNM selling rate (0.003 = 0.3%%)")
    args = ap.parse_args()

    conn = connect()
    init_db(conn)
    panel = build_panel(conn, args.spread)
    write_panel(conn, panel)

    print(f"daily_panel: {len(panel)} rows, "
          f"{panel.date.min().date()} to {panel.date.max().date()}")
    print(f"spread applied: {args.spread:.3%}")
    print(panel.tail(3).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
"""Simulated payment schedule for the importer.

USD 18,000 due each month-end. Month-end resolves to the last day the FX market
actually quoted, following the modified-following convention: a payment landing
on a non-business day settles on the previous business day rather than rolling
into the next month.

    python payments.py
"""
import argparse

import pandas as pd

from db import connect, init_db

USD_PER_MONTH = 18_000
FIRST_MONTH = "2015-06"      # interbank rates begin 2015-06-05


def build_schedule(conn, usd=USD_PER_MONTH, first=FIRST_MONTH):
    cal = pd.read_sql("SELECT date FROM daily_panel ORDER BY date",
                      conn, parse_dates=["date"])["date"]
    cal = cal[cal >= pd.Timestamp(f"{first}-01")]

    last_trading_day = cal.groupby(cal.dt.to_period("M")).max()

    # Drop the current month: it has not finished, so its "last trading day"
    # is merely today, not a real month-end.
    last_trading_day = last_trading_day.iloc[:-1]

    return pd.DataFrame({
        "payment_date": last_trading_day.dt.strftime("%Y-%m-%d"),
        "usd_amount": float(usd),
    })


def write(conn, df):
    # DELETE + append rather than replace, so the column types declared in
    # schema.sql survive. daily_panel is derived and can be replaced; payments
    # is a declared table.
    conn.execute("DELETE FROM payments")
    df.to_sql("payments", conn, index=False, if_exists="append")
    conn.commit()


def main():
    ap = argparse.ArgumentParser(description="Build the payment schedule.")
    ap.add_argument("--usd", type=float, default=USD_PER_MONTH)
    args = ap.parse_args()

    conn = connect()
    init_db(conn)
    df = build_schedule(conn, args.usd)
    write(conn, df)
    print(f"payments: {len(df)} months, "
          f"{df.payment_date.min()} to {df.payment_date.max()}")
    print(df.tail(3).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
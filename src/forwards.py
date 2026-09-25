"""Forward pricing from covered interest parity.

One row per payment. The decision is made at the previous month-end and the
contract settles at the payment date, so everything here uses only information
available on the decision date.

    python forwards.py
"""
import pandas as pd

from db import connect

# Money-market day counts: MYR quotes ACT/365, USD money market ACT/360.
MYR_BASIS = 365
USD_BASIS = 360


def build_forwards(conn):
    panel = pd.read_sql("SELECT * FROM daily_panel ORDER BY date", conn,
                        parse_dates=["date"]).set_index("date")
    pay = pd.read_sql("SELECT payment_date, usd_amount FROM payments "
                      "ORDER BY payment_date", conn, parse_dates=["payment_date"])

    # The hedge for payment i is decided at payment i-1: one month ahead.
    # The first payment therefore has no decision date and is dropped.
    f = pd.DataFrame({
        "payment_date":  pay.payment_date,
        "decision_date": pay.payment_date.shift(1),
        "usd_amount":    pay.usd_amount,
    }).dropna(subset=["decision_date"])

    f["days"] = (f.payment_date - f.decision_date).dt.days

    dec = panel.reindex(f.decision_date)
    f["spot_decision"] = dec.spot_sell.values
    f["myr_1m"] = dec.myr_1m.values
    f["usd_1m"] = dec.usd_1m.values
    f["myr_age"] = dec.myr_1m_age.values      # audit trail for staleness
    f["spot_payment"] = panel.reindex(f.payment_date).spot_sell.values

    f["forward_rate"] = f.spot_decision * (
        (1 + f.myr_1m / 100 * f.days / MYR_BASIS) /
        (1 + f.usd_1m / 100 * f.days / USD_BASIS)
    )

    return f.dropna(subset=["forward_rate", "spot_payment"]).reset_index(drop=True)


def write(conn, f):
    out = f.assign(
        payment_date=f.payment_date.dt.strftime("%Y-%m-%d"),
        decision_date=f.decision_date.dt.strftime("%Y-%m-%d"),
    )
    out.to_sql("forwards", conn, index=False, if_exists="replace")
    conn.commit()


def main():
    conn = connect()
    f = build_forwards(conn)
    write(conn, f)
    prem = (f.forward_rate - f.spot_decision) * 100
    print(f"forwards: {len(f)} contracts, "
          f"{f.payment_date.min().date()} to {f.payment_date.max().date()}")
    print(f"  premium, sen: mean {prem.mean():+.2f}  "
          f"min {prem.min():+.2f}  max {prem.max():+.2f}")
    print(f"  MYR rate older than 14 days on {(f.myr_age > 14).sum()} decisions")
    conn.close()


if __name__ == "__main__":
    main()
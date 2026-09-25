"""Export analysis tables to CSV for Power BI.

Power BI has no native SQLite connector, and an ODBC driver would be friction
for anyone cloning the repo. CSV is universal and these tables are small.

The design rule: export COMPONENTS, never precomputed costs. DAX recomputes
cost from spot, forward, hedge ratio and spread, so a what-if parameter can
move the ratio without rerunning Python. A precomputed myr_cost column would
make the simulator impossible.

    python export.py
"""
from pathlib import Path

import pandas as pd

from backtest import budget_series, strategy_e, DEFAULT_SPREAD
from db import connect
from forwards import build_forwards

OUT = Path(__file__).resolve().parents[1] / "exports"


def payments_fact(conn):
    """The simulator's fact table: one row per payment, components only."""
    f = build_forwards(conn).set_index("payment_date")
    budget = budget_series(conn, f)
    vol = pd.read_sql("SELECT payment_date, garch FROM vol_forecasts", conn,
                      parse_dates=["payment_date"]).set_index("payment_date")

    return pd.DataFrame({
        "payment_date":  f.index.strftime("%Y-%m-%d"),
        "decision_date": f.decision_date.dt.strftime("%Y-%m-%d"),
        "year":          f.index.year,
        "days":          f.days.values,
        "usd_amount":    f.usd_amount.values,
        "spot_decision": f.spot_decision.values,   # known when hedging
        "spot_payment":  f.spot_payment.values,    # known only at settlement
        "forward_rate":  f.forward_rate.values,
        "budget_rate":   (budget / f.usd_amount / (1 + DEFAULT_SPREAD)).values,
        "garch_vol":     vol.garch.reindex(f.index).values,
        "h_garch":       pd.Series(strategy_e(conn, f)).values,
    })


def main():
    OUT.mkdir(exist_ok=True)
    conn = connect()

    tables = {
        "payments_fact": payments_fact(conn),
        "daily_panel": pd.read_sql(
            "SELECT date, spot_mid, spot_sell, cost_rate, log_ret, "
            "myr_1m, usd_1m FROM daily_panel ORDER BY date", conn),
        "hedge_frontier": pd.read_sql(
            "SELECT * FROM hedge_frontier ORDER BY hedge_ratio", conn),
        "bootstrap_ci": pd.read_sql("SELECT * FROM bootstrap_ci", conn),
        "strategy_results": pd.read_sql(
            "SELECT * FROM strategy_results ORDER BY strategy, payment_date", conn),
    }

    for name, df in tables.items():
        path = OUT / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"  {name:18} {len(df):>5} rows  ->  {path.name}")

    conn.close()


if __name__ == "__main__":
    main()
"""Backtest hedging policies against the simulated payment schedule.

Every strategy is a rule for one number: the fraction of each payment locked
forward at the previous month-end. Cost is therefore

    [h * forward_rate + (1-h) * spot_at_payment] * (1 + spread) * usd

    python backtest.py
"""
import argparse

import numpy as np
import pandas as pd

from db import connect
from forwards import build_forwards

DEFAULT_SPREAD = 0.003
STATIC = {"A_no_hedge": 0.0, "B_full_forward": 1.0, "C_half_static": 0.5}


def budget_series(conn, f):
    """Budget rate is fixed on the first trading day of each January."""
    panel = pd.read_sql("SELECT date, cost_rate FROM daily_panel ORDER BY date",
                        conn, parse_dates=["date"]).set_index("date")
    jan = panel.cost_rate.groupby(panel.index.year).first()
    return pd.Series(f.index.year, index=f.index).map(jan) * f.usd_amount


def cost_of(f, h, spread):
    """h may be a scalar or a per-payment Series (Strategy E)."""
    rate = h * f.forward_rate + (1 - h) * f.spot_payment
    return rate * (1 + spread) * f.usd_amount


def expected_at_decision(f, h, spread):
    """What the firm believed the cost would be when it decided.

    The unhedged fraction is valued at spot on the decision date: the Fama
    regression showed the forward carries no signal, so a random walk is the
    honest forecast.
    """
    rate = h * f.forward_rate + (1 - h) * f.spot_decision
    return rate * (1 + spread) * f.usd_amount


def kpis(f, h, spread, budget):
    cost = cost_of(f, h, spread)
    err = cost - expected_at_decision(f, h, spread)
    over = cost - budget
    k = max(1, int(np.ceil(len(cost) * 0.05)))
    return {
        "total_cost": cost.sum(),
        "mean_cost": cost.mean(),
        "planning_err_sd": err.std(),     # the headline risk measure
        "cost_sd": cost.std(),            # shallow U, explain why
        "worst_overrun": over.max(),
        "cvar95": cost.nlargest(k).mean(),
        "months_over_budget": int((over > 0).sum()),
    }


def min_variance_ratio(f):
    F, S = f.forward_rate, f.spot_payment
    return (S.var() - F.cov(S)) / (F.var() + S.var() - 2 * F.cov(S))

def strategy_e(conn, f):
    """GARCH-triggered: hedge fully when the forecast is in the top quartile.

    The quantile must expand, not span the full sample - a full-sample
    quantile uses forecasts that did not exist at the decision date.
    """
    v = pd.read_sql("SELECT payment_date, garch FROM vol_forecasts", conn,
                    parse_dates=["payment_date"]).set_index("payment_date")
    g = v.garch.reindex(f.index)
    threshold = g.expanding(min_periods=12).quantile(0.75).shift(1)
    return pd.Series(np.where(g > threshold, 1.0, 0.5),
                     index=f.index).where(g.notna(), 0.5)


def run(conn, spread=DEFAULT_SPREAD):
    f = build_forwards(conn).set_index("payment_date")
    budget = budget_series(conn, f)

    table = {name: kpis(f, h, spread, budget) for name, h in STATIC.items()}
    h_star = min_variance_ratio(f)
    table[f"MV_h={h_star:.2f}"] = kpis(f, h_star, spread, budget)
    h_e = strategy_e(conn, f)
    table["E_garch_trigger"] = kpis(f, h_e, spread, budget)
    table[f"E_control_static_{h_e.mean():.2f}"] = kpis(f, h_e.mean(), spread, budget)

    frontier = pd.DataFrame([
        dict(hedge_ratio=h, **kpis(f, h, spread, budget))
        for h in np.round(np.arange(0, 1.001, 0.05), 3)
    ])

    rows = []
    strategies = (list(STATIC.items())
                  + [(f"MV_h={h_star:.2f}", h_star), ("E_garch_trigger", h_e)])
    for name, h in strategies:
        c = cost_of(f, h, spread)
        rows.append(pd.DataFrame({
            "strategy": name,
            "payment_date": f.index.strftime("%Y-%m-%d"),
            "hedge_ratio": h,
            "spot_rate": f.spot_payment.values,
            "forward_rate": f.forward_rate.values,
            "usd_amount": f.usd_amount.values,
            "myr_cost": c.values,
        }))
    results = pd.concat(rows, ignore_index=True)
    return pd.DataFrame(table).T, frontier, results, h_star


def main():
    ap = argparse.ArgumentParser(description="Backtest hedging policies.")
    ap.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
    args = ap.parse_args()

    conn = connect()
    summary, frontier, results, h_star = run(conn, args.spread)

    results.to_sql("strategy_results", conn, index=False, if_exists="replace")
    frontier.to_sql("hedge_frontier", conn, index=False, if_exists="replace")
    conn.commit()

    pd.set_option("display.float_format", lambda v: f"{v:,.1f}")
    print(summary.to_string())
    print(f"\nminimum-variance hedge ratio: {h_star:.3f}")
    print(f"planning error at h=0: RM {summary.loc['A_no_hedge','planning_err_sd']:,.0f}"
          f"  ->  at h=1: RM {summary.loc['B_full_forward','planning_err_sd']:,.0f}")
    conn.close()


if __name__ == "__main__":
    main()
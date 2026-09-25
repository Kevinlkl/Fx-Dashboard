"""Block bootstrap confidence intervals for the strategy comparisons.

Monthly cost is highly persistent (lag-1 autocorrelation 0.895, still 0.30 at
lag 12), so an iid bootstrap would destroy that structure and return
confidence intervals far too narrow. We resample contiguous blocks instead.

All strategies are evaluated on the same resampled path, so comparisons stay
paired rather than being two independent draws.

    python bootstrap.py
"""
import warnings

import numpy as np
import pandas as pd
from arch.bootstrap import StationaryBootstrap, optimal_block_length

from backtest import (DEFAULT_SPREAD, budget_series, min_variance_ratio,
                      strategy_e)
from db import connect
from forwards import build_forwards

REPS = 2000
SEED = 42


def panel_frame(conn):
    """One self-contained row per payment: everything a KPI needs."""
    f = build_forwards(conn).set_index("payment_date")
    return pd.DataFrame({
        "fwd": f.forward_rate.values,
        "s_dec": f.spot_decision.values,
        "s_pay": f.spot_payment.values,
        "usd": f.usd_amount.values,
        "budget": budget_series(conn, f).values,
        "h_e": np.asarray(strategy_e(conn, f)),
    }), f


def kpi(d, h, spread):
    cost = (h * d.fwd + (1 - h) * d.s_pay) * (1 + spread) * d.usd
    expected = (h * d.fwd + (1 - h) * d.s_dec) * (1 + spread) * d.usd
    over = cost - d.budget
    k = max(1, int(np.ceil(len(d) * 0.05)))
    return dict(cost_sd=cost.std(), plan_sd=(cost - expected).std(),
                worst=over.max(), total=cost.sum(), cvar=cost.nlargest(k).mean())


COMPARISONS = [
    "cost sd: MV vs unhedged",
    "total cost: 100% vs unhedged",
    "planning err: E vs control",
    "cost sd: E vs control",
    "worst overrun: E vs control",
    "cvar95: MV vs unhedged",
]


def make_stat(h_star, mean_he, spread):
    def stat(d):
        a = kpi(d, 0.0, spread)
        b = kpi(d, 1.0, spread)
        mv = kpi(d, h_star, spread)
        e = kpi(d, d.h_e.values, spread)
        ec = kpi(d, mean_he, spread)
        return np.array([
            (mv["cost_sd"] / a["cost_sd"] - 1) * 100,
            (b["total"] / a["total"] - 1) * 100,
            (e["plan_sd"] - ec["plan_sd"]) / ec["plan_sd"] * 100,
            (e["cost_sd"] - ec["cost_sd"]) / ec["cost_sd"] * 100,
            (e["worst"] - ec["worst"]) / ec["worst"] * 100,
            (mv["cvar"] / a["cvar"] - 1) * 100,
        ])
    return stat


def main():
    warnings.filterwarnings("ignore")
    conn = connect()
    D, f = panel_frame(conn)
    h_star = min_variance_ratio(f)
    mean_he = D.h_e.mean()

    # Block length from the data, not a rule of thumb.
    cost = D.s_pay * (1 + DEFAULT_SPREAD) * D.usd
    block = float(optimal_block_length(np.asarray(cost))["stationary"].iloc[0])

    stat = make_stat(h_star, mean_he, DEFAULT_SPREAD)
    point = stat(D)
    bs = StationaryBootstrap(block, D, seed=SEED)
    ci = bs.conf_int(stat, reps=REPS, method="percentile", size=0.95)

    print(f"stationary bootstrap, expected block {block:.1f} months, "
          f"{REPS} reps, n={len(D)}\n")
    print(f"{'comparison':32}{'point':>9}{'95% CI':>22}   sig?")
    rows = []
    for i, name in enumerate(COMPARISONS):
        lo, hi = ci[0, i], ci[1, i]
        sig = (lo > 0) == (hi > 0)
        print(f"{name:32}{point[i]:>+8.2f}%   [{lo:>+7.2f}, {hi:>+7.2f}]   "
              f"{'yes' if sig else 'NO'}")
        rows.append(dict(comparison=name, point=point[i], lo=lo, hi=hi,
                         significant=int(sig)))

    pd.DataFrame(rows).to_sql("bootstrap_ci", conn, index=False,
                              if_exists="replace")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
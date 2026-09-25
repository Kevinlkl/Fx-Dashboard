"""Walk-forward GARCH(1,1) volatility forecasts.

At each decision date, refit on returns available strictly up to that date and
forecast volatility over the coming month. Nothing after the decision date
touches the fit.

    python volatility.py
"""
import time
import warnings

import numpy as np
import pandas as pd
from arch import arch_model

from db import connect
from forwards import build_forwards

MIN_OBS = 250          # GARCH needs a warm-up; ~1 year of daily data
TRADING_RATIO = 5 / 7  # calendar days -> trading days


def qlike(forecast, realised):
    """QLIKE loss. Penalises under-forecasting risk far more than over-.

    RMSE treats a forecast 2 points too low the same as 2 points too high.
    For a risk application those are not the same mistake.
    """
    x = realised ** 2 / forecast ** 2
    return (x - np.log(x) - 1).mean()


def walk_forward(conn):
    panel = pd.read_sql("SELECT date, log_ret FROM daily_panel ORDER BY date",
                        conn, parse_dates=["date"]).set_index("date")
    r = panel.log_ret.dropna() * 100      # percent: arch converges far better
    f = build_forwards(conn).set_index("payment_date")

    rows = []
    for pay_date, row in f.iterrows():
        dec = row.decision_date
        hist = r.loc[:dec]                # strictly up to the decision date
        if len(hist) < MIN_OBS:
            continue
        horizon = int((pay_date - dec).days * TRADING_RATIO)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = arch_model(hist, vol="GARCH", p=1, q=1,
                             dist="t", mean="Constant").fit(disp="off",
                                                            show_warning=False)
            var_path = res.forecast(horizon=horizon,
                                    reindex=False).variance.values[-1]

        realised_fwd = r.loc[dec:pay_date].iloc[1:]      # strictly after
        rows.append(dict(
            payment_date=pay_date, decision_date=dec, horizon=horizon,
            garch=np.sqrt(var_path.sum()),
            naive=hist.iloc[-21:].std() * np.sqrt(horizon),
            realised=np.sqrt((realised_fwd ** 2).sum()),
        ))
    return pd.DataFrame(rows).dropna()


def main():
    conn = connect()
    t0 = time.time()
    d = walk_forward(conn)
    print(f"{len(d)} walk-forward forecasts in {time.time()-t0:.1f}s")

    for name in ("garch", "naive"):
        err = d[name] - d.realised
        print(f"  {name:6} RMSE {np.sqrt((err**2).mean()):.3f}  "
              f"bias {err.mean():+.3f}  QLIKE {qlike(d[name], d.realised):.4f}")

    out = d.assign(payment_date=d.payment_date.dt.strftime("%Y-%m-%d"),
                   decision_date=d.decision_date.dt.strftime("%Y-%m-%d"))
    out.to_sql("vol_forecasts", conn, index=False, if_exists="replace")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
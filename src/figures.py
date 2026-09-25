"""EDA figures. Each function makes one chart and saves a PNG.

Static matplotlib rather than Plotly: these are for the README and the
methodology write-up. The interactive versions come in Phase 5.

    python figures.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from db import connect

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"

# Palette roles, not raw colors, so every chart stays consistent.
BLUE   = "#2a78d6"   # primary series
ORANGE = "#eb6834"   # second series
RED    = "#d03b3b"   # the "bad" pole of a diverging scale
INK    = "#0b0b0b"
MUTED  = "#898781"   # axis labels, reference lines
GRID   = "#e1e0d9"
SURFACE = "#fcfcfb"


def style_axes(ax, title, subtitle=None, ylabel=None):
    """Recessive chrome: the data should be the darkest thing on the chart."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(colors=MUTED, labelsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.set_title(title, color=INK, fontsize=13, fontweight="600",
                 loc="left", pad=26 if subtitle else 10)
    if subtitle:
        # offset points, not axes fraction: fixed spacing at any figure size
        ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 7), textcoords="offset points",
                    color=MUTED, fontsize=10, va="bottom")


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=150, bbox_inches="tight",
                facecolor=SURFACE)
    plt.close(fig)
    print(f"  wrote {name}.png")


def panel(conn):
    return pd.read_sql("SELECT * FROM daily_panel ORDER BY date", conn,
                       parse_dates=["date"]).set_index("date")


# --------------------------------------------------------------------------
def fig_spot(p):
    """One series over time: a single hue, no legend, events as annotations."""
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(p.index, p.spot_mid, color=BLUE, linewidth=1.6)

    # date, label, (dx, dy) offset in points, horizontal alignment
    events = [
        ("2015-08-31", "Aug 2015\nringgit slide", (-14, -52), "right"),
        ("2020-03-23", "Mar 2020\nCOVID shock",   (-8,   30), "right"),
        ("2024-04-17", "Apr 2024\npeak 4.79",     (18,   10), "left"),
    ]
    for date, label, off, ha in events:
        d = pd.Timestamp(date)
        if d not in p.index:
            d = p.index[p.index.get_indexer([d], method="nearest")[0]]
        y = p.spot_mid[d]
        ax.scatter([d], [y], s=30, color=BLUE, zorder=3,
                   edgecolor=SURFACE, linewidth=1.8)
        ax.annotate(label, (d, y), xytext=off, textcoords="offset points",
                    ha=ha, fontsize=9, color=MUTED, linespacing=1.3,
                    arrowprops=dict(arrowstyle="-", color="#c3c2b7", linewidth=1))

    ax.set_ylim(p.spot_mid.min() - 0.05, p.spot_mid.max() + 0.10)
    style_axes(ax, "USD/MYR, 2015 to 2026",
               "Mid rate. A rising line means a weaker ringgit and costlier imports.",
               "MYR per USD")
    save(fig, "01_spot")


# --------------------------------------------------------------------------
def fig_returns(p):
    """Two panels: the intuitive view and the rigorous one."""
    r = p.log_ret.dropna() * 100
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    counts, bins, _ = ax.hist(r, bins=90, color=BLUE, alpha=0.85, label="Observed")
    x = np.linspace(r.min(), r.max(), 400)
    ax.plot(x, stats.norm.pdf(x, r.mean(), r.std()) * len(r) * (bins[1] - bins[0]),
            color=MUTED, linewidth=2, linestyle="--", label="Normal")
    ax.set_yscale("log")
    ax.set_ylim(bottom=0.6)          # floor just under one count
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED)
    style_axes(ax, "Daily returns vs a normal curve",
               "Log scale: the tails are the point.", "Days (log)")
    ax.set_xlabel("Daily log return, %", color=MUTED, fontsize=9)

    ax = axes[1]
    z = (r - r.mean()) / r.std()     # standardise so y = x is the right reference
    osm, osr = stats.probplot(z, dist="norm", fit=False)
    ax.scatter(osm, osr, s=8, color=BLUE, alpha=0.6)
    lim = [min(osm.min(), osr.min()) - 0.2, max(osm.max(), osr.max()) + 0.2]
    ax.plot(lim, lim, color=MUTED, linewidth=1.5, linestyle="--")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    style_axes(ax, "Normal Q-Q plot",
               f"Excess kurtosis {stats.kurtosis(r):.1f}; normal would be 0.",
               "Observed quantile (sd units)")
    ax.set_xlabel("Theoretical quantile (sd units)", color=MUTED, fontsize=9)

    fig.tight_layout()
    save(fig, "02_returns")

def fig_volatility(p):
    """Two windows of the same measure, plus the Strategy E threshold."""
    r = p.log_ret
    v30 = r.rolling(30).std() * np.sqrt(252) * 100
    v90 = r.rolling(90).std() * np.sqrt(252) * 100
    trigger = v30.quantile(0.75)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(v30.index, v30, color=BLUE, linewidth=1.3, label="30-day")
    ax.plot(v90.index, v90, color=ORANGE, linewidth=1.8, label="90-day")
    ax.axhline(trigger, color=MUTED, linewidth=1, linestyle=":")
    ax.text(pd.Timestamp("2018-01-01"), trigger + 0.55,
            f"Strategy E trigger: 75th pct = {trigger:.1f}%",
            fontsize=8.5, color=MUTED)
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper right")
    ax.set_ylim(0, v30.max() * 1.12)
    style_axes(ax, "Rolling annualised volatility",
               "Calm and turbulent periods cluster; they do not alternate randomly.",
               "Annualised volatility, %")
    save(fig, "03_volatility")


def fig_differential(p):
    """The rate gap that sets the forward price, as one series against zero.

    Deliberately NOT a dual-axis chart of rates against spot.
    """
    d = (p.myr_1m - p.usd_1m).dropna()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.axhline(0, color="#c3c2b7", linewidth=1.2)
    ax.fill_between(d.index, d, 0, where=(d >= 0), color=RED,
                    alpha=0.18, interpolate=True)
    ax.fill_between(d.index, d, 0, where=(d < 0), color=BLUE,
                    alpha=0.18, interpolate=True)
    ax.plot(d.index, d, color=INK, linewidth=1.2)

    cross = pd.Timestamp("2022-09-01")
    ax.scatter([cross], [d.asof(cross)], s=34, color=INK, zorder=3,
               edgecolor=SURFACE, linewidth=1.8)
    ax.annotate("Sep 2022\nfirst crossing", (cross, d.asof(cross)),
                xytext=(-14, -46), textcoords="offset points", ha="right",
                fontsize=9, color=MUTED, linespacing=1.3,
                arrowprops=dict(arrowstyle="-", color="#c3c2b7", linewidth=1))

    # The colour alone would mislead here, so each region is labelled.
    ax.text(pd.Timestamp("2017-01-01"), 3.05,
            "MYR rate higher  -  forward above spot\nhedging costs a premium",
            fontsize=9, color=RED, linespacing=1.4)
    ax.text(d.index[-20], -0.42,
            "USD rate higher  -  forward below spot\nhedging pays",
            ha="right", fontsize=9, color=BLUE, linespacing=1.4)

    style_axes(ax, "Malaysian minus US 1-month interest rate",
               "This gap sets the forward rate. Its sign decides who pays for the hedge.",
               "Rate differential, percentage points")
    save(fig, "04_differential")

def fig_forward_predicts(p):
    """Fama regression: does the forward premium predict the spot move?

    Monthly, non-overlapping. Sampling daily with a one-month horizon would
    overlap 20 of every 21 observations, leaving the residuals badly
    autocorrelated and the standard errors far too small.
    """
    m = p.dropna(subset=["myr_1m", "usd_1m"]).resample("ME").last()
    t = 1 / 12
    fwd = np.log((1 + m.myr_1m / 100 * t) / (1 + m.usd_1m / 100 * t)) * 100
    real = (np.log(m.spot_mid).shift(-1) - np.log(m.spot_mid)) * 100
    d = pd.DataFrame({"fwd": fwd, "real": real}).dropna()
    res = stats.linregress(d.fwd, d.real)

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    ax.axhline(0, color=GRID, linewidth=1)
    ax.axvline(0, color=GRID, linewidth=1)
    ax.scatter(d.fwd, d.real, s=22, color=BLUE, alpha=0.55, edgecolor="none")
    xs = np.linspace(d.fwd.min(), d.fwd.max(), 50)
    ax.plot(xs, xs, color=MUTED, linestyle="--", linewidth=1.5)
    ax.plot(xs, res.intercept + res.slope * xs, color=ORANGE, linewidth=2)
    ax.annotate("unbiased forward\n(slope 1)", (xs[-1], xs[-1]), xytext=(-6, 14),
                textcoords="offset points", ha="right", fontsize=8.5,
                color=MUTED, linespacing=1.3)
    ax.annotate(f"fitted slope {res.slope:.2f}",
                (xs[-1], res.intercept + res.slope * xs[-1]), xytext=(-6, -20),
                textcoords="offset points", ha="right", fontsize=8.5, color=ORANGE)
    style_axes(ax, "Does the forward predict the spot move?",
               f"Monthly, non-overlapping. n={len(d)}, R-sq {res.rvalue**2:.3f}.",
               "Realised spot move over next month, %")
    ax.set_xlabel("Forward premium at decision date, %", color=MUTED, fontsize=9)
    save(fig, "05_forward_predicts")
    print(f"    beta={res.slope:.2f} se={res.stderr:.2f} p={res.pvalue:.3f}")


def fig_budget(p, conn):
    """The business question in one chart: how often was the budget blown?"""
    pay = pd.read_sql("SELECT payment_date, usd_amount FROM payments", conn,
                      parse_dates=["payment_date"]).set_index("payment_date")
    cost = (p.cost_rate.reindex(pay.index) * pay.usd_amount).dropna()
    jan = p.cost_rate.groupby(p.index.year).first()   # budget rate set each January
    budget = pd.Series(cost.index.year, index=cost.index).map(jan) * pay.usd_amount

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(cost.index, cost, budget, where=(cost >= budget),
                    color=RED, alpha=0.20, interpolate=True)
    ax.fill_between(cost.index, cost, budget, where=(cost < budget),
                    color=BLUE, alpha=0.20, interpolate=True)
    ax.plot(budget.index, budget, color=MUTED, linewidth=1.4,
            linestyle="--", label="Budget rate")
    ax.plot(cost.index, cost, color=INK, linewidth=1.6, label="Actual cost")
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper left")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v/1000:.0f}k")
    style_axes(ax, "Monthly cost of USD 18,000, unhedged",
               "Budget rate fixed each January. Red is a month over budget.", "MYR")
    save(fig, "06_budget")

    over = cost - budget
    print(f"    {(over > 0).sum()} of {len(over)} months over budget, "
          f"worst RM {over.max():,.0f}")


def main():
    conn = connect()
    p = panel(conn)
    fig_spot(p)
    fig_returns(p)
    fig_volatility(p)
    fig_differential(p)
    fig_forward_predicts(p)
    fig_budget(p, conn)
    conn.close()


if __name__ == "__main__":
    main()
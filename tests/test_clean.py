"""Logic tests for the cleaning layer.

These run against a tiny in-memory fixture where the correct answer is known by
hand, not against the real database. They never touch data/fx.db.
"""
import math
import sqlite3

import numpy as np
import pytest

from cleaning import build_panel, write_panel
from db import init_db
from payment import build_schedule

# date, buying, selling, middle
FX = [
    ("2024-01-01", 3.98, 4.00, 3.99),
    ("2024-01-02", 4.08, 4.10, 4.09),
    ("2024-01-05", 4.18, 4.20, 4.19),   # Friday after a weekend gap
]

# The 01-04 MYR quote deliberately falls on a day with no FX quote, mirroring
# the ~400 real interbank quotes that land outside the FX calendar.
RATES = [
    ("2024-01-01", "MY", "interbank", "1_month", 3.00),
    ("2024-01-04", "MY", "interbank", "1_month", 3.50),
    ("2024-01-02", "US", "DTB4WK",    "1_month", 5.00),
]


def make_db(fx=FX, rates=RATES):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.executemany(
        "INSERT INTO fx_rates (date,currency,session,unit,buying,selling,middle,"
        "source,ingested_at) VALUES (?,'USD','1200',1,?,?,?,'test','test')", fx)
    conn.executemany(
        "INSERT INTO interest_rates (date,country,series,tenor,rate,source,"
        "ingested_at) VALUES (?,?,?,?,?,'test','test')", rates)
    conn.commit()
    return conn


@pytest.fixture
def panel():
    return build_panel(make_db())


def test_asof_uses_latest_prior_quote(panel):
    """On 01-05 the newest MYR quote is 01-04, a day with no FX row at all."""
    assert list(panel.myr_1m) == [3.00, 3.00, 3.50]
    assert list(panel.myr_1m_age) == [0, 1, 1]


def test_asof_never_looks_forward(panel):
    """The only USD quote is 01-02, so 01-01 must stay empty rather than
    borrow it. This is the look-ahead guard: direction='nearest' would fill it."""
    assert np.isnan(panel.usd_1m[0])
    assert np.isnan(panel.usd_1m_age[0])
    assert list(panel.usd_1m[1:]) == [5.00, 5.00]
    assert list(panel.usd_1m_age[1:]) == [0, 3]


def test_cost_rate_applies_spread_to_selling(panel):
    assert panel.cost_rate[0] == pytest.approx(4.00 * 1.003)
    assert (panel.cost_rate > panel.spot_sell).all()


def test_log_ret_uses_mid_not_selling(panel):
    """Returns must come off the mid, or bid-ask bounce leaks into volatility."""
    assert np.isnan(panel.log_ret[0])
    assert panel.log_ret[1] == pytest.approx(math.log(4.09 / 3.99))
    # and would be a different number off the selling rate
    assert panel.log_ret[1] != pytest.approx(math.log(4.10 / 4.00))


def test_spread_is_configurable():
    p = build_panel(make_db(), spread=0.01)
    assert p.cost_rate[0] == pytest.approx(4.00 * 1.01)


def test_payment_rolls_back_to_last_trading_day():
    """February ends on the 29th in 2024, but the market last quoted on the
    28th. Modified following rolls backward, never into March."""
    fx = [("2024-01-30", 3.98, 4.00, 3.99), ("2024-01-31", 3.98, 4.00, 3.99),
          ("2024-02-27", 3.98, 4.00, 3.99), ("2024-02-28", 3.98, 4.00, 3.99),
          ("2024-03-28", 3.98, 4.00, 3.99)]
    conn = make_db(fx=fx, rates=[])
    write_panel(conn, build_panel(conn))
    s = build_schedule(conn, usd=18000, first="2024-01")

    assert list(s.payment_date) == ["2024-01-31", "2024-02-28"]
    assert (s.usd_amount == 18000).all()
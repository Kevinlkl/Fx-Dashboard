# Progress

**Read this file first at the start of a session.** It is the current state of
the project. It is rewritten, not appended to — history lives in
`docs/sessions/`, which does not need reading unless you are chasing *why* a
past decision was made.

Last updated: 2026-09-25 (session 2)

## Status

| Phase | State |
|---|---|
| 0 — Framing | done (scenario + KPIs settled) |
| 1 — Ingestion | **done** |
| 2 — Cleaning | **done** |
| 3 — EDA | **done** (6 figures) |
| 4 — Modelling / backtest | next |
| 5 — Dashboard | not started |
| 6 — Packaging | not started |

## What the project is

Simulated Malaysian importer (KL Trading Sdn Bhd) paying USD 18,000 month-end,
~RM 1M/year. Question: should it hedge with forwards, how much, and does a
volatility-triggered rule beat a fixed policy? KPIs: total MYR cost, sd of
monthly cost, worst-month overrun vs budget rate, 95% CVaR.

Framing that governs everything: hedging reduces **variance**, not expected
cost. An honest result beats a cherry-picked saving.

## Environment

Windows 11, PowerShell 5.1 (no `&&`, no ternary, no `??`; use `;` and
here-strings with `'@` at column 0). Python 3.11.9 with requests/pandas/numpy
already installed. `curl` is an alias for Invoke-WebRequest — type `curl.exe`.
In `python -c`, double quotes outside, single inside; `\"` does not work.

Scripts use flat imports (`from config import ...`), so **run them from inside
`src/`**, not the repo root.

## Current data (SQLite at `data/fx.db`, gitignored)

| Table | Rows | Span |
|---|---|---|
| `fx_rates` | 2,868 | 2015-01-02 → 2026-09-21 |
| `interest_rates` MY interbank | 9,534 | 2015-06-05 → 2026-09-18 |
| `interest_rates` MY opr | 70 | 2015-01-28 → 2026-09-03 |
| `interest_rates` US DTB3 | 2,929 | 2015-01-02 → 2026-09-17 |
| `interest_rates` US DTB4WK | 2,929 | 2015-01-02 → 2026-09-17 |
| `interest_rates` US SOFR | 2,113 | 2018-04-03 → 2026-09-17 |

Rebuild from scratch: `cd src; python ingest_bnm.py; python ingest_fred.py`
(~2 min first run, seconds after — incremental by month).

## Decisions already locked

Full reasoning in `docs/data_cleaning.md`. Do not re-derive these:

- **Session 1200** of BNM's four (all four have complete data).
- **Hedge tenor: 1 month**, not 3. 3-month interbank is quoted on only 35% of
  days and forward-filling it means rates up to 100 days stale on 7% of
  decision dates. 1-month is 66% covered, never worse than 27 days stale.
- **USD leg: DTB4WK**, tenor-matched to the 1-month hedge.
- **Cost side: `selling` + an added bank spread, default 0.3%.** BNM's raw
  spread averages 0.11% of mid, which is interbank, not retail.
- **Forwards are synthetic**, from covered interest parity. No free source has
  real USD/MYR forward quotes — BNM's `interbank-swap` endpoint is trade
  volumes, not swap points.
- **Missing dates:** forward-fill for payment lookups, drop for returns. Never
  mix.
- **Nulls become absent rows**, not null rows. Interest rates stored long.
- **The firm stays fictional** (KL Trading Sdn Bhd, USD 18,000/month). Considered
  swapping in a real large-cap (TNB, Mr DIY, Capital A) and rejected it: big
  firms already hedge with treasury desks, their exposure is not RM 1M, and
  attaching a real name to invented numbers is worse than an honest fiction.

## Findings worth keeping

- 1-month forward premium averages +0.28 sen; sd of a one-month spot move is
  9.30 sen. Carry is ~3% of the risk being hedged, so results will be driven by
  spot, not rates.
- That premium **flips sign in 2023** — positive 2015-2022, negative 2023-2026.
  Any backtest on recent data only will flatter forward hedging.

## Framing notes (for the README and any economics-literate reader)

- **Results are scale-invariant.** "Cut cost volatility by X%" is a percentage;
  hedge ratios are fractions. RM 1M is a *default input* to the scenario
  simulator, not a premise. Say this explicitly in the README — it reframes the
  fictional firm as a worked example of a general tool.
- **Why a firm should hedge at all.** In frictionless markets hedging adds no
  value (Modigliani-Miller); shareholders can diversify FX risk themselves. The
  defensible friction here is the **SME credit constraint**: a small importer
  hit by a 17% cost rise cannot easily raise capital, so cash-flow variance
  turns into forgone orders. Use that argument, not "management likes budget
  certainty", which reads as managerial risk aversion.
- **CIP does not hold exactly in practice.** Since 2008 there is a persistent
  cross-currency basis, especially for non-major currencies. Our synthetic
  forwards assume CIP holds. State this as a limitation before anyone raises it.

## Phase 2 output (done)

`cleaning.py` builds `daily_panel` (2,868 rows): spot_sell, spot_mid, cost_rate,
log_ret, myr_1m(+age), usd_1m(+age). `payment.py` writes 135 month-end payments
from 2015-06. `validate.py` regenerates every figure in `data_cleaning.md` and
exits non-zero on a broken invariant. `tests/test_clean.py` — 6 passing tests
against an in-memory fixture. First date with both rate legs: **2015-06-08**,
giving 2,763 usable rows.

## Phase 3 findings (done)

Six figures in `docs/figures/`, built by `src/figures.py`:

1. **Spot** — 3.51 (2015) to 4.79 peak (Apr 2024) to ~4.08 now.
2. **Returns** — excess kurtosis **5.8**, Jarque-Bera p ~ 0. Worst day was a
   **7.2-sigma** move; a normal over 2,867 draws tops out near 3.5. Justifies
   CVaR and percentile risk measures over anything Gaussian.
3. **Volatility** — 30-day annualised ranges **1.5% to 17.7%**, clustered not
   scattered. Strategy E trigger (75th pct) = **6.9%**.
4. **Rate differential** — crosses zero **Sep 2022**, months before the forward
   premium flipped in 2023. This is the mechanism behind the headline finding.
5. **Fama regression** — beta 1.54, se 1.40, R-sq **0.009**, p 0.27, n=135
   non-overlapping. Cannot reject beta=0 *or* beta=1. **The forward carries no
   usable signal about future spot.** Do NOT report 1.54 as a finding; it is
   noise. This is what makes the project a variance problem, not a forecasting
   one.
6. **Budget** — **76 of 135 months over budget** (56%), worst month RM 16,917
   over. This is the README's opening image.

## Next session: Phase 4

1. `forwards.py` — CIP pricing off `daily_panel`, tenor 1 month.
2. `backtest.py` — strategies A (no hedge), B (100% forward), C (50% static),
   D (layered ladder), E (GARCH-triggered).
3. Walk-forward GARCH with `arch`, expanding window, refit at each decision
   date. Evaluate out-of-sample with QLIKE.
4. **Block** bootstrap for CIs on variance reduction — see the overlapping
   observations entry in the glossary for why iid resampling is wrong here.
5. Write `strategy_results` with **rate components kept separate**
   (spot_rate, forward_rate, hedge_ratio), not just `myr_cost` — Power BI would
   need the pieces to recompute under a different ratio.

Open: does Strategy E survive walk-forward? Given finding 5, expect it not to
beat a static policy by much.

## Working agreement

User types all code themselves and wants to learn — explain the reasoning and
give code to type, do not write project files unprompted. Documentation and
analysis scripts are fine to write when asked.

User is an experienced data scientist but **entirely new to finance**. Introduce
and explain every finance term when it first comes up, and explain the reasoning
behind analytics, cleaning and visualisation choices too — not the mechanics of
pandas, but why *this* technique for *this* problem (why an as-of join here, why
block bootstrap over iid, why QLIKE over RMSE). Add new terms to
`docs/glossary.md` as they arise.

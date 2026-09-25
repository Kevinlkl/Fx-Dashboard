# Progress

**Read this file first at the start of a session.** It is the current state of
the project. It is rewritten, not appended to — history lives in
`docs/sessions/`, which does not need reading unless you are chasing *why* a
past decision was made.

Last updated: 2026-09-25 (session 2, Phase 4 done)

## Status

| Phase | State |
|---|---|
| 0 — Framing | done (scenario + KPIs settled) |
| 1 — Ingestion | **done** |
| 2 — Cleaning | **done** |
| 3 — EDA | **done** (6 figures) |
| 4 — Modelling / backtest | **done** |
| 5 — Dashboard | next |
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

## Phase 4 results (done)

`forwards.py` (134 contracts, CIP with ACT/365 MYR and ACT/360 USD),
`volatility.py` (127 walk-forward GARCH forecasts), `backtest.py`,
`bootstrap.py`.

**The plan's main KPI was wrong.** "sd of monthly cost" barely moves under a
rolling 1-month hedge, because the forward you lock is essentially spot from a
month earlier (corr 0.897, sd 0.2207 vs 0.2212). Full hedging cuts it 0.2%.
The KPI that matters is **planning error** — sd of (actual cost minus the cost
known at the decision date). Keep cost sd, but demote it and explain why it
barely moves.

| strategy | planning err | cost sd | worst overrun | total cost |
|---|---|---|---|---|
| A unhedged | 1,816 | 3,994 | 16,917 | 10,302,605 |
| B 100% | **0** | 3,985 | 17,156 | 10,304,896 |
| C 50% | 908 | 3,886 | **15,759** | 10,303,750 |
| MV h=0.511 | 888 | **3,886** | 15,790 | 10,303,777 |
| E GARCH trigger | 810 | 3,848 | 15,759 | 10,297,553 |
| E fair control (h=0.60) | 725 | 3,889 | 16,040 | 10,303,981 |

Bootstrap (stationary, block 14.9 months from Politis-White, 2000 reps, n=134):

- total cost 100% vs unhedged **+0.02% [-0.26, +0.30]** — hedging is FREE
- cost sd MV vs unhedged **-2.72% [-5.70, -0.53]** — real but small
- planning err E vs control +11.63% [-4.47, +23.85] — **no detectable difference**
- cost sd E vs control -1.05% [-1.61, -0.06] — significant but economically nil
- cvar95 MV vs unhedged -0.31% [-0.77, +0.09] — nothing on tails

GARCH eval: RMSE 0.771 vs naive 0.764 (loses), QLIKE 0.372 vs 0.609 (wins
clearly). GARCH over-forecasts (bias +0.215), which RMSE punishes and QLIKE
forgives. Report both.

**Conclusion.** Hedge 50-75% one month ahead. Certainty costs nothing; ~50%
minimises dispersion and worst-month overrun; higher ratios buy more planning
certainty. Skip volatility timing.

**Scope changes.** Strategy D (layered ladder) dropped — needs 3/6-month
forwards that the data cannot price. Replaced by a 0-100% hedge-ratio frontier
(`hedge_frontier` table), which is more informative anyway.

**Caveats to state.** Only ~9 effective independent blocks at n=134, so tail
CIs are wide. Max-based statistics (worst overrun) bootstrap badly; CVaR is the
stable tail metric. Six comparisons at 95% means ~1 expected false positive.

## Next session: Phase 5

Dashboard. Decision deferred: Streamlit (free public link, Python end-to-end)
vs Power BI (no public link without a Pro licence and a work email; strong
signal for Malaysian BI roles). Recommended: Streamlit primary, .pbix as a
second artifact.

Tables ready to drive it: `daily_panel`, `forwards`, `strategy_results`,
`hedge_frontier`, `vol_forecasts`, `bootstrap_ci`. All carry rate components
separately so a BI tool can recompute cost at any hedge ratio.

Pages: market overview; strategy comparison (frontier scatter is the key
visual); scenario simulator (exposure, hedge ratio, bank spread, date range);
methodology.

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

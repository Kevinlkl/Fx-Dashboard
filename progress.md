# Progress

**Read this file first at the start of a session.** It is the current state of
the project. It is rewritten, not appended to — history lives in
`docs/sessions/`, which does not need reading unless you are chasing *why* a
past decision was made.

Last updated: 2026-09-21 (end of session 1)

## Status

| Phase | State |
|---|---|
| 0 — Framing | done (scenario + KPIs settled) |
| 1 — Ingestion | **done** |
| 2 — Cleaning | next |
| 3 — EDA | not started |
| 4 — Modelling / backtest | not started |
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

## Next session: Phase 2

Build the analysis-ready layer.

1. `src/clean.py` → materialise a `daily_panel` table: date, spot_mid,
   spot_sell, cost_rate, log_ret, myr_1m, myr_1m_age, usd_1m, usd_1m_age.
   Rebuild from scratch each run.
2. As-of joins via `pd.merge_asof(..., direction='backward')`. Both frames must
   be sorted. `direction='nearest'` would inject look-ahead — never use it.
3. `_age` columns are the audit trail for the tenor decision. Keep them.
4. `src/payments.py` → month-end USD 18,000 from 2015-06 into `payments`.
5. `src/validate.py` → regenerate every number quoted in `data_cleaning.md`.
   They are currently asserted, not reproducible. This is the real work.
6. `tests/test_clean.py` → four tests, the important one being "as-of join never
   returns a rate dated after the target date".

Open decisions:
- Bank spread as config constant or `clean.py` argument? (argument — the
  dashboard simulator varies it)
- Returns off `middle`, costing off `selling`. Agreed in principle, needs
  stating explicitly somewhere or it reads as an inconsistency.
- Trading calendar = "days BNM quoted", or a real MY holiday list?

Estimate 3-4 hours. `validate.py` is where the time goes.

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

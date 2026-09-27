# Interview brief — FX hedging dashboard

Read this the morning of. Written to be spoken, not recited.

---

## The 30-second version

> A Malaysian importer pays USD 18,000 every month and earns in ringgit. Over
> the last eleven years that identical invoice cost anywhere from RM 64,000 to
> RM 86,000, and 76 of 135 months came in over budget. I built a pipeline that
> pulls eleven years of exchange rates and interest rates from Bank Negara and
> the US Federal Reserve into SQL, prices forward contracts, backtests five
> hedging policies, and puts the result in a Power BI dashboard where the
> finance manager can move the hedge ratio and watch the risk change.

If they want one more sentence: **the finding is that hedging this exposure is
essentially free — full hedging cost 0.02% more over eleven years, which is
statistically indistinguishable from zero — and it removes all of the
one-month-ahead uncertainty.**

---

## The live demo (do this first, it is the whole project in 20 seconds)

Open the scenario page. Drag the hedge ratio slider from 0 to 1 and narrate:

1. "Total cost barely moves — RM 2,291 on RM 10.3 million."
2. "Planning error collapses from RM 1,816 to exactly zero."
3. "Cost dispersion dips in the middle and rises at both ends."

Then: *"So certainty is nearly free, and the optimal amount to hedge depends on
which risk you care about."*

Everything else in the interview can hang off those three sentences.

---

## Numbers to know cold

| | |
|---|---|
| Daily FX observations | 2,868 (2015-01-02 to today) |
| Interest rate observations | 17,575 |
| Monthly payments backtested | 134 hedged contracts, 135 payments |
| Baseline total cost, unhedged | **RM 10,302,605** |
| Total cost, fully hedged | RM 10,304,896 (**+0.02%**, CI −0.26% to +0.30%) |
| Planning error, unhedged → hedged | **RM 1,816 → RM 0** |
| Months over budget | **76 of 135** (56%) |
| Worst month over budget | RM 16,917 |
| Minimum-variance hedge ratio | **0.511** |

---

## How I built it: SQL

Narrate as a sequence of decisions, not a list of features.

**1. Schema first, from scratch.** Five declared tables (`fx_rates`,
`interest_rates`, `payments`, `strategy_results`, `ingest_log`) plus derived
ones built by the pipeline. Dates stored as ISO text because SQLite has no date
type and ISO strings sort and compare correctly.

**2. Composite primary keys, chosen for a reason.** `fx_rates` is keyed on
(date, currency, session); `interest_rates` on (date, country, series, tenor).
The key *is* the grain of the data, and it is what makes re-ingestion safe.

**3. Long format for the rate table** — see the concepts section below.

**4. Incremental, idempotent ingestion** — see below. First run about two
minutes, every run after that a few seconds.

**5. An audit table.** `ingest_log` records source, scope, row count and status
for every API call — 426 rows. When a number looks wrong later, you can see
whether that row came from the first backfill or a re-run.

**6. A validation script that exits non-zero.** `validate.py` regenerates every
figure quoted in the documentation and asserts the invariants — row counts
match, no negative staleness, no duplicates. It caught two wrong numbers I had
already written into my own docs.

---

## How I built it: Power BI

**1. Export components, never totals.** *(This is the most important thing to
say.)* The Python layer writes spot rate, forward rate, USD amount and budget
rate as separate columns — never a precomputed cost. If I had exported a
`total_cost` column, the dashboard would be a static report. Because DAX
recomputes cost from the components, the hedge ratio, bank spread and annual
exposure are all live inputs. That is the difference between a report and a
tool.

**2. A proper star schema.** Five CSVs, a DAX date dimension built with
`CALENDAR` + `ADDCOLUMNS` and marked as a date table, related to the fact table
on payment date.

**3. Three what-if parameters** — hedge ratio, bank spread, annual exposure.

**4. Nine measures**, including one that needed real DAX: CVaR.

**5. I validated DAX against Python to the decimal.** Total cost reads
10,302,605 in both. Most dashboards are never checked against an independent
implementation of the same logic.

**6. A deliberate architecture boundary.** Anything with a window function, a
model fit or a resampling loop — rolling volatility, GARCH, bootstrap — runs in
Python and arrives as data. DAX does what-if arithmetic over a fact table, which
it is very good at, and nothing else. Knowing what *not* to put in DAX is the
judgment call.

---

## Concepts, in plain words

### Wide vs long format (the rate table)

**Wide** is how the API returns it: one row per date, one column per tenor.

```
date         overnight   1_month   3_month   6_month
2023-06-02   2.99        3.15      3.41      null
2023-06-06   2.99        3.17      null      null
```

**Long** is how I store it: one row per observation, with the tenor as a value.

```
date         series      tenor      rate
2023-06-02   interbank   overnight  2.99
2023-06-02   interbank   1_month    3.15
2023-06-02   interbank   3_month    3.41
```

Three reasons:

1. **Missing data becomes an absent row, not a null.** In the wide table, most
   cells are null. In long format a quote that does not exist simply is not
   there, which is honest and avoids "did I remember to filter the nulls?"
2. **New series need no schema change.** Malaysian interbank rates and US
   Treasury yields have completely different native shapes, but both fit the
   same four columns. Adding the 4-week T-bill later was a data change, not a
   migration.
3. **It is the natural grain.** One row = one observed rate. The primary key
   falls out of it.

The cost is that queries need a `WHERE tenor = '1_month'`. Worth it.

### Idempotent ingestion

**Idempotent** means running it twice produces the same result as running it
once. No duplicates, no drift.

Two mechanisms working together:

```sql
INSERT INTO fx_rates (...) VALUES (...)
ON CONFLICT (date, currency, session) DO UPDATE SET ...
```

If a row with that key already exists, update it instead of raising an error or
inserting a duplicate. The composite primary key defines what "already exists"
means.

And incrementally: before fetching January 2015, the script asks the database
which months it already holds and skips them — except the current month, which
is always refetched because it is still filling up.

**Why it matters:** during development you re-run the pipeline constantly. On a
daily schedule it runs unattended. Either way, a pipeline that can be safely
re-run is one you never have to reason about. It is the difference between "run
this once, carefully" and "run this whenever."

### CVaR (Conditional Value at Risk, 95%)

**The average cost of the worst 5% of months.**

With 134 months, that is the mean of the 7 most expensive ones — RM 85,671
unhedged.

Contrast with two weaker measures:

- **Average cost** tells you nothing about bad months.
- **VaR 95%** tells you the threshold the worst 5% exceed — where the cliff edge
  is, but nothing about how far the drop goes.

**CVaR tells you: when it goes bad, how bad on average.** That is the question a
finance manager actually asks.

I used it because the returns are not normally distributed — excess kurtosis of
5.8, and the worst single day was a 7.2-standard-deviation move where a normal
distribution over 2,867 days should top out near 3.5. Anything assuming
normality would understate the tail badly.

The DAX is the non-trivial measure in the model:

```dax
VAR k = ROUNDUP ( COUNTROWS ( payments_fact ) * 0.05, 0 )
VAR tbl = ADDCOLUMNS ( payments_fact, "@cost", <cost expression> )
RETURN AVERAGEX ( TOPN ( k, tbl, [@cost], DESC ), [@cost] )
```

`TOPN` can only rank by something that exists in the table, and cost depends on
the parameters, so it has to be materialised with `ADDCOLUMNS` first.

### What-if parameters

A Power BI feature that creates a **disconnected table** — one with no
relationship to anything — plus a slicer and a measure that reads whichever
value is selected.

Disconnected is the point. A normal slicer *filters* rows. A what-if parameter
does not filter anything; it hands a scalar to your measures, which then
recompute. That is what lets a single number change every KPI on the page
without touching the data.

Mine:

| Parameter | Range | Step | Default |
|---|---|---|---|
| Hedge Ratio | 0 – 1 | 0.05 | 0.5 |
| Bank Spread | 0 – 1% | 0.05% | 0.3% |
| Annual USD | 12k – 1.2M | 12,000 | 216,000 |

One practical detail worth mentioning if asked: the slider can only land on
values in the generated series, so `(target − minimum)` has to be divisible by
the step. My first attempt could not reach 216,000 because it stepped by 10,000
from a base of 50,000.

---

## The five dashboard metrics

Ordered by how much they matter.

**1. Planning Error SD — the headline.**
*"When I commit to a hedge at month-end, how wrong is my expectation for next
month's cost?"* Unhedged RM 1,816; fully hedged exactly RM 0. This is what
hedging actually buys, and it is the only metric that goes to zero.

**2. Total Cost.** Eleven years of payments. RM 10,302,605 unhedged,
RM 10,304,896 fully hedged. **The gap is 0.02%**, with a bootstrap CI of −0.26%
to +0.30% — indistinguishable from zero. *Certainty is free.*

**3. Cost SD.** Dispersion of monthly cost across the whole period. Minimised at
h ≈ 0.51 (that is the minimum-variance hedge ratio), but the dip is only 2.7%.
**Be ready to explain why it barely moves:** a rolling one-month forward locks
essentially last month's spot rate, so the hedged cost series is the unhedged
one shifted by a month — same dispersion. This was the original plan's main KPI,
and testing it showed it was the wrong measure for this instrument. Saying that
is a strength.

**4. Worst Overrun.** The worst single month against the January budget rate —
RM 16,917 unhedged. Intuitive, but unstable: it is one observation, so it
bootstraps badly and its confidence intervals are very wide.

**5. CVaR 95.** The stable tail measure. RM 85,671 unhedged. Use this rather
than Worst Overrun when making a claim about tail risk.

---

## Likely questions

**"Is it deployed?"**
No. Power BI Service requires a work or school account — personal Gmail is not
supported — and Publish to web needs a Pro licence. I can demo the `.pbix` live
and the repository is public. It is a licensing constraint, not a gap.

**"Is the data real?"**
The market data is entirely real: eleven years from Bank Negara Malaysia's open
API and the US Federal Reserve. The *company* is simulated on purpose. Attaching
invented cash flows to a real firm's name would misrepresent it, and the results
are percentages, so the firm's size does not change any conclusion.

**"Why SQLite and not a real database?"**
Zero setup, so anyone can clone the repo and run it. Every statement is standard
SQL and the connection layer is one module, so moving to Postgres means changing
that file and nothing else.

**"Why Power BI and not Python plotting?"**
The scenario simulator needs to respond to user input, which a static chart
cannot. And separating the semantic model from the presentation means someone
non-technical can explore it without reading code.

**"What was hardest?"**
The data, not the modelling. Malaysia's 3-month interbank rate is only quoted on
35% of business days, and forward-filling it would mean pricing contracts off
rates up to 100 days old on 7% of decision dates. I measured the staleness,
documented it, and moved the whole analysis to the 1-month tenor where the
median staleness is zero days. That constraint also forced me to drop one of the
five planned strategies.

**"What would you do differently?"**
Longer tenors. A rolling one-month hedge removes short-horizon uncertainty but
cannot flatten multi-year cost drift — that needs 6 and 12-month forwards, which
no free source prices for the ringgit. I would pay for forward quotes.

---

## Limitations to volunteer before they ask

Raising these yourself reads as competence, not weakness.

- **Forwards are synthetic**, derived from covered interest parity rather than
  observed quotes. No free source carries historical USD/MYR forward prices.
- **Covered interest parity does not hold exactly** in practice — there has been
  a persistent cross-currency basis since 2008, especially for non-major
  currencies.
- **The 0.3% bank spread is an assumption**, not data. It is the single largest
  unverified input and it moves every cost figure. The dashboard makes it a
  parameter so anyone can test their own number.
- **The payment schedule is simulated.** Real invoice timing is lumpier.
- **134 monthly observations with 15-month bootstrap blocks** means roughly nine
  effective independent samples. The tail confidence intervals are wide and I
  report them as wide.
- **Six comparisons at 95% confidence** means about one false positive is
  expected. The one marginally significant result (cost dispersion, Strategy E
  versus its control, −1.05%) is economically meaningless: RM 40 on a RM 3,900
  standard deviation.

---

## If they ask about the modelling (optional depth)

Only go here if they push. It is not what the recruiter flagged.

- **Walk-forward GARCH(1,1)**: refit at each of 127 decision dates on an
  expanding window, forecasting one month ahead. Nothing after the decision date
  touches the fit.
- **GARCH lost to a naive 21-day window on RMSE (0.771 vs 0.764) but won clearly
  on QLIKE (0.372 vs 0.609).** QLIKE penalises under-forecasting risk far more
  than over-forecasting, which matches the real cost of being wrong. Reporting
  both is the honest move.
- **The volatility-triggered strategy did not work.** It beat the 50% static
  policy on every metric — but only because its average hedge ratio was 0.60,
  not 0.50. Against a fair control at the *same* average ratio, there was no
  detectable improvement. That comparison is the part I am most pleased with.
- **Block bootstrap, not iid.** Monthly cost has lag-1 autocorrelation of 0.895.
  Resampling individual months would destroy that and return confidence
  intervals far too narrow. Block length of 15 months came from the
  Politis–White automatic rule, not a guess.

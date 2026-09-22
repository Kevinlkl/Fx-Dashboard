# Glossary

Terms used in this project, with what they mean *here* rather than a textbook
definition. Grows as new ones come up.

## FX basics

**Spot rate** — the price for exchanging currency now. A USD/MYR of ~4.07 means
one US dollar costs 4.07 ringgit today. Our `fx_rates` table is entirely spot
rates.

**Sen** — 1/100 of a ringgit, like a cent. A "1 sen move" is 0.01 MYR. At a spot
of 4.07 that is about 0.25%. We quote small FX moves in sen because "0.0025 MYR"
is hard to read.

**Buying / selling rate (bid / ask)** — the two prices a bank quotes. It *buys*
USD from you at the lower one and *sells* USD to you at the higher one. The gap
is its margin. An importer needs USD, so it pays the **selling** rate. Using the
midpoint would silently understate cost, which is why `data_cleaning.md` pins
this down.

**Spread** — that gap, usually quoted as a percentage. BNM's is 0.11% on average.
A real SME pays far more, hence our added 0.3% assumption.

**Appreciation / depreciation** — a *weaker* ringgit means USD/MYR goes *up* and
imports cost more. The number going up is bad news for our importer. Easy to get
backwards.

**Exposure** — the amount of foreign currency you are on the hook for. Ours is
USD 18,000 a month, USD 216,000 a year.

## Hedging

**Hedge** — a transaction taken to reduce uncertainty about a future price, not
to make money. This distinction is the spine of the whole project.

**Forward contract** — an agreement made today to buy a set amount of currency at
a fixed rate on a specific future date. No money changes hands upfront. If you
lock USD at 4.10 and spot turns out to be 4.30, you saved; if spot is 3.95, you
overpaid. Either way you *knew your cost in advance*, which is the point.

**Tenor** — how far ahead the contract settles. A 1-month tenor means you agree
today, settle in a month. Our tenor decision (1-month, not 3) was forced by data
availability, documented in `data_cleaning.md`.

**Hedge ratio** — the fraction of exposure covered. 0.5 means half the USD 18,000
is locked forward and half is bought at whatever spot turns out to be. Strategies
A-E are really just different rules for setting this number.

**Layered / laddered hedging** — hedging different fractions at different tenors
(75% of next month, 50% of month three, and so on), so you are never fully
committed to one rate. Standard corporate practice because it averages out
timing luck.

**Budget rate** — the exchange rate a finance manager assumes when setting the
annual budget. If actual costs exceed it, the budget is blown. Our "worst-month
overrun vs budget rate" KPI measures exactly that.

## Interest rates

**Why rates matter for FX** — holding a currency earns interest. That is what
links today's spot rate to a fair forward rate, via CIP below.

**Basis point (bp)** — 1/100th of a percentage point. 18bp = 0.18%. Rate
differences are small, so percentages get clumsy; bps are the working unit.

**OPR (Overnight Policy Rate)** — the rate Bank Negara Malaysia sets as policy,
currently 2.75%. Changed a handful of times a year at scheduled meetings. It
anchors every other MYR rate. Malaysia's equivalent of the Fed funds rate.

**Interbank rate** — what banks charge each other to lend, quoted by tenor
(overnight, 1-week, 1-month...). Sits slightly above OPR because lending to a
bank is riskier than holding central bank money. Our measured gap: +18bp at
1-month.

**Yield curve / term structure** — the set of rates across maturities. Longer
tenors usually pay more. Our 3-month rate averaged +46bp over OPR versus
1-month's +18bp; that is the curve sloping upward.

**T-bill (DTB3, DTB4WK)** — short-term US government debt. Because the US
government is treated as the safest borrower, the yield is the closest thing to a
"risk-free" USD rate. DTB4WK is the 4-week one, which is why we added it to match
our 1-month tenor.

**SOFR** — the benchmark USD overnight rate, based on actual repo transactions.
Replaced LIBOR after LIBOR was found to be manipulable. Only exists from 2018,
which is why our SOFR series starts there.

## Forward pricing

**Covered interest parity (CIP)** — the no-arbitrage rule that sets the forward
rate:

```
F = S × (1 + r_MYR × t) / (1 + r_USD × t)
```

The logic: you can either hold ringgit for a month and earn the MYR rate, or
convert to USD now, earn the USD rate, and convert back at a rate agreed today.
Both are riskless, so both must pay the same, otherwise you could borrow one way,
lend the other, and pocket free money. That constraint pins F.

This is why the project needs *both* countries' interest rates and not just the
exchange rate. It is also the standard interview question about this kind of
work.

**Forward premium / discount** — `F − S`. Positive (premium) means the forward
rate sits above spot, so hedging costs the importer slightly more than buying
today. Negative (discount) means the reverse. Our measured 1-month premium
averages +0.25 sen and flipped negative in 2023.

**Carry** — informal term for that same premium: the built-in cost or benefit of
holding a hedge. Our key finding is that carry (+0.25 sen) is tiny next to spot
risk (9.30 sen), so it barely moves the results.

**Synthetic pricing** — deriving a price from a formula because no observed
market price exists. All our forwards are synthetic, from CIP. A real limitation,
and it belongs in the README.

## Risk measures

**Volatility** — the standard deviation of returns. In finance, "volatility"
essentially always means this, usually annualised. Our daily sd is 0.408%.

**Annualising** — daily volatility is scaled by `√252` (252 trading days a year)
to get an annual figure. The square root comes from variance adding over
independent periods while standard deviation does not. So 0.408% daily is roughly
6.5% annualised.

**Volatility clustering** — calm periods follow calm periods and wild ones follow
wild ones. It is why a constant volatility assumption fails, and the reason GARCH
exists.

**Fat tails** — FX returns produce far more extreme moves than a normal
distribution predicts. Our series has 57 days beyond 3 standard deviations; a
normal distribution over 2,868 days would predict about 8. This is why risk is
measured with percentiles rather than by assuming normality.

**VaR (Value at Risk), 95%** — the threshold that losses exceed 5% of the time.
Answers "how bad is a bad month?"

**CVaR / Expected Shortfall, 95%** — the *average* of that worst 5%. Answers
"when it goes bad, how bad on average?" Preferred over VaR because VaR tells you
where the cliff edge is but nothing about the drop.

**Variance reduction** — the actual goal here. If hedging cuts the standard
deviation of monthly cost from RM 8,000 to RM 5,000, that is a 38% reduction,
whether or not average cost fell.

## Modelling and statistics

**GARCH(1,1)** — a model where today's variance depends on yesterday's variance
plus yesterday's squared shock. Two terms, which is enough to reproduce
volatility clustering. The workhorse volatility model.

**Look-ahead bias** — using information in a backtest that would not have been
available when the decision was made. The most common way backtests lie. Our
`_age` columns and `direction='backward'` as-of joins exist to prevent it.

**Walk-forward / expanding window** — refit the model using only data up to each
decision date, then forecast one step ahead. Slower than fitting once on
everything, and the only honest way.

**Out-of-sample** — evaluated on data the model never saw while fitting. An
in-sample volatility fit will always look good and means nothing.

**QLIKE** — a loss function for comparing volatility forecasts. Preferred over
RMSE because it penalises under-forecasting risk more heavily than
over-forecasting, which matches what actually hurts you.

**Bootstrap** — resample your data many times to see how much a result would have
varied by luck. Turns "reduced volatility 38%" into "38%, 95% CI 29-46%".

**Block bootstrap** — resample *contiguous chunks* rather than individual
observations. Necessary because financial data is autocorrelated: shuffling
individual days destroys volatility clustering and produces falsely narrow
confidence intervals.

## Data handling

**As-of join** (`pd.merge_asof`) — join on the nearest *prior* key rather than an
exact match. Essential here because FX quotes daily while the 1-month interbank
rate is quoted sporadically; for any given date you want the most recent rate
*already published*. `direction='backward'` is mandatory — `'nearest'` can pull a
future value and silently creates look-ahead bias.

**Staleness** — how old a forward-filled value is. Forward-filling is fine when
the number is a day old and indefensible when it is 100 days old, which is the
entire basis for our tenor decision. Tracked in the `_age` columns.

**Log returns** — `ln(P_t / P_t-1)` rather than percentage change. They add up
over time (a week's return is the sum of its days) and are symmetric, so +10% and
−10% are equal and opposite. Standard for volatility work.

**Trading calendar** — the set of days a market actually quotes. Weekends and
public holidays simply do not exist in the data. Whether to treat absent days as
gaps or fill them is a decision with real consequences, which is why it is
recorded in `data_cleaning.md`.

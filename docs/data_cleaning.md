# Data decisions

Notes on every judgement call made between the raw API responses and the tables
the analysis runs on. Written as I went, so the reasoning is here rather than
reconstructed later.

## Sources

| Series | Source | Endpoint | Coverage in DB |
|---|---|---|---|
| USD/MYR daily | BNM Open API | `exchange-rate/usd/year/{y}/month/{m}` | 2,868 days, 2015-01-02 to present |
| MY interbank by tenor | BNM Open API | `interest-rate/.../product=interbank` | 9,534 quotes, from 2015-06-05 |
| OPR decisions | BNM Open API | `opr/year/{y}` | 70 decisions, from 2015-01-28 |
| US T-bill / SOFR | FRED CSV | `fredgraph.csv?id=...` | DTB3, DTB4WK from 2015; SOFR from 2018 |

BNM requires the header `Accept: application/vnd.BNM.API.v1+json`. Without it
the request fails. FRED's CSV endpoint needs no API key, which keeps the repo
runnable by anyone who clones it.

## Decisions

### Session: 1200

BNM publishes USD/MYR at four times a day (0900, 1130, 1200, 1700). I checked
and all four return complete data, so this is a real choice rather than a
default. I use 1200 throughout.

Reason: daily returns have to be measured between comparable points in time. If
I mixed sessions, part of the day-to-day variation would just be time-of-day
noise, and the volatility estimates that feed the hedging rules would be wrong.
1200 also sits inside the window when a Malaysian SME would realistically call
its bank.

### Cost side: selling rate, plus an added spread

An importer buys USD, so the cost is the rate the bank *sells* at. All costing
uses `selling`, never `middle`. I store all three columns anyway so the raw
layer stays raw.

The catch is that BNM's spread is interbank, not retail. Across the full series
it averages 0.11% of mid (range 0.016% to 0.486%). No SME gets that. Using
these numbers unadjusted would understate the real cost by roughly an order of
magnitude, so the model adds an explicit bank spread on top, configurable, with
0.3% as the default.

That 0.3% is an assumption, not data. It is the single largest unverified input
in the whole project and it shifts every cost number. Flagged in the README
limitations as well.

### Hedge tenor: 1 month

The original plan was a 3-month forward. The data does not support it.

Longer tenors are only quoted on days an interbank trade actually happened, so
coverage drops off sharply:

| Tenor | Days quoted (of 2,868) | Median staleness if forward-filled | p90 | Worst | Days on a >30d old rate |
|---|---|---|---|---|---|
| 1-month | 1,882 (66%) | 0 days | 6 days | 27 days | 0 |
| 3-month | 1,009 (35%) | 2 days | 22 days | 100 days | 187 (7%) |

Forward-filling the 1-month rate is close to harmless. Half the time there is a
quote that same day, and it is never more than a month old. Forward-filling the
3-month rate means that on 7% of decision dates I would be pricing a contract
off a rate up to 100 days stale, which can easily span an OPR change. I am not
willing to defend that.

I also tested reconstructing the missing days from OPR plus a spread. It works
for 1-month (spread +18bp, sd 7bp, within-year sd 2-8bp — stable enough) but
not for 3-month, where the spread moved from +17bp in 2021 to +63bp in 2023 and
had a within-year sd of 25bp in 2022. So the fallback does not rescue the
3-month tenor either.

Hedging one month ahead is also the more realistic business case. An SME
importer knows next month's invoice; it usually does not know next quarter's.

6-month (132 quotes) and 1-year (17 quotes) are unusable from this source. Both
are still ingested so the coverage problem can be shown rather than asserted.

### US leg: DTB4WK

Covered interest parity needs both legs at the same tenor. DTB3 is 3-month and
would not match a 1-month hedge, so the USD leg is DTB4WK (4-week T-bill).
DTB3 is kept for a 3-month robustness check and SOFR as an overnight sanity
check.

### Missing dates

The API returns business days only. Weekends and Malaysian public holidays are
simply absent, with no flag. January 2015 returns 21 rows, not 31.

Two different rules depending on what the date is for, and they must not be
mixed:

- **Payment-date lookups** forward-fill (as-of join, last quote on or before the
  date). A payment falling on a holiday settles at the last available rate,
  which is what happens in practice.
- **Return and volatility calculations** drop missing days entirely. Forward-
  filling here would inject artificial zero-return days and bias volatility
  downward, which would then feed straight into the hedging rules.

Longest gap in the FX series is 6 days (three occurrences: Sep 2017, May 2018,
May 2022). 91 gaps of 4+ days, 529 of 3 days (ordinary weekends). Nothing long
enough to distort anything.

### Nulls vs absent rows

The interest-rate endpoint returns tenors as columns full of nulls. I pivot to
long format and drop the nulls rather than storing them. A missing quote becomes
an absent row. This means BNM and FRED data coexist in one table despite having
completely different native shapes, and adding a series later needs no schema
change.

## Known limits of the data

- **Interbank starts 2015-06-05**, not January. Anything needing a MYR rate —
  which is all forward pricing — effectively begins mid-2015. The FX series
  itself is complete from 2015-01-02.
- **The two BNM series do not share a calendar.** 397 of the 1,882 one-month
  interbank quotes (and 162 of the 1,009 three-month ones) fall on days with no
  FX quote at all, including weekends. Staleness therefore has to be measured
  against *every* published quote, not only those landing on FX trading days —
  measuring it the second way overstates staleness. `merge_asof` gets this
  right; a manual walk over the FX calendar does not.
- **SOFR starts 2018.** It did not exist before that. Overnight cross-checks
  cannot cover the early sample.
- **No real forward quotes exist in any free source.** I checked BNM's
  `interbank-swap` endpoint hoping for forward points; it returns trade
  *volumes*, not swap points. All forwards in this project are derived from
  covered interest parity, which is an assumption about how they would have been
  priced, not a record of how they were.
- **Float representation.** Values come back as e.g. `3.5089999999999999`. That
  is ordinary IEEE 754, the value is 3.509. Stored as-is and rounded only for
  display. Rounding at ingest would be lossy and irreversible.

## Checks run

- Duplicates on `(date, currency, session)`: 0. The composite primary key plus
  `ON CONFLICT DO UPDATE` makes re-ingestion idempotent by construction.
- Nulls in `selling`: 0 across all 2,868 rows.
- Daily log return: sd 0.408%, range -2.94% to +2.34%. 56 moves beyond 3sd.
  Flagged, not removed. Those are real events (Aug 2015, Mar 2020) and deleting
  them would remove exactly the periods hedging is meant to protect against.
- `ingest_log` records source, scope, row count and status for every request, so
  a failed fetch inside a long backfill is visible afterwards rather than silent.

## One thing that surprised me

The 1-month forward premium averages +0.28 sen. The standard deviation of a
one-month spot move is 9.30 sen. So the interest-rate carry is about 3% of the
size of the risk being hedged, which means small errors in the rate leg barely
matter, and the results will be driven almost entirely by spot moves.

It also flips sign. Positive every year 2015-2022, negative from 2023 onward:

```
2015 +1.15   2018 +0.53   2021 +0.62   2024 -0.68
2016 +1.04   2019 +0.40   2022 +0.23   2025 -0.35
2017 +0.84   2020 +0.66   2023 -0.68   2026 -0.21
```

Forward hedging cost this importer a small premium for eight years, then started
paying one. Any strategy backtested only on recent data would look better than
it deserves.

## Open

- The 0.3% bank spread needs a source, or at minimum a sensitivity range in the
  dashboard.
- Payment schedule is simulated (USD 18,000 month-end). Real invoice timing
  would be lumpier.

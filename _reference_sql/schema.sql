-- FX hedging analysis: raw + derived tables.
-- All dates are ISO 'YYYY-MM-DD' strings (SQLite has no native date type).

-- Daily BNM exchange rates. One row per (date, currency, session).
CREATE TABLE IF NOT EXISTS fx_rates (
    date        TEXT NOT NULL,
    currency    TEXT NOT NULL,   -- 'USD'
    session     TEXT NOT NULL,   -- '0900' | '1200' | '1700'
    unit        INTEGER NOT NULL,-- quote is per `unit` of foreign currency
    buying      REAL,            -- bank buys FX from you
    selling     REAL,            -- bank sells FX to you  <- importer's cost side
    middle      REAL,
    source      TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (date, currency, session)
);

-- Interest rates from both countries, long format so tenors/series coexist.
CREATE TABLE IF NOT EXISTS interest_rates (
    date        TEXT NOT NULL,
    country     TEXT NOT NULL,   -- 'MY' | 'US'
    series      TEXT NOT NULL,   -- 'interbank' | 'opr' | 'DTB3' | 'SOFR'
    tenor       TEXT NOT NULL,   -- 'overnight' | '1_month' | '3_month' | 'policy' | ...
    rate        REAL,            -- percent per annum
    source      TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (date, country, series, tenor)
);

-- Simulated importer payment schedule (populated in Phase 4).
CREATE TABLE IF NOT EXISTS payments (
    payment_date TEXT PRIMARY KEY,
    usd_amount   REAL NOT NULL
);

-- Backtest output (populated in Phase 4).
CREATE TABLE IF NOT EXISTS strategy_results (
    strategy     TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    myr_cost     REAL NOT NULL,
    hedge_ratio  REAL NOT NULL,
    PRIMARY KEY (strategy, payment_date)
);

-- Audit trail: what was fetched, when, how much.
CREATE TABLE IF NOT EXISTS ingest_log (
    ts      TEXT NOT NULL,
    source  TEXT NOT NULL,
    scope   TEXT NOT NULL,   -- e.g. 'USD 2015-01'
    rows    INTEGER NOT NULL,
    status  TEXT NOT NULL    -- 'ok' | 'empty' | 'error: ...'
);

CREATE INDEX IF NOT EXISTS ix_fx_date  ON fx_rates(date);
CREATE INDEX IF NOT EXISTS ix_ir_date  ON interest_rates(date, country);

-- FX hedging analysis schema
-- Dates are ISO "YYYY-MM-DD" TEXT: SQLITE does not have a native date type, so we store dates as TEXT in ISO format.
-- sort and compare as text

-- Daily BNM exchange rates, one row per (date, currency, session).
CREATE TABLE IF NOT EXISTS fx_rates (
    date            TEXT NOT NULL,
    currency        TEXT NOT NULL,
    session         TEXT NOT NULL,
    unit            INTEGER NOT NULL,
    buying          REAL NOT NULL,
    selling         REAL NOT NULL,
    middle          REAL NOT NULL,
    source          TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    PRIMARY KEY (date, currency, session)
);

-- Long format: BNM and FRED coexist, missing quotes are absent rows not NULLs.
CREATE TABLE IF NOT EXISTS interest_rates (
    date        TEXT NOT NULL,
    country     TEXT NOT NULL,
    series      TEXT NOT NULL,
    tenor       TEXT NOT NULL,
    rate        REAL,
    source      TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (date, country, series, tenor)
);

-- Populated by Phase 4
CREATE TABLE IF NOT EXISTS payments (
    payment_date  TEXT PRIMARY KEY,
    usd_amount    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_results (
    strategy        TEXT NOT NULL,
    payment_date    TEXT NOT NULL,
    myr_cost        REAL NOT NULL,
    hedge_ratio     REAL NOT NULL,
    PRIMARY KEY (strategy, payment_date)
);

-- Audit Trail: fetched, when, how many rows
CREATE TABLE IF NOT EXISTS ingest_log (
    ts      TEXT NOT NULL,
    source  TEXT NOT NULL,
    scope   TEXT NOT NULL,   -- e.g. 'USD 2015-01'
    rows    INTEGER NOT NULL,
    status  TEXT NOT NULL    -- 'ok' | 'empty' | 'error: ...'
);

CREATE INDEX IF NOT EXISTS ix_fx_date ON fx_rates(date);
CREATE INDEX IF NOT EXISTS ix_ir_date ON interest_rates(date, country);
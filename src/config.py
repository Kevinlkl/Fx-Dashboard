"""Project-wide constants. Change analysis window here, not the scripts"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "fx.db"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"

# BNM FX history reaches back to at least 2010; 2015 is chosen so the sample
# spans the 2015 ringgit slide, COVID, the 2022-24 USD run-up and the recovery.
START_YEAR = 2015

# BNM quotes FX several times a day. Fixed for the whole project so that
# day-to-day returns are measured between comparable points in time.
FX_SESSION = "1200"
CURRENCY = "USD"

BNM_BASE = "https://api.bnm.gov.my/public"
BNM_HEADERS = {"Accept": "application/vnd.BNM.API.v1+json"}

# FRED's CSV endpoint need no API key
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SERIES = {
    "DTB3": "3-Month Treasury Bill secondary market rate",
    "DTB4WK": "4-Week Treasury Bill secondary market rate",
    "SOFR": "Secured Overnight Financing Rate",
}

TENOR_OF = {"DTB3": "3_month", "DTB4WK": "1_month", "SOFR": "overnight"}
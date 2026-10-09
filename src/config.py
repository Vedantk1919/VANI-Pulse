"""Paths and shared constants. Override the data locations with env vars if the folder moves."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.environ.get(
    "BTC_RAW_DIR", ROOT.parent / "Aids to solve Problems" / "BesTime to Call"))
PERSONA_DIR = Path(os.environ.get("BTC_PERSONA_DIR", ROOT / "data" / "persona"))
WORK_DIR = ROOT / "data" / "work"
MODEL_DIR = ROOT / "models"
OUT_DIR = ROOT / "outputs"
for d in (WORK_DIR, MODEL_DIR, OUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

ATTEMPTS_CSV = RAW_DIR / "Best-Time-to-Call - Call Attempts Apr-Sep 2026.csv"
SELLERS_CSV = RAW_DIR / "Best-Time-to-Call - Sellers.csv"

# Dialing window seen in the data: 09:00-20:59.
CALL_HOURS = list(range(9, 21))
# Hour bands used for per-seller "slot" history.
BANDS = [(9, 10, "09-10"), (10, 12, "10-12"), (12, 14, "12-14"),
         (14, 16, "14-16"), (16, 18, "16-18"), (18, 21, "18-21")]

# Time-based split: train on Apr-Aug, hold out September.
TEST_START = "2026-09-01"

TURNOVER_ORDER = {"0 - 40 L": 0, "40 L - 1.5 Cr": 1, "1.5 - 5 Cr": 2, "5 - 25 Cr": 3,
                  "25 - 100 Cr": 4, "100 - 500 Cr": 5, "> 500 Cr": 6}


def band_of(hour):
    for lo, hi, name in BANDS:
        if lo <= hour < hi:
            return name
    return BANDS[-1][2] if hour >= 18 else BANDS[0][2]

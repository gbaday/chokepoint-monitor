"""Bloomberg fetcher: short interest, days to cover, next earnings.

Mirrors the style of bbg_multiples.py:
  - load_dotenv(_SCRIPT_DIR.parent / ".env")
  - small isolated _fetch_one helpers, try/except per call
  - intermediate DataFrames before extracting scalars
  - dates relative to date.today() (no hardcode)

Returns dict keyed by ticker (without ' US Equity'):
  { "VG": {"si_pct_float": 8.2, "delta_short_2w": -0.5,
           "days_to_cover": 3.1,
           "next_earnings_date": "2026-08-10",
           "days_to_earnings": 96,
           "earnings_flag": "green"},
    ... }

If vista_bbg unavailable (ImportError): log warning, return {} so the
dashboard degrades gracefully and shows "—".
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

_SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(_SCRIPT_DIR.parent / ".env")

log = logging.getLogger(__name__)

try:
    import vista_bbg as vbbg  # type: ignore
    _VBBG_OK = True
except Exception as e:
    log.warning("vista_bbg unavailable: %s — Bloomberg fields skipped", e)
    _VBBG_OK = False


SHORT_LOOKBACK_DAYS = 30
DELTA_BACK_DAYS = 14


def _empty() -> dict:
    return {"si_pct_float": None, "delta_short_2w": None,
            "days_to_cover": None,
            "next_earnings_date": None, "days_to_earnings": None,
            "earnings_flag": None}


def _ticker_key(ticker_bbg: str) -> str:
    return ticker_bbg.replace(" US Equity", "").strip()


def _fetch_short_interest_df(ticker_bbg: str, start_str: str, end_str: str) -> pd.DataFrame:
    try:
        df = vbbg.bdh(ticker_bbg, "SHORT_INT_RATIO",
                      start_date=start_str, end_date=end_str)
    except Exception as e:
        log.info("    BBG SHORT_INT_RATIO %s: %s", ticker_bbg, e)
        return pd.DataFrame(columns=["DATE", "SHORT_INT_RATIO"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["DATE", "SHORT_INT_RATIO"])
    return df


def _scalar_bdp(ticker_bbg: str, field: str):
    try:
        v = vbbg.bdp(ticker_bbg, field)
    except Exception as e:
        log.info("    BBG %s %s: %s", field, ticker_bbg, e)
        return None
    return v


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _to_date(v) -> dt.date | None:
    if v is None:
        return None
    try:
        ts = pd.to_datetime(v)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return ts.date() if hasattr(ts, "date") else None


def _earnings_flag(d: dt.date | None) -> tuple[int | None, str | None]:
    if d is None:
        return None, None
    days = (d - dt.date.today()).days
    if days < 0:
        return None, None
    if days < 10:
        return days, "red"
    if days <= 30:
        return days, "yellow"
    return days, "green"


def fetch_one(ticker_bbg: str) -> dict:
    out = _empty()

    today = dt.date.today()
    start = today - dt.timedelta(days=SHORT_LOOKBACK_DAYS + 5)
    df = _fetch_short_interest_df(ticker_bbg,
                                  start.strftime("%Y%m%d"),
                                  today.strftime("%Y%m%d"))
    if not df.empty and "SHORT_INT_RATIO" in df.columns:
        s = df.set_index("DATE")["SHORT_INT_RATIO"].dropna().sort_index()
        if not s.empty:
            out["si_pct_float"] = float(s.iloc[-1])
            cutoff = pd.Timestamp(today - dt.timedelta(days=DELTA_BACK_DAYS))
            past = s[s.index <= cutoff]
            if not past.empty:
                out["delta_short_2w"] = float(s.iloc[-1] - past.iloc[-1])

    out["days_to_cover"] = _to_float(_scalar_bdp(ticker_bbg, "DAYS_TO_COVER"))

    nxt = _to_date(_scalar_bdp(ticker_bbg, "NEXT_ANNOUNCEMENT_DT"))
    if nxt is not None:
        out["next_earnings_date"] = nxt.isoformat()
        days, flag = _earnings_flag(nxt)
        out["days_to_earnings"] = days
        out["earnings_flag"] = flag

    return out


def get_bloomberg_data(tickers_bbg: list[str]) -> dict[str, dict]:
    if not _VBBG_OK:
        return {}
    out: dict[str, dict] = {}
    for tb in tickers_bbg:
        key = _ticker_key(tb)
        log.info("  bbg %s", tb)
        try:
            out[key] = fetch_one(tb)
        except Exception as e:
            log.warning("  bbg fetch_one %s failed: %s", tb, e)
            out[key] = _empty()
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sample = ["VG US Equity", "CRK US Equity", "LNG US Equity"]
    result = get_bloomberg_data(sample)
    if not result:
        print("\n(empty — vista_bbg unavailable or all calls failed)")
    for k, v in result.items():
        print(f"\n=== {k} ===")
        for fk, fv in v.items():
            print(f"  {fk}: {fv}")

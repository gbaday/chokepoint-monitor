"""Bloomberg fetcher: fundamentals (batch BDP) + short interest + earnings.

Mirrors the style of bbg_multiples.py:
  - load_dotenv(_SCRIPT_DIR.parent / ".env")
  - small isolated helpers, try/except per call
  - dates relative to date.today() (no hardcode)

Fundamental fields fetched via a single batch bdp call (one request for all
tickers × all fields). Falls back to a per-ticker loop if vista_bbg does not
support the batch form.

Returns dict keyed by ticker (without ' US Equity'):
  { "VG": {"si_pct_float": 8.2, "delta_short_2w": -0.5,
           "days_to_cover": 3.1,
           "next_earnings_date": "2026-08-10",
           "days_to_earnings": 96,
           "earnings_flag": "green",
           "ev_ebitda": 7.2, "net_debt_ebitda": 1.8, "fcf_ev": 0.09,
           "mkt_cap_b": 4.1, "fwd_rev_growth": 0.12,
           "roic": 0.14, "roe": 0.21},
    ... }

If vista_bbg unavailable (ImportError): log warning, return {} so the
dashboard degrades gracefully to yfinance values.
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

# Fundamental fields fetched via BDP.
# Each entry: (internal_key, bbg_field, scale_factor)
#   scale_factor converts BBG units → internal units:
#     CUR_MKT_CAP          : USD (absolute) → billions    (× 1e-9)
#     FCF_YIELD_WITH_CUR_ENTP_VAL: percent  → decimal    (× 1e-2)
#     SALES_GROWTH         : percent        → decimal    (× 1e-2)
#     RETURN_ON_INV_CAPITAL: percent        → decimal    (× 1e-2)
#     RETURN_COM_EQY       : percent        → decimal    (× 1e-2)
#     EV_TO_T12M_EBITDA / NET_DEBT_TO_EBITDA: already ratios (× 1.0)
_FUND_FIELDS: list[tuple[str, str, float]] = [
    ("ev_ebitda",       "EV_TO_T12M_EBITDA",           1.0),
    ("net_debt_ebitda", "NET_DEBT_TO_EBITDA",           1.0),
    ("fcf_ev",          "FCF_YIELD_WITH_CUR_ENTP_VAL",  1e-2),
    ("mkt_cap_b",       "CUR_MKT_CAP",                  1e-9),
    ("fwd_rev_growth",  "SALES_GROWTH",                  1e-2),
    ("roic",            "RETURN_ON_INV_CAPITAL",         1e-2),
    ("roe",             "RETURN_COM_EQY",                1e-2),
]

FUND_KEYS: tuple[str, ...] = tuple(k for k, _, _ in _FUND_FIELDS)


def _empty_fund() -> dict:
    return {k: None for k, _, _ in _FUND_FIELDS}


def _empty() -> dict:
    d: dict = {
        "si_pct_float": None, "delta_short_2w": None,
        "days_to_cover": None,
        "next_earnings_date": None, "days_to_earnings": None,
        "earnings_flag": None,
    }
    d.update(_empty_fund())
    return d


def _ticker_key(ticker_bbg: str) -> str:
    return ticker_bbg.replace(" US Equity", "").strip()


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


def _scalar_bdp(ticker_bbg: str, field: str):
    try:
        v = vbbg.bdp(ticker_bbg, field)
    except Exception as e:
        log.info("    BBG %s %s: %s", field, ticker_bbg, e)
        return None
    # vista_bbg returns a single-row DataFrame even for scalar queries
    if isinstance(v, pd.DataFrame):
        if v.empty:
            return None
        if field in v.columns:
            return v[field].iloc[0]
        cols = [c for c in v.columns if c != "TICKER"]
        return v[cols[0]].iloc[0] if cols else None
    return v


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


def _fetch_fundamentals(tickers_bbg: list[str]) -> dict[str, dict]:
    """Fetch fundamental BDP fields for all tickers.

    Tries a single batch bdp(tickers, fields) call first; falls back to a
    per-ticker loop if the batch form is unsupported or raises.
    """
    bbg_fields = [f for _, f, _ in _FUND_FIELDS]
    result: dict[str, dict] = {_ticker_key(t): _empty_fund() for t in tickers_bbg}

    # Attempt batch call
    try:
        df = vbbg.bdp(tickers_bbg, bbg_fields)
        if isinstance(df, pd.DataFrame) and not df.empty:
            # vista_bbg returns TICKER as a column rather than the index
            if "TICKER" in df.columns:
                df = df.set_index("TICKER")
            for tb in tickers_bbg:
                key = _ticker_key(tb)
                if tb not in df.index:
                    continue
                row = df.loc[tb]
                for local_key, bbg_field, scale in _FUND_FIELDS:
                    raw = row[bbg_field] if bbg_field in row.index else None
                    v = _to_float(raw)
                    result[key][local_key] = None if v is None else v * scale
            log.info("  bbg fundamentals fetched via batch bdp (%d tickers)", len(tickers_bbg))
            return result
    except Exception as e:
        log.info("  batch bdp unsupported or failed (%s); falling back to per-ticker loop", e)

    # Per-ticker fallback
    for tb in tickers_bbg:
        key = _ticker_key(tb)
        log.info("  bbg fundamentals %s", tb)
        for local_key, bbg_field, scale in _FUND_FIELDS:
            v = _to_float(_scalar_bdp(tb, bbg_field))
            result[key][local_key] = None if v is None else v * scale

    return result


def fetch_one_crowding(ticker_bbg: str) -> dict:
    """Fetch short interest + days_to_cover + next earnings for a single ticker."""
    out: dict = {
        "si_pct_float": None, "delta_short_2w": None,
        "days_to_cover": None,
        "next_earnings_date": None, "days_to_earnings": None,
        "earnings_flag": None,
    }

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

    # 1. Fundamentals — single batch BDP call (minimises datapoint cost)
    log.info("  bbg fundamentals (batch bdp, %d tickers × %d fields)...",
             len(tickers_bbg), len(_FUND_FIELDS))
    try:
        fund = _fetch_fundamentals(tickers_bbg)
    except Exception as e:
        log.warning("  fundamentals batch failed entirely: %s", e)
        fund = {}

    # 2. Crowding / catalyst — per-ticker (requires bdh for short interest history)
    out: dict[str, dict] = {}
    for tb in tickers_bbg:
        key = _ticker_key(tb)
        log.info("  bbg crowding/catalyst %s", tb)
        try:
            d = fetch_one_crowding(tb)
        except Exception as e:
            log.warning("  bbg crowding %s failed: %s", tb, e)
            d = {k: None for k in ("si_pct_float", "delta_short_2w", "days_to_cover",
                                   "next_earnings_date", "days_to_earnings", "earnings_flag")}
        d.update(fund.get(key, _empty_fund()))
        out[key] = d

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

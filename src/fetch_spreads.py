"""Macro spread fetcher: JKM, TTF, HH, Brent + computed daily spreads.

Tries yfinance first (per ticker). Falls back to CSVs in data/spreads/ when
yfinance returns nothing usable. CSVs may carry raw legs (jkm.csv, ttf.csv,
hh.csv, brent.csv) and/or pre-computed spreads (jkm_hh.csv, ttf_hh.csv).

CSV format: 2 columns, header `date,close` (or `date,value`), date in any
pandas-parseable format. Values must already be in compatible units
($/MMBtu for gas legs, $/bbl for Brent).

Returns dict:
    frame  -> pd.DataFrame indexed by date with columns
              {jkm, ttf, hh, brent, jkm_hh, ttf_hh, jkm_ttf} (any may be missing)
    latest -> dict of latest scalars per column (None if unavailable)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPREADS_DIR = _PROJECT_ROOT / "data" / "spreads"

# Yahoo symbols, tried in order. Each entry: (symbol, unit_converter).
# unit_converter is one of:
#   None                     -> leave value as-is (assumed $/MMBtu for gas, $/bbl for oil)
#   "eur_mwh_to_usd_mmbtu"   -> convert EUR/MWh to $/MMBtu using EURUSD=X and 1 MWh = 3.412 MMBtu
SYMBOLS = {
    "jkm":   [("JKM=F", None)],
    "ttf":   [("TTF=F", "eur_mwh_to_usd_mmbtu"), ("TTFM.L", None), ("TTFG.L", None)],
    "hh":    [("NG=F", None)],
    "brent": [("BZ=F", None)],
}

_MWH_PER_MMBTU = 3.412  # 1 MWh thermal ≈ 3.412 MMBtu

CSV_FALLBACK = {
    "jkm":    SPREADS_DIR / "jkm.csv",
    "ttf":    SPREADS_DIR / "ttf.csv",
    "hh":     SPREADS_DIR / "hh.csv",
    "brent":  SPREADS_DIR / "brent.csv",
    "jkm_hh": SPREADS_DIR / "jkm_hh.csv",
    "ttf_hh": SPREADS_DIR / "ttf_hh.csv",
}

PERIOD = "5y"


def _yf_close(symbol: str) -> pd.Series:
    try:
        h = yf.Ticker(symbol).history(period=PERIOD, auto_adjust=False)
    except Exception as e:
        log.info("  %s: yfinance error %s", symbol, e)
        return pd.Series(dtype=float)
    if h is None or h.empty or "Close" not in h.columns:
        return pd.Series(dtype=float)
    s = h["Close"].dropna()
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    return s


def _apply_converter(series: pd.Series, converter: str | None) -> pd.Series:
    if converter is None or series.empty:
        return series
    if converter == "eur_mwh_to_usd_mmbtu":
        fx = _yf_close("EURUSD=X")
        if fx.empty:
            log.warning("  EURUSD=X unavailable, leaving TTF in raw units")
            return series
        fx = fx.reindex(series.index).ffill().bfill()
        return (series * fx) / _MWH_PER_MMBTU
    log.warning("  unknown converter %s", converter)
    return series


def _try_yfinance(symbols: list[tuple[str, str | None]]) -> pd.Series:
    for sym, converter in symbols:
        s = _yf_close(sym)
        if len(s) < 30:
            log.info("  %s: %d rows, skipping", sym, len(s))
            continue
        s = _apply_converter(s, converter)
        log.info("  %s: %d rows from yfinance%s", sym, len(s),
                 f" [converted: {converter}]" if converter else "")
        return s
    return pd.Series(dtype=float)


def _try_csv(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        date_col = next((c for c in df.columns if c in ("date", "dt", "timestamp")), df.columns[0])
        val_col = next((c for c in df.columns if c != date_col), df.columns[-1])
        df[date_col] = pd.to_datetime(df[date_col])
        s = df.set_index(date_col)[val_col].astype(float).dropna().sort_index()
        log.info("  CSV %s: %d rows", path.name, len(s))
        return s
    except Exception as e:
        log.warning("  CSV %s parse error: %s", path.name, e)
        return pd.Series(dtype=float)


def _fetch_leg(name: str) -> pd.Series:
    log.info("leg %s", name)
    s = _try_yfinance(SYMBOLS.get(name, []))
    if s.empty:
        s = _try_csv(CSV_FALLBACK[name])
    return s


def fetch_spreads() -> dict:
    legs = {name: _fetch_leg(name) for name in ("jkm", "ttf", "hh", "brent")}

    df = pd.concat(legs, axis=1).sort_index()
    df = df.ffill().dropna(how="all")

    have_hh = "hh" in df.columns and df["hh"].notna().any()

    if "jkm" in df.columns and df["jkm"].notna().any() and have_hh:
        df["jkm_hh"] = df["jkm"] - df["hh"]
    else:
        s = _try_csv(CSV_FALLBACK["jkm_hh"])
        if not s.empty:
            df = df.join(s.rename("jkm_hh"), how="outer").sort_index()

    if "ttf" in df.columns and df["ttf"].notna().any() and have_hh:
        df["ttf_hh"] = df["ttf"] - df["hh"]
    else:
        s = _try_csv(CSV_FALLBACK["ttf_hh"])
        if not s.empty:
            df = df.join(s.rename("ttf_hh"), how="outer").sort_index()

    if "jkm_hh" in df.columns and "ttf_hh" in df.columns:
        df["jkm_ttf"] = df["jkm_hh"] - df["ttf_hh"]

    df = df.sort_index()

    latest: dict[str, float | None] = {}
    for col in ("jkm", "ttf", "hh", "brent", "jkm_hh", "ttf_hh", "jkm_ttf"):
        if col in df.columns:
            s = df[col].dropna()
            latest[col] = float(s.iloc[-1]) if not s.empty else None
        else:
            latest[col] = None

    return {"frame": df, "latest": latest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    res = fetch_spreads()
    df = res["frame"]
    if df.empty:
        print("frame: EMPTY")
    else:
        print(f"\nframe: {len(df)} rows, {df.index.min().date()} -> {df.index.max().date()}")
        print(f"columns: {list(df.columns)}")
        print("\nlast 5 rows:")
        print(df.tail(5).to_string())
    print("\nlatest scalars:")
    for k, v in res["latest"].items():
        print(f"  {k}: {v}")

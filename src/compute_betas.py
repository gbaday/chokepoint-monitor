"""180-day rolling OLS: stock daily returns ~ JKM-HH + TTF-HH + Brent.

Window is 180 business days (the most recent aligned observations).
Returns dict per ticker:
  jkm_hh_beta, jkm_hh_t, ttf_hh_beta, ttf_hh_t, brent_beta, r_squared, n_obs
  spread_score_raw = jkm_hh_beta + ttf_hh_beta - 0.5 * brent_beta
Any failure on a ticker yields a dict of None values.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

log = logging.getLogger(__name__)

WINDOW = 180


def _daily_returns(s: pd.Series) -> pd.Series:
    return s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def _empty() -> dict[str, Any]:
    return {"jkm_hh_beta": None, "jkm_hh_t": None,
            "ttf_hh_beta": None, "ttf_hh_t": None,
            "brent_beta": None, "r_squared": None,
            "spread_score_raw": None, "n_obs": 0}


def compute_one(stock_prices: pd.Series, spreads: pd.DataFrame) -> dict[str, Any]:
    out = _empty()

    if stock_prices is None or stock_prices.empty:
        return out

    needed = ["jkm_hh", "ttf_hh", "brent"]
    missing = [c for c in needed if c not in spreads.columns]
    if missing:
        log.warning("spreads frame missing %s", missing)
        return out

    sp = stock_prices.copy()
    if isinstance(sp.index, pd.DatetimeIndex) and sp.index.tz is not None:
        sp.index = sp.index.tz_localize(None)

    df = pd.concat({
        "y": _daily_returns(sp),
        "jkm_hh": _daily_returns(spreads["jkm_hh"]),
        "ttf_hh": _daily_returns(spreads["ttf_hh"]),
        "brent": _daily_returns(spreads["brent"]),
    }, axis=1).dropna()

    if len(df) < 30:
        out["n_obs"] = len(df)
        return out

    df = df.tail(WINDOW)
    out["n_obs"] = len(df)

    X = sm.add_constant(df[["jkm_hh", "ttf_hh", "brent"]])
    try:
        res = sm.OLS(df["y"], X).fit()
    except Exception as e:
        log.warning("OLS failed: %s", e)
        return out

    out["jkm_hh_beta"] = float(res.params["jkm_hh"])
    out["jkm_hh_t"] = float(res.tvalues["jkm_hh"])
    out["ttf_hh_beta"] = float(res.params["ttf_hh"])
    out["ttf_hh_t"] = float(res.tvalues["ttf_hh"])
    out["brent_beta"] = float(res.params["brent"])
    out["r_squared"] = float(res.rsquared)
    out["spread_score_raw"] = (out["jkm_hh_beta"] + out["ttf_hh_beta"]
                               - 0.5 * out["brent_beta"])
    return out


def compute_all(prices_dict: dict[str, dict], spreads: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ticker, payload in prices_dict.items():
        stock = payload.get("prices")
        try:
            out[ticker] = compute_one(stock, spreads)
        except Exception as e:
            log.warning("compute_one %s failed: %s", ticker, e)
            out[ticker] = _empty()
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from src.fetch_prices import fetch_all
    from src.fetch_spreads import fetch_spreads

    sample = ["VG", "LNG", "CRK"]
    print("fetching prices...")
    prices = fetch_all(sample)
    print("fetching spreads...")
    sp = fetch_spreads()["frame"]
    print("running OLS...")
    res = compute_all(prices, sp)
    for t in sample:
        print(f"\n=== {t} ===")
        for k, v in res[t].items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")

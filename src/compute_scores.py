"""Cross-sectional z-scores + composite Sweet Spot / Broad scores.

All z-scores are computed across the universe of tickers in `prices_dict`
(not across history). Missing values stay missing through z-scoring; for
composite scores they are coalesced to 0 (= universe mean).

Composite weights:
  Sweet Spot = 0.30 Value + 0.20 Growth + 0.20 Spread + 0.20 Reset + 0.10 NotExtended
  Broad      = 0.25 Value + 0.15 Growth + 0.15 Spread + 0.15 Reset
              + 0.10 NotExtended + 0.10 Setup + 0.10 Quality
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

GROWTH_CLIP_SIGMA = 3.0


def _z(series: pd.Series, clip: float | None = None) -> pd.Series:
    s = series.astype(float)
    if clip is not None:
        mu0, sd0 = s.mean(skipna=True), s.std(skipna=True, ddof=0)
        if sd0 and not np.isnan(sd0) and sd0 > 0:
            s = s.clip(lower=mu0 - clip * sd0, upper=mu0 + clip * sd0)
    mu, sd = s.mean(skipna=True), s.std(skipna=True, ddof=0)
    if not sd or np.isnan(sd) or sd == 0:
        out = pd.Series(np.nan, index=s.index)
        out[s.notna()] = 0.0
        return out
    return (s - mu) / sd


def _to_float_or_none(x: Any) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _g(d: dict, key: str) -> float:
    v = d.get(key) if d else None
    return np.nan if v is None else float(v)


def compute_scores(prices_dict: dict[str, dict],
                   betas_dict: dict[str, dict]) -> dict[str, dict]:
    tickers = list(prices_dict.keys())

    raw = pd.DataFrame(index=tickers)
    raw["spread_raw"]      = [_g(betas_dict.get(t, {}), "spread_score_raw") for t in tickers]
    raw["ev_ebitda"]       = [_g(prices_dict[t], "ev_ebitda")               for t in tickers]
    raw["price_sales"]     = [_g(prices_dict[t], "price_sales")             for t in tickers]
    raw["debt_ebitda"]     = [_g(prices_dict[t], "debt_ebitda")             for t in tickers]
    raw["fcf_ev"]          = [_g(prices_dict[t], "fcf_ev")                  for t in tickers]
    raw["fwd_rev_growth"]  = [_g(prices_dict[t], "fwd_rev_growth")          for t in tickers]
    raw["from_1y_hi"]      = [_g(prices_dict[t], "from_1y_hi")              for t in tickers]
    raw["from_5y_hi"]      = [_g(prices_dict[t], "from_5y_hi")              for t in tickers]
    raw["ytd"]             = [_g(prices_dict[t], "ytd")                     for t in tickers]
    raw["from_1y_lo"]      = [_g(prices_dict[t], "from_1y_lo")              for t in tickers]
    raw["ebitda_margin"]   = [_g(prices_dict[t], "ebitda_margin")           for t in tickers]
    raw["roic"]            = [_g(prices_dict[t], "roic")                    for t in tickers]
    raw["roe"]             = [_g(prices_dict[t], "roe")                     for t in tickers]

    z = pd.DataFrame(index=tickers)

    # Spread
    z["spread"] = _z(raw["spread_raw"])

    # Value: invert cost-style metrics; FCF/EV is already a yield (direct).
    val_components = pd.DataFrame({
        "ev_ebitda_inv":   _z(-raw["ev_ebitda"]),
        "price_sales_inv": _z(-raw["price_sales"]),
        "debt_ebitda_inv": _z(-raw["debt_ebitda"]),
        "fcf_ev":          _z(raw["fcf_ev"]),
    }, index=tickers)
    z["value"] = _z(val_components.mean(axis=1, skipna=True))

    # Growth (clip ±3σ before z-scoring)
    z["growth"] = _z(raw["fwd_rev_growth"], clip=GROWTH_CLIP_SIGMA)

    # Reset: mean of (price/1y_high − 1) and (price/5y_high − 1), inverted.
    reset_raw = -((raw["from_1y_hi"] + raw["from_5y_hi"]) / 2.0)
    z["reset"] = _z(reset_raw)

    # Not Extended: penalize high YTD + large distance from 1y low.
    not_ext_raw = -((_z(raw["ytd"]) + _z(raw["from_1y_lo"])) / 2.0)
    z["not_extended"] = _z(not_ext_raw)

    # Setup
    z["setup"] = _z((z["reset"] + z["not_extended"]) / 2.0)

    # Quality
    roic_or_roe = raw["roic"].copy()
    roic_or_roe = roic_or_roe.where(roic_or_roe.notna(), raw["roe"])
    qual = pd.DataFrame({
        "margin": _z(raw["ebitda_margin"]),
        "ret":    _z(roic_or_roe),
    }, index=tickers)
    z["quality"] = _z(qual.mean(axis=1, skipna=True))

    def _composite(weights: list[tuple[str, float]]) -> pd.Series:
        s = pd.Series(0.0, index=tickers)
        for col, w in weights:
            s = s + w * z[col].fillna(0.0)
        return s

    sweet = _composite([("value", 0.30), ("growth", 0.20), ("spread", 0.20),
                        ("reset", 0.20), ("not_extended", 0.10)])
    broad = _composite([("value", 0.25), ("growth", 0.15), ("spread", 0.15),
                        ("reset", 0.15), ("not_extended", 0.10),
                        ("setup", 0.10), ("quality", 0.10)])

    out: dict[str, dict] = {}
    for t in tickers:
        out[t] = {
            "sweet_spot":   float(sweet.loc[t]),
            "broad_score":  float(broad.loc[t]),
            "spread":       _to_float_or_none(z["spread"].loc[t]),
            "value":        _to_float_or_none(z["value"].loc[t]),
            "growth":       _to_float_or_none(z["growth"].loc[t]),
            "reset":        _to_float_or_none(z["reset"].loc[t]),
            "not_extended": _to_float_or_none(z["not_extended"].loc[t]),
            "setup":        _to_float_or_none(z["setup"].loc[t]),
            "quality":      _to_float_or_none(z["quality"].loc[t]),
        }
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from config.universe import TICKERS
    from src.compute_betas import compute_all as compute_betas
    from src.fetch_prices import fetch_all
    from src.fetch_spreads import fetch_spreads

    universe = [t["ticker"] for t in TICKERS]
    print(f"fetching {len(universe)} tickers...")
    prices = fetch_all(universe)
    print("fetching spreads...")
    sp = fetch_spreads()["frame"]
    print("computing betas...")
    betas = compute_betas(prices, sp)
    print("computing scores...")
    scores = compute_scores(prices, betas)

    rows = []
    for t in universe:
        s = scores[t]
        rows.append([t, s["sweet_spot"], s["broad_score"], s["spread"],
                     s["value"], s["growth"], s["reset"],
                     s["not_extended"], s["setup"], s["quality"]])
    df = pd.DataFrame(rows, columns=["tk", "sweet", "broad", "spr",
                                      "val", "grw", "rst", "nxt",
                                      "stp", "qty"])
    df = df.sort_values("sweet", ascending=False)
    print("\nRanking by Sweet Spot:")
    print(df.to_string(index=False, float_format=lambda x: f"{x:6.2f}"))

"""Cross-sectional z-scores + composite Sweet Spot score.

All z-scores are computed across the universe of tickers in `prices_dict`
(not across history). Missing values stay missing through z-scoring; for
composite scores they are coalesced to 0 (= universe mean).

Composite weights:
  Sweet Spot = 0.30 Value + 0.20 Growth + 0.20 Spread + 0.20 Reset + 0.10 RoomToRun

  Spread = average of z(TTF-HH beta) and z(JKM-HH beta).
  Value  = average of z(-EV/EBITDA), z(-NetDebt/EBITDA), z(FCF/EV)  [P/S excluded].
  Growth = z(forward EBITDA growth, clipped ±3σ).
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
    raw["ttf_hh_beta_uni"]   = [_g(betas_dict.get(t, {}), "ttf_hh_beta_uni")   for t in tickers]
    raw["jkm_hh_beta_uni"]   = [_g(betas_dict.get(t, {}), "jkm_hh_beta_uni")   for t in tickers]
    raw["ev_ebitda"]         = [_g(prices_dict[t], "ev_ebitda")                for t in tickers]
    raw["net_debt_ebitda"]   = [_g(prices_dict[t], "net_debt_ebitda")          for t in tickers]
    raw["fcf_ev"]            = [_g(prices_dict[t], "fcf_ev")                   for t in tickers]
    raw["fwd_rev_growth"]    = [_g(prices_dict[t], "fwd_rev_growth")           for t in tickers]
    raw["from_1y_hi"]        = [_g(prices_dict[t], "from_1y_hi")               for t in tickers]
    raw["from_5y_hi"]        = [_g(prices_dict[t], "from_5y_hi")               for t in tickers]
    raw["ytd"]               = [_g(prices_dict[t], "ytd")                      for t in tickers]
    raw["from_1y_lo"]        = [_g(prices_dict[t], "from_1y_lo")               for t in tickers]
    raw["ebitda_margin"]     = [_g(prices_dict[t], "ebitda_margin")             for t in tickers]
    raw["roic"]              = [_g(prices_dict[t], "roic")                      for t in tickers]
    raw["roe"]               = [_g(prices_dict[t], "roe")                       for t in tickers]

    z = pd.DataFrame(index=tickers)

    # Spread: bivariate (univariate) betas — avoids multicollinearity between JKM and TTF.
    # Each beta is estimated independently (stock ~ const + spread_i).
    z["spread_ttf"] = _z(raw["ttf_hh_beta_uni"])
    z["spread_jkm"] = _z(raw["jkm_hh_beta_uni"])
    spread_avg = pd.DataFrame(
        {"ttf": z["spread_ttf"], "jkm": z["spread_jkm"]}, index=tickers
    ).mean(axis=1, skipna=True)
    z["spread"] = _z(spread_avg)

    # Value: invert cost-style metrics; FCF/EV is already a yield (direct). P/S excluded.
    val_components = pd.DataFrame({
        "ev_ebitda_inv":      _z(-raw["ev_ebitda"]),
        "net_debt_ebitda_inv": _z(-raw["net_debt_ebitda"]),
        "fcf_ev":             _z(raw["fcf_ev"]),
    }, index=tickers)
    z["value"] = _z(val_components.mean(axis=1, skipna=True))

    # Growth: forward revenue growth (clip ±3σ before z-scoring)
    z["growth"] = _z(raw["fwd_rev_growth"], clip=GROWTH_CLIP_SIGMA)

    # Reset: mean of (price/1y_high − 1) and (price/5y_high − 1), inverted.
    reset_raw = -((raw["from_1y_hi"] + raw["from_5y_hi"]) / 2.0)
    z["reset"] = _z(reset_raw)

    # Room to Run: penalize high YTD + large distance from 1y low.
    room_raw = -((_z(raw["ytd"]) + _z(raw["from_1y_lo"])) / 2.0)
    z["room_to_run"] = _z(room_raw)

    # Setup
    z["setup"] = _z((z["reset"] + z["room_to_run"]) / 2.0)

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
                        ("reset", 0.20), ("room_to_run", 0.10)])

    out: dict[str, dict] = {}
    for t in tickers:
        out[t] = {
            "sweet_spot":   float(sweet.loc[t]),
            "spread":       _to_float_or_none(z["spread"].loc[t]),
            "spread_ttf":   _to_float_or_none(z["spread_ttf"].loc[t]),
            "spread_jkm":   _to_float_or_none(z["spread_jkm"].loc[t]),
            "value":        _to_float_or_none(z["value"].loc[t]),
            "growth":       _to_float_or_none(z["growth"].loc[t]),
            "reset":        _to_float_or_none(z["reset"].loc[t]),
            "room_to_run":  _to_float_or_none(z["room_to_run"].loc[t]),
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
        rows.append([t, s["sweet_spot"], s["spread"],
                     s["value"], s["growth"], s["reset"],
                     s["room_to_run"], s["setup"], s["quality"]])
    df = pd.DataFrame(rows, columns=["tk", "sweet", "spr",
                                      "val", "grw", "rst", "rtr",
                                      "stp", "qty"])
    df = df.sort_values("sweet", ascending=False)
    print("\nRanking by Sweet Spot:")
    print(df.to_string(index=False, float_format=lambda x: f"{x:6.2f}"))

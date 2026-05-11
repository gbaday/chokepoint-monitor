"""Consolidate prices + spreads + betas + bloomberg + scores into web/data_<sector>.json.

Schema:
  generated_at        ISO timestamp
  sector              e.g. "gas_lng"
  spreads.jkm_hh_latest, ttf_hh_latest, jkm_ttf_latest
  spreads.history     list of {date, jkm_hh, ttf_hh, jkm_ttf} (>= 18 months)
  tickers[]           ordered by Sweet Spot desc, with nested
                      scores / betas / fundamentals / returns / crowding / catalyst
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = _PROJECT_ROOT / "docs"

HISTORY_MONTHS = 24  # keep 24 months of spread history for the line chart


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _spreads_payload(frame: pd.DataFrame, latest: dict) -> dict:
    out_history: list[dict] = []
    if frame is not None and not frame.empty:
        cutoff = pd.Timestamp(dt.date.today() - dt.timedelta(days=HISTORY_MONTHS * 31))
        sub = frame[frame.index >= cutoff].copy()
        for col in ("jkm_hh", "ttf_hh", "jkm_ttf"):
            if col not in sub.columns:
                sub[col] = float("nan")
        sub = sub[["jkm_hh", "ttf_hh", "jkm_ttf"]].dropna(how="all")
        for ts, row in sub.iterrows():
            out_history.append({
                "date": ts.date().isoformat(),
                "jkm_hh": _f(row.get("jkm_hh")),
                "ttf_hh": _f(row.get("ttf_hh")),
                "jkm_ttf": _f(row.get("jkm_ttf")),
            })
    return {
        "jkm_hh_latest": _f(latest.get("jkm_hh")),
        "ttf_hh_latest": _f(latest.get("ttf_hh")),
        "jkm_ttf_latest": _f(latest.get("jkm_ttf")),
        "hh_latest": _f(latest.get("hh")),
        "brent_latest": _f(latest.get("brent")),
        "history": out_history,
    }


def _ticker_payload(meta: dict, prices: dict, betas: dict,
                    scores: dict, bbg: dict) -> dict:
    return {
        "ticker": meta["ticker"],
        "bucket": meta["bucket"],
        "what_it_does": meta["what_it_does"],
        "scores": {
            "sweet_spot":  _f(scores.get("sweet_spot")),
            "spread":      _f(scores.get("spread")),
            "spread_ttf":  _f(scores.get("spread_ttf")),
            "spread_jkm":  _f(scores.get("spread_jkm")),
            "value":       _f(scores.get("value")),
            "growth":      _f(scores.get("growth")),
            "reset":       _f(scores.get("reset")),
            "room_to_run": _f(scores.get("room_to_run")),
            "setup":       _f(scores.get("setup")),
            "quality":     _f(scores.get("quality")),
        },
        "betas": {
            "jkm_hh_beta": _f(betas.get("jkm_hh_beta")),
            "jkm_hh_t":    _f(betas.get("jkm_hh_t")),
            "ttf_hh_beta": _f(betas.get("ttf_hh_beta")),
            "ttf_hh_t":    _f(betas.get("ttf_hh_t")),
            "brent_beta":  _f(betas.get("brent_beta")),
            "r_squared":   _f(betas.get("r_squared")),
            "reg_scatter": betas.get("reg_scatter"),
            "reg_line":    betas.get("reg_line"),
        },
        "fundamentals": {
            "mkt_cap_b":       _f(prices.get("mkt_cap_b")),
            "ev_ebitda":       _f(prices.get("ev_ebitda")),
            "net_debt_ebitda": _f(prices.get("net_debt_ebitda")),
            "fcf_ev":          _f(prices.get("fcf_ev")),
            "fwd_rev_growth":  _f(prices.get("fwd_rev_growth")),
            "roic":            _f(prices.get("roic")),
            "roe":             _f(prices.get("roe")),
            "price_sales":     _f(prices.get("price_sales")),
            "from_1y_hi":      _f(prices.get("from_1y_hi")),
        },
        "returns": {
            "mar_run":  _f(prices.get("mar_run")),
            "apr_sell": _f(prices.get("apr_sell")),
            "ytd":      _f(prices.get("ytd")),
            "rsi_14":   _f(prices.get("rsi_14")),
        },
        "crowding": {
            "si_pct_float":   _f(bbg.get("si_pct_float")),
            "days_to_cover":  _f(bbg.get("days_to_cover")),
            "delta_short_2w": _f(bbg.get("delta_short_2w")),
        },
        "catalyst": {
            "next_earnings_date": bbg.get("next_earnings_date"),
            "days_to_earnings":   bbg.get("days_to_earnings"),
            "earnings_flag":      bbg.get("earnings_flag"),
        },
    }


def build(universe: list[dict], sector_name: str,
          spreads: dict, prices: dict, betas: dict,
          scores: dict, bbg: dict) -> dict:
    tickers_payload = []
    for meta in universe:
        t = meta["ticker"]
        tickers_payload.append(_ticker_payload(
            meta=meta,
            prices=prices.get(t, {}),
            betas=betas.get(t, {}),
            scores=scores.get(t, {}),
            bbg=bbg.get(t, {}),
        ))
    tickers_payload.sort(
        key=lambda d: (d["scores"]["sweet_spot"] is None,
                       -(d["scores"]["sweet_spot"] or 0.0)))

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sector": sector_name,
        "spreads": _spreads_payload(spreads["frame"], spreads["latest"]),
        "tickers": tickers_payload,
    }


def write_json(payload: dict, sector_name: str) -> Path:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    path = WEB_DIR / f"data_{sector_name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log.info("wrote %s (%d tickers, %d history rows)",
             path, len(payload["tickers"]), len(payload["spreads"]["history"]))
    return path

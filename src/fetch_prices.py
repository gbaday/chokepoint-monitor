"""yfinance fetcher: 5y price history + returns + fundamentals.

Output of fetch_all(tickers) is a dict keyed by ticker; each value carries:
  prices              -> pd.Series of adjusted closes (5y, used by compute_betas)
  price_last, high_1y, low_1y, high_5y
  from_1y_hi, from_1y_lo, from_5y_hi
  ytd, mar_run, apr_sell
  price_sales                       (stays in yfinance — not in Bloomberg)
  mkt_cap_b, ev_ebitda, net_debt_ebitda, fcf_ev, fwd_rev_growth,
  ebitda_margin, roic, roe          (fallback — Bloomberg values take priority
                                     when merged in run_daily.py)

EBITDA <= 0 -> ev_ebitda and net_debt_ebitda forced to None.
Any failure on a ticker logs a warning and yields None values; never raises.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# 2026 seasonal windows. Revisit annually.
MAR_RUN_START = dt.date(2026, 3, 1)
MAR_RUN_END = dt.date(2026, 3, 27)
APR_SELL_START = dt.date(2026, 4, 1)
APR_SELL_END = dt.date(2026, 4, 24)


def _first_not_none(d: dict, *keys) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _next_earnings_yf(tk: yf.Ticker) -> tuple[str | None, int | None]:
    today = dt.date.today()
    # Method 1: tk.calendar (dict in modern yfinance)
    try:
        cal = tk.calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if not isinstance(dates, list):
                dates = [dates]
            for d in dates:
                if d is None:
                    continue
                try:
                    ts = pd.Timestamp(d)
                except Exception:
                    continue
                if pd.isna(ts):
                    continue
                date_obj = ts.date()
                days = (date_obj - today).days
                if days >= 0:
                    return date_obj.isoformat(), days
    except Exception:
        pass
    # Method 2: tk.earnings_dates DataFrame
    try:
        ed = tk.earnings_dates
        if ed is not None and not ed.empty:
            future = [i for i in ed.index if pd.Timestamp(i).date() >= today]
            if future:
                earliest = min(future, key=lambda x: pd.Timestamp(x).date())
                date_obj = pd.Timestamp(earliest).date()
                return date_obj.isoformat(), (date_obj - today).days
    except Exception:
        pass
    return None, None


def _rsi14(prices: pd.Series) -> float | None:
    if prices is None or len(prices) < 15:
        return None
    delta = prices.diff().dropna()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    last = rsi.iloc[-1]
    return float(last) if pd.notna(last) else None


def _window_return(prices: pd.Series, start: dt.date, end: dt.date) -> float | None:
    if prices is None or prices.empty:
        return None
    idx = prices.index.date
    s = prices[(idx >= start) & (idx <= end)]
    if len(s) < 2:
        return None
    return float(s.iloc[-1] / s.iloc[0] - 1)


def _fetch_history(tk: yf.Ticker, ticker: str) -> pd.Series:
    try:
        h = tk.history(period="5y", auto_adjust=True)
    except Exception as e:
        log.warning("history failed %s: %s", ticker, e)
        return pd.Series(dtype=float)
    if h is None or h.empty or "Close" not in h.columns:
        return pd.Series(dtype=float)
    s = h["Close"].dropna()
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    return s


def _fetch_info(tk: yf.Ticker, ticker: str) -> dict:
    try:
        info = tk.info or {}
    except Exception as e:
        log.warning("info failed %s: %s", ticker, e)
        info = {}
    return info


def _forward_revenue_growth(tk: yf.Ticker, info: dict) -> float | None:
    try:
        ge = getattr(tk, "growth_estimates", None)
        if ge is not None and not ge.empty:
            for label in ("+1y", "1y", "+5y"):
                if label in ge.index:
                    row = ge.loc[label]
                    if isinstance(row, pd.Series):
                        for col in ("stockTrend", "growth", "estimate"):
                            if col in row and pd.notna(row[col]):
                                return float(row[col])
                        first = row.dropna()
                        if not first.empty:
                            return float(first.iloc[0])
                    elif pd.notna(row):
                        return float(row)
                    break
    except Exception:
        pass
    val = _first_not_none(info, "revenueGrowth")
    return float(val) if val is not None else None


def fetch_one(ticker: str) -> dict[str, Any]:
    out: dict[str, Any] = {"ticker": ticker}
    try:
        tk = yf.Ticker(ticker)
    except Exception as e:
        log.warning("Ticker init failed %s: %s", ticker, e)
        return out

    hist = _fetch_history(tk, ticker)
    out["prices"] = hist

    if not hist.empty:
        last = float(hist.iloc[-1])
        idx_dates = hist.index.date
        today = dt.date.today()

        one_y_ago = today - dt.timedelta(days=365)
        s1y = hist[idx_dates >= one_y_ago]
        out["price_last"] = last
        out["high_1y"] = float(s1y.max()) if not s1y.empty else None
        out["low_1y"] = float(s1y.min()) if not s1y.empty else None
        out["high_5y"] = float(hist.max())
        out["from_1y_hi"] = (last / out["high_1y"] - 1) if out["high_1y"] else None
        out["from_1y_lo"] = (last / out["low_1y"] - 1) if out["low_1y"] else None
        out["from_5y_hi"] = (last / out["high_5y"] - 1) if out["high_5y"] else None

        ytd_start = dt.date(today.year, 1, 1)
        sytd = hist[idx_dates >= ytd_start]
        out["ytd"] = float(sytd.iloc[-1] / sytd.iloc[0] - 1) if len(sytd) >= 2 else None

        out["mar_run"] = _window_return(hist, MAR_RUN_START, MAR_RUN_END)
        out["apr_sell"] = _window_return(hist, APR_SELL_START, APR_SELL_END)
        out["rsi_14"] = _rsi14(hist)
    else:
        for k in ("price_last", "high_1y", "low_1y", "high_5y",
                 "from_1y_hi", "from_1y_lo", "from_5y_hi",
                 "ytd", "mar_run", "apr_sell", "rsi_14"):
            out[k] = None

    info = _fetch_info(tk, ticker)

    mc = _first_not_none(info, "marketCap")
    out["mkt_cap_b"] = mc / 1e9 if mc else None

    ev = _first_not_none(info, "enterpriseValue")
    ebitda = _first_not_none(info, "ebitda")
    ev_ebitda = _first_not_none(info, "enterpriseToEbitda")
    if ev_ebitda is None and ev and ebitda and ebitda > 0:
        ev_ebitda = ev / ebitda
    if ebitda is None or ebitda <= 0:
        ev_ebitda = None  # don't treat negative EBITDA as cheap
    out["ev_ebitda"] = ev_ebitda
    out["ebitda_negative"] = bool(ebitda is not None and ebitda <= 0)

    out["price_sales"] = _first_not_none(info, "priceToSalesTrailing12Months")

    total_debt = _first_not_none(info, "totalDebt")
    cash = _first_not_none(info, "totalCash")
    if total_debt is not None and cash is not None and ebitda and ebitda > 0:
        out["net_debt_ebitda"] = (total_debt - cash) / ebitda
    else:
        out["net_debt_ebitda"] = None

    fcf = _first_not_none(info, "freeCashflow")
    if fcf is None:
        ocf = _first_not_none(info, "operatingCashflow")
        capex = _first_not_none(info, "capitalExpenditures")
        if ocf is not None and capex is not None:
            fcf = ocf + capex  # capex is negative in yfinance
    out["fcf_ev"] = (fcf / ev) if (fcf is not None and ev) else None

    out["fwd_rev_growth"] = _forward_revenue_growth(tk, info)

    out["ebitda_margin"] = _first_not_none(info, "ebitdaMargins")
    out["roic"] = _first_not_none(info, "returnOnAssets")  # proxy; Bloomberg RETURN_ON_INV_CAPITAL takes priority
    out["roe"] = _first_not_none(info, "returnOnEquity")

    # Days to cover (short ratio = shares short / avg daily volume)
    sr = _first_not_none(info, "shortRatio")
    out["days_to_cover_yf"] = float(sr) if sr is not None else None

    # Next earnings date
    nxt_date, nxt_days = _next_earnings_yf(tk)
    out["next_earnings_date_yf"] = nxt_date
    out["days_to_earnings_yf"] = nxt_days

    return out


def fetch_all(tickers: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in tickers:
        log.info("fetching %s", t)
        try:
            out[t] = fetch_one(t)
        except Exception as e:
            log.warning("fetch_one failed %s: %s", t, e)
            out[t] = {"ticker": t}
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sample = ["VG", "CRK", "LNG"]
    data = fetch_all(sample)
    for t in sample:
        d = data[t]
        prices = d.get("prices")
        n = len(prices) if isinstance(prices, pd.Series) else 0
        first = prices.index[0].date() if n else None
        last_dt = prices.index[-1].date() if n else None
        print(f"\n=== {t} ===")
        print(f"  prices: {n} rows  ({first} -> {last_dt})")
        for k, v in d.items():
            if k == "prices":
                continue
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")

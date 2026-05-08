"""Daily orchestration. Usage: python -m src.run_daily --sector gas_lng

Order: spreads -> prices -> betas -> bloomberg -> scores -> build -> write JSON.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="Build chokepoint dashboard data.")
    parser.add_argument("--sector", default="gas_lng",
                        help="Sector module under config/sectors (default: gas_lng)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("run_daily")

    os.environ["ACTIVE_SECTOR"] = args.sector

    # Imports happen after env var is set so config.universe picks the right sector.
    from config.universe import TICKERS, SECTOR_NAME
    from src.build_output import build, write_json
    from src.compute_betas import compute_all as compute_betas
    from src.compute_scores import compute_scores
    from src.fetch_bloomberg import get_bloomberg_data, FUND_KEYS
    from src.fetch_prices import fetch_all as fetch_prices
    from src.fetch_spreads import fetch_spreads

    log.info("sector=%s tickers=%d", SECTOR_NAME, len(TICKERS))

    yf_symbols = [t["ticker"] for t in TICKERS]
    bbg_symbols = [t["ticker_bbg"] for t in TICKERS]

    t0 = time.time()
    log.info("[1/5] fetching macro spreads...")
    spreads = fetch_spreads()

    log.info("[2/5] fetching prices/fundamentals (yfinance)...")
    prices = fetch_prices(yf_symbols)

    log.info("[3/5] computing betas (180d OLS)...")
    betas = compute_betas(prices, spreads["frame"])

    log.info("[4/5] fetching Bloomberg fundamentals + crowding/catalyst...")
    bbg = get_bloomberg_data(bbg_symbols)
    if not bbg:
        log.warning("Bloomberg data unavailable — BBG fields will fall back to yfinance values.")

    # Merge BBG fundamentals into prices (BBG takes priority over yfinance).
    for t, bbg_data in bbg.items():
        if t in prices:
            for k in FUND_KEYS:
                v = bbg_data.get(k)
                if v is not None:
                    prices[t][k] = v

    log.info("[5/5] computing scores + building output...")
    scores = compute_scores(prices, betas)
    payload = build(TICKERS, SECTOR_NAME, spreads, prices, betas, scores, bbg)
    path = write_json(payload, SECTOR_NAME)

    log.info("done in %.1fs -> %s", time.time() - t0, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

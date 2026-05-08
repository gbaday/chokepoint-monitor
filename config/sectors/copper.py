"""Copper mining sector — TEMPLATE.

To activate, populate TICKERS and confirm MACRO_SPREADS / spread fetcher logic
in src/fetch_spreads.py handles the copper-relevant macro variable
(LME copper price, Shanghai-LME arb, treatment/refining charges, etc.).

Run with: python -m src.run_daily --sector copper
Output:    web/data_copper.json
Frontend:  index.html?sector=copper
"""

SECTOR_NAME = "copper"
SECTOR_LABEL = "Copper Mining"

# For copper, the central macro variable is the LME copper price (HG=F as a USD proxy on COMEX).
# Replace `["jkm_hh", "ttf_hh"]` with copper-relevant spreads when extending fetch_spreads.py.
MACRO_SPREADS = ["copper_usd"]

# Populate with copper-mining tickers. Format follows config/sectors/gas_lng.py:
#   {"ticker": "FCX", "ticker_bbg": "FCX US Equity",
#    "bucket": "core" | "small/levered",
#    "what_it_does": "Short business description in English."}
TICKERS: list[dict] = [
    # {"ticker": "FCX", "ticker_bbg": "FCX US Equity", "bucket": "core",
    #  "what_it_does": "Freeport-McMoRan: largest US copper miner; Indonesian Grasberg + US ops."},
    # ... add others
]

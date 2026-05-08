"""Active sector loader. Reads ACTIVE_SECTOR env var (default: gas_lng) and
re-exports the sector module's TICKERS / metadata."""

import importlib
import os

ACTIVE = os.environ.get("ACTIVE_SECTOR", "gas_lng")

_module = importlib.import_module(f"config.sectors.{ACTIVE}")

TICKERS = _module.TICKERS
SECTOR_NAME = _module.SECTOR_NAME
SECTOR_LABEL = _module.SECTOR_LABEL
MACRO_SPREADS = _module.MACRO_SPREADS

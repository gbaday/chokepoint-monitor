"""Utilities for saving and loading daily Sweet Spot ranking snapshots.

Snapshots are stored as docs/history/YYYY-MM-DD.json.
Each file contains only the ranking data needed to reconstruct history.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import date, timedelta

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = _PROJECT_ROOT / "docs" / "history"


def save_snapshot(tickers_payload: list[dict], run_date: date | None = None) -> Path:
    """Write a daily ranking snapshot to docs/history/YYYY-MM-DD.json.

    tickers_payload is the already-sorted list of ticker dicts from build_output.build().
    """
    if run_date is None:
        run_date = date.today()

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    rankings = []
    for rank, t in enumerate(tickers_payload, start=1):
        score = t.get("scores", {}).get("sweet_spot")
        rankings.append({
            "ticker":     t["ticker"],
            "bucket":     t.get("bucket", ""),
            "sweet_spot": round(score, 4) if score is not None else None,
            "rank":       rank,
        })

    snapshot = {"date": run_date.isoformat(), "rankings": rankings}

    path = HISTORY_DIR / f"{run_date.isoformat()}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, separators=(",", ":"))

    log.info("saved ranking snapshot -> %s (%d tickers)", path.name, len(rankings))
    return path


def load_ranking_history(weeks: int = 12) -> dict:
    """Load ranking snapshots for the last `weeks` weeks of business days.

    Returns:
        {
            "dates":   ["2026-02-17", ...],
            "tickers": {
                "VG":  {"ranks": [1, 2, ...], "sweet_spots": [1.61, ...]},
                ...
            }
        }
    If no history files exist, returns {"dates": [], "tickers": {}}.
    """
    if not HISTORY_DIR.exists():
        return {"dates": [], "tickers": {}}

    # Collect all available snapshot files
    files: dict[str, Path] = {}
    for p in HISTORY_DIR.glob("*.json"):
        files[p.stem] = p  # stem = "YYYY-MM-DD"

    if not files:
        return {"dates": [], "tickers": {}}

    # Build the target date range: last (weeks * 7) calendar days, business days only
    today = date.today()
    lookback_start = today - timedelta(days=weeks * 7)
    target_dates: list[str] = []
    d = lookback_start
    while d <= today:
        if d.weekday() < 5:  # Mon-Fri
            target_dates.append(d.isoformat())
        d += timedelta(days=1)

    # Filter to dates that actually have a snapshot file
    available_dates = sorted(dt for dt in target_dates if dt in files)

    if not available_dates:
        return {"dates": [], "tickers": {}}

    # Load each snapshot and build per-ticker series
    ticker_data: dict[str, dict] = {}

    for dt_str in available_dates:
        try:
            with files[dt_str].open(encoding="utf-8") as f:
                snap = json.load(f)
        except Exception as e:
            log.warning("could not read snapshot %s: %s", dt_str, e)
            continue

        for entry in snap.get("rankings", []):
            tkr = entry["ticker"]
            if tkr not in ticker_data:
                ticker_data[tkr] = {"ranks": [], "sweet_spots": [], "buckets": []}
            ticker_data[tkr]["ranks"].append(entry.get("rank"))
            ticker_data[tkr]["sweet_spots"].append(entry.get("sweet_spot"))
            ticker_data[tkr]["buckets"].append(entry.get("bucket", ""))

    # Strip buckets from final output (was only needed for a potential future use)
    tickers_out: dict[str, dict] = {}
    for tkr, series in ticker_data.items():
        tickers_out[tkr] = {
            "ranks":       series["ranks"],
            "sweet_spots": series["sweet_spots"],
            "bucket":      series["buckets"][-1] if series["buckets"] else "",
        }

    return {"dates": available_dates, "tickers": tickers_out}


if __name__ == "__main__":
    import pprint
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = load_ranking_history(weeks=12)
    print(f"dates ({len(result['dates'])}): {result['dates']}")
    print(f"tickers ({len(result['tickers'])}): {list(result['tickers'].keys())}")
    if result["tickers"]:
        first = next(iter(result["tickers"].items()))
        print(f"\nsample — {first[0]}:")
        pprint.pprint(first[1])

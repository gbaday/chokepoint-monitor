# Gas Chokepoint Dashboard

Static web dashboard ranking US gas/LNG equities by a composite **Sweet Spot** score.
Inspired by [snow.ai/energy.pipelines](https://snow.ai/energy.pipelines).

Python pulls prices/fundamentals (yfinance), short-interest/earnings (vista_bbg),
and macro spreads (JKM, TTF, HH, Brent) into `web/data_<sector>.json`.
HTML/CSS/JS vanilla consumes the JSON. Hostable as a static site (e.g. GitHub Pages serving `/web`).

## Setup

```powershell
# Clone, then from project root:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`vista_bbg` is internal (Vista Bloomberg wrapper) and assumed installed in your global Python — it
is **not** in `requirements.txt` so the GitHub Actions runner does not break. The dashboard
gracefully degrades when `vista_bbg` is unavailable (crowding/catalyst columns show "—").

### Bloomberg credentials (`.env`)

Create a `.env` file in the project root with the credentials expected by `vista_bbg`
(same format as other Vista projects, e.g. `Projeto Global Indices/.env`).
This file is git-ignored.

## Run

```powershell
python -m src.run_daily --sector gas_lng
```

Default sector is `gas_lng`. Output is written to `web/data_gas_lng.json`.

## Project layout

```
chokepoint monitor/
├── config/
│   ├── universe.py            # loads ACTIVE_SECTOR (default: gas_lng)
│   └── sectors/gas_lng.py     # tickers, buckets, descriptions
├── data/spreads/              # CSV fallbacks for JKM/TTF when yfinance fails
├── src/                       # fetch_*, compute_*, build_output, run_daily
├── web/                       # index.html, style.css, app.js, data_*.json
├── .github/workflows/         # daily auto-update (yfinance only)
└── requirements.txt
```

## Adding a new sector

1. Copy `config/sectors/copper.py` (template included) and rename to your sector.
2. Populate `TICKERS`, set `SECTOR_NAME`, `SECTOR_LABEL`, `MACRO_SPREADS`.
3. If your sector's central macro variable is not gas, adjust `src/fetch_spreads.py`
   (add new symbols to `SYMBOLS` and any required unit converters; build the
   relevant spread columns in `fetch_spreads()`).
4. `python -m src.run_daily --sector <name>` → produces `web/data_<name>.json`.
5. Frontend reads `?sector=<name>` from the URL: open
   `web/index.html?sector=copper` to view that dataset.

## Hosting (GitHub Pages)

1. Push the repo to GitHub.
2. Settings → Pages → deploy from branch `main`, folder `/docs`.
3. Workflow `.github/workflows/update_data.yml` refreshes `web/data_gas_lng.json`
   daily at 17:30 ET on weekdays (cron schedules both 21:30 UTC and 22:30 UTC
   to cover EDT/EST). The workflow runs only the yfinance pipeline; Bloomberg
   fields stay empty until you refresh them locally and commit the JSON manually.

## Caveat — Bloomberg fields

`SHORT_INT_RATIO`, `DAYS_TO_COVER`, and `NEXT_ANNOUNCEMENT_DT` require an open Bloomberg Terminal
session, so they cannot run on GitHub Actions. Refresh those locally on demand
(`python -m src.run_daily --sector gas_lng`) and commit the updated JSON.

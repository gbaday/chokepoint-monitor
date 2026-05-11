"""Gas / LNG sector universe (12 core + 18 small/levered = 30 tickers)."""

SECTOR_NAME = "gas_lng"
SECTOR_LABEL = "Gas / LNG"
MACRO_SPREADS = ["jkm_hh", "ttf_hh"]

TICKERS = [
    # --- Core ---
    {"ticker": "VG", "ticker_bbg": "VG US Equity", "bucket": "core",
     "what_it_does": "Venture Global: LNG exporter/developer; maximum LNG torque with high leverage/legal-contract overhang."},
    {"ticker": "LNG", "ticker_bbg": "LNG US Equity", "bucket": "core",
     "what_it_does": "Cheniere: operating LNG exporter; contracted liquefaction fees plus spot/marketing upside to JKM-HH spreads."},
    {"ticker": "EXE", "ticker_bbg": "EXE US Equity", "bucket": "core",
     "what_it_does": "Expand Energy: large US gas producer; cheap producer exposure to higher HH with lower oil beta."},
    {"ticker": "ET", "ticker_bbg": "ET US Equity", "bucket": "core",
     "what_it_does": "Energy Transfer: diversified midstream MLP; Permian gas takeaway, intrastate pipes, NGL, fractionation, exports."},
    {"ticker": "OKE", "ticker_bbg": "OKE US Equity", "bucket": "core",
     "what_it_does": "ONEOK: NGL/gas midstream; more levered and less clean than TRGP/ET for this specific thesis."},
    {"ticker": "RRC", "ticker_bbg": "RRC US Equity", "bucket": "core",
     "what_it_does": "Range Resources: low-leverage Appalachia gas producer; cleaner balance sheet, lower LNG-spread directness."},
    {"ticker": "CTRA", "ticker_bbg": "CTRA US Equity", "bucket": "core",
     "what_it_does": "Coterra: gas-weighted E&P with Permian/Appalachia mix; lower leverage, more balanced producer exposure."},
    {"ticker": "WMB", "ticker_bbg": "WMB US Equity", "bucket": "core",
     "what_it_does": "Williams: Transco gas pipe owner; LNG/feedgas and Southeast power-demand tollbooth."},
    {"ticker": "KMI", "ticker_bbg": "KMI US Equity", "bucket": "core",
     "what_it_does": "Kinder Morgan: giant gas pipeline tollbooth; GCX/Permian Highway/Tennessee Gas/Trident LNG feedgas exposure."},
    {"ticker": "AM", "ticker_bbg": "AM US Equity", "bucket": "core",
     "what_it_does": "Antero Midstream: Appalachia gathering/processing MLP; tied to AR volumes, high yield."},
    {"ticker": "EQT", "ticker_bbg": "EQT US Equity", "bucket": "core",
     "what_it_does": "EQT: largest US gas producer; Appalachia scale operator, high leverage to HH price."},
    {"ticker": "AR", "ticker_bbg": "AR US Equity", "bucket": "core",
     "what_it_does": "Antero Resources: Appalachia gas/NGL producer; liquids-rich with LNG export upside."},

    # --- Small / levered ---
    {"ticker": "PAA", "ticker_bbg": "PAA US Equity", "bucket": "small/levered",
     "what_it_does": "Plains All American: crude/NGL pipelines; Permian logistics but wrong commodity for dry-gas spread."},
    {"ticker": "DTM", "ticker_bbg": "DTM US Equity", "bucket": "small/levered",
     "what_it_does": "DT Midstream: gas pipes/storage with Haynesville/Gulf Coast exposure; smaller midstream compounder."},
    {"ticker": "VST", "ticker_bbg": "VST US Equity", "bucket": "small/levered",
     "what_it_does": "Vistra: power generator; gas-fired capacity beneficiary of power demand surge, less direct LNG linkage."},
    {"ticker": "MPLX", "ticker_bbg": "MPLX US Equity", "bucket": "small/levered",
     "what_it_does": "MPLX: large midstream MLP; Permian/Marcellus gathering, stable distributions, lower spread beta."},
    {"ticker": "GLNG", "ticker_bbg": "GLNG US Equity", "bucket": "small/levered",
     "what_it_does": "Golar LNG: floating LNG (FLNG) owner/operator; direct exposure to global LNG infrastructure and JKM/TTF shipping spreads."},
]

// Gas Chokepoint Dashboard — vanilla JS frontend.
// Loads web/data_<sector>.json (default sector via ?sector=… or gas_lng)
// and renders KPIs, four charts, screen table, watchlist, and column dictionary.

const SECTOR = new URLSearchParams(location.search).get("sector") || "gas_lng";
const DATA_URL = `data_${SECTOR}.json`;

// Read CSS custom properties so charts inherit the active theme palette.
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function palette() {
  return {
    segments: {
      value:        cssVar("--c-value"),
      growth:       cssVar("--c-growth"),
      spread:       cssVar("--c-spread"),
      reset:        cssVar("--c-reset"),
      not_extended: cssVar("--c-not-extended"),
    },
    text:    cssVar("--text"),
    dim:     cssVar("--text-dim"),
    mute:    cssVar("--text-mute"),
    grid:    cssVar("--grid"),
    bg:      cssVar("--bg-elev"),
    accent:  cssVar("--accent"),
    green:   cssVar("--green"),
    red:     cssVar("--red"),
  };
}

const FMT = {
  z: (v) => (v == null ? "—" : v.toFixed(2)),
  pct: (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%"),
  num: (v, d = 2) => (v == null ? "—" : v.toFixed(d)),
  intish: (v) => (v == null ? "—" : Math.round(v).toString()),
  bil: (v) => (v == null ? "—" : v.toFixed(2) + "B"),
  date: (v) => (v ? v : "—"),
};

let STATE = {
  data: null,
  filter: "",
  sortKey: "sweet_spot",
  sortDir: "desc",
  topMode: "top10",
  charts: {},
};

// ---------- Bootstrap ----------
fetch(DATA_URL)
  .then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  })
  .then((data) => {
    STATE.data = data;
    document.getElementById("generatedAt").textContent =
      `Generated ${data.generated_at}  •  Sector: ${data.sector}`;
    renderKpis();
    renderAll();
    renderDictionary();
    bindControls();
  })
  .catch((err) => {
    document.querySelector("main").innerHTML =
      `<div style="padding:32px;color:#f85149">Failed to load ${DATA_URL}: ${err.message}</div>`;
  });

// ---------- KPIs ----------
function renderKpis() {
  const d = STATE.data;
  const ts = [...d.tickers];
  const bestSweet = ts.reduce((a, b) =>
    (b.scores.sweet_spot ?? -Infinity) > (a.scores.sweet_spot ?? -Infinity) ? b : a
  );
  const bestSpread = ts.reduce((a, b) =>
    (b.betas.jkm_hh_beta ?? -Infinity) > (a.betas.jkm_hh_beta ?? -Infinity) ? b : a
  );
  const bestQuality = ts.reduce((a, b) =>
    (b.scores.quality ?? -Infinity) > (a.scores.quality ?? -Infinity) ? b : a
  );

  const cards = [
    { label: "Latest JKM-HH", value: FMT.num(d.spreads.jkm_hh_latest), sub: "$/MMBtu" },
    { label: "Latest TTF-HH", value: FMT.num(d.spreads.ttf_hh_latest), sub: "$/MMBtu" },
    { label: "Best Sweet Spot", value: bestSweet.ticker, sub: "z = " + FMT.z(bestSweet.scores.sweet_spot) },
    { label: "Best JKM-HH β", value: bestSpread.ticker, sub: "β = " + FMT.z(bestSpread.betas.jkm_hh_beta) },
    { label: "Cleanest Quality", value: bestQuality.ticker, sub: "z = " + FMT.z(bestQuality.scores.quality) },
  ];

  document.getElementById("kpiRow").innerHTML = cards
    .map((c) => `
      <div class="kpi-card">
        <div class="kpi-label">${c.label}</div>
        <div class="kpi-value">${c.value}</div>
        <div class="kpi-sub">${c.sub}</div>
      </div>`)
    .join("");
}

// ---------- Filtering / sorting ----------
function getFilteredSorted() {
  const d = STATE.data;
  const f = STATE.filter.trim().toUpperCase();
  let rows = d.tickers.filter((t) =>
    !f || t.ticker.toUpperCase().includes(f) || t.what_it_does.toUpperCase().includes(f)
  );
  const key = STATE.sortKey;
  const dir = STATE.sortDir === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    const va = pluck(a, key);
    const vb = pluck(b, key);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return (va - vb) * dir;
  });
  return rows;
}

function pluck(t, key) {
  if (key in t.scores) return t.scores[key];
  if (key in t.betas) return t.betas[key];
  if (key in t.fundamentals) return t.fundamentals[key];
  if (key in t.returns) return t.returns[key];
  return null;
}

function topSlice(rows) {
  return STATE.topMode === "top10" ? rows.slice(0, 10) : rows;
}

// ---------- Render all sections that depend on filter/sort ----------
function renderAll() {
  const rows = topSlice(getFilteredSorted());
  renderStackChart(rows);
  renderSetupScatter(rows);
  renderValLevScatter(rows);
  renderSpreadChart();
  renderScreenTable(getFilteredSorted());
  renderWatchlist();
}

// ---------- Stacked horizontal bars ----------
function renderStackChart(rows) {
  const labels = rows.map((r) => r.ticker);
  const components = ["value", "growth", "spread", "reset", "not_extended"];
  const componentLabels = {
    value: "Value (30%)",
    growth: "Growth (20%)",
    spread: "Spread (20%)",
    reset: "Reset (20%)",
    not_extended: "Not Extended (10%)",
  };
  const componentWeights = {
    value: 0.30, growth: 0.20, spread: 0.20, reset: 0.20, not_extended: 0.10,
  };

  const datasets = components.map((c) => ({
    label: componentLabels[c],
    data: rows.map((r) => (r.scores[c] ?? 0) * componentWeights[c]),
    backgroundColor: palette().segments[c],
    borderWidth: 0,
  }));

  const ctx = document.getElementById("stackChart");
  if (STATE.charts.stack) STATE.charts.stack.destroy();
  STATE.charts.stack = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets },
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      responsive: true,
      plugins: {
        legend: { labels: { color: palette().text, boxWidth: 12 }, position: "top" },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.x.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: palette().dim },
          grid: { color: palette().grid, drawBorder: false },
          title: { display: true, text: "Weighted z-score contribution", color: palette().dim },
        },
        y: {
          stacked: true,
          ticks: { color: palette().text, font: { family: "ui-monospace, monospace" } },
          grid: { display: false },
        },
      },
    },
  });
}

// ---------- Plotly scatter helpers ----------
function hexToRgb(hex) {
  const m = hex.replace("#", "").match(/.{2}/g);
  if (!m || m.length < 3) return [0, 0, 0];
  return m.slice(0, 3).map((h) => parseInt(h, 16));
}
function colorScale(v, min, max) {
  // Sweet Spot gradient: theme red (low) -> theme green (high).
  if (v == null) return cssVar("--text-mute");
  const t = Math.max(0, Math.min(1, (v - min) / (max - min || 1)));
  const lo = hexToRgb(cssVar("--red"));
  const hi = hexToRgb(cssVar("--green"));
  const r = Math.round(lo[0] + (hi[0] - lo[0]) * t);
  const g = Math.round(lo[1] + (hi[1] - lo[1]) * t);
  const b = Math.round(lo[2] + (hi[2] - lo[2]) * t);
  return `rgb(${r},${g},${b})`;
}

function bubbleSize(mc, mcMin, mcMax) {
  if (mc == null) return 8;
  const t = Math.sqrt((mc - mcMin) / (mcMax - mcMin || 1));
  return 8 + 28 * t;
}

function plotlyLayout(xTitle, yTitle) {
  const p = palette();
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: p.text, family: "-apple-system, Segoe UI, Helvetica, Arial, sans-serif", size: 12 },
    margin: { t: 12, r: 16, b: 48, l: 56 },
    xaxis: { title: xTitle, gridcolor: p.grid, zerolinecolor: p.grid, color: p.dim },
    yaxis: { title: yTitle, gridcolor: p.grid, zerolinecolor: p.grid, color: p.dim },
    showlegend: false,
    hovermode: "closest",
  };
}

function renderSetupScatter(rows) {
  const sweets = rows.map((r) => r.scores.sweet_spot).filter((v) => v != null);
  const sMin = Math.min(...sweets), sMax = Math.max(...sweets);
  const mcs = rows.map((r) => r.fundamentals.mkt_cap_b).filter((v) => v != null);
  const mcMin = Math.min(...mcs), mcMax = Math.max(...mcs);

  const trace = {
    x: rows.map((r) => r.scores.setup),
    y: rows.map((r) => r.scores.spread),
    text: rows.map((r) => r.ticker),
    mode: "markers+text",
    textposition: "top center",
    textfont: { color: palette().text, size: 11 },
    marker: {
      size: rows.map((r) => bubbleSize(r.fundamentals.mkt_cap_b, mcMin, mcMax)),
      color: rows.map((r) => colorScale(r.scores.sweet_spot, sMin, sMax)),
      line: { color: cssVar("--bg"), width: 1 },
      opacity: 0.85,
    },
    hovertemplate:
      "<b>%{text}</b><br>Setup z: %{x:.2f}<br>Spread z: %{y:.2f}<extra></extra>",
  };
  Plotly.newPlot("scatterSetup", [trace], plotlyLayout("Setup z-score", "Spread z-score"),
    { displayModeBar: false, responsive: true });
}

function renderValLevScatter(rows) {
  const sweets = rows.map((r) => r.scores.sweet_spot).filter((v) => v != null);
  const sMin = Math.min(...sweets), sMax = Math.max(...sweets);
  const mcs = rows.map((r) => r.fundamentals.mkt_cap_b).filter((v) => v != null);
  const mcMin = Math.min(...mcs), mcMax = Math.max(...mcs);

  const trace = {
    x: rows.map((r) => r.fundamentals.ev_ebitda),
    y: rows.map((r) => r.fundamentals.debt_ebitda),
    text: rows.map((r) => r.ticker),
    mode: "markers+text",
    textposition: "top center",
    textfont: { color: palette().text, size: 11 },
    marker: {
      size: rows.map((r) => bubbleSize(r.fundamentals.mkt_cap_b, mcMin, mcMax)),
      color: rows.map((r) => colorScale(r.scores.sweet_spot, sMin, sMax)),
      line: { color: cssVar("--bg"), width: 1 },
      opacity: 0.85,
    },
    hovertemplate:
      "<b>%{text}</b><br>EV/EBITDA: %{x:.1f}<br>Debt/EBITDA: %{y:.1f}<extra></extra>",
  };
  Plotly.newPlot("scatterValLev", [trace], plotlyLayout("EV / EBITDA", "Net Debt / EBITDA"),
    { displayModeBar: false, responsive: true });
}

// ---------- Spread time series ----------
function renderSpreadChart() {
  const h = STATE.data.spreads.history;
  const ctx = document.getElementById("spreadChart");
  if (STATE.charts.spread) STATE.charts.spread.destroy();
  STATE.charts.spread = new Chart(ctx, {
    type: "line",
    data: {
      labels: h.map((p) => p.date),
      datasets: [
        { label: "JKM-HH", data: h.map((p) => p.jkm_hh), borderColor: palette().segments.spread, backgroundColor: "transparent", borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        { label: "TTF-HH", data: h.map((p) => p.ttf_hh), borderColor: palette().segments.reset, backgroundColor: "transparent", borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        { label: "JKM-TTF", data: h.map((p) => p.jkm_ttf), borderColor: palette().segments.value, backgroundColor: "transparent", borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      plugins: {
        legend: { labels: { color: palette().text, boxWidth: 12 } },
        tooltip: { mode: "index", intersect: false },
      },
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          ticks: { color: palette().dim, maxTicksLimit: 12, autoSkip: true },
          grid: { color: palette().grid, drawBorder: false },
        },
        y: {
          ticks: { color: palette().dim },
          grid: { color: palette().grid, drawBorder: false },
          title: { display: true, text: "$/MMBtu", color: palette().dim },
        },
      },
    },
  });
}

// ---------- Tables ----------
function flagSpan(flag) {
  if (!flag) return "";
  return `<span class="flag flag-${flag}"></span>`;
}

function signedClass(v) { return v == null ? "" : v >= 0 ? "cell-pos" : "cell-neg"; }

const SCREEN_COLS = [
  { k: "ticker", label: "Ticker", cls: "col-ticker", get: (r) => r.ticker },
  { k: "sweet_spot", label: "Sweet Spot", get: (r) => FMT.z(r.scores.sweet_spot), cls2: (r) => signedClass(r.scores.sweet_spot) },
  { k: "broad_score", label: "Broad", get: (r) => FMT.z(r.scores.broad_score), cls2: (r) => signedClass(r.scores.broad_score) },
  { k: "what_it_does", label: "What It Does", cls: "col-text", get: (r) => r.what_it_does, sortable: false },
  { k: "bucket", label: "Bucket", get: (r) => `<span class="${r.bucket === 'core' ? 'bucket-core' : 'bucket-small'}">${r.bucket}</span>`, sortable: false },
  { k: "spread", label: "Spread", get: (r) => FMT.z(r.scores.spread), cls2: (r) => signedClass(r.scores.spread) },
  { k: "value", label: "Value", get: (r) => FMT.z(r.scores.value), cls2: (r) => signedClass(r.scores.value) },
  { k: "growth", label: "Growth", get: (r) => FMT.z(r.scores.growth), cls2: (r) => signedClass(r.scores.growth) },
  { k: "reset", label: "Reset", get: (r) => FMT.z(r.scores.reset), cls2: (r) => signedClass(r.scores.reset) },
  { k: "not_extended", label: "Not Ext.", get: (r) => FMT.z(r.scores.not_extended), cls2: (r) => signedClass(r.scores.not_extended) },
  { k: "setup", label: "Setup", get: (r) => FMT.z(r.scores.setup), cls2: (r) => signedClass(r.scores.setup) },
  { k: "quality", label: "Quality", get: (r) => FMT.z(r.scores.quality), cls2: (r) => signedClass(r.scores.quality) },
  { sep: true, k: "si_pct_float", label: "SI% Float", get: (r) => FMT.num(r.crowding.si_pct_float, 2) },
  { k: "delta_short_2w", label: "ΔShort 2w", get: (r) => FMT.num(r.crowding.delta_short_2w, 2), cls2: (r) => signedClass(r.crowding.delta_short_2w) },
  { k: "days_to_cover", label: "Days to Cover", get: (r) => FMT.num(r.crowding.days_to_cover, 1) },
  { k: "days_to_earnings", label: "Days to Earnings", get: (r) => `${flagSpan(r.catalyst.earnings_flag)}${FMT.intish(r.catalyst.days_to_earnings)}` },
  { sep: true, k: "ev_ebitda", label: "EV/EBITDA", get: (r) => FMT.num(r.fundamentals.ev_ebitda, 1) },
  { k: "debt_ebitda", label: "Debt/EBITDA", get: (r) => FMT.num(r.fundamentals.debt_ebitda, 1) },
  { k: "fcf_ev", label: "FCF/EV", get: (r) => FMT.pct(r.fundamentals.fcf_ev), cls2: (r) => signedClass(r.fundamentals.fcf_ev) },
  { k: "mkt_cap_b", label: "Mkt Cap", get: (r) => FMT.bil(r.fundamentals.mkt_cap_b) },
];

function renderScreenTable(rows) {
  const tbl = document.getElementById("screenTable");
  const head = "<thead><tr>" + SCREEN_COLS.map((c) => {
    const cls = (c.cls || "") + (c.sep ? " group-sep" : "")
      + (c.k === STATE.sortKey ? (STATE.sortDir === "asc" ? " sort-asc" : " sort-desc") : "");
    const dataAttr = c.sortable === false ? "" : `data-sortkey="${c.k}"`;
    return `<th class="${cls.trim()}" ${dataAttr}>${c.label}</th>`;
  }).join("") + "</tr></thead>";

  const body = "<tbody>" + rows.map((r) => "<tr>" + SCREEN_COLS.map((c) => {
    const cls = [c.cls || "", c.sep ? "group-sep" : "", typeof c.cls2 === "function" ? c.cls2(r) : ""].filter(Boolean).join(" ");
    return `<td class="${cls}">${c.get(r)}</td>`;
  }).join("") + "</tr>").join("") + "</tbody>";

  tbl.innerHTML = head + body;

  tbl.querySelectorAll("th[data-sortkey]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.sortkey;
      if (STATE.sortKey === k) STATE.sortDir = STATE.sortDir === "asc" ? "desc" : "asc";
      else { STATE.sortKey = k; STATE.sortDir = "desc"; }
      document.getElementById("sortSelect").value =
        [...document.getElementById("sortSelect").options].some((o) => o.value === k) ? k : STATE.sortKey;
      renderAll();
    });
  });
}

const WATCHLIST_COLS = [
  { label: "Ticker", cls: "col-ticker", get: (r) => r.ticker },
  { label: "What It Does", cls: "col-text", get: (r) => r.what_it_does },
  { label: "Mkt Cap", get: (r) => FMT.bil(r.fundamentals.mkt_cap_b) },
  { label: "Debt/EBITDA", get: (r) => FMT.num(r.fundamentals.debt_ebitda, 1) },
  { label: "EV/EBITDA", get: (r) => FMT.num(r.fundamentals.ev_ebitda, 1) },
  { label: "FCF/EV", get: (r) => FMT.pct(r.fundamentals.fcf_ev), cls2: (r) => signedClass(r.fundamentals.fcf_ev) },
  { label: "Spread", get: (r) => FMT.z(r.scores.spread), cls2: (r) => signedClass(r.scores.spread) },
  { label: "Setup", get: (r) => FMT.z(r.scores.setup), cls2: (r) => signedClass(r.scores.setup) },
  { label: "SI% Float", get: (r) => FMT.num(r.crowding.si_pct_float, 2) },
  { label: "Days to Cover", get: (r) => FMT.num(r.crowding.days_to_cover, 1) },
  { label: "Earnings", get: (r) => `${flagSpan(r.catalyst.earnings_flag)}${FMT.intish(r.catalyst.days_to_earnings)}` },
];

function renderWatchlist() {
  const rows = STATE.data.tickers.filter((t) => t.bucket === "small/levered")
    .sort((a, b) => (b.scores.sweet_spot ?? -Infinity) - (a.scores.sweet_spot ?? -Infinity));
  const tbl = document.getElementById("watchlistTable");
  const head = "<thead><tr>" + WATCHLIST_COLS.map((c) => `<th class="${c.cls || ''}">${c.label}</th>`).join("") + "</tr></thead>";
  const body = "<tbody>" + rows.map((r) => "<tr>" + WATCHLIST_COLS.map((c) => {
    const cls = [c.cls || "", typeof c.cls2 === "function" ? c.cls2(r) : ""].filter(Boolean).join(" ");
    return `<td class="${cls}">${c.get(r)}</td>`;
  }).join("") + "</tr>").join("") + "</tbody>";
  tbl.innerHTML = head + body;
}

// ---------- Column dictionary ----------
const DICTIONARY = [
  ["Ticker", "Stock symbol (yfinance form).", "Static config.", "n/a", "n/a"],
  ["Sweet Spot", "Composite z-score: 0.30 Value + 0.20 Growth + 0.20 Spread + 0.20 Reset + 0.10 NotExt.", "Cross-sectional weighted z-scores.", "Best risk/reward profile in universe.", "Worst risk/reward in universe."],
  ["Broad", "Same as Sweet Spot plus Quality and Setup with smaller weights.", "Cross-sectional.", "Quality-aware sweet spot.", "Weak across multiple lenses."],
  ["What It Does", "Short business description for context.", "Static config.", "n/a", "n/a"],
  ["Bucket", "Core (large/liquid) vs small/levered.", "Static config.", "n/a", "n/a"],
  ["Spread", "Cross-sectional z of (JKM-HH β + TTF-HH β − 0.5·Brent β) from 180-day OLS.", "Daily-return regression on macro spreads.", "High torque to widening LNG spreads.", "Decoupled from spread cycle."],
  ["Value", "Cross-sec z of equal-weighted EV/EBITDA, P/S, Debt/EBITDA (inverted) + FCF/EV.", "Yahoo fundamentals; negative EBITDA flagged, not treated as cheap.", "Cheaper / less levered.", "Expensive or stretched balance sheet."],
  ["Growth", "Cross-sec z of forward revenue growth (clipped ±3σ).", "Yahoo growth estimates.", "Faster expected revenue growth.", "Decline expected."],
  ["Reset", "Inverted distance to 1y and 5y highs (mean) → cross-sec z.", "Price history.", "More room back to highs.", "Already at/near highs."],
  ["Not Ext.", "Inverted blend of YTD return + distance from 1y low.", "Price history.", "Not stretched, room to run.", "Crowded / extended."],
  ["Setup", "Cross-sec z of (Reset z + NotExt z) average.", "Derived.", "Best technical setup.", "Worst technical setup."],
  ["Quality", "Cross-sec z of EBITDA margin + ROIC (or ROE fallback).", "Yahoo fundamentals.", "Cleaner profitability.", "Weak profitability."],
  ["SI% Float", "Latest short interest as % of float.", "Bloomberg SHORT_INT_RATIO.", "Heavily shorted.", "Not crowded."],
  ["ΔShort 2w", "Change in SI%Float vs ~14 days ago.", "Bloomberg SHORT_INT_RATIO bdh.", "Shorts piling on.", "Shorts covering."],
  ["Days to Cover", "Short interest ÷ avg daily volume.", "Bloomberg DAYS_TO_COVER.", "Slow to cover, more squeeze risk.", "Easy to cover."],
  ["Days to Earnings", "Days until next reported earnings; flag green > 30, yellow 10-30, red < 10.", "Bloomberg NEXT_ANNOUNCEMENT_DT.", "Plenty of room before binary event.", "Earnings imminent."],
  ["EV/EBITDA", "Trailing enterprise value / EBITDA.", "Yahoo fundamentals.", "Expensive vs peers.", "Cheap vs peers."],
  ["Debt/EBITDA", "Net debt / EBITDA.", "Yahoo fundamentals.", "Highly levered.", "Clean balance sheet."],
  ["FCF/EV", "Free cash flow yield on enterprise value.", "(OCF − Capex) / EV.", "Strong cash conversion.", "Burning cash."],
  ["Mkt Cap", "Market capitalization, $B.", "Yahoo fundamentals.", "Larger / more liquid.", "Smaller / less liquid."],
];

function renderDictionary() {
  const head = "<thead><tr><th>Column</th><th>Meaning</th><th>How It Is Built</th><th>High Means</th><th>Low Means</th></tr></thead>";
  const body = "<tbody>" + DICTIONARY.map((r) => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td></tr>`).join("") + "</tbody>";
  document.getElementById("dictionaryTable").innerHTML = head + body;
}

// ---------- Controls ----------
function bindControls() {
  document.getElementById("searchInput").addEventListener("input", (e) => {
    STATE.filter = e.target.value;
    renderAll();
  });
  document.getElementById("sortSelect").addEventListener("change", (e) => {
    STATE.sortKey = e.target.value;
    STATE.sortDir = "desc";
    renderAll();
  });
  document.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".toggle-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      STATE.topMode = btn.dataset.mode;
      renderAll();
    });
  });
  document.getElementById("themeToggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "light";
    const next = cur === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("chokepoint-theme", next);
    // Charts cache colors at construction; re-render so they pick up the new palette.
    renderAll();
  });
}

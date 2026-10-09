/* Macro dashboard front end: reads data/data.json (built by fetch_data.py) */
const COLORS = window.COLORS_BASE = ['#4f8cff', '#f5b642', '#3ecf8e', '#ff6b6b', '#b18cff', '#2ad4d9', '#ff9f43', '#e86fd0', '#9bd36b', '#c9ced8'];
const CT = 'America/Chicago';
const EMBEDDED = window.__MACRO_DATA__ || null; // set by export_html.py (offline snapshot)
let DATA = null, RANGE_YEARS = 5, CHARTS = [], CURVE_CHART = null, ALLOC = null, ALLOC_DEFS = [];

// s: series ids; scale: multiply values (100 => bp); type: 'bar' for bars; y2: ids on right axis
const DEFS = [
  { sec: 'rates', title: 'Policy & funding rates (%)', s: ['DFF', 'SOFR', 'DGS3MO'] },
  { sec: 'rates', title: 'Treasury yields (%)', s: ['DGS2', 'DGS5', 'DGS10', 'DGS30'] },
  { sec: 'rates', title: 'Curve slope (bp): 2s10s and 3m10y', s: ['T10Y2Y', 'T10Y3M'], scale: 100, unit: 'bp', zero: true },
  { sec: 'positioning', title: 'KRE short interest: notional ($bn) vs % of shares outstanding', s: ['KRE_SI_NOTIONAL', 'KRE_SI_PCT_SO'], y2: ['KRE_SI_PCT_SO'], labels: ['Notional SI, $bn (left)', 'SI % of shares outstanding (right)'], fmt: ['bn2', 'pct'], points: true, note: 'Notional = FINRA SI shares × KRE close on the settlement date (Yahoo). Shares outstanding: State Street.' },
  { sec: 'positioning', title: 'KRE short interest (M shares) vs days to cover', s: ['KRE_SI_SHARES', 'KRE_DTC'], scales: [1e-6, 1], y2: ['KRE_DTC'], labels: ['SI, M shares (left)', 'Days to cover (right)'], fmt: ['M', 'days'], points: true, note: 'FINRA consolidated short interest, twice monthly; days to cover = SI / average daily volume (FINRA).' },
  { sec: 'credit', title: 'High-yield OAS (bp)', s: ['BAMLH0A0HYM2'], scale: 100, unit: 'bp', note: 'ICE BofA indices: FRED provides ~3 years of history only.' },
  { sec: 'credit', title: 'Investment-grade & BBB OAS (bp)', s: ['BAMLC0A0CM', 'BAMLC0A4CBBB'], scale: 100, unit: 'bp', note: 'ICE BofA indices: FRED provides ~3 years of history only.' },
  { sec: 'credit', title: "Moody's Baa & Aaa yield minus 10Y (bp) — long-history proxy", s: ['BAA10Y', 'AAA10Y'], scale: 100, unit: 'bp' },
  { sec: 'quality', title: 'Delinquency rates (%)', s: ['DRALACBS', 'DRCCLACBS', 'DRCRELEXFACBS'], labels: ['All loans', 'Credit cards', 'CRE (ex farmland)'] },
  { sec: 'quality', title: 'Net charge-off rate, all loans (%)', s: ['CORALACBS'] },
  { sec: 'quality', title: 'SLOOS: net % of banks tightening C&I standards (large & mid firms)', s: ['DRTSCILM'], zero: true, labels: ['Net % tightening'] },
  { sec: 'housing', title: '30Y mortgage rate vs 10Y Treasury (%)', s: ['MORTGAGE30US', 'DGS10'], labels: ['30Y mortgage (PMMS)', '10Y Treasury'] },
  { sec: 'housing', title: 'Mortgage rate minus 10Y Treasury (bp)', s: ['MORT_SPREAD'], scale: 100, unit: 'bp', labels: ['30Y mortgage – 10Y'] },
  { sec: 'housing', title: 'Housing starts (SAAR, thousands)', s: ['HOUST'], labels: ['Housing starts'] },
  { sec: 'labor', title: 'Unemployment rate (%)', s: ['UNRATE'] },
  { sec: 'labor', title: 'Nonfarm payrolls, monthly change (k)', s: ['PAYEMS_CHG'], type: 'bar', zero: true, labels: ['Payrolls Δ (k)'] },
  { sec: 'labor', title: 'Inflation YoY (%): CPI & core PCE', s: ['CPI_YOY', 'COREPCE_YOY'], labels: ['CPI-U', 'Core PCE'] },
  { sec: 'labor', title: 'Real GDP growth (%)', s: ['GDP_QOQ', 'GDP_YOY'], types: ['bar', 'line'], zero: true, labels: ['QoQ SAAR', 'YoY'] },
  { sec: 'labor', title: 'Initial jobless claims (k, SA)', span2: true, s: ['ICSA'], scale: 0.001, unit: 'k', labels: ['Initial claims'] },
  { sec: 'stress', title: 'VIX', s: ['VIXCLS'], labels: ['VIX'] },
  { sec: 'stress', title: 'MOVE index (ICE BofA Treasury implied volatility)', s: ['MOVE'], labels: ['MOVE'], note: 'Source: Yahoo Finance chart API (^MOVE), daily closes; not from FRED.' },
  { sec: 'stress', title: 'MOVE vs VIX', s: ['MOVE', 'VIXCLS'], y2: ['VIXCLS'], labels: ['MOVE (left)', 'VIX (right)'] },
  { sec: 'stress', title: 'VIX vs HY OAS', s: ['VIXCLS', 'BAMLH0A0HYM2'], scales: [1, 100], y2: ['BAMLH0A0HYM2'], labels: ['VIX (left)', 'HY OAS, bp (right)'] },
];

Chart.defaults.color = '#8d9ab3';
Chart.defaults.borderColor = '#26324a';
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 11;

const fmtNum = (v, d = 2) => v == null || isNaN(v) ? '–' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtDate = s => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }); };
const fmtPeriod = (s, freq) => {
  const [y, m] = s.split('-').map(Number);
  if (freq === 'Quarterly') return `Q${Math.floor((m - 1) / 3) + 1} ${y}`;
  if (freq === 'Monthly') return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
  return fmtDate(s);
};
const sig = v => (v > 0 ? '+' : v < 0 ? '−' : '±');

function fmtValue(fmt, v) {
  switch (fmt) {
    case 'pct2': return fmtNum(v, 2) + '%';
    case 'pct1': return fmtNum(v, 1) + '%';
    case 'bp': return fmtNum(v * 100, 0) + ' bp';
    case 'num2': return fmtNum(v, 2);
    case 'tn': return '$' + fmtNum(v / 1000, 2) + 'T';
    case 'bn2': return '$' + fmtNum(v, 2) + 'bn';
    case 'k': return fmtNum(v / 1000, 0) + 'k';
    default: return fmtNum(v, 2);
  }
}
function fmtLatest(code, v) {
  switch (code) {
    case 'pct': return fmtNum(v, 2) + '%';
    case 'pp': return (v > 0 ? '+' : '') + fmtNum(v, 2) + ' pp';
    case 'bp': return fmtNum(v, 0) + ' bp';
    case 'bn2': return '$' + fmtNum(v, 2) + 'bn';
    case 'T': return '$' + fmtNum(v, 2) + 'T';
    case 'M': return fmtNum(v, 2) + 'M';
    case 'days': return fmtNum(v, 2) + ' days';
    default: return fmtNum(v, 2);
  }
}

function fmtChange(unit, c) {
  if (!c || c.value == null) return '–';
  const v = c.value;
  if (unit === 'bp') return sig(v) + fmtNum(Math.abs(v), 0) + ' bp';
  if (unit === 'pct') return sig(v) + fmtNum(Math.abs(v), Math.abs(v) < 10 ? 2 : 1) + '%';
  if (unit === 'k') return sig(v) + fmtNum(Math.abs(v), 0) + 'k';
  if (unit === 'days') return sig(v) + fmtNum(Math.abs(v), 2) + 'd';
  return sig(v) + fmtNum(Math.abs(v), 2);
}

function renderTiles() {
  const el = document.getElementById('tiles');
  el.innerHTML = DATA.tiles.map(t => {
    if (t.missing) return `<div class="tile"><div class="lbl">${t.label}</div><div class="val na">n/a</div><div class="asof">series unavailable</div></div>`;
    const hs = t.hs || ['1w', '1m', '1y'];
    const chips = hs.map(k => {
      const c = t.chg[k];
      let cls = 'na';
      if (c && c.value != null && Math.abs(c.value) > 1e-9) cls = t.polarity === 0 ? 'neu' : ((c.value > 0) === (t.polarity > 0) ? 'good' : 'bad');
      const prior = k === '1w' && t.freq === 'Semi-monthly';
      const tip = c ? `vs ${prior ? 'prior report, ' : ''}${fmtPeriod(c.vs_date, t.freq)}: ${fmtValue(t.fmt, c.vs_value)}` : 'no comparable observation';
      return `<div title="${tip}"><span>${prior ? 'PRIOR' : k.toUpperCase()}</span><b class="${cls}">${fmtChange(t.unit, c)}</b></div>`;
    }).join('');
    return `<div class="tile" title="FRED: ${t.key}">
      <div class="lbl"><span>${t.label}</span>${t.stale ? '<span class="stale">STALE</span>' : ''}</div>
      <div class="val">${fmtValue(t.fmt, t.latest)}</div>
      <div class="asof">as of ${fmtPeriod(t.asof, t.freq)} · ${t.freq}</div>
      ${t.extra ? `<div class="extra">${t.extra}</div>` : ''}
      <div class="chg" style="grid-template-columns:repeat(${hs.length},1fr)">${chips}</div></div>`;
  }).join('');
}

function moveClass(r, c) {
  if (!c || c.value == null || Math.abs(c.value) < 1e-9) return 'na';
  if (r.polarity === 0) return 'neu';
  return (c.value > 0) === (r.polarity > 0) ? 'good' : 'bad';
}

function renderSummary() {
  const el = document.getElementById('summaryTable');
  const rows = DATA.summary || [];
  if (!rows.length) { el.innerHTML = '<div class="note">Summary unavailable.</div>'; return; }
  const H = ['1w', '1m', '3m', '1y'];
  let html = `<table class="summary"><thead><tr><th>Series</th><th>Units</th><th class="r">Latest</th><th>As of</th><th>Chg in</th>${H.map(h => `<th class="r">${h.toUpperCase()}</th>`).join('')}</tr></thead><tbody>`;
  let sec = null;
  for (const r of rows) {
    if (r.section !== sec) { sec = r.section; html += `<tr class="grp"><td colspan="9">${sec}</td></tr>`; }
    if (r.missing) { html += `<tr><td>${r.name} <span class="sid">${r.id}</span></td><td colspan="8" class="na">series unavailable</td></tr>`; continue; }
    const cells = H.map(h => { const c = r.chg[h]; const tip = c ? `vs ${c.basis ? 'prior report, ' : ''}${fmtPeriod(c.vs_date, r.freq)} (${fmtNum(c.vs_value, 2)})` : (h === '1w' || h === '1m' ? 'not meaningful at this frequency' : 'no prior observation');
      return `<td class="r ${moveClass(r, c)}" title="${tip}">${r.chg_fmt[h]}</td>`; }).join('');
    const src = r.source && r.source !== 'FRED' && r.source !== 'FRED (derived)' ? ` <span class="src">${r.source.split(' (')[0]}</span>` : '';
    html += `<tr><td>${r.name} <span class="sid">${r.id}</span>${src}${r.stale ? ' <span class="stale">STALE</span>' : ''}</td><td>${r.units}</td><td class="r b">${r.latest_fmt}</td><td>${fmtPeriod(r.asof, r.freq)}</td><td class="cu">${r.change_unit}</td>${cells}</tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

function cutoffMs() {
  if (!RANGE_YEARS) return -Infinity;
  const d = new Date(); d.setFullYear(d.getFullYear() - RANGE_YEARS); return d.getTime();
}
const toMs = s => { const [y, m, d] = s.split('-').map(Number); return Date.UTC(y, m - 1, d, 12); };

function seriesPoints(id, scale) {
  const s = DATA.series[id];
  if (!s) return [];
  return s.data.map(([d, v]) => ({ x: toMs(d), y: +(v * scale).toFixed(4) }));
}

function makeCard(def, idx) {
  const grid = document.querySelector(`.grid[data-sec="${def.sec}"]`);
  const card = document.createElement('div');
  card.className = 'card' + (def.wide ? ' wide' : '') + (def.span2 ? ' span2' : '');
  card.innerHTML = `<h3>${def.title}</h3><div class="latest"></div><div class="cv"><canvas></canvas></div>${def.note ? `<div class="note">${def.note}</div>` : ''}`;
  grid.appendChild(card);
  return card;
}

function buildCharts() {
  CHARTS.forEach(c => c.chart.destroy()); CHARTS = [];
  document.querySelectorAll('.grid').forEach(g => g.innerHTML = '');
  buildCurveCard();
  DEFS.concat(ALLOC_DEFS).forEach((def, i) => {
    const card = makeCard(def, i);
    const COLORS = def.colors || window.COLORS_BASE;
    const available = def.s.filter(id => DATA.series[id]);
    const full = def.s.map((id, j) => {
      const scale = def.scales ? def.scales[j] : (def.scale ?? 1);
      return { id, scale, pts: seriesPoints(id, scale) };
    });
    // latest-values line
    card.querySelector('.latest').innerHTML = full.map((f, j) => {
      const s = DATA.series[f.id];
      const label = def.labels ? def.labels[j] : (s ? s.title : f.id);
      if (!s) return `<i style="background:${COLORS[j]}"></i>${label}: <b>unavailable</b>`;
      if (def.noLatest) return `<i style="background:${COLORS[j]}"></i>${label}`;
      const last = s.data[s.data.length - 1];
      const unit = def.scales ? (j === 1 ? ' bp' : '') : (def.unit === 'bp' ? ' bp' : def.unit === '$T' ? 'T' : def.unit === 'k' ? 'k' : (s.units === '%' ? '%' : ''));
      const pre = (!def.scales && def.unit === '$T') ? '$' : '';
      const dec = (def.unit === 'bp' || (def.scales && j === 1) || def.unit === 'k' || s.units === 'k units' || s.units === 'k') ? 0 : 2;
      const stale = s.stale ? ' <span class="stale">STALE</span>' : '';
      const shown = def.fmt ? fmtLatest(def.fmt[j], last[1] * f.scale) : `${pre}${fmtNum(last[1] * f.scale, dec)}${unit}`;
      return `<i style="background:${COLORS[j]}"></i>${label}: <b>${shown}</b> (${fmtPeriod(last[0], s.freq)})${stale}`;
    }).join('');
    const datasets = full.map((f, j) => {
      const type = def.types ? def.types[j] : (def.type || 'line');
      return {
        type, label: def.labels ? def.labels[j] : (DATA.series[f.id]?.title || f.id), _full: f.pts,
        data: f.pts, borderColor: COLORS[j], backgroundColor: type === 'bar' ? COLORS[j] + 'b0' : (def.fill ? COLORS[j] + '99' : COLORS[j]),
        borderWidth: def.fill ? 1 : 1.6, pointRadius: def.points ? 1.8 : 0, pointHoverRadius: 3, tension: 0, spanGaps: true,
        fill: def.fill ? (j === 0 ? 'origin' : '-1') : false,
        stack: def.stacked ? (type === 'line' && !def.fill ? 'total' : 'parts') : undefined,
        yAxisID: def.y2 && def.y2.includes(f.id) ? 'y2' : 'y', order: type === 'bar' ? 2 : 1,
        barPercentage: 1, categoryPercentage: 1,
      };
    });
    const scales = {
      x: { type: 'time', time: { tooltipFormat: 'MMM d, yyyy' }, grid: { display: false }, ticks: { maxTicksLimit: 8 } },
      y: { position: 'left', grid: { color: (ctx) => def.zero && ctx.tick.value === 0 ? '#5a6a8a' : '#1f2a3e' }, ticks: { maxTicksLimit: 7 } },
    };
    if (def.y2) scales.y2 = { position: 'right', grid: { display: false }, ticks: { maxTicksLimit: 7 } };
    if (def.stacked) { scales.y.stacked = true; scales.x.stacked = true; if (def.fill) { scales.y.min = 0; scales.y.max = 100; } }
    const chart = new Chart(card.querySelector('canvas'), {
      data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, parsing: false, normalized: true,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        plugins: {
          legend: { display: false },
          decimation: { enabled: !def.stacked, algorithm: 'lttb', samples: 600 },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtNum(c.parsed.y, Math.abs(c.parsed.y) >= 100 ? 0 : 2)}` } },
        },
        scales,
      },
    });
    CHARTS.push({ chart, def });
  });
  buildKreTable();
  applyRange();
}

function buildKreTable() {
  const grid = document.querySelector('.grid[data-sec="positioning"]');
  const reps = (DATA.kre_si_reports || []).slice(-10).reverse();
  if (!grid || !reps.length) return;
  const card = document.createElement('div');
  card.className = 'card wide';
  const n = (v, d) => v == null ? '–' : fmtNum(v, d);
  card.innerHTML = `<h3>KRE short interest, recent FINRA reports</h3>
    <table class="summary kre"><thead><tr><th>Settlement date</th><th class="r">SI shares</th><th class="r">Chg vs prior</th><th class="r">KRE close (date)</th><th class="r">Notional SI</th><th class="r">Avg daily vol</th><th class="r">Days to cover</th><th class="r">Shares out</th><th class="r">SI % shs out</th></tr></thead><tbody>` +
    reps.map(r => `<tr><td>${fmtDate(r.date)}</td><td class="r b">${n(r.si_shares / 1e6, 2)}M</td><td class="r ${r.chg_pct > 0 ? 'neu' : 'neu'}">${r.chg_pct == null ? '–' : sig(r.chg_pct) + fmtNum(Math.abs(r.chg_pct), 2) + '%'}</td><td class="r">${r.price == null ? '–' : '$' + n(r.price, 2) + (r.price_date !== r.date ? ` (${r.price_date})` : '')}</td><td class="r b">${r.notional_bn == null ? '–' : '$' + n(r.notional_bn, 2) + 'bn'}</td><td class="r">${r.adv == null ? '–' : n(r.adv / 1e6, 2) + 'M'}</td><td class="r">${n(r.dtc, 2)}</td><td class="r">${r.shares_out == null ? '–' : n(r.shares_out / 1e6, 2) + 'M'}</td><td class="r">${r.pct_so == null ? '–' : n(r.pct_so, 1) + '%'}</td></tr>`).join('') +
    '</tbody></table><div class="note">Sources: FINRA consolidated short interest (SI, avg daily volume, days to cover); KRE close: Yahoo Finance; shares outstanding: State Street. SI above 100% of shares outstanding is possible for ETFs (shares lent and re-lent; creations settle later).</div>';
  grid.appendChild(card);
}

function buildCurveCard() {
  const grid = document.querySelector('.grid[data-sec="rates"]');
  const card = document.createElement('div');
  card.className = 'card';
  const c = DATA.curve;
  if (!c) { card.innerHTML = '<h3>Treasury yield curve</h3><div class="latest">unavailable</div>'; grid.appendChild(card); return; }
  card.innerHTML = `<h3>Treasury yield curve (%) — latest vs 1M and 1Y ago</h3><div class="latest">${c.curves.map((cv, j) => `<i style="background:${COLORS[j]}"></i>${cv.label}: <b>${cv.date ? fmtDate(cv.date) : '–'}</b>`).join('')}</div><div class="cv"><canvas></canvas></div>`;
  grid.appendChild(card);
  if (CURVE_CHART) CURVE_CHART.destroy();
  CURVE_CHART = new Chart(card.querySelector('canvas'), {
    type: 'line',
    data: { labels: c.tenors, datasets: c.curves.map((cv, j) => ({ label: `${cv.label} (${cv.date ? fmtDate(cv.date) : '–'})`, data: cv.values, borderColor: COLORS[j], backgroundColor: COLORS[j], borderWidth: j === 0 ? 2.4 : 1.6, borderDash: j === 0 ? [] : [5, 4], pointRadius: 3, tension: 0.25 })) },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => `${x.dataset.label}: ${fmtNum(x.parsed.y, 2)}%` } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: '#1f2a3e' } } },
    },
  });
}

function applyRange() {
  const cut = cutoffMs();
  CHARTS.forEach(({ chart, def }) => {
    chart.data.datasets.forEach(ds => {
      const pts = ds._full.filter(p => p.x >= cut);
      if (def.rebase && pts.length) { const b = pts[0].y; ds.data = pts.map(p => ({ x: p.x, y: +(100 * p.y / b).toFixed(3) })); }
      else ds.data = pts;
    });
    const first = Math.min(...chart.data.datasets.map(ds => ds._full.length ? ds._full[0].x : Infinity));
    chart.options.scales.x.min = isFinite(cut) ? Math.max(cut, first) : undefined;
    chart.options.scales.x.max = Date.now();
    chart.update('none');
  });
}

function renderMeta() {
  const gen = new Date(DATA.generated_utc);
  document.getElementById('updated').textContent = gen.toLocaleString('en-US', { timeZone: CT, month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }) + ' CT';
  const ok = DATA.status.filter(s => s.ok).length;
  const failed = DATA.status.filter(s => !s.ok);
  document.getElementById('okcount').innerHTML = `${ok}/${DATA.status.length} series OK` + (failed.length ? ` · <span class="bad">${failed.length} failed: ${failed.map(f => f.id).join(', ')}</span>` : '');
  document.getElementById('statusTable').innerHTML = `<table class="status"><tr><th>ID</th><th>Series</th><th>Source</th><th>Freq</th><th>Units</th><th>First obs</th><th>Last obs</th><th>Obs</th><th>Blank obs</th><th>Largest gap</th><th>Status</th></tr>` +
    DATA.status.map(s => { const m = DATA.series[s.id] || {};
      const gap = s.max_gap_days != null ? `${s.max_gap_days}d${s.gap_flag ? ` <span class="stale">GAP after ${s.max_gap_after}</span>` : ''}` : '–';
      return `<tr><td>${s.id}</td><td>${m.title || ''}</td><td>${s.source || 'FRED'}</td><td>${m.freq || ''}</td><td>${m.units || ''}</td><td>${s.first || '–'}</td><td>${s.last || '–'}</td><td>${s.rows || '–'}</td><td>${s.missing ?? '–'}</td><td>${gap}</td><td>${s.ok ? '<span class="good">OK</span>' : `<span class="bad">FAILED</span>${s.stale_kept ? ' (showing previous data, STALE)' : ''}`}</td></tr>`; }).join('') + '</table>' +
    '<div class="note">Blank obs = dates the source published with no value (mostly market holidays), dropped. Largest gap = longest spacing between consecutive observations; flagged when above normal holiday spacing for the frequency.</div>';
}

const ALLOC_FREQ = { AL_RS_: 'Daily', AL_PAIR_: 'Daily', AL_DTC_: 'Semi-monthly', AL_BETA_: 'Weekly' };
function mergeAlloc(A) {
  ALLOC = A; ALLOC_DEFS = [];
  if (!A || !window.ALLOC_PANEL) return;
  Object.entries(A.series || {}).forEach(([id, data]) => {
    const pre = Object.keys(ALLOC_FREQ).find(k => id.startsWith(k));
    DATA.series[id] = { data, title: id, freq: ALLOC_FREQ[pre] || 'Daily', units: '' };
  });
  try { ALLOC_DEFS = window.ALLOC_PANEL.defs(A); } catch (e) { console.warn('alloc defs', e); ALLOC_DEFS = []; }
}
function renderAlloc() {
  const meta = document.getElementById('alMeta');
  if (!meta) return;
  if (!ALLOC || !window.ALLOC_PANEL) { meta.innerHTML = '<span class="bad">Allocation data (data/alloc.json) unavailable. Run fetch_alloc.py.</span>'; return; }
  window.ALLOC_PANEL.render(ALLOC);
}
async function fetchAlloc() {
  try { const r = await fetch('data/alloc.json?t=' + Date.now(), { cache: 'no-store' }); return r.ok ? await r.json() : null; } catch (e) { return null; }
}
function renderAll() { renderMeta(); renderTiles(); renderSummary(); buildCharts(); renderAlloc(); }

async function load(force) {
  if (EMBEDDED) {
    DATA = EMBEDDED; mergeAlloc(window.__ALLOC_DATA__ || null);
    renderAll();
    document.body.dataset.ready = '1';
    return true;
  }
  const r = await fetch('data/data.json?t=' + Date.now(), { cache: 'no-store' });
  const j = await r.json();
  if (!force && DATA && j.generated_utc === DATA.generated_utc) return false;
  DATA = j; mergeAlloc(await fetchAlloc());
  renderAll();
  document.body.dataset.ready = '1';
  return true;
}

document.getElementById('range').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  document.querySelectorAll('#range button').forEach(x => x.classList.toggle('on', x === b));
  RANGE_YEARS = +b.dataset.r; applyRange();
});

document.getElementById('refresh')?.addEventListener('click', async (e) => {
  const btn = e.currentTarget; btn.disabled = true; btn.textContent = 'Refreshing…';
  try {
    const r = await fetch('api/refresh', { method: 'POST' });
    if (r.status === 429) {
      const j = await r.json();
      btn.textContent = `Refresh limited: try again in ${Math.ceil(j.retry_after_s / 60)} min`;
      await load(false);
      await new Promise(res => setTimeout(res, 3500));
    } else {
      for (let i = 0; i < 120; i++) {
        await new Promise(res => setTimeout(res, 2000));
        const s = await (await fetch('api/status', { cache: 'no-store' })).json();
        if (!s.running) break;
      }
      await load(true);
    }
  } catch (err) { alert('Refresh failed: ' + err); }
  btn.disabled = false; btn.textContent = '↻ Refresh data';
});

if (EMBEDDED) {
  // offline snapshot: no refresh button, no network calls
  document.getElementById('refresh')?.remove();
  document.getElementById('updLabel').textContent = 'Snapshot as of';
  document.getElementById('updated').classList.add('snap');
} else {
  setInterval(() => load(false).catch(() => {}), 10 * 60 * 1000); // pick up scheduled refreshes
}
load(true);

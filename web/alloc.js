/* Financials Time Allocation panel. Loaded before app.js; app.js calls ALLOC_PANEL.defs()/render(). */
(function () {
  const PAL = ['#4f8cff', '#f5b642', '#3ecf8e', '#ff6b6b', '#b18cff', '#2ad4d9', '#ff9f43', '#e86fd0', '#9bd36b', '#c9ced8', '#ffd166', '#5ec2ff', '#ff7aa2', '#a0a7ff'];
  const SHORT = { B_CONSFIN: 'Cons. fin', B_SMINS: 'Sm/mid ins', B_AMBRK: 'AM/brokers' };
  const short = id => SHORT[id] || id;
  const BANKS = ['KRE', 'IAT', 'KBE', 'KBWB', 'PSCF', 'RSPF'];
  let extraCharts = [];

  const n = (v, d = 2) => (v == null || isNaN(v)) ? '–' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sg = (v, d = 1, suf = '') => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '±') + n(Math.abs(v), d) + suf;
  const cls = v => v == null ? 'na' : v > 0 ? 'good' : v < 0 ? 'bad' : 'na';
  const heat = (v, scale) => { if (v == null) return ''; const a = Math.min(1, Math.abs(v) / scale) * 0.55; return `background:${v > 0 ? `rgba(62,207,142,${a})` : `rgba(255,107,107,${a})`}`; };
  const heatAbs = (v, scale) => { if (v == null) return ''; const a = Math.min(1, Math.abs(v) / scale) * 0.6; return `background:rgba(245,182,66,${a})`; };
  const ord = x => x == null ? '–' : `${Math.round(x)}${['th', 'st', 'nd', 'rd'][(Math.round(x) % 100 > 10 && Math.round(x) % 100 < 14) ? 0 : Math.min(Math.round(x) % 10, 4) % 4] || 'th'}`;

  function defs(A) {
    const ids = A.groups.map(g => g.id);
    const banks = ids.filter(i => BANKS.includes(i));
    const other = ids.filter(i => !BANKS.includes(i));
    const lab = i => short(i);
    const d = [
      { sec: 'alloc-perf', title: 'Relative strength vs XLF: banks (total return ratio, rebased to 100 at range start)', s: banks.map(i => 'AL_RS_' + i), labels: banks.map(lab), rebase: true, noLatest: true, colors: PAL },
      { sec: 'alloc-perf', title: 'Relative strength vs XLF: insurance, brokers, mREITs, consumer finance (rebased)', s: other.map(i => 'AL_RS_' + i), labels: other.map(lab), rebase: true, noLatest: true, colors: PAL.slice(6).concat(PAL) },
      { sec: 'alloc-size', title: 'Within financials: cumulative spread return (ratio of total-return indices, rebased)', s: A.pairs.filter(p => p.scope === 'fin').map(p => 'AL_PAIR_' + p.id), labels: A.pairs.filter(p => p.scope === 'fin').map(p => p.label.split('(')[1].replace(')', '')), rebase: true, noLatest: true },
      { sec: 'alloc-size', title: 'Broad market size & style, and financials vs market (rebased)', s: A.pairs.filter(p => p.scope === 'mkt').map(p => 'AL_PAIR_' + p.id), labels: A.pairs.filter(p => p.scope === 'mkt').map(p => p.label.split('(')[1].replace(')', '')), rebase: true, noLatest: true },
      { sec: 'alloc-pos', title: 'Days to cover (SI ÷ FINRA avg daily volume), bank ETFs + XLF', s: ['KRE', 'KBE', 'KBWB', 'IAT', 'XLF'].filter(i => A.series['AL_DTC_' + i]).map(i => 'AL_DTC_' + i), labels: ['KRE', 'KBE', 'KBWB', 'IAT', 'XLF'].filter(i => A.series['AL_DTC_' + i]) },
      { sec: 'alloc-pos', title: 'Days to cover: baskets (equal-wt avg of members), insurance & mREIT ETFs', s: ['B_CONSFIN', 'B_SMINS', 'B_AMBRK', 'KIE', 'REM'].filter(i => A.series['AL_DTC_' + i]).map(i => 'AL_DTC_' + i), labels: ['B_CONSFIN', 'B_SMINS', 'B_AMBRK', 'KIE', 'REM'].filter(i => A.series['AL_DTC_' + i]).map(lab) },
      { sec: 'alloc-macro', title: 'Rolling 6M beta to 10Y yield (% return per +10 bp), weekly samples', s: ['KRE', 'KBWB', 'KIE', 'IAI', 'REM', 'B_CONSFIN'].map(i => 'AL_BETA_DGS10_' + i), labels: ['KRE', 'KBWB', 'KIE', 'IAI', 'REM', 'Cons. fin'], zero: true },
      { sec: 'alloc-macro', title: 'Rolling 6M beta to HY OAS (% return per +10 bp), weekly samples', s: ['KRE', 'KBWB', 'KIE', 'IAI', 'REM', 'B_CONSFIN'].map(i => 'AL_BETA_BAMLH0A0HYM2_' + i), labels: ['KRE', 'KBWB', 'KIE', 'IAI', 'REM', 'Cons. fin'], zero: true, note: 'HY OAS history on FRED starts Oct 2023, so this beta begins Apr 2024.' },
    ];
    return d.filter(x => x.s.length);
  }

  function staleSummary(list) {
    const by = {};
    list.forEach(x => { const m = x.match(/^(\S+) (.+)$/); const k = m ? m[2] : x; (by[k] = by[k] || []).push(m ? m[1] : ''); });
    return Object.entries(by).map(([k, v]) => v.length > 6 ? `${k} for ${v.length} symbols` : `${k}: ${v.join(', ')}`).join('; ');
  }

  function render(A, ctx) {
    extraCharts.forEach(c => c.destroy()); extraCharts = [];
    const lbl = id => (A.groups.find(g => g.id === id) || A.benchmarks.find(b => b.id === id) || { label: id }).label;
    document.getElementById('alMeta').innerHTML = `Prices through <b>${A.price_asof}</b> · short interest settlement <b>${(A.positioning.find(p => p.id === 'XLF') || {}).settle || '–'}</b> · built ${A.generated_ct}` +
      (A.stale.length ? ` · <span class="stale">STALE</span> (cached copies used): ${staleSummary(A.stale)}` : '') +
      (A.failures.length ? ` · <details class="alfail"><summary class="bad">${A.failures.length} fetch issue(s)</summary>${A.failures.join('<br>')}</details>` : ' · all inputs fetched OK') +
      `<br>Excluded tickers: ${Object.entries(A.excluded_tickers).map(([k, v]) => `${k} (${v})`).join(', ')}. ` +
      `Baskets (equal-weight, daily rebalanced, <b>illustrative until the coverage list is supplied</b>): ` +
      A.groups.filter(g => g.basket).map(g => `<b>${g.label}</b>: ${g.members.join(', ')}`).join(' · ');

    // 6. score
    const C = ['rel_perf', 'positioning', 'macro_beta_shift', 'technical_stretch'];
    const CN = { rel_perf: 'Rel. perf', positioning: 'Positioning', macro_beta_shift: 'Macro-beta shift', technical_stretch: 'Tech. stretch' };
    document.getElementById('alScore').innerHTML = `<table class="summary al"><thead><tr><th>#</th><th>Group</th><th class="r">Score</th>${C.map(c => `<th class="r">${CN[c]}</th>`).join('')}<th>Why look (largest component first)</th></tr></thead><tbody>` +
      A.scores.map(s => `<tr><td>${s.rank}</td><td class="b">${s.label}</td><td class="r b"><span class="bar" style="width:${Math.round(Math.min(1, s.score / 2) * 60)}px"></span>${n(s.score, 2)}</td>${C.map(c => `<td class="r" style="${heatAbs(s.components[c], 3)}">${n(s.components[c], 2)}</td>`).join('')}<td class="why">${s.reason}</td></tr>`).join('') + '</tbody></table>';
    document.getElementById('alMethod').innerHTML = `<b>Method.</b> Each component is an absolute z-score (capped at 3), so the score flags <i>unusual</i> readings in either direction. It is a prompt for where to spend research time, not a buy/sell signal.
      <b>Rel. perf</b> = |z| of the group's 21-trading-day total return relative to XLF vs its own rolling history since mid-2015.
      <b>Positioning</b> = average of |z| of days-to-cover (SI ÷ FINRA average daily volume, unfloored) vs its own history since Dec 2017 and |z| of its change over the last 2 reports (~1M).
      <b>Macro-beta shift</b> = largest |z| across 10Y, 2s10s, HY OAS and MOVE of the 3M change in the 6M rolling beta, measured relative to the median change across groups and scaled by that beta's historical 3M-change volatility, so a market-wide shift doesn't dominate.
      <b>Tech. stretch</b> = average of |z| of the gap to the 200-day MA and of 21-day realized vol vs own history.
      <b>Score</b> = simple average of the available components (equal weights). Baskets use equal-weight daily-rebalanced member returns and the average of member days-to-cover.`;

    // 1. performance table
    const H = ['1w', '1m', '3m', 'ytd', '1y'];
    const rows = A.perf.slice().sort((a, b) => (a.bench - b.bench) || ((a.rank_1m || 99) - (b.rank_1m || 99)));
    document.getElementById('alPerf').innerHTML = `<table class="summary al"><thead><tr><th>Rank (1M vs XLF)</th><th>Group</th>${H.map(h => `<th class="r">${h.toUpperCase()}</th>`).join('')}${H.map(h => `<th class="r">vs XLF ${h.toUpperCase()}</th>`).join('')}</tr></thead><tbody>` +
      rows.map(p => `<tr class="${p.bench ? 'benchrow' : ''}"><td>${p.bench ? 'bench' : p.rank_1m}</td><td class="b">${p.label}</td>${H.map(h => `<td class="r ${cls(p.ret[h])}">${sg(p.ret[h], 2, '%')}</td>`).join('')}${H.map(h => `<td class="r" style="${p.id === 'XLF' ? '' : heat(p.rel_xlf[h], 10)}">${p.id === 'XLF' ? '–' : sg(p.rel_xlf[h], 2, 'pp')}</td>`).join('')}</tr>`).join('') +
      `</tbody></table><div class="note">Total returns (dividends reinvested, Yahoo adjusted close) from the close on or before each lookback date to ${A.price_asof}. "vs XLF" = return minus XLF return, in percentage points.</div>`;

    // RRG scatter
    const perfGrid = document.querySelector('.grid[data-sec="alloc-perf"]');
    const card = document.createElement('div'); card.className = 'card wide';
    card.innerHTML = `<h3>Rotation vs XLF (RRG-style): RS-ratio vs RS-momentum, last 8 weeks</h3><div class="latest">Right/up = improving relative to XLF and accelerating. Dot = latest week.</div><div class="cv" style="height:470px"><canvas></canvas></div><div class="note">Approximation, not JdK's proprietary RRG: RS = group/XLF total-return ratio (weekly); RS-ratio = 100 × RS / 26-week average of RS; RS-momentum = 100 × RS-ratio / RS-ratio 4 weeks earlier.</div>`;
    perfGrid.appendChild(card);
    const ds = A.rrg.map((r, i) => ({
      label: short(r.id), data: r.trail.map(t => ({ x: t[1], y: t[2], d: t[0] })), borderColor: PAL[i % PAL.length], backgroundColor: PAL[i % PAL.length],
      showLine: true, borderWidth: 1.2, pointRadius: r.trail.map((_, k) => k === r.trail.length - 1 ? 5 : 1.5), tension: 0.3,
    }));
    const quad = { id: 'quad', beforeDraw(ch) { const { ctx: c, chartArea: a, scales: { x, y } } = ch; const px = x.getPixelForValue(100), py = y.getPixelForValue(100); c.save(); c.strokeStyle = '#5a6a8a'; c.setLineDash([4, 4]); c.beginPath(); c.moveTo(px, a.top); c.lineTo(px, a.bottom); c.moveTo(a.left, py); c.lineTo(a.right, py); c.stroke(); c.setLineDash([]); c.fillStyle = '#5f6d88'; c.font = '11px sans-serif'; c.fillText('Leading', a.right - 52, a.top + 12); c.fillText('Improving', a.left + 6, a.top + 12); c.fillText('Lagging', a.left + 6, a.bottom - 6); c.fillText('Weakening', a.right - 64, a.bottom - 6); c.restore(); } };
    const lastLabels = { id: 'lastLabels', afterDatasetsDraw(ch) { const c = ch.ctx; c.save(); c.font = '10.5px sans-serif'; ch.data.datasets.forEach((d, i) => { const m = ch.getDatasetMeta(i); const p = m.data[m.data.length - 1]; if (p) { c.fillStyle = d.borderColor; c.fillText(d.label, p.x + 6, p.y - 4); } }); c.restore(); } };
    extraCharts.push(new Chart(card.querySelector('canvas'), {
      type: 'scatter', data: { datasets: ds }, plugins: [quad, lastLabels],
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.dataset.label} ${c.raw.d}: ratio ${n(c.raw.x, 2)}, mom ${n(c.raw.y, 2)}` } } },
        scales: { x: { title: { display: true, text: 'RS-ratio' }, grid: { color: '#1f2a3e' } }, y: { title: { display: true, text: 'RS-momentum' }, grid: { color: '#1f2a3e' } } } },
    }));

    // 2. pairs table
    document.getElementById('alPairs').innerHTML = `<table class="summary al"><thead><tr><th>Spread (long − short)</th><th>Scope</th>${H.map(h => `<th class="r">${h.toUpperCase()}</th>`).join('')}</tr></thead><tbody>` +
      A.pairs.map(p => `<tr><td class="b">${p.label}</td><td>${p.scope === 'fin' ? 'within financials' : 'broad market'}</td>${H.map(h => `<td class="r" style="${heat(p.spread[h], 8)}">${sg(p.spread[h], 2, 'pp')}</td>`).join('')}</tr>`).join('') +
      `</tbody></table><div class="note">Difference in total return (pp). Compare the financials rows with IWM − SPY and IWD − IWF / VTV − VUG to judge whether a move is financials-specific or factor-driven. There is no free financials momentum ETF; KBWD (high-dividend) is a value/yield proxy only.</div>`;

    // 3. positioning table
    document.getElementById('alPos').innerHTML = `<table class="summary al"><thead><tr><th>Group</th><th>Settle</th><th class="r">SI shares</th><th class="r">Δ prior</th><th class="r">Notional</th><th class="r">Δ prior</th><th class="r">Days to cover</th><th class="r">Δ prior</th><th class="r">DTC pctile</th><th class="r">~1M ago</th><th class="r">Notional pctile</th><th class="r">SI % shs out (pctile)</th><th class="r">Implied flows 1M / 3M</th><th>History from</th></tr></thead><tbody>` +
      A.positioning.map(p => p.na ? `<tr><td>${p.label}</td><td colspan="13" class="na">${p.na}</td></tr>` :
        `<tr><td class="b">${p.label}${p.basket ? ` <span class="sid">${p.members_with_si} members</span>` : ''}</td><td>${p.settle}</td><td class="r">${p.si_shares == null ? 'n/a' : p.si_shares >= 1e6 ? n(p.si_shares / 1e6, 2) + 'M' : n(p.si_shares / 1e3, 1) + 'K'}</td><td class="r">${sg(p.si_chg_prior_pct, 1, '%')}</td><td class="r b">${p.notional_bn == null ? '–' : p.notional_bn >= 1 ? '$' + n(p.notional_bn, 2) + 'bn' : '$' + n(p.notional_musd ?? p.notional_bn * 1000, p.notional_musd < 1 ? 2 : 1) + 'm'}</td><td class="r">${sg(p.notional_chg_prior_pct, 1, '%')}</td><td class="r b">${n(p.dtc, 2)}</td><td class="r">${sg(p.dtc_chg_prior, 2)}</td><td class="r" style="${heatAbs(Math.abs((p.dtc_pct ?? 50) - 50), 50)}">${ord(p.dtc_pct)}</td><td class="r">${ord(p.dtc_pct_1m_ago)}</td><td class="r">${ord(p.notional_pct)}</td><td class="r">${p.pct_so == null ? '–' : n(p.pct_so, 1) + '% (' + ord(p.pct_so_pct) + ')'}</td><td class="r">${p.flows_1m_musd == null ? '–' : sg(p.flows_1m_musd, 0, '') + ' / ' + sg(p.flows_3m_musd, 0, '') + ' $m'}</td><td>${p.since}</td></tr>`).join('') +
      `</tbody></table><div class="note">FINRA consolidated short interest, twice monthly (published ~7 business days after settlement). Days to cover = SI ÷ FINRA average daily volume (unfloored; FINRA's own figure is floored at 1.00). Percentiles are vs each series' own history. Shares outstanding and implied flows (daily Δ shares outstanding × NAV) are only available free for SPDR ETFs (XLF, KRE, KBE, KIE) from State Street. Basket notional = Σ member SI × close on the settlement date.</div>`;

    // 4. macro heatmap
    const F = A.factors;
    document.getElementById('alMacro').innerHTML = `<table class="summary al heat"><thead><tr><th rowspan="2">Group</th>${F.map(f => `<th colspan="4" class="c">${f.name} <span class="sid">${f.unit}</span></th>`).join('')}</tr><tr>${F.map(() => '<th class="r">β 6M</th><th class="r">Δ vs 3M ago</th><th class="r">ρ 6M</th><th class="r">β 1Y</th>').join('')}</tr></thead><tbody>` +
      A.macro.map(m => `<tr><td class="b">${m.label}</td>${F.map(f => { const v = m.f[f.id] || {}; const dd = v.beta_6m != null && v.beta_6m_3m_ago != null ? v.beta_6m - v.beta_6m_3m_ago : null;
        return `<td class="r" style="${heat(v.beta_6m, 1.5)}">${sg(v.beta_6m, 2)}</td><td class="r" style="${heat(dd, 1)}">${sg(dd, 2)}</td><td class="r">${sg(v.corr_6m, 2)}</td><td class="r">${sg(v.beta_1y, 2)}</td>`; }).join('')}</tr>`).join('') +
      `</tbody></table><div class="note">Rolling OLS beta of daily total returns (%) on daily changes in each factor, scaled per +10 bp (10Y, 2s10s, HY OAS) or per +10 points (MOVE); 6M = 126 trading days, 1Y = 252. Δ = change in 6M beta vs 63 trading days ago. Factors: FRED DGS10, T10Y2Y, BAMLH0A0HYM2; MOVE from Yahoo. Green = the group tends to rise when the factor rises. Peer-median 3M beta changes: ${Object.entries(A.median_beta_shift).map(([k, v]) => `${(F.find(f => f.id === k) || {}).name} ${sg(v, 2)}`).join(', ')}.</div>`;

    // 5. valuation / sentiment
    document.getElementById('alVal').innerHTML = `<table class="summary al"><thead><tr><th>Group</th><th class="r">From 52w high</th><th class="r">vs 200-day MA</th><th class="r">z (own hist)</th><th class="r">21d realized vol</th><th class="r">Vol pctile</th><th class="r">Volume surge (5d / 63d)</th></tr></thead><tbody>` +
      A.valuation.map(v => `<tr><td class="b">${v.label}</td><td class="r" style="${heat(v.dist_52w_high, 30)}">${sg(v.dist_52w_high, 1, '%')}</td><td class="r" style="${heat(v.gap_200dma, 20)}">${sg(v.gap_200dma, 1, '%')}</td><td class="r">${sg(v.z_gap_200dma, 2)}</td><td class="r">${n(v.rv21, 1)}%</td><td class="r" style="${heatAbs(Math.abs((v.rv21_pct ?? 50) - 50), 50)}">${ord(v.rv21_pct)}</td><td class="r" style="${heatAbs(Math.max(0, (v.vol_surge ?? 1) - 1), 1.5)}">${v.vol_surge == null ? '–' : n(v.vol_surge, 2) + '×'}</td></tr>`).join('') +
      `</tbody></table><div class="note">Price-based proxies only. 52-week high and 200-day MA use closing prices (basket: equal-weight index). Realized vol = 21-day stdev of daily total returns, annualized; percentile vs history since mid-2016. Volume surge = 5-day / 63-day average volume (basket: average across members).</div>`;
    document.getElementById('alPlaceholders').innerHTML = `<div class="ph"><b>Needs a data feed (not shown, not estimated):</b><ul>${A.placeholders.map(p => `<li><b>${p.item}</b>: ${p.note}</li>`).join('')}</ul></div>`;
  }

  window.ALLOC_PANEL = { defs, render };
})();

/* Live Treasury strip: CNBC/Tradeweb quotes fetched in the browser (CORS allowed) every 60s.
   Falls back per-symbol to the last good snapshot (data/treasury.json from the refresh workflow,
   or the last live pull cached in this browser), clearly marked stale. Never invents numbers. */
(function () {
  const SYMS = [["US1M","1M"],["US3M","3M"],["US6M","6M"],["US1Y","1Y"],["US2Y","2Y"],["US5Y","5Y"],["US10Y","10Y"],["US30Y","30Y"]];
  const URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" +
    SYMS.map(s => s[0]).join("|") + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json";
  const LS = "tsyQuotesLastGood";
  const el = document.getElementById("tsyStrip");
  if (!el) return;
  let snap = {}; // symbol -> {last, prev, time}
  const num = s => { const v = parseFloat(String(s ?? "").replace(/[%+]/g, "")); return isFinite(v) ? v : null; };
  const ct = t => new Date(t).toLocaleString("en-US", { timeZone: "America/Chicago", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " CT";
  function addSnap(q, src) { for (const k in (q || {})) if (q[k] && q[k].last != null && (!snap[k] || new Date(q[k].time) >= new Date(snap[k].time))) snap[k] = Object.assign({}, q[k], { src }); }
  try { addSnap(JSON.parse(localStorage.getItem(LS) || "{}").quotes, "browser cache"); } catch (e) {}
  if (window.__TSY_SNAPSHOT__) addSnap(window.__TSY_SNAPSHOT__.quotes, "workflow snapshot");
  let live = {}, lastErr = null;
  const bp = (a, b) => (a == null || b == null) ? null : Math.round((a - b) * 1000) / 10;
  const fmtBp = v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + " bp";
  function render() {
    const get = s => live[s] ? Object.assign({ stale: false }, live[s]) : (snap[s] ? Object.assign({ stale: true }, snap[s]) : null);
    let cells = SYMS.map(([s, lbl]) => {
      const q = get(s);
      if (!q) return `<div class="tq stale"><span class="tl">${lbl}</span><b>–</b><span class="tc na">stale · no quote</span></div>`;
      const c = bp(q.last, q.prev), cls = c == null ? "na" : c > 0 ? "bad" : c < 0 ? "good" : "na";
      return `<div class="tq${q.stale ? " stale" : ""}" title="${q.stale ? "STALE: last good quote (" + q.src + ")" : "live"} · ${ct(q.time)}"><span class="tl">${lbl}${q.stale ? ' <i>stale</i>' : ""}</span><b>${q.last.toFixed(3)}%</b><span class="tc ${cls}">${fmtBp(c)}</span></div>`;
    });
    const spread = (a, b, lbl) => {
      const qa = get(a), qb = get(b);
      if (!qa || !qb) return `<div class="tq sp stale"><span class="tl">${lbl}</span><b>–</b><span class="tc na">stale</span></div>`;
      const v = bp(qb.last, qa.last), pv = bp(qb.prev, qa.prev), d = (v != null && pv != null) ? Math.round((v - pv) * 10) / 10 : null;
      const st = qa.stale || qb.stale;
      return `<div class="tq sp${st ? " stale" : ""}"><span class="tl">${lbl}${st ? " <i>stale</i>" : ""}</span><b>${v.toFixed(1)} bp</b><span class="tc na">${fmtBp(d)}</span></div>`;
    };
    cells.push(spread("US2Y", "US10Y", "2s10s"), spread("US3M", "US10Y", "3m10y"));
    const times = SYMS.map(([s]) => get(s)).filter(Boolean).map(q => new Date(q.time));
    const latest = times.length ? ct(new Date(Math.max(...times))) : "–";
    const anyLive = Object.keys(live).length;
    const status = anyLive ? `<span class="good">● live</span> · updates every 60s` :
      `<span class="bad">● stale</span> · live feed unavailable${lastErr ? " (" + lastErr + ")" : ""}, showing last good snapshot`;
    el.innerHTML = `<div class="tsyhead"><b>US Treasury yields</b> <span>Δ vs prior close · quote time ${latest} · source: CNBC/Tradeweb · ${status}</span></div><div class="tsyrow">${cells.join("")}</div>`;
  }
  async function pull() {
    try {
      const r = await fetch(URL, { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json(), fresh = {};
      for (const q of j.FormattedQuoteResult.FormattedQuote) {
        const last = num(q.last);
        if (last != null && q.last_time) fresh[q.symbol] = { last, prev: num(q.previous_day_closing), time: q.last_time };
      }
      if (!Object.keys(fresh).length) throw new Error("empty response");
      live = fresh; lastErr = null; addSnap(fresh, "browser cache");
      try { localStorage.setItem(LS, JSON.stringify({ quotes: snap })); } catch (e) {}
    } catch (e) { live = {}; lastErr = e.message || "fetch failed"; }
    render();
  }
  render();
  (window.__TSY_SNAPSHOT__ ? Promise.resolve() :
    fetch("data/treasury.json?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(j => j && addSnap(j.quotes, "workflow snapshot")).catch(() => {}))
    .then(() => { render(); pull(); setInterval(pull, 60000); });
})();

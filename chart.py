"""Groww-style interactive price chart built on TradingView Lightweight Charts (runs in the browser).

Period buttons, line/candle switch, indicator menu and the hover price header all work client-side,
and the viewer's choices are remembered in localStorage."""
import json

import numpy as np
import pandas as pd

IST_OFFSET = 19800  # seconds; lightweight-charts shows UTC, so shift timestamps to read as IST
MAX_BARS = 3000     # the browser gets at most this many recent candles (keeps the page light)


def _t(ts: pd.Timestamp) -> int:
    return int(ts.timestamp()) + IST_OFFSET


def _col(x, nd: int = 2) -> list:
    """Column -> JSON-able list, NaN -> null, rounded (vectorised)."""
    a = np.round(np.asarray(x, dtype=float), nd)
    return np.where(np.isnan(a), None, a).tolist()


def build_html(df: pd.DataFrame, *, symbol: str, intraday: bool, prev_close: float, overlays: list[dict],
               default_overlays: list[str], panes: list[dict], markers: list[dict], price_lines: list[dict],
               up: str, down: str, accent: str, bg: str, store_key: str, height: int, live: dict | None = None,
               max_bars: int = MAX_BARS, alert: dict | None = None) -> str:
    """overlays: {name, col, color, style(0 solid/2 dashed), width, step}; panes: {name, lines:[{col,color}], hist:col?, levels:[]}

    Data is sent column-wise (one time array + one array per series) and expanded in the browser,
    which is ~4x smaller than one JSON object per point."""
    df = df.iloc[-max_bars:]
    times = ((df.index.asi8 // 10**9) + IST_OFFSET).tolist()
    has_vol = bool(df.Volume.sum() > 0)
    ov = [{**o, "v": _col(df[o["col"]])} for o in overlays if o["col"] in df and df[o["col"]].notna().any()]
    pn = []
    for p in panes:
        lines = [{**ln, "v": _col(df[ln["col"]])} for ln in p.get("lines", []) if ln["col"] in df]
        hist = _col(df[p["hist"]].fillna(0)) if p.get("hist") else None
        pn.append({"name": p["name"], "lines": lines, "hist": hist, "levels": p.get("levels", [])})
    mk = sorted(({**m, "time": _t(m["time"])} for m in markers if m["time"] >= df.index[0]), key=lambda m: m["time"])
    last_day = df.index[-1].date()
    session_start = _t(df.index[df.index.date == last_day][0])   # start of the last session (1D view)
    cfg = {
        "symbol": symbol, "intraday": intraday, "prevClose": prev_close,
        "t": times, "o": _col(df.Open), "h": _col(df.High), "l": _col(df.Low), "c": _col(df.Close),
        "v": _col(df.Volume, 0) if has_vol else None,
        "overlays": ov, "defaultOverlays": default_overlays, "panes": pn, "markers": mk, "priceLines": price_lines,
        "live": live, "alert": alert, "up": up, "down": down, "accent": accent, "bg": bg, "storeKey": store_key, "sessionStart": session_start,
        "periods": ["1D", "1W", "1M", "3M", "All"] if intraday else ["1M", "3M", "6M", "1Y", "3Y", "5Y", "All"],
    }
    payload = json.dumps(cfg, separators=(",", ":")).replace("</", "<\\/")  # keep user text from closing the <script>
    return TEMPLATE.replace("__H__", str(height)).replace("__CFG__", payload)


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
  * { box-sizing: border-box; }
  :root { --fg:#e8e8e6; --muted:#8b8f99; --btn:#b8bcc6; --hover:#1b1f27; --hover-fg:#fff; --line:#262a33;
          --menu:#171a21; --menu-line:#2b303a; --menu-fg:#d6d8de; --pane:#20242c; }
  :root.light { --fg:#1f2328; --muted:#6b7280; --btn:#4b5563; --hover:#eef0f3; --hover-fg:#111; --line:#e3e6ea;
          --menu:#ffffff; --menu-line:#e3e6ea; --menu-fg:#1f2328; --pane:#eceef1; }
  html, body { margin:0; padding:0; background: transparent; color:var(--fg); height:__H__px; overflow:hidden;
    font-family: "Source Sans Pro", Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  #wrap { display:flex; flex-direction:column; height:100%; }
  #head { display:flex; justify-content:space-between; align-items:flex-end; padding:2px 4px 8px; gap:12px; flex-wrap:wrap; }
  #px { font-size:28px; font-weight:700; font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
  #chg { font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; margin-top:2px; }
  #chg .per { color:var(--muted); font-weight:500; margin-left:4px; }
  #when { font-size:12px; color:var(--muted); min-height:16px; }
  #live { font-size:11.5px; font-weight:700; letter-spacing:.06em; min-height:16px; }
  #live .d { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; vertical-align:1px; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.25 } }
  #bar { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;
         border-bottom:1px solid var(--line); padding-bottom:8px; }
  .periods, .right { display:flex; gap:4px; align-items:center; flex-wrap:wrap; }
  button { background:transparent; color:var(--btn); border:1px solid transparent; border-radius:8px; padding:5px 11px;
           font: inherit; font-size:13px; font-weight:600; cursor:pointer; }
  button:hover { background:var(--hover); color:var(--hover-fg); }
  button.on { color: var(--accent2); border-color: var(--accent2); background: color-mix(in srgb, var(--accent2) 10%, transparent); }
  .seg { display:flex; border:1px solid var(--line); border-radius:9px; overflow:hidden; }
  .seg button { border-radius:0; border:none; padding:5px 10px; }
  .seg button.on { background:var(--line); color:var(--hover-fg); }
  #menu { position:absolute; right:6px; top:0; z-index:10; background:var(--menu); border:1px solid var(--menu-line); border-radius:10px;
          padding:8px 10px; display:none; min-width:210px; box-shadow:0 8px 24px rgba(0,0,0,.45); max-height:420px; overflow:auto; }
  #menu label { display:flex; align-items:center; gap:8px; font-size:13px; padding:5px 2px; cursor:pointer; color:var(--menu-fg); }
  #menu .sec { font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:6px 0 2px; }
  #menu .sw { width:10px; height:10px; border-radius:2px; display:inline-block; }
  #legend { display:flex; gap:12px; flex-wrap:wrap; font-size:11.5px; color:var(--muted); padding:6px 2px 2px; min-height:22px; }
  #legend span { display:inline-flex; align-items:center; gap:5px; }
  #legend i { width:12px; height:2px; display:inline-block; border-radius:1px; }
  #main { flex:1; min-height:200px; position:relative; }
  .pane { height:112px; border-top:1px solid var(--pane); position:relative; }
  .pane a[href*="tradingview"] { display:none !important; }  /* attribution stays on the main chart */
  .pane .ttl { position:absolute; left:6px; top:3px; font-size:11px; color:var(--muted); z-index:3; pointer-events:none; }
  #err { color:#e66767; padding:20px; display:none; }
</style></head><body>
<div id="wrap">
  <div id="head"><div><div id="px">—</div><div id="chg"></div></div><div style="text-align:right"><div id="live"></div><div id="when"></div></div></div>
  <div id="bar">
    <div class="periods" id="periods"></div>
    <div class="right">
      <div class="seg" id="type"><button data-t="line" title="Line">〰 Line</button><button data-t="candle" title="Candles">▮▯ Candles</button></div>
      <button id="indBtn">ƒx Indicators ▾</button>
      <button id="bell" title="Desktop alerts when the signal changes">🔕</button>
      <button id="fit" title="Reset zoom">⤢</button>
    </div>
  </div>
  <div id="menu"></div>
  <div id="legend"></div>
  <div id="main"></div>
  <div id="panes"></div>
  <div id="err">Chart library failed to load — check your internet connection.</div>
</div>
<script>
const C = __CFG__;
// expand the column-wise payload: one time array + one value array per series
C.bars = C.t.map((t, i) => ({ time: t, open: C.o[i], high: C.h[i], low: C.l[i], close: C.c[i] }));
C.vol = C.v ? C.t.map((t, i) => ({ time: t, value: C.v[i], color: (C.c[i] >= C.o[i] ? C.up : C.down) + '66' })) : [];
const _pts = v => C.t.map((t, i) => v[i] == null ? { time: t } : { time: t, value: v[i] });
C.overlays.forEach(o => { o.data = _pts(o.v); });
C.panes.forEach(p => {
  p.lines.forEach(ln => { ln.data = _pts(ln.v); });
  if (p.hist) p.hist = C.t.map((t, i) => ({ time: t, value: p.hist[i], color: (p.hist[i] >= 0 ? C.up : C.down) + 'aa' }));
});
// follow the host page's theme (light / dark) — read its background colour, re-check every 2 s
function hostIsDark() {
  try {
    const el = window.parent.document.querySelector('.stApp') || window.parent.document.body;
    const m = getComputedStyle(el).backgroundColor.match(/[\d.]+/g);
    if (!m) return true;
    const [r, g, b] = m.map(Number);
    return 0.299 * r + 0.587 * g + 0.114 * b < 140;
  } catch (e) { return true; }
}
let DARK = hostIsDark();
document.documentElement.classList.toggle('light', !DARK);
const store = {
  get(k, d) { try { const v = localStorage.getItem(C.storeKey + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(C.storeKey + k, JSON.stringify(v)); } catch (e) {} },
};
const fmt = v => v == null ? '—' : v.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const tfmt = t => { const d = new Date(t * 1000);
  const s = `${String(d.getUTCDate()).padStart(2,'0')} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  return C.intraday ? `${s}, ${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}` : s; };

if (!window.LightweightCharts) { document.getElementById('err').style.display = 'block'; throw new Error('lwc'); }
const L = LightweightCharts;
const base = {
  autoSize: true,
  layout: { background: { type: 'solid', color: 'transparent' }, textColor: DARK ? '#9aa0ab' : '#5b6170', fontSize: 11,
            fontFamily: getComputedStyle(document.body).fontFamily },
  grid: { vertLines: { visible: false }, horzLines: { color: DARK ? 'rgba(139,143,153,0.08)' : 'rgba(60,64,72,0.08)' } },
  rightPriceScale: { borderVisible: false, minimumWidth: 78 },
  timeScale: { borderVisible: false, timeVisible: C.intraday, secondsVisible: false, rightOffset: 4, minBarSpacing: 0.5 },
  crosshair: { mode: L.CrosshairMode.Normal,
               vertLine: { color: '#8b8f99', style: L.LineStyle.Dashed, labelBackgroundColor: DARK ? '#2b303a' : '#4b5563' },
               horzLine: { color: '#8b8f99', style: L.LineStyle.Dashed, labelBackgroundColor: DARK ? '#2b303a' : '#4b5563' } },
  localization: { priceFormatter: fmt, timeFormatter: tfmt },
};
const main = L.createChart(document.getElementById('main'), base);
const area = main.addAreaSeries({ lineWidth: 2, priceLineVisible: false, lastValueVisible: true, crosshairMarkerRadius: 4 });
const candle = main.addCandlestickSeries({ upColor: C.up, downColor: C.down, borderVisible: false,
  wickUpColor: C.up, wickDownColor: C.down, priceLineVisible: false });
area.setData(C.bars.map(b => ({ time: b.time, value: b.close })));
candle.setData(C.bars);
let vol = null;
if (C.vol.length) {
  vol = main.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
  main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vol.setData(C.vol);
}
const byTime = new Map(C.bars.map((b, i) => [b.time, i]));
let last = C.bars[C.bars.length - 1];

// overlays
const ovSeries = {};
C.overlays.forEach(o => {
  const s = main.addLineSeries({ color: o.color, lineWidth: o.width || 1.5, lineStyle: o.style || 0,
    lineType: o.step ? 1 : 0, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, visible: false });
  s.setData(o.data);
  (ovSeries[o.name] = ovSeries[o.name] || []).push({ s, color: o.color });
});
// trade levels
const lines = { area: [], candle: [] };
C.priceLines.forEach(p => ['area', 'candle'].forEach(k => {
  const ser = k === 'area' ? area : candle;
  lines[k].push(ser.createPriceLine({ price: p.price, color: p.color, lineWidth: 1, lineStyle: L.LineStyle.Dashed,
                                      axisLabelVisible: true, title: p.title }));
}));
let prevLine = null;

// sub panes (RSI / MACD / ...)
const panes = {};
C.panes.forEach(p => {
  const div = document.createElement('div'); div.className = 'pane'; div.style.display = 'none';
  div.innerHTML = `<div class="ttl">${p.name}</div>`;
  document.getElementById('panes').appendChild(div);
  const ch = L.createChart(div, { ...base, layout: { ...base.layout, attributionLogo: false }, timeScale: { ...base.timeScale, visible: false },
                                  handleScroll: false, handleScale: false,
                                  rightPriceScale: { ...base.rightPriceScale, scaleMargins: { top: 0.15, bottom: 0.1 } } });
  if (p.hist) { const h = ch.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }); h.setData(p.hist); }
  let first = null;
  p.lines.forEach(ln => {
    const s = ch.addLineSeries({ color: ln.color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false });
    s.setData(ln.data); first = first || s;
  });
  p.levels.forEach(v => first && first.createPriceLine({ price: v, color: '#6b7280', lineWidth: 1, lineStyle: L.LineStyle.Dotted, axisLabelVisible: false }));
  panes[p.name] = { div, ch };
});
// panels follow the main chart's scroll/zoom (one way, so a panel resizing can't reset the main view)
main.timeScale().subscribeVisibleLogicalRangeChange(r => {
  if (r) Object.values(panes).forEach(p => p.ch.timeScale().setVisibleLogicalRange(r));
});

// ---------- state
const state = {
  type: store.get('type', 'candle'),
  period: store.get('period', C.intraday ? '1D' : '1Y'),
  on: new Set(store.get('ind', [...C.defaultOverlays, 'Signals', 'Volume'])),
};
if (!C.periods.includes(state.period)) state.period = C.periods[C.periods.length - 1];

function periodStart() {
  if (state.period === 'All') return C.bars[0].time;
  if (state.period === '1D') return C.sessionStart;
  const days = { '1W': 7, '1M': 30, '3M': 91, '6M': 182, '1Y': 365, '3Y': 1095, '5Y': 1826 }[state.period];
  return last.time - days * 86400;
}
function baseIndex() {  // the bar the period's change is measured from
  const from = periodStart();
  let i = C.bars.findIndex(b => b.time >= from);
  return Math.max(i, 0);
}
function periodBase() {
  if (state.period === '1D' && C.prevClose) return C.prevClose;
  const i = baseIndex(); return i > 0 ? C.bars[i - 1].close : C.bars[i].open;
}
let up = true;
function header(price, t) {
  const b = periodBase(), d = price - b, pc = d / b * 100;
  document.getElementById('px').textContent = '₹' + fmt(price);
  const col = d >= 0 ? C.up : C.down;
  const lbl = { '1D': '1D', 'All': 'All time' }[state.period] || state.period;
  document.getElementById('chg').innerHTML = `<span style="color:${col}">${d >= 0 ? '+' : ''}${fmt(d)} (${d >= 0 ? '+' : ''}${pc.toFixed(2)}%)</span><span class="per">${lbl}</span>`;
  document.getElementById('when').textContent = t ? tfmt(t) : '';
}
function applyType() {
  const line = state.type === 'line';
  up = last.close >= periodBase();
  const col = up ? C.up : C.down;
  area.applyOptions({ visible: line, lineColor: col, topColor: col + '40', bottomColor: col + '00' });
  candle.applyOptions({ visible: !line });
  document.querySelectorAll('#type button').forEach(b => b.classList.toggle('on', b.dataset.t === state.type));
  document.documentElement.style.setProperty('--accent2', line ? col : C.accent);
  if (prevLine) { area.removePriceLine(prevLine); prevLine = null; }
  if (line && state.period === '1D' && C.prevClose)
    prevLine = area.createPriceLine({ price: C.prevClose, color: '#8b8f99', lineWidth: 1, lineStyle: L.LineStyle.Dashed,
                                      axisLabelVisible: false, title: 'Prev close' });
  applyMarkers();
}
function applyMarkers() {
  const m = state.on.has('Signals') ? C.markers : [];
  area.setMarkers(state.type === 'line' ? m : []); candle.setMarkers(state.type === 'candle' ? m : []);
}
function applyPeriod() {
  document.querySelectorAll('#periods button').forEach(b => b.classList.toggle('on', b.dataset.p === state.period));
  const n = C.bars.length;
  if (state.period === 'All') main.timeScale().setVisibleLogicalRange({ from: 0, to: n + 3 });
  else main.timeScale().setVisibleLogicalRange({ from: baseIndex() - 0.5, to: n + 3 });
  applyType(); header(last.close, null);
}
function applyIndicators() {
  Object.entries(ovSeries).forEach(([name, arr]) => arr.forEach(x => x.s.applyOptions({ visible: state.on.has(name) })));
  if (vol) vol.applyOptions({ visible: state.on.has('Volume') });
  Object.entries(panes).forEach(([name, p]) => p.div.style.display = state.on.has(name) ? 'block' : 'none');
  // only the bottom-most chart shows the time axis
  const shown = Object.values(panes).filter(p => p.div.style.display !== 'none');
  main.timeScale().applyOptions({ visible: shown.length === 0 });
  Object.values(panes).forEach(p => p.ch.timeScale().applyOptions({ visible: p === shown[shown.length - 1] }));
  applyMarkers();
  const lg = document.getElementById('legend'); lg.innerHTML = '';
  Object.entries(ovSeries).forEach(([name, arr]) => { if (state.on.has(name))
    lg.insertAdjacentHTML('beforeend', `<span><i style="background:${arr[0].color}"></i>${name}</span>`); });
  if (state.on.has('Signals') && C.markers.length)
    lg.insertAdjacentHTML('beforeend', `<span style="color:${C.up}">▲ Buy</span><span style="color:${C.down}">▼ Short</span><span style="color:#ec835a">● Exit</span>`);
  store.set('ind', [...state.on]);
  // newly shown panels pick up the main chart's zoom once they have a size
  setTimeout(() => { const r = main.timeScale().getVisibleLogicalRange();
    if (r) Object.values(panes).forEach(p => p.ch.timeScale().setVisibleLogicalRange(r)); }, 0);
}

// ---------- toolbar
const pBox = document.getElementById('periods');
C.periods.forEach(p => { const b = document.createElement('button'); b.textContent = p; b.dataset.p = p;
  b.onclick = () => { state.period = p; store.set('period', p); applyPeriod(); }; pBox.appendChild(b); });
document.querySelectorAll('#type button').forEach(b => b.onclick = () => { state.type = b.dataset.t; store.set('type', state.type); applyType(); });
document.getElementById('fit').onclick = applyPeriod;
const menu = document.getElementById('menu');
const sections = [['On price', Object.keys(ovSeries).map(n => [n, ovSeries[n][0].color])],
                  ['Signals & volume', [['Signals', C.up], ...(vol ? [['Volume', '#6b7280']] : [])]],
                  ['Panels below', C.panes.map(p => [p.name, (p.lines[0] || {}).color || '#9085e9'])]];
sections.forEach(([title, items]) => { if (!items.length) return;
  menu.insertAdjacentHTML('beforeend', `<div class="sec">${title}</div>`);
  items.forEach(([name, color]) => {
    const id = 'i_' + name.replace(/\W/g, '');
    menu.insertAdjacentHTML('beforeend', `<label><input type="checkbox" id="${id}" ${state.on.has(name) ? 'checked' : ''}>` +
      `<span class="sw" style="background:${color}"></span>${name}</label>`);
    document.getElementById(id).onchange = e => { e.target.checked ? state.on.add(name) : state.on.delete(name); applyIndicators(); };
  });
});
document.getElementById('indBtn').onclick = e => { e.stopPropagation();
  menu.style.top = (e.currentTarget.getBoundingClientRect().bottom + 4) + 'px';
  menu.style.display = menu.style.display === 'block' ? 'none' : 'block'; };
document.addEventListener('click', e => { if (!menu.contains(e.target)) menu.style.display = 'none'; });

// hover: the header follows the crosshair, like Groww
let hovering = false;
main.subscribeCrosshairMove(p => {
  if (!p || !p.time || !byTime.has(p.time)) { hovering = false; header(last.close, null); return; }
  hovering = true; header(C.bars[byTime.get(p.time)].close, p.time);
});

// ---------- live updates: update the last candle in place from the live feed
function setLive(ok, txt) {
  const el = document.getElementById('live');
  el.innerHTML = `<span class="d" style="background:${ok ? C.up : '#8b8f99'};${ok ? 'animation:pulse 1.6s infinite' : ''}"></span>` +
                 `<span style="color:${ok ? C.up : '#8b8f99'}">${txt}</span>`;
}
const clock = s => { const d = new Date(s * 1000 + 19800000);
  return [d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()].map(x => String(x).padStart(2, '0')).join(':'); };
let streaming = false, lastTickAt = 0, feedFails = 0, pollTimer = null, es = null;
function bucket(t) {  // candle start (shifted seconds) that a tick at time t belongs to
  const day = t - (t % 86400);
  if (!C.live.ivSec) return day;
  const open = day + 9 * 3600 + 15 * 60, close = day + 15 * 3600 + 30 * 60;   // NSE session 09:15–15:30
  t = Math.min(Math.max(t, open), close - 1);   // closing-price ticks after 15:30 belong to the last candle
  return open + Math.floor((t - open) / C.live.ivSec) * C.live.ivSec;
}
function applyTick(px, t) {
  const bt = bucket(t);
  if (bt < last.time) return;
  let b;
  if (bt > last.time) { b = { time: bt, open: px, high: px, low: px, close: px };
                        C.bars.push(b); byTime.set(bt, C.bars.length - 1); }
  else { b = { ...last, close: px, high: Math.max(last.high, px), low: Math.min(last.low, px) };
         C.bars[C.bars.length - 1] = b; }
  last = b;
  candle.update(b); area.update({ time: b.time, value: b.close });
  if (!hovering) header(px, null);
}
// where the live feed is: a file the app serves itself (opened online, e.g. Streamlit Cloud), a proxy path
// (FEED_BASE), or the feed port on the same computer that serves this page (this computer / your WiFi)
function feedUrl(path) {
  if (/^https?:/.test(path)) return path;
  if (C.live.file) {
    let base = document.baseURI;
    try { base = window.parent.location.href; } catch (e) {}
    return new URL(path, base).href + '?t=' + Date.now();
  }
  if (C.live.base) return C.live.base + path;
  let host = 'localhost', proto = 'http:';
  try { host = window.parent.location.hostname || host; proto = window.parent.location.protocol || proto; } catch (e) {}
  return `${proto}//${host}:${C.live.port}${path}`;
}
if (C.live && C.live.stream && window.EventSource) {
  es = new EventSource(feedUrl(C.live.stream));
  es.onmessage = e => { const m = JSON.parse(e.data); streaming = true; lastTickAt = Date.now();
                        window.__tickLag = Date.now() / 1000 - m.ts; window.__ticks = (window.__ticks || 0) + 1;
                        applyTick(m.ltp, m.t); setLive(true, `LIVE TICKS · ${clock(m.ts)}`); };
  es.onerror = () => { streaming = false; setLive(false, 'reconnecting…'); };
}
async function poll() {
  if (streaming && Date.now() - lastTickAt > 20000) streaming = false;  // stream went quiet: fall back
  const ctl = new AbortController(), timeout = setTimeout(() => ctl.abort(), 8000);
  try {
    const r = await fetch(feedUrl(C.live.url), { cache: 'no-store', signal: ctl.signal });
    const j = await r.json();
    if (!j.bars) throw new Error(j.error || 'no data');
    let changed = false;
    for (const b0 of j.bars) {
      let b = b0;
      if (b.time < last.time) continue;
      if (streaming && b.time === last.time)  // keep the live tick price; take volume and extremes from the feed
        b = { ...b, close: last.close, high: Math.max(b.high, last.high), low: Math.min(b.low, last.low) };
      candle.update(b); area.update({ time: b.time, value: b.close });
      if (vol) vol.update({ time: b.time, value: b.volume, color: (b.close >= b.open ? C.up : C.down) + '66' });
      if (b.time > last.time) { C.bars.push(b); byTime.set(b.time, C.bars.length - 1); }
      else C.bars[C.bars.length - 1] = b;
      last = C.bars[C.bars.length - 1]; changed = true;
    }
    if (changed && !hovering) header(last.close, null);
    if (j.tick) applyTick(j.tick.ltp, j.tick.t);   // file feed: the newest price, fresher than the candles
    if (C.live.file) {
      const ts = Math.max(j.ts, j.tick ? j.tick.ts : 0), fresh = Date.now() / 1000 - ts < 90;
      setLive(fresh, `${fresh ? 'LIVE' : 'DELAYED'} · ${clock(ts)}`);
    } else if (!streaming) setLive(true, `LIVE · ${clock(j.ts)}`);
    feedFails = 0;
  } catch (e) {
    // the feed can't be reached from here: stop asking; the page shows new prices when it reloads
    if (++feedFails >= (C.live.file ? 6 : 3)) { clearInterval(pollTimer); if (es) es.close(); setLive(false, 'Live paused · reload'); }
    else setLive(false, 'reconnecting…');
  } finally { clearTimeout(timeout); }
}
if (C.live) {
  setLive(true, 'LIVE');
  setTimeout(poll, C.live.file ? 1500 : 0);   // a file feed is written a moment after the page asks for it
  pollTimer = setInterval(poll, (C.live.stream ? 5 : C.live.every) * 1000);
}
else setLive(false, 'Market closed');

applyIndicators(); applyPeriod();
function applyTheme() {
  const d = hostIsDark();
  if (d === DARK) return;
  DARK = d;
  document.documentElement.classList.toggle('light', !DARK);
  const opts = { layout: { textColor: DARK ? '#9aa0ab' : '#5b6170' },
                 grid: { horzLines: { color: DARK ? 'rgba(139,143,153,0.08)' : 'rgba(60,64,72,0.08)' } },
                 crosshair: { vertLine: { labelBackgroundColor: DARK ? '#2b303a' : '#4b5563' },
                              horzLine: { labelBackgroundColor: DARK ? '#2b303a' : '#4b5563' } } };
  [main, ...Object.values(panes).map(p => p.ch)].forEach(c => c.applyOptions(opts));
}
setInterval(applyTheme, 2000);

// ---------- alerts: desktop notification + beep when the signal changes (works with the tab in the background)
const bell = document.getElementById('bell');
const ALERT_KEY = 'tsi-alerts-on';   // shared by every chart and page
const alertsFlag = () => { try { return localStorage.getItem(ALERT_KEY) === '1'; } catch (e) { return false; } };
const alertsOn = () => { try { return Notification.permission === 'granted' && alertsFlag(); } catch (e) { return false; } };
const paintBell = () => { bell.textContent = alertsOn() ? '🔔' : '🔕';
  bell.title = alertsOn() ? 'Desktop alerts ON — click to turn off' : 'Turn on desktop alerts for signal changes'; };
function beep() {
  try { const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain();
        o.frequency.value = 880; o.connect(g); g.connect(a.destination); g.gain.setValueAtTime(0.15, a.currentTime);
        o.start(); o.stop(a.currentTime + 0.25); } catch (e) {}
}
bell.onclick = async () => {
  if (!('Notification' in window)) { bell.title = 'This browser does not support desktop notifications'; return; }
  if (Notification.permission !== 'granted' && (await Notification.requestPermission()) !== 'granted') { paintBell(); return; }
  try { localStorage.setItem(ALERT_KEY, alertsFlag() ? '0' : '1'); } catch (e) {}
  paintBell();
  if (alertsOn()) new Notification('Trade Signals alerts are on', { body: 'You will be notified when ' + C.symbol + "'s signal changes." });
};
paintBell();
if (C.alert) {
  const k = 'v:' + C.alert.key, prev = store.get(k, null);
  if (prev && prev !== C.alert.verdict && /^(BUY|SHORT|SELL)/.test(C.alert.verdict)) {
    beep();
    if (alertsOn()) { try { new Notification(C.alert.title, { body: C.alert.body }); } catch (e) {} }
  }
  store.set(k, C.alert.verdict);
}
</script></body></html>"""

#!/usr/bin/env python3
"""
Emit plots/interactive.html -- a self-contained, zoomable Plotly view of the
exp30 result CSVs (aggregate30.py output). Plotly from cdnjs, pure-ASCII output.

Reuses exp29's _asciiify + the same JS engine shape (theme/draw/ciBand/lineTrace
/drawVsF/radio) and the exp28-dashboard viridis-over-full-B-ladder colours.

    python3 build_interactive.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent.parent / "plots" / "interactive.html"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent
                       / "exp29_failure_response" / "scripts"))
from build_interactive import _asciiify  # noqa: E402

B_LADDER = [1, 2, 4, 8, 16, 32]
# viridis at the 6 B_LADDER positions -- matches exp28's interactive + static PNGs
B_COLOR = {1: "#440154", 2: "#414487", 4: "#2a788e", 8: "#22a884",
           16: "#7ad151", 32: "#fde725"}

# dual-window REPS+MPRDMA at B=8 -- one extra series alongside the mprdma B
# ladder, same LB/buffer flags as reps_b8, CC swapped (see common30.base_flags)
DUAL_ARM = "reps_b8_dual"
DUAL_COLOR = "#dc2626"
DUAL_LABEL = "B=8 dual-window"


def payload():
    fct = pd.read_csv(D / "fct.csv")
    diag = pd.read_csv(D / "diagnostics.csv")
    rv = pd.read_csv(D / "resolvable.csv")
    return {
        "B_LADDER": B_LADDER,
        "B_COLOR": B_COLOR,
        "DUAL_ARM": DUAL_ARM,
        "DUAL_COLOR": DUAL_COLOR,
        "DUAL_LABEL": DUAL_LABEL,
        "fct": fct.round(4).to_dict(orient="records"),
        "diag": diag.round(5).to_dict(orient="records"),
        "rv": rv.to_dict(orient="records"),
    }


HTML = r"""<title>exp30 Concentrated Path Loss</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f6f7f9; --surface: #ffffff; --ink: #1a1f2b; --muted: #5b6472;
  --hairline: #e3e6ec; --accent: #6d28d9; --accent-soft: #ede9fe;
  --good: #15803d; --bad: #b91c1c;
  --shadow: 0 1px 2px rgba(20,25,40,.06), 0 8px 24px rgba(20,25,40,.05);
}
:root:not([data-theme="light"]) { @media (prefers-color-scheme: dark) {
  --ground: #101319; --surface: #191d26; --ink: #e6e9ef; --muted: #99a1b0;
  --hairline: #2b313d; --accent: #a78bfa; --accent-soft: #2a2140;
  --good: #4ade80; --bad: #f87171;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
} }
:root[data-theme="dark"] {
  --ground: #101319; --surface: #191d26; --ink: #e6e9ef; --muted: #99a1b0;
  --hairline: #2b313d; --accent: #a78bfa; --accent-soft: #2a2140;
  --good: #4ade80; --bad: #f87171;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
body { background: var(--ground); color: var(--ink); margin: 0;
  font: 400 16px/1.6 "IBM Plex Sans", system-ui, -apple-system, sans-serif; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 48px 24px 96px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 20px; }
.eyebrow { font: 500 12px/1 "IBM Plex Mono", monospace; letter-spacing: .14em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 12px; }
h1 { font-weight: 600; font-size: clamp(26px, 4vw, 38px); line-height: 1.15;
  margin: 0; text-wrap: balance; letter-spacing: -.01em; }
.lede { color: var(--muted); max-width: 68ch; margin: 16px 0 0; }
.cfg { color: var(--muted); font-size: 12.5px; line-height: 1.7; max-width: 94ch; margin: 12px 0 0; }
.cfg code { font-size: .92em; background: none; padding: 0; color: var(--ink); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px; margin: 32px 0 8px; }
.tile { background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; padding: 18px 20px; box-shadow: var(--shadow); }
.tile .k { font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }
.tile .v { font: 500 25px/1.1 "IBM Plex Mono", monospace; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; }
.tile .v.good { color: var(--good); } .tile .v.bad { color: var(--bad); }
.tile .s { font-size: 13px; color: var(--muted); margin-top: 8px; }
section { margin-top: 54px; }
h2 { font-weight: 600; font-size: 21px; margin: 0 0 6px; padding-bottom: 8px;
  border-bottom: 1px solid var(--hairline); }
section > p { color: var(--muted); max-width: 70ch; margin: 12px 0 16px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 0 0 12px; font: 500 13px/1 "IBM Plex Mono", monospace; }
.controls label { color: var(--muted); letter-spacing: .04em; }
.controls button { font: inherit; color: var(--ink); background: var(--surface);
  border: 1px solid var(--hairline); border-radius: 7px; padding: 7px 12px; cursor: pointer; }
.controls button[aria-pressed="true"] { background: var(--accent); color: #fff;
  border-color: var(--accent); }
.controls button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.chart { background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); padding: 10px; overflow-x: auto; }
.chart > div { min-width: 640px; height: 470px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin-top: 4px; }
.tblwrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); }
th, td { text-align: right; padding: 9px 14px; border-bottom: 1px solid var(--hairline);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
th { font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
.pill { display: inline-block; font: 500 11px/1 "IBM Plex Mono", monospace;
  padding: 4px 9px; border-radius: 999px; }
.pill.no { background: color-mix(in srgb, var(--good) 16%, transparent); color: var(--good); }
.pill.yes { background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
code { font: 500 .92em "IBM Plex Mono", monospace; background: var(--accent-soft);
  padding: 1px 5px; border-radius: 4px; }
footer { margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--hairline);
  color: var(--muted); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
/* Hide Plotly's own unified-hover box (incl. its per-trace color swatches --
   making just the box bg/border/text transparent leaves those swatches
   floating detached at the data point); our own sorted tooltip replaces it.
   Spike lines live in a separate layer and are unaffected. */
.js-plotly-plot .hoverlayer { display: none !important; }
</style>

<div class="wrap">
<header>
  <p class="eyebrow">REPS EuroSys artifact &middot; exp30 &middot; 894 runs</p>
  <h1>Concentrated path loss vs buffer size</h1>
  <p class="lede">exp28/29 found buffer size <strong>B</strong> does not move FCT
  &mdash; but exp28's degradation only slows packets (ECN, no loss) and exp29's
  full kill is transient (100&ndash;200&nbsp;&micro;s, then recovers). exp30 fills
  the two remaining cells: <strong>Part&nbsp;A</strong> is static
  <em>degradation</em> (<em>n</em> ToR0 uplinks slowed to 50&nbsp;% for the whole
  run); <strong>Part&nbsp;B</strong> is static <em>true kill</em> (<em>F</em> of
  ToR0's 32 uplinks 100&nbsp;% dead, permanently, from t&asymp;0 &mdash; reusing
  exp29's own <code>-timed_fail_tor_uplinks</code> mechanism with
  <code>recover&le;start</code> so it never thaws). Both parts share the same
  affected population: ToR0's 32 senders. Two flow sizes: 4&nbsp;MiB (the exp27
  resonance peak, healthy REPS mechanism live) and 16&nbsp;MiB (exp28/29 anchor).
  Drag to zoom, click a B in the legend to hide it (its CI band hides with it).</p>
  <p class="cfg" id="cfg"></p>
</header>

<div class="tiles" id="tiles"></div>

<section>
  <h2>1 &nbsp; FCT vs severity &mdash; Part A concentrated degradation</h2>
  <p>Affected-host (ToR0 sender) FCT percentiles against <em>n</em> = number of
  ToR0 uplinks degraded to 50&nbsp;% (severity = n/32). Healthy anchor at n=0.
  One line + 95&nbsp;% CI band per B (n=3 seeds, t-mult 4.30).</p>
  <div class="controls" id="a1-size"><label>flow size</label></div>
  <div class="controls" id="a1-ctl"><label>metric</label></div>
  <div class="chart"><div id="a1"></div></div>
</section>

<section>
  <h2>2 &nbsp; FCT vs degradation depth &mdash; Part A ratio sweep</h2>
  <p>8 ToR0 uplinks fixed degraded (1/4 of 32); x = how hard, 10&ndash;95&nbsp;%
  (95&nbsp;% &asymp; a full failure). Affected-host FCT percentiles.</p>
  <div class="controls" id="a2-size"><label>flow size</label></div>
  <div class="controls" id="a2-ctl"><label>metric</label></div>
  <div class="chart"><div id="a2"></div></div>
</section>

<section>
  <h2>3 &nbsp; Diagnostics vs severity &mdash; Part A</h2>
  <p>Per-affected-host counters off the flow-finish line, against <em>n</em>.
  <code>random-EV rate</code> = (random + explore EV draws) &divide; packets sent.
  Degradation drives ECN, not RTO, so <code>freeze entries</code> should stay
  near zero (exp28's finding &mdash; watch whether concentration changes that).</p>
  <div class="controls" id="d1-size"><label>flow size</label></div>
  <div class="controls" id="d1-ctl"><label>metric</label></div>
  <div class="chart"><div id="d1"></div></div>
</section>

<section>
  <h2>4 &nbsp; FCT / diagnostics vs static real kill &mdash; Part B</h2>
  <p><code>-timed_fail_tor_uplinks 0 F</code> + <code>-timed_window 1 1</code>
  (recover&nbsp;&le;&nbsp;start, so the kill fires at t&asymp;0 and never
  recovers): <em>F</em> of ToR0's 32 uplinks are 100&nbsp;% dead &mdash; a real
  <code>Pipe::_failed</code> kill, not a speed ratio &mdash; for the entire run.
  Same affected population as Part A (ToR0's 32 senders), same severity axis
  shape (<em>F</em>/32), but degradation swapped for a true kill and transient
  (exp29) swapped for static. x = F (0&nbsp;=&nbsp;healthy, capped at 31 so one
  uplink always stays alive).</p>
  <div class="controls" id="b-size"><label>flow size</label></div>
  <div class="controls" id="b-ctl"><label>metric</label></div>
  <div class="chart"><div id="b"></div></div>
</section>

<section>
  <h2>5 &nbsp; The verdict table</h2>
  <p><code>resolvable</code> = best-B vs worst-B mean separated by more than the
  sum of their 95&nbsp;% CI half-widths (n=3 seeds). Affected group only. If this
  is <code>no</code> everywhere &mdash; including Part B's F=31 static kill &mdash;
  &ldquo;B is irrelevant&rdquo; is robust to the strongest case we can build.</p>
  <div class="controls" id="rv-metric"><label>metric</label></div>
  <div class="tblwrap"><table id="rvtbl"></table></div>
</section>

<footer>
  Source: <code>experiments/exp30_concentrated_path_loss/data/*.csv</code> &middot;
  regenerate with <code>scripts/build_interactive.py</code> &middot;
  <code>fat_tree_1024_1os_2t_400g</code>, tornado, MPRDMA, seeds 42/43/44.
</footer>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<script>
const DATA = __PAYLOAD__;
const B_LADDER = DATA.B_LADDER, BC = DATA.B_COLOR;
// dual-window B=8: one more pseudo-"B" value ('dual') threaded through the
// same BC/B_SYMBOL maps as the real B ladder -- only the arm-string lookup
// differs (armFor below).
const DUAL_KEY = 'dual';
BC[DUAL_KEY] = DATA.DUAL_COLOR;
const armFor = b => b === DUAL_KEY ? DATA.DUAL_ARM : 'reps_b'+b;
const FCT = DATA.fct, DIAG = DATA.diag, RV = DATA.rv;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const rgba = (hex, a) => { const n = parseInt(hex.slice(1),16);
  return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`; };
const SHAPES = ['circle-open','diamond-open','triangle-up-open','triangle-down-open',
                'cross-open','x-open','star-open'];
const B_SYMBOL = Object.fromEntries(B_LADDER.map((b,i)=>[b, SHAPES[i]]));
B_SYMBOL[DUAL_KEY] = 'star-open';   // unused by the 6-entry B ladder above
const MiB = s => (s/1048576) + ' MiB';

function theme() {
  const ink = css('--ink'), grid = css('--hairline'), paper = css('--surface');
  return { paper_bgcolor: paper, plot_bgcolor: paper, height: 470,
    font: { family: 'IBM Plex Sans, sans-serif', color: ink, size: 13 },
    xaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    yaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    margin: { l: 66, r: 20, t: 16, b: 48 },
    legend: { orientation: 'h', y: -0.22 },
    // 'x unified' kept so plotly_hover events + the x-axis crosshair still
    // fire/render; the native hover BOX itself is hidden via the
    // .hoverlayer{display:none} CSS rule above, and our own high-to-low
    // sorted tooltip (bindSortedHover below) replaces it visually.
    hovermode: 'x unified',
    modebar: { orientation: 'v' } };
}
const CFG = { displaylogo: false, responsive: true,
  modeBarButtonsToRemove: ['lasso2d','select2d'] };

// Small outline SVG matching each B_SYMBOL shape (same marker family Plotly
// draws on the chart), used in the tooltip instead of a plain color dot.
function shapeSVG(sym, c) {
  const s = `stroke="${c}" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"`;
  const shapes = {
    'circle-open': `<circle cx="6" cy="6" r="4.5" ${s}/>`,
    'diamond-open': `<path d="M6 1 L11 6 L6 11 L1 6 Z" ${s}/>`,
    'triangle-up-open': `<path d="M6 1 L11 10.5 L1 10.5 Z" ${s}/>`,
    'triangle-down-open': `<path d="M1 1.5 L11 1.5 L6 11 Z" ${s}/>`,
    'cross-open': `<path d="M6 1 V11 M1 6 H11" ${s}/>`,
    'x-open': `<path d="M1.5 1.5 L10.5 10.5 M10.5 1.5 L1.5 10.5" ${s}/>`,
    'star-open': `<path d="M6 0.5 L7.3 4.2 L11.3 4.2 L8.1 6.6 L9.3 10.5 L6 8.2 `
      + `L2.7 10.5 L3.9 6.6 L0.7 4.2 L4.7 4.2 Z" ${s}/>`,
  };
  return `<svg width="13" height="13" viewBox="0 0 12 12" style="flex:none;">`
    + `${shapes[sym] || shapes['circle-open']}</svg>`;
}

// Plotly's real marker symbols (esp. 'x-open') aren't simple geometric shapes
// -- pull the exact rendered path 'd' straight from the chart's own SVG
// (the point Plotly just drew for this trace/point) instead of guessing it,
// so the tooltip swatch is pixel-identical to what's on the chart. Cached per
// symbol since the path geometry only depends on symbol+size, not position.
const _markerDCache = {};
function markerShapeSVG(divId, curveNumber, pointNumber, sym, c) {
  if (!(sym in _markerDCache)) {
    let d = null;
    try {
      const traceGroups = document.querySelectorAll('#' + divId + ' .scatterlayer > .trace');
      const g = traceGroups[curveNumber];
      const pts = g && g.querySelectorAll('path.point');
      const el = pts && pts[pointNumber];
      d = el && el.getAttribute('d');
    } catch (e) { /* fall through to hand-drawn shape below */ }
    _markerDCache[sym] = d;
  }
  const d = _markerDCache[sym];
  if (!d) return shapeSVG(sym, c);   // fallback if the DOM lookup ever misses
  return `<svg width="14" height="14" viewBox="-7 -7 14 14" style="flex:none;">`
    + `<path d="${d}" stroke="${c}" fill="none" stroke-width="1.8"/></svg>`;
}

// --- custom hover tooltip: same data Plotly's unified hover would show, but
// sorted high-to-low by y instead of by trace order. One shared floating div,
// positioned at the cursor; bound once per chart div (Plotly.react keeps the
// DOM node + listeners across redraws, so re-binding on every draw() would
// stack duplicate handlers).
let _tipEl;
function _tip() {
  if (!_tipEl) {
    _tipEl = document.createElement('div');
    _tipEl.style.cssText = 'position:fixed;pointer-events:none;z-index:9999;'
      + 'display:none;max-width:280px;padding:8px 11px;border-radius:8px;'
      + 'font:500 12.5px/1.6 "IBM Plex Mono",monospace;box-shadow:0 4px 16px rgba(0,0,0,.18);';
    document.body.appendChild(_tipEl);
  }
  // re-read theme colors every call (not just at creation) so a light/dark
  // toggle doesn't leave the tooltip showing stale colors.
  _tipEl.style.background = css('--surface');
  _tipEl.style.border = '1px solid ' + css('--hairline');
  _tipEl.style.color = css('--ink');
  return _tipEl;
}
const _hoverBound = new Set();
function bindSortedHover(id) {
  if (_hoverBound.has(id)) return;
  _hoverBound.add(id);
  const el = document.getElementById(id);
  el.on('plotly_hover', (ev) => {
    const pts = (ev.points || []).filter(p => p.data.hoverinfo !== 'skip');
    if (!pts.length) return;
    const sorted = pts.slice().sort((a, b) => b.y - a.y);
    const rows = sorted.map(p => {
      const c = (p.data.line && p.data.line.color) || '#888';
      const sym = (p.data.marker && p.data.marker.symbol) || 'circle-open';
      const pn = p.pointNumber ?? p.pointIndex ?? 0;
      const yv = (+p.y).toLocaleString(undefined, { maximumFractionDigits: 2 });
      return '<div style="display:flex;align-items:center;gap:7px;white-space:nowrap;">'
        + markerShapeSVG(id, p.curveNumber, pn, sym, c)
        + '<span>' + p.data.name + ':&nbsp;' + yv + '</span></div>';
    }).join('');
    const tip = _tip();
    tip.innerHTML = '<div style="color:' + css('--muted') + ';margin-bottom:5px;">x = '
      + pts[0].x + '</div>' + rows;
    tip.style.display = 'block';
    const me = ev.event;
    if (me) {
      const vw = innerWidth, vh = innerHeight;
      const left = me.clientX + 16 + 280 > vw ? me.clientX - 296 : me.clientX + 16;
      const top = me.clientY + 200 > vh ? me.clientY - 200 : me.clientY + 14;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    }
  });
  el.on('plotly_unhover', () => { if (_tipEl) _tipEl.style.display = 'none'; });
}
function draw(id, traces, layout) {
  Plotly.react(id, traces, layout, CFG);
  bindSortedHover(id);
  requestAnimationFrame(() => Plotly.Plots.resize(document.getElementById(id)));
}
function ciBand(xs, ys, cis, b) {
  return { x: [...xs, ...xs.slice().reverse()],
    y: [...ys.map((y,i)=>y+cis[i]), ...ys.map((y,i)=>Math.max(y-cis[i],0)).reverse()],
    fill: 'toself', fillcolor: rgba(BC[b], 0.13), line: { width: 0 }, mode: 'lines',
    hoverinfo: 'skip', showlegend: false, type: 'scatter', legendgroup: 'B'+b };
}
function lineTrace(xs, ys, b) {
  const c = BC[b];
  const name = b === DUAL_KEY ? DATA.DUAL_LABEL : 'B='+b;
  return { x: xs, y: ys, name, mode: 'lines+markers', type: 'scatter',
    legendgroup: 'B'+b, line: { color: c, width: 2.4,
      dash: b === DUAL_KEY ? 'dash' : 'solid' },
    marker: { color: c, symbol: B_SYMBOL[b] ?? 'circle-open', size: 8,
              line: { color: c, width: 1.8 } } };
}

// generic "metric vs x" for a filtered slice; rows already have x + col + col_ci
function drawVsX(divId, rows, col, xlabel, ylabel, healthy) {
  const traces = [];
  for (const b of [...B_LADDER, DUAL_KEY]) {
    const rs = rows.filter(r => r.arm === armFor(b)).sort((p,q)=>p.x-q.x);
    if (!rs.length) continue;
    const xs = rs.map(r=>r.x), ys = rs.map(r=>r[col]);
    const cis = rs.map(r=>r[col+'_ci'] ?? 0);
    traces.push(ciBand(xs, ys, cis, b));
    traces.push(lineTrace(xs, ys, b));
  }
  const t = theme();
  t.xaxis.title = xlabel; t.yaxis.title = ylabel;
  const xv = [...new Set(traces.flatMap(tr=>tr.x))].sort((a,b)=>a-b);
  t.xaxis.tickvals = xv;
  if (healthy != null && xv.length)
    t.shapes = [{type:'line', x0:xv[0], x1:xv[xv.length-1], y0:healthy, y1:healthy,
      line:{color:css('--muted'), width:1, dash:'dot'}}];
  draw(divId, traces, t);
}

const affFCT = FCT.filter(r => r.group === 'affected');
const affDIAG = DIAG.filter(r => r.group === 'affected');
const sizes = [...new Set(affFCT.map(r=>r.size))].sort((a,b)=>a-b);

const FCT_METRICS = { 'p50 FCT (us)':'p50_fct_us', 'p95 FCT (us)':'p95_fct_us',
  'p99 FCT (us)':'p99_fct_us', 'max FCT (us)':'max_fct_us' };
const DIAG_METRICS = { 'ECN acks / host':'ecn_per_host', 'RTOs / host':'rto_per_host',
  'RTS / host':'rts_per_host', 'freeze entries / host':'freeze_entries_per_host',
  'time in freezing (us)':'freeze_us_mean', 'random-EV draws / host':'ev_random_per_host',
  'random-EV rate (draws/pkt)':'ev_random_rate' };

function healthyFor(part, size, metric) {
  if (metric !== 'p50_fct_us' && metric !== 'p95_fct_us') return null;
  const r = affFCT.find(x => x.part===part && x.size===size
    && (x.x===0) && x.arm==='reps_b8');
  return r ? r[metric] : null;
}

const S = { a1: sizes[0], a2: sizes[0], d1: sizes[0], bSize: sizes[0],
            a1m:'p99 FCT (us)', a2m:'p99 FCT (us)', d1m:'random-EV draws / host',
            bm:'p99 FCT (us)', rvm:'p99_fct_us' };

function drawA1(){ const c=FCT_METRICS[S.a1m];
  drawVsX('a1', affFCT.filter(r=>r.part==='a1'&&r.size===S.a1), c,
    '# degraded ToR0 uplinks n  (severity n/32)', S.a1m, healthyFor('a1',S.a1,c)); }
function drawA2(){ const c=FCT_METRICS[S.a2m];
  drawVsX('a2', affFCT.filter(r=>r.part==='a2'&&r.size===S.a2), c,
    'link degradation (%)  -- 8 fixed ToR0 uplinks', S.a2m, null); }
function drawD1(){ const c=DIAG_METRICS[S.d1m];
  drawVsX('d1', affDIAG.filter(r=>r.part==='a1'&&r.size===S.d1), c,
    '# degraded ToR0 uplinks n', S.d1m, null); }
function drawB(){ const c=FCT_METRICS[S.bm] || DIAG_METRICS[S.bm];
  const rows = (S.bm in FCT_METRICS ? affFCT : affDIAG)
    .filter(r=>r.part==='b' && r.size===S.bSize);
  drawVsX('b', rows, c, '# ToR0 uplinks permanently killed, F  (severity F/32, static)',
    S.bm, (S.bm in FCT_METRICS) ? healthyFor('b', S.bSize, c) : null);
}

function drawTable() {
  const rows = RV.filter(r => r.metric === S.rvm)
    .sort((a,b) => a.part.localeCompare(b.part) || a.size-b.size || a.ef-b.ef || a.x-b.x);
  const h = `<thead><tr><th>part</th><th>size</th><th>ef</th><th>x</th>
    <th>best B</th><th>worst B</th><th>spread</th><th>&Sigma; CI</th><th>resolvable</th></tr></thead>`;
  const body = rows.map(r => {
    const yes = r.resolvable === true || r.resolvable === 'True';
    return `<tr><td>${r.part}</td><td>${MiB(r.size)}</td><td>${r.ef}</td><td>${r.x}</td>
      <td>B${r.best_b} (${(+r.best_val).toFixed(1)})</td>
      <td>B${r.worst_b} (${(+r.worst_val).toFixed(1)})</td>
      <td>${(+r.spread).toFixed(2)}</td><td>${(+r.ci_sum).toFixed(2)}</td>
      <td><span class="pill ${yes?'yes':'no'}">${yes?'yes':'no'}</span></td></tr>`;
  }).join('');
  document.getElementById('rvtbl').innerHTML = h + '<tbody>' + body + '</tbody>';
}

function tiles() {
  const at = (arr, f) => { const r = arr.find(f); return r; };
  const worstA1 = affFCT.filter(r=>r.part==='a1' && r.size===sizes[0]
    && r.x===Math.max(...affFCT.filter(x=>x.part==='a1').map(x=>x.x)));
  const anyRes = RV.some(r => (r.resolvable===true||r.resolvable==='True')
    && (r.metric.includes('fct')));
  const bMax = affFCT.filter(r=>r.part==='b');
  const bFMax = bMax.length ? Math.max(...bMax.map(r=>r.x)) : 0;
  const b1 = at(affDIAG, r=>r.part==='b' && r.x===bFMax && r.arm==='reps_b1' && r.size===sizes[0]);
  const b32 = at(affDIAG, r=>r.part==='b' && r.x===bFMax && r.arm==='reps_b32' && r.size===sizes[0]);
  const b8m = at(affFCT, r=>r.part==='b' && r.x===bFMax && r.arm==='reps_b8' && r.size===sizes[0]);
  const b8d = at(affFCT, r=>r.part==='b' && r.x===bFMax && r.arm===DATA.DUAL_ARM && r.size===sizes[0]);
  const T = [
    ['B resolvable on FCT', anyRes ? 'somewhere' : 'nowhere', anyRes ? 'bad' : 'good',
     'see the verdict table'],
    ['flow sizes', sizes.map(MiB).join('  /  '), '', '4 MiB = exp27 resonance peak'],
    ['Part B max kill', bFMax + '/32 uplinks dead, static', '', 'whole ToR0, real Pipe::_failed'],
    ['random-EV draws @ max kill',
     (b1&&b32) ? `${Math.round(b1.ev_random_per_host)} vs ${Math.round(b32.ev_random_per_host)}` : '?',
     '', 'B=1 vs B=32, ToR0 senders'],
    ['dual-window vs mprdma, Part B max kill',
     (b8m&&b8d) ? `${Math.round(b8d.p99_fct_us)} vs ${Math.round(b8m.p99_fct_us)} µs` : '?',
     '', 'p99 FCT, B=8 both arms, ' + MiB(sizes[0])],
  ];
  document.getElementById('tiles').innerHTML = T.map(([k,v,c,s]) =>
    `<div class="tile"><p class="k">${k}</p><div class="v ${c}">${v}</div>
     <div class="s">${s}</div></div>`).join('');
}

function cfgLine() {
  document.getElementById('cfg').innerHTML =
    '<code>fat_tree_1024_1os_2t_400g</code> &middot; tornado &middot; '
    + '<code>-use_srv6 -paths 32</code> &middot; <code>-sender_cc_algo mprdma</code> '
    + '(B ladder) plus one <code>dual_mprdma_reps</code> point at B=8, same LB/'
    + 'buffer/severity/exit_freeze flags, CC only &mdash; <em>' + DATA.DUAL_LABEL
    + '</em> in red &middot; '
    + '<code>-q 101 -ecn 25 76 -cwnd 151</code> &middot; <code>-exit_freeze 200us</code> '
    + '(both parts) &middot; seeds 42/43/44 &middot; '
    + '<code>-disable_tor_ecn</code> omitted (paper-faithful)';
}

function radio(host, names, current, cb) {
  const el = document.getElementById(host); if (!el) return;
  names.forEach(n => {
    const b = document.createElement('button');
    b.textContent = n; b.setAttribute('aria-pressed', String(n) === String(current));
    b.onclick = () => { [...el.querySelectorAll('button')].forEach(x =>
      x.setAttribute('aria-pressed', x === b)); cb(n); };
    el.appendChild(b);
  });
}

radio('a1-size', sizes.map(MiB), MiB(S.a1), v => { S.a1 = sizes[sizes.map(MiB).indexOf(v)]; drawA1(); });
radio('a1-ctl', Object.keys(FCT_METRICS), S.a1m, v => { S.a1m = v; drawA1(); });
radio('a2-size', sizes.map(MiB), MiB(S.a2), v => { S.a2 = sizes[sizes.map(MiB).indexOf(v)]; drawA2(); });
radio('a2-ctl', Object.keys(FCT_METRICS), S.a2m, v => { S.a2m = v; drawA2(); });
radio('d1-size', sizes.map(MiB), MiB(S.d1), v => { S.d1 = sizes[sizes.map(MiB).indexOf(v)]; drawD1(); });
radio('d1-ctl', Object.keys(DIAG_METRICS), S.d1m, v => { S.d1m = v; drawD1(); });
radio('b-size', sizes.map(MiB), MiB(S.bSize), v => { S.bSize = sizes[sizes.map(MiB).indexOf(v)]; drawB(); });
radio('b-ctl', [...Object.keys(FCT_METRICS), ...Object.keys(DIAG_METRICS)], S.bm,
  v => { S.bm = v; drawB(); });
radio('rv-metric', ['p50_fct_us','p95_fct_us','p99_fct_us','max_fct_us',
  'ecn_per_host','rto_per_host','freeze_entries_per_host','ev_random_per_host','ev_random_rate'],
  S.rvm, v => { S.rvm = v; drawTable(); });

function drawAll() { cfgLine(); tiles(); drawA1(); drawA2(); drawD1(); drawB(); drawTable(); }
drawAll();

let rt;
addEventListener('resize', () => { clearTimeout(rt);
  rt = setTimeout(() => document.querySelectorAll('.chart > div').forEach(el => {
    if (el._fullLayout) Plotly.Plots.resize(el); }), 120); });
const mq = window.matchMedia('(prefers-color-scheme: dark)');
mq.addEventListener && mq.addEventListener('change', drawAll);
new MutationObserver(drawAll).observe(document.documentElement,
  { attributes: true, attributeFilter: ['data-theme'] });
</script>
"""


def main():
    html = HTML.replace("__PAYLOAD__", json.dumps(payload()))
    OUT.write_text(_asciiify(html), encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()

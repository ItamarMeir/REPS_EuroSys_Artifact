#!/usr/bin/env python3
"""
Emit plots/interactive.html -- a self-contained, zoomable Plotly view of the
exp29 result CSVs (aggregate29.py output). No server; Plotly from cdnjs.

    python3 build_interactive.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent.parent / "plots" / "interactive.html"

B_LADDER = [1, 2, 4, 8, 32]
# viridis sampled at the B_LADDER positions -- matches the static PNGs / exp26-28
B_COLOR = {1: "#440154", 2: "#3b528b", 4: "#21918c", 8: "#5ec962", 32: "#fde725"}

# dual-window REPS+MPRDMA at B=8 -- one extra series alongside the mprdma B
# ladder, same LB/buffer flags as reps_b8, CC swapped (see common29.base_flags)
DUAL_ARM = "reps_b8_dual"
DUAL_COLOR = "#dc2626"
DUAL_LABEL = "B=8 dual-window"


def load():
    fct = pd.read_csv(D / "fct.csv")
    resp = pd.read_csv(D / "response.csv")
    ts = pd.read_csv(D / "timeseries.csv")
    rv = pd.read_csv(D / "resolvable.csv")
    ts = ts[(ts.group == "affected") & (ts.ef == 100)][
        ["F", "arm", "t_us", "ef", "d_rto", "d_freeze_entries", "d_ev_random",
         "d_ecn_acks", "frozen_frac"]].round(4)
    return fct, resp, ts, rv


def payload():
    fct, resp, ts, rv = load()
    diag = pd.read_csv(D / "diagnostics.csv")
    return {
        "B_LADDER": B_LADDER,
        "B_COLOR": B_COLOR,
        "DUAL_ARM": DUAL_ARM,
        "DUAL_COLOR": DUAL_COLOR,
        "DUAL_LABEL": DUAL_LABEL,
        "fct": fct.to_dict(orient="records"),
        "resp": resp.to_dict(orient="records"),
        "ts": ts.to_dict(orient="records"),
        "rv": rv.to_dict(orient="records"),
        "diag": diag.to_dict(orient="records"),
    }


HTML = r"""<title>exp29 Failure-Response Explorer</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f6f7f9;
  --surface: #ffffff;
  --ink: #1a1f2b;
  --muted: #5b6472;
  --hairline: #e3e6ec;
  --accent: #c2410c;
  --accent-soft: #fde9dc;
  --good: #15803d;
  --bad: #b91c1c;
  --shadow: 0 1px 2px rgba(20,25,40,.06), 0 8px 24px rgba(20,25,40,.05);
}
:root:not([data-theme="light"]) {
  @media (prefers-color-scheme: dark) {
    --ground: #101319;
    --surface: #191d26;
    --ink: #e6e9ef;
    --muted: #99a1b0;
    --hairline: #2b313d;
    --accent: #fb923c;
    --accent-soft: #3a2417;
    --good: #4ade80;
    --bad: #f87171;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"] {
  --ground: #101319;
  --surface: #191d26;
  --ink: #e6e9ef;
  --muted: #99a1b0;
  --hairline: #2b313d;
  --accent: #fb923c;
  --accent-soft: #3a2417;
  --good: #4ade80;
  --bad: #f87171;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
body {
  background: var(--ground);
  color: var(--ink);
  font: 400 16px/1.6 "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  margin: 0;
}
.wrap { max-width: 1120px; margin: 0 auto; padding: 48px 24px 96px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 20px; margin-bottom: 8px; }
.eyebrow {
  font: 500 12px/1 "IBM Plex Mono", monospace;
  letter-spacing: .14em; text-transform: uppercase; color: var(--accent);
  margin: 0 0 12px;
}
h1 {
  font-weight: 600; font-size: clamp(26px, 4vw, 38px); line-height: 1.15;
  margin: 0; text-wrap: balance; letter-spacing: -.01em;
}
.lede { color: var(--muted); max-width: 68ch; margin: 16px 0 0; }
.cfg { color: var(--muted); font-size: 12.5px; line-height: 1.7; max-width: 92ch; margin: 12px 0 0; }
.cfg code { font-size: .92em; background: none; padding: 0; color: var(--ink); }
.tiles {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px; margin: 32px 0 8px;
}
.tile {
  background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; padding: 18px 20px; box-shadow: var(--shadow);
}
.tile .k {
  font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin: 0 0 10px;
}
.tile .v {
  font: 500 27px/1.05 "IBM Plex Mono", monospace; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
}
.tile .v.good { color: var(--good); }
.tile .v.bad { color: var(--bad); }
.tile .s { font-size: 13px; color: var(--muted); margin-top: 8px; }
section { margin-top: 56px; }
h2 {
  font-weight: 600; font-size: 21px; margin: 0 0 6px;
  padding-bottom: 8px; border-bottom: 1px solid var(--hairline);
}
section > p { color: var(--muted); max-width: 68ch; margin: 12px 0 18px; }
.controls {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 0 0 14px; font: 500 13px/1 "IBM Plex Mono", monospace;
}
.controls label { color: var(--muted); letter-spacing: .04em; }
.controls button {
  font: inherit; color: var(--ink); background: var(--surface);
  border: 1px solid var(--hairline); border-radius: 7px; padding: 7px 12px;
  cursor: pointer;
}
.controls button[aria-pressed="true"] {
  background: var(--accent); color: #fff; border-color: var(--accent);
}
.controls button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.chart {
  background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); padding: 10px;
  overflow-x: auto;
}
.chart > div { min-width: 640px; height: 470px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin-top: 4px; }
.tblwrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); }
th, td {
  text-align: right; padding: 9px 14px; border-bottom: 1px solid var(--hairline);
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
th { font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
.pill {
  display: inline-block; font: 500 11px/1 "IBM Plex Mono", monospace;
  padding: 4px 9px; border-radius: 999px;
}
.pill.no { background: color-mix(in srgb, var(--good) 16%, transparent); color: var(--good); }
.pill.yes { background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent); }
code { font: 500 .92em "IBM Plex Mono", monospace; background: var(--accent-soft);
  padding: 1px 5px; border-radius: 4px; }
footer { margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--hairline);
  color: var(--muted); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
<header>
  <p class="eyebrow">REPS EuroSys artifact &middot; exp29 &middot; 162 runs</p>
  <h1>REPS failure-response, zoomable</h1>
  <p class="lede">One ToR loses <strong>F</strong> of its 32 spine uplinks for
  t&nbsp;&isin;&nbsp;(100,&nbsp;200)&nbsp;&micro;s, then they recover. Every affected host
  takes one RTO, freezes, waits out <code>exit_freeze</code>, thaws. These are the
  seed-averaged curves with 95&nbsp;% CI &mdash; drag to zoom, double-click to reset,
  click a B in the legend to hide it.</p>
  <p class="cfg"><code>fat_tree_1024_1os_2t_400g</code> &middot; tornado 16&nbsp;MiB
  &middot; <code>-use_srv6 -paths 32</code> &middot; <code>-sender_cc_algo mprdma</code>
  (B ladder) plus one <code>dual_mprdma_reps</code> point at B=8, same LB/buffer/
  failure/exit_freeze flags, CC only &mdash; <em>B=8 dual-window</em> in red
  &middot; <code>-q 101 -ecn 25 76 -cwnd 151</code> &middot;
  <code>-exit_freeze 100&nbsp;&micro;s</code> (each freeze holds for the full
  100&nbsp;&micro;s timeout &mdash; not recovery-aware &mdash; then force-thaws)
  &middot; failure window = one min-RTO &middot; seeds 42/43/44 at every point
  &middot; <code>-disable_tor_ecn</code> deliberately omitted (paper-faithful).</p>
</header>

<div class="tiles" id="tiles"></div>

<section>
  <h2>1 &nbsp; Flow completion time vs F</h2>
  <p>Affected-host FCT percentiles against the number of dead paths, one line +
  95&nbsp;% CI band per B. Healthy baseline 356&nbsp;&micro;s (dotted). FCT climbs
  smoothly with F and the B bands sit on top of each other &mdash; buffer size
  does not move FCT at any severity.</p>
  <div class="controls" id="fct-ctl"><label>metric</label></div>
  <div class="chart"><div id="fct"></div></div>
</section>

<section>
  <h2>2 &nbsp; Diagnostics vs F</h2>
  <p>Per-host counters against F. <em>during</em>/<em>recovery</em> = per-host
  count summed over the failure window (100&ndash;200&nbsp;&micro;s) vs everything
  after; <em>flow</em> = whole-flow per-host total off the finish line.
  <em>frozen fraction</em> is a 0&ndash;1 duty cycle &mdash; the share of the
  window the average host spent in REPS&rsquo;s frozen state (post-RTO hold:
  recycle known-good EVs, no fresh spraying, until <code>exit_freeze</code>).
  RTOs are ~linear in F; <code>freeze_us</code> sits at exactly
  <code>exit_freeze</code>; <code>random-EV draws</code> is the one metric where
  B splits hard (B=1 empties its buffer on thaw and re-explores).</p>
  <div class="controls" id="diag-ctl"><label>metric</label></div>
  <div class="chart"><div id="diag"></div></div>
</section>

<section>
  <h2>3 &nbsp; Time analysis</h2>
  <p>A logger snapshots every affected host&rsquo;s counters every
  <strong>10&nbsp;&micro;s</strong> and reports the delta since the previous
  snapshot &mdash; so each point is one <em>non-overlapping</em> 10&nbsp;&micro;s
  bin (t&minus;10, t], not a sliding window; the counts are then meaned over the
  32 hosts and the 3 seeds. The y-axis is a <em>rate</em>: &ldquo;RTOs / host /
  10&nbsp;&micro;s&rdquo; = retransmission timeouts per host in each 10&nbsp;&micro;s
  bin. A spike of 50 means each host timed out ~50 times in that one bin; it
  falls to ~0 once hosts freeze (a frozen host sends nothing, so nothing times
  out). <em>frozen fraction</em> is the exception &mdash; not a count but a
  0&ndash;1 duty cycle, the share of the 10&nbsp;&micro;s slice the host spent in
  REPS&rsquo;s <em>frozen</em> state (after an RTO it stops spraying fresh
  entropy, recycles only known-good EVs, and holds that for
  <code>exit_freeze</code> before force-thawing). Its value <em>is</em>
  frozen-time&nbsp;&divide;&nbsp;10&nbsp;&micro;s &mdash; the fraction of the bin the
  host was frozen, 1.0 = the whole bin &mdash; so it is a ratio in [0,&nbsp;1],
  not a count.
  Dashed line = links fail (t=100&nbsp;&micro;s), dotted = links recover
  (t=200&nbsp;&micro;s); <code>exit_freeze</code>=100&nbsp;&micro;s.
  Only B=1 and B=8 are drawn (B=1 empties its buffer on thaw and re-explores hard;
  B=8 replays cached EVs); the grey band spans B&nbsp;&isin;&nbsp;{2,&nbsp;4,&nbsp;32}.</p>
  <div class="controls" id="ts-ctl"><label>F</label></div>
  <div class="controls" id="tsm-ctl"><label>metric</label></div>
  <div class="chart"><div id="ts"></div></div>
</section>

<section>
  <h2>4 &nbsp; The verdict table</h2>
  <p><code>resolvable</code> = best-B vs worst-B mean separated by more than the sum
  of their 95&nbsp;% CI half-widths. <code>exit_freeze</code>=100&nbsp;&micro;s, affected hosts.
  <code>phase</code>: <code>during</code>/<code>recovery</code> = failure-window metric;
  <code>flow</code> = whole-flow total.</p>
  <div class="tblwrap"><table id="rvtbl"></table></div>
</section>

<footer>
  Source: <code>experiments/exp29_failure_response/data/*.csv</code> &middot;
  regenerate with <code>scripts/build_interactive.py</code> &middot;
  fabric <code>fat_tree_1024_1os_2t_400g</code>, tornado 16&nbsp;MiB, MPRDMA,
  seeds 42/43/44.
</footer>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<script>
const DATA = __PAYLOAD__;
const B_LADDER = DATA.B_LADDER, BC = DATA.B_COLOR;
// dual-window B=8: treated as one more pseudo-"B" value ('dual') threaded
// through the same BC/B_SYMBOL maps used for the real B ladder, so ciBand()/
// lineTrace() need no changes -- only the arm-string lookup differs (below).
const DUAL_KEY = 'dual';
BC[DUAL_KEY] = DATA.DUAL_COLOR;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function theme() {
  const ink = css('--ink'), grid = css('--hairline'), paper = css('--surface');
  return {
    paper_bgcolor: paper, plot_bgcolor: paper,
    height: 470,
    font: { family: 'IBM Plex Sans, sans-serif', color: ink, size: 13 },
    xaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    yaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    margin: { l: 64, r: 20, t: 16, b: 48 },
    legend: { orientation: 'h', y: -0.22 },
    hovermode: 'x unified',
    modebar: { orientation: 'v' },
  };
}
const CFG = { displaylogo: false, responsive: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'] };

// Plotly.react can measure a mid-layout container and collapse the plot; a
// resize on the next frame settles it.
function draw(id, traces, layout) {
  Plotly.react(id, traces, layout, CFG);
  requestAnimationFrame(() => Plotly.Plots.resize(document.getElementById(id)));
}

const rgba = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`;
};

// ---- data helpers ----
const FCT = DATA.fct, RESP = DATA.resp, TS = DATA.ts, RV = DATA.rv;
const affF = FCT.filter(r => r.group === 'affected');
const Fs = [...new Set(affF.filter(r => r.ef === 100).map(r => r.F))].sort((a,b)=>a-b);

// match the static PNGs: viridis-over-B_LADDER + hollow markers cycled o D ^ v P
const SHAPES = ['circle-open', 'diamond-open', 'triangle-up-open',
                'triangle-down-open', 'cross-open', 'x-open', 'star-open'];
const B_SYMBOL = Object.fromEntries(B_LADDER.map((b, i) => [b, SHAPES[i]]));
B_SYMBOL[DUAL_KEY] = 'star-open';   // unused by the 5-entry B ladder above

function ciBand(xs, ys, cis, b) {
  // every metric here is non-negative -- clip the lower edge at 0 so the band
  // never dips below the axis on a near-zero mean (e.g. frozen_frac, RTO count)
  return {
    x: [...xs, ...xs.slice().reverse()],
    y: [...ys.map((y,i)=>y+cis[i]), ...ys.map((y,i)=>Math.max(y-cis[i], 0)).reverse()],
    fill: 'toself', fillcolor: rgba(BC[b], 0.13), line: { width: 0 },
    mode: 'lines',   // else Plotly auto-adds markers at every polygon vertex
    hoverinfo: 'skip', showlegend: false, type: 'scatter',
    legendgroup: 'B' + b,   // toggled together with the B line in the legend
  };
}
function lineTrace(xs, ys, b, name, dash) {
  const color = BC[b];
  return { x: xs, y: ys, name, mode: 'lines+markers', type: 'scatter',
    legendgroup: 'B' + b,
    line: { color, width: 2.4, dash: dash || 'solid' },
    marker: { color, symbol: B_SYMBOL[b] ?? 'circle-open', size: 8,
              line: { color, width: 1.8 } } };
}

// ---- sections 1 & 2: metrics vs F ----
const DIAG = DATA.diag;
// src: fct = data/fct.csv | during/recovery = data/response.csv phase |
//      flow = data/diagnostics.csv (whole-flow per-host)
const FCT_METRICS = {
  'p50 FCT (µs)': {src:'fct', col:'p50_fct_us'},
  'p95 FCT (µs)': {src:'fct', col:'p95_fct_us'},
  'p99 FCT (µs)': {src:'fct', col:'p99_fct_us'},
  'max FCT (µs)': {src:'fct', col:'max_fct_us'},
};
const DIAG_METRICS = {
  'RTOs/host (during)':        {src:'during', col:'d_rto'},
  'RTOs/host (recovery)':      {src:'recovery', col:'d_rto'},
  'frozen frac (during)':      {src:'during', col:'frozen_frac'},
  'frozen frac (recovery)':    {src:'recovery', col:'frozen_frac'},
  'ECN acks/host (flow)':      {src:'flow', col:'ecn_per_host'},
  'RTOs/host (flow)':          {src:'flow', col:'rto_per_host'},
  'RTS/host (flow)':           {src:'flow', col:'rts_per_host'},
  'time in freezing µs (flow)':{src:'flow', col:'freeze_us_mean'},
  'random-EV draws/host (flow)':{src:'flow', col:'ev_random_per_host'},
  'random-EV rate draws/pkt (flow)':{src:'flow', col:'ev_random_rate'},
};
const armFor = b => b === DUAL_KEY ? DATA.DUAL_ARM : `reps_b${b}`;
function sevRows(spec) {
  if (spec.src === 'fct')
    return b => affF.filter(r => r.ef===100 && r.arm===armFor(b)).sort((x,y)=>x.F-y.F);
  if (spec.src === 'flow')
    return b => DIAG.filter(r => r.group==='affected' && r.ef===100
        && r.arm===armFor(b)).sort((x,y)=>x.F-y.F);
  return b => RESP.filter(r => r.group==='affected' && r.ef===100 && r.phase===spec.src
      && r.arm===armFor(b)).sort((x,y)=>x.F-y.F);
}
function drawVsF(divId, spec, label) {
  const rows = sevRows(spec), traces = [];
  for (const b of [...B_LADDER, DUAL_KEY]) {
    const rs = rows(b); if (!rs.length) continue;
    const xs = rs.map(r=>r.F), ys = rs.map(r=>r[spec.col]);
    const cis = rs.map(r=>r[spec.col+'_ci'] ?? 0);
    traces.push(ciBand(xs, ys, cis, b));
    traces.push(lineTrace(xs, ys, b, b === DUAL_KEY ? DATA.DUAL_LABEL : 'B='+b));
  }
  const t = theme();
  t.xaxis.title = '# failed ToR0 spine uplinks (F)';
  t.xaxis.tickvals = Fs; t.yaxis.title = label;
  if (spec.src==='fct') t.shapes = [{type:'line', x0:Fs[0], x1:Fs[Fs.length-1],
    y0:356, y1:356, line:{color:css('--muted'), width:1, dash:'dot'}}];
  draw(divId, traces, t);
}
const drawFct = label => drawVsF('fct', FCT_METRICS[label], label);
const drawDiag = label => drawVsF('diag', DIAG_METRICS[label], label);

// ---- 3. time analysis ----
const TS_METRICS = {
  'ECN acks / host / 10µs': 'd_ecn_acks',
  'RTOs / host / 10µs': 'd_rto',
  'freeze entries / host / 10µs': 'd_freeze_entries',
  'frozen fraction / 10µs': 'frozen_frac',
  'random-EV draws / host / 10µs': 'd_ev_random',
};
let tsF = 8, tsMetric = 'RTOs / host / 10µs';
function drawTS() {
  const col = TS_METRICS[tsMetric], traces = [];
  for (const b of [...B_LADDER, DUAL_KEY]) {
    const rs = TS.filter(r => r.ef===100 && r.F===tsF && r.arm===armFor(b))
      .sort((x,y)=>x.t_us-y.t_us);
    if (!rs.length) continue;
    traces.push({ x: rs.map(r=>r.t_us), y: rs.map(r=>r[col]),
      name: b === DUAL_KEY ? DATA.DUAL_LABEL : 'B='+b,
      mode:'lines', type:'scatter',
      line:{color:BC[b], width:2, dash: b === DUAL_KEY ? 'dash' : 'solid'} });
  }
  const t = theme();
  t.xaxis.title = 't (µs)'; t.yaxis.title = tsMetric;
  t.hovermode = 'x unified';
  t.shapes = [
    {type:'line', x0:100, x1:100, yref:'paper', y0:0, y1:1,
      line:{color:css('--ink'), width:1, dash:'dash'}},
    {type:'line', x0:200, x1:200, yref:'paper', y0:0, y1:1,
      line:{color:css('--ink'), width:1, dash:'dot'}},
  ];
  draw('ts', traces, t);
}

// ---- 5. table ----
function drawTable() {
  const order = ['p50_fct_us','p99_fct_us','max_fct_us','d_rto','frozen_frac','d_ev_random'];
  const rows = RV.filter(r => r.ef === 100)
    .sort((a,b) => order.indexOf(a.metric) - order.indexOf(b.metric)
      || a.F - b.F || (a.phase||'').localeCompare(b.phase||''));
  const h = `<thead><tr><th>metric</th><th>phase</th><th>F</th>
    <th>best B</th><th>worst B</th><th>spread</th><th>Σ CI</th><th>resolvable</th></tr></thead>`;
  const body = rows.map(r => {
    const yes = r.resolvable === true || r.resolvable === 'True';
    return `<tr><td>${r.metric}</td><td>${r.phase==='-'?'':r.phase}</td><td>${r.F}</td>
      <td>B${r.best_b} (${(+r.best_val).toFixed(1)})</td>
      <td>B${r.worst_b} (${(+r.worst_val).toFixed(1)})</td>
      <td>${(+r.spread).toFixed(1)}</td><td>${(+r.ci_sum).toFixed(1)}</td>
      <td><span class="pill ${yes?'yes':'no'}">${yes?'yes':'no'}</span></td></tr>`;
  }).join('');
  document.getElementById('rvtbl').innerHTML = h + '<tbody>' + body + '</tbody>';
}

// ---- tiles ----
function tiles() {
  const p99 = (F, arm) => {
    const r = affF.find(x=>x.ef===100 && x.F===F && x.arm===arm);
    return r ? Math.round(r.p99_fct_us) : '?';
  };
  const evr = (F, arm) => {
    const r = DIAG.find(x=>x.group==='affected' && x.ef===100 && x.F===F && x.arm===arm);
    return r ? Math.round(r.ev_random_per_host) : '?';
  };
  const dualP99_31 = p99(31, DATA.DUAL_ARM);
  const T = [
    ['B resolvable on FCT', 'none', 'good', 'p50 / p99 / max, every F 1–31'],
    ['affected p99 FCT, F=31', `${p99(31,'reps_b8')} µs`, 'bad', 'healthy baseline 356 µs'],
    ['random-EV draws / host', `${evr(8,'reps_b1')} vs ${evr(8,'reps_b8')}`, '',
     'B=1 vs B=8 at F=8 — the one place B splits'],
    ['fastLossRecovery', 'never', 'good', 'fast_loss = 0 at every F'],
    ['dual-window vs mprdma, F=31', `${dualP99_31} vs ${p99(31,'reps_b8')} µs`, '',
     'p99 FCT, B=8 both arms — same CI/failure setup, CC only'],
  ];
  document.getElementById('tiles').innerHTML = T.map(([k,v,c,s]) =>
    `<div class="tile"><p class="k">${k}</p><div class="v ${c}">${v}</div>
     <div class="s">${s}</div></div>`).join('');
}

// ---- control builders ----
function radio(host, names, current, cb) {
  const el = document.getElementById(host);
  names.forEach(n => {
    const b = document.createElement('button');
    b.textContent = n; b.setAttribute('aria-pressed', n === current);
    b.onclick = () => {
      [...el.querySelectorAll('button')].forEach(x =>
        x.setAttribute('aria-pressed', x === b));
      cb(n);
    };
    el.appendChild(b);
  });
}

radio('fct-ctl', Object.keys(FCT_METRICS), 'p99 FCT (µs)', drawFct);
radio('diag-ctl', Object.keys(DIAG_METRICS), 'random-EV draws/host (flow)', drawDiag);
radio('ts-ctl', Fs.map(String), String(tsF), v => { tsF = +v; drawTS(); });
radio('tsm-ctl', Object.keys(TS_METRICS), tsMetric, v => { tsMetric = v; drawTS(); });

function drawAll() {
  drawFct(document.querySelector('#fct-ctl [aria-pressed="true"]').textContent);
  drawDiag(document.querySelector('#diag-ctl [aria-pressed="true"]').textContent);
  drawTS();
}
tiles(); drawTable(); drawAll();

let rt;
addEventListener('resize', () => {
  clearTimeout(rt);
  rt = setTimeout(() => document.querySelectorAll('.chart > div').forEach(el => {
    if (el._fullLayout) Plotly.Plots.resize(el);
  }), 120);
});

const mq = window.matchMedia('(prefers-color-scheme: dark)');
mq.addEventListener && mq.addEventListener('change', drawAll);
const mo = new MutationObserver(drawAll);
mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
</script>
"""


def _asciiify(html: str) -> str:
    """Emit a pure-ASCII file so a mis-negotiated charset can't mojibake it:
    non-ASCII becomes &#N; in HTML/CSS and \\uXXXX inside the inline <script>."""
    import re
    non = re.compile(r"[^\x00-\x7f]")
    out = []
    for part in re.split(r"(<script>\n[\s\S]*?</script>)", html):
        if part.startswith("<script>\n"):
            out.append(non.sub(lambda m: "\\u%04x" % ord(m.group(0)), part))
        else:
            out.append(non.sub(lambda m: "&#%d;" % ord(m.group(0)), part))
    return "".join(out)


def main():
    html = HTML.replace("__PAYLOAD__", json.dumps(payload()))
    OUT.write_text(_asciiify(html), encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()

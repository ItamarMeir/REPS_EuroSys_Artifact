#!/usr/bin/env python3
"""
Emit plots/interactive.html -- a self-contained, zoomable Plotly view of the
exp28 buffer-size / failure-severity sweep. Reuses plot_sweep.load() + agg_ci()
so the aggregation is identical to the static PNGs. Plotly from cdnjs.

    python3 build_interactive.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from plot_sweep import EXP_DIR, METRIC_COLS, XLABEL, agg_ci, load

OUT = EXP_DIR / "plots" / "interactive.html"

B_LADDER = [1, 2, 4, 8, 16, 32]
B_COLOR = {1: "#440154", 2: "#414487", 4: "#2a788e", 8: "#22a884",
           16: "#7ad151", 32: "#fde725"}

# columns worth an interactive view (speedup_vs_ops_* is all-NaN -- no OPS arm)
FCT_METRICS = {
    "p50 FCT (µs)": "p50_fct_us",
    "p95 FCT (µs)": "fct_p95_us",
    "p99 FCT (µs)": "p99_fct_us",
    "max FCT (µs)": "max_fct_us",
}
N_HOSTS = 1024   # fat_tree_1024_1os_2t -- every exp28 run

DIAG_METRICS = {
    "ECN acks / host": "ecn_per_host",
    "RTOs / host": "rto_per_host",
    "freeze entries / host": "freeze_entries_per_host",
    "time in freezing (µs, mean/host)": "freeze_us_mean",
    "random-EV draws / host": "ev_random_per_host",
    "random-EV rate (draws / pkt)": "ev_random_rate",
}


def part_payload(part: int):
    raw = load(part)
    raw = raw[raw.arm != "ops"]
    df = agg_ci(raw, METRIC_COLS)
    # aggregate28 emits freeze_entries as a fabric SUM; every other diag metric
    # is a per-host mean, so divide it down to match.
    df["freeze_entries_per_host"] = df["freeze_entries_total"] / N_HOSTS
    df["freeze_entries_per_host_ci"] = df["freeze_entries_total_ci"] / N_HOSTS
    keep = ["arm", "x", "buf_size"] + [
        c for c in df.columns
        if c in set(FCT_METRICS.values()) | set(DIAG_METRICS.values())
        or c.rstrip("_ci") in set(FCT_METRICS.values()) | set(DIAG_METRICS.values())]
    df = df[[c for c in keep if c in df.columns]].replace({np.nan: None})
    return dict(xlabel=XLABEL[part], rows=df.to_dict(orient="records"),
               xs=sorted(float(x) for x in df.x.unique()))


def payload():
    return {
        "B_LADDER": B_LADDER, "B_COLOR": B_COLOR,
        "FCT_METRICS": FCT_METRICS, "DIAG_METRICS": DIAG_METRICS,
        "part1": part_payload(1), "part2": part_payload(2),
    }


HTML = r"""<title>exp28 Buffer-Size Sweep Explorer</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f6f7f9; --surface: #ffffff; --ink: #1a1f2b; --muted: #5b6472;
  --hairline: #e3e6ec; --accent: #2a6f7f; --accent-soft: #dcefef;
  --good: #15803d; --bad: #b91c1c;
  --shadow: 0 1px 2px rgba(20,25,40,.06), 0 8px 24px rgba(20,25,40,.05);
}
:root:not([data-theme="light"]) { @media (prefers-color-scheme: dark) {
  --ground: #101319; --surface: #191d26; --ink: #e6e9ef; --muted: #99a1b0;
  --hairline: #2b313d; --accent: #5eb3c4; --accent-soft: #17313a;
  --good: #4ade80; --bad: #f87171;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
} }
:root[data-theme="dark"] {
  --ground: #101319; --surface: #191d26; --ink: #e6e9ef; --muted: #99a1b0;
  --hairline: #2b313d; --accent: #5eb3c4; --accent-soft: #17313a;
  --good: #4ade80; --bad: #f87171;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
body { background: var(--ground); color: var(--ink); margin: 0;
  font: 400 16px/1.6 "IBM Plex Sans", system-ui, sans-serif; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 48px 24px 96px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 20px; }
.eyebrow { font: 500 12px/1 "IBM Plex Mono", monospace; letter-spacing: .14em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 12px; }
h1 { font-weight: 600; font-size: clamp(26px, 4vw, 38px); line-height: 1.15;
  margin: 0; text-wrap: balance; letter-spacing: -.01em; }
.lede { color: var(--muted); max-width: 68ch; margin: 16px 0 0; }
.cfg { color: var(--muted); font-size: 12.5px; line-height: 1.7; max-width: 92ch; margin: 12px 0 0; }
.cfg code { font-size: .92em; background: none; padding: 0; color: var(--ink); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px; margin: 32px 0 8px; }
.tile { background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; padding: 18px 20px; box-shadow: var(--shadow); }
.tile .k { font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }
.tile .v { font: 500 25px/1.1 "IBM Plex Mono", monospace; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; }
.tile .v.good { color: var(--good); }
.tile .s { font-size: 13px; color: var(--muted); margin-top: 8px; }
section { margin-top: 52px; }
h2 { font-weight: 600; font-size: 21px; margin: 0 0 6px; padding-bottom: 8px;
  border-bottom: 1px solid var(--hairline); }
section > p { color: var(--muted); max-width: 68ch; margin: 12px 0 16px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 0 0 14px; font: 500 13px/1 "IBM Plex Mono", monospace; }
.controls label { color: var(--muted); letter-spacing: .04em; }
.controls button { font: inherit; color: var(--ink); background: var(--surface);
  border: 1px solid var(--hairline); border-radius: 7px; padding: 7px 12px; cursor: pointer; }
.controls button[aria-pressed="true"] { background: var(--accent); color: #fff;
  border-color: var(--accent); }
.controls button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.partbar { display: flex; gap: 8px; align-items: baseline; margin: 28px 0 4px;
  font: 500 13px/1 "IBM Plex Mono", monospace; color: var(--muted); }
.partbar button { font: inherit; padding: 8px 16px; border-radius: 8px;
  border: 1px solid var(--hairline); background: var(--surface); color: var(--ink);
  cursor: pointer; }
.partbar button[aria-pressed="true"] { background: var(--ink); color: var(--ground);
  border-color: var(--ink); }
.chart { background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); padding: 10px; overflow-x: auto; }
.chart > div { min-width: 640px; height: 470px; }
code { font: 500 .92em "IBM Plex Mono", monospace; background: var(--accent-soft);
  padding: 1px 5px; border-radius: 4px; }
footer { margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--hairline);
  color: var(--muted); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
<header>
  <p class="eyebrow">REPS EuroSys artifact &middot; exp28 &middot; 276 runs</p>
  <h1>REPS buffer size vs failure severity</h1>
  <p class="lede">One fixed fabric (<code>fat_tree_1024_1os_2t_400g</code>, tornado
  16&nbsp;MiB, MPRDMA). <strong>Part&nbsp;1</strong> degrades D ToR&rarr;spine-0 uplinks
  to 50&nbsp;%; <strong>Part&nbsp;2</strong> fixes 4 uplinks and sweeps the degradation
  depth. One line per REPS circular-buffer size B. Drag to zoom, double-click to
  reset, click a B in the legend to hide it.</p>
  <p class="cfg"><code>-use_srv6 -paths 32</code> &middot;
  <code>-sender_cc_algo mprdma</code> &middot; <code>-q 101 -ecn 25 76 -cwnd 151</code>
  &middot; <code>-exit_freeze 200&nbsp;&micro;s</code> (each freeze holds for the
  full 200&nbsp;&micro;s timeout; flows finish before any auto-thaw) &middot;
  seed 42 everywhere, +43/44 at an X subset (95&nbsp;% CI where n=3) &middot;
  <code>-disable_tor_ecn</code> deliberately omitted (paper-faithful).</p>
</header>

<div class="tiles" id="tiles"></div>

<div class="partbar">
  <span>sweep:</span>
  <button data-part="part1" aria-pressed="true">Part 1 &mdash; # degraded links</button>
  <button data-part="part2" aria-pressed="false">Part 2 &mdash; degradation %</button>
</div>

<section>
  <h2>1 &nbsp; FCT vs severity</h2>
  <p>Flow completion time percentiles across all 1024 hosts. The B=1&nbsp;&gg;&nbsp;B=2&nbsp;&gt;&nbsp;B&ge;4
  structure is CI-separated in p50 and p99; B&ge;4 are mutually indistinguishable.</p>
  <div class="controls" id="fct-ctl"><label>metric</label></div>
  <div class="chart"><div id="fct"></div></div>
</section>

<section>
  <h2>2 &nbsp; Diagnostics vs severity</h2>
  <p>Per-host counters from the flow-finish line. <code>freeze_entries</code> stays
  tiny even at D=32 &mdash; degradation drives ECN, not RTO, so the freeze machinery
  barely engages (this is what motivated exp29's full-failure sweep).</p>
  <div class="controls" id="diag-ctl"><label>metric</label></div>
  <div class="chart"><div id="diag"></div></div>
</section>

<footer>
  Source: <code>experiments/exp28_link_degradation_sweep/data/part{1,2}/*.csv</code> &middot;
  regenerate with <code>scripts/build_interactive.py</code> &middot;
  seed 42 everywhere, +43/44 at an X subset (95&nbsp;% CI where n=3).
</footer>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<script>
const DATA = __PAYLOAD__;
const B_LADDER = DATA.B_LADDER, BC = DATA.B_COLOR;
const FCT_M = DATA.FCT_METRICS, DIAG_M = DATA.DIAG_METRICS;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
let part = 'part1';

// match the static PNGs: viridis-over-B_LADDER + hollow markers cycled o D ^ v X P
const SHAPES = ['circle-open', 'diamond-open', 'triangle-up-open',
                'triangle-down-open', 'x-open', 'cross-open', 'star-open'];
const B_SYMBOL = Object.fromEntries(B_LADDER.map((b, i) => [b, SHAPES[i]]));

function theme() {
  const ink = css('--ink'), grid = css('--hairline'), paper = css('--surface');
  return {
    paper_bgcolor: paper, plot_bgcolor: paper, height: 470,
    font: { family: 'IBM Plex Sans, sans-serif', color: ink, size: 13 },
    xaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    yaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    margin: { l: 66, r: 20, t: 16, b: 52 },
    legend: { orientation: 'h', y: -0.22 }, hovermode: 'x unified',
    modebar: { orientation: 'v' },
  };
}
const CFG = { displaylogo: false, responsive: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'] };
function draw(id, traces, layout) {
  Plotly.react(id, traces, layout, CFG);
  requestAnimationFrame(() => Plotly.Plots.resize(document.getElementById(id)));
}
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16);
  return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`; };

function series(col) {
  const P = DATA[part];
  const out = [];
  for (const b of B_LADDER) {
    const rs = P.rows.filter(r => r.buf_size === b && r[col] != null)
      .sort((a,c) => a.x - c.x);
    if (!rs.length) continue;
    const xs = rs.map(r => r.x), ys = rs.map(r => r[col]);
    const cis = rs.map(r => r[col + '_ci'] ?? 0);
    out.push({
      // metrics are non-negative -- clip the band's lower edge at 0
      x: [...xs, ...xs.slice().reverse()],
      y: [...ys.map((y,i)=>y+cis[i]), ...ys.map((y,i)=>Math.max(y-cis[i], 0)).reverse()],
      fill: 'toself', fillcolor: rgba(BC[b], 0.13), line: { width: 0 },
      mode: 'lines',   // else Plotly auto-adds markers at every polygon vertex
      hoverinfo: 'skip', showlegend: false, type: 'scatter',
      legendgroup: 'B' + b,   // hidden together with the B line on legend click
    });
    out.push({ x: xs, y: ys, name: 'B=' + b, mode: 'lines+markers', type: 'scatter',
      legendgroup: 'B' + b,
      line: { color: BC[b], width: 2.4 },
      marker: { color: BC[b], symbol: B_SYMBOL[b] ?? 'circle-open', size: 8,
                line: { color: BC[b], width: 1.8 } } });
  }
  return out;
}
function drawChart(id, mmap, label) {
  const col = mmap[label];
  const t = theme();
  t.xaxis.title = DATA[part].xlabel;
  t.xaxis.tickvals = DATA[part].xs;
  t.yaxis.title = label;
  draw(id, series(col), t);
}

function currentLabel(host) {
  return document.querySelector('#' + host + ' [aria-pressed="true"]').textContent;
}
function redraw() {
  drawChart('fct', FCT_M, currentLabel('fct-ctl'));
  drawChart('diag', DIAG_M, currentLabel('diag-ctl'));
}

function radio(host, names, current, cb) {
  const el = document.getElementById(host);
  names.forEach(n => {
    const b = document.createElement('button');
    b.textContent = n; b.setAttribute('aria-pressed', n === current);
    b.onclick = () => {
      [...el.querySelectorAll('button')].forEach(x =>
        x.setAttribute('aria-pressed', x === b));
      cb();
    };
    el.appendChild(b);
  });
}
radio('fct-ctl', Object.keys(FCT_M), 'p99 FCT (µs)', redraw);
radio('diag-ctl', Object.keys(DIAG_M), 'random-EV draws / host', redraw);

document.querySelectorAll('.partbar button').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.partbar button').forEach(b =>
      b.setAttribute('aria-pressed', b === btn));
    part = btn.dataset.part; redraw();
  };
});

function tiles() {
  const p1 = DATA.part1.rows;
  const at = (b, x, col) => {
    const r = p1.find(r => r.buf_size === b && Math.abs(r.x - x) < 0.01);
    return r ? r[col] : null;
  };
  const d16b1 = at(1, 16, 'p99_fct_us'), d16b4 = at(4, 16, 'p99_fct_us');
  const gap = (d16b1 && d16b4) ? Math.round(d16b1 - d16b4) : '?';
  const T = [
    ['above B=4', 'no resolvable Δ', 'good', 'B4 / B8 / B16 / B32 indistinguishable'],
    ['B=1 penalty at D=16', `+${gap} µs`, '', 'p99 FCT vs B=4'],
    ['freeze machinery', 'barely engages', '', 'degradation → ECN, not RTO'],
  ];
  document.getElementById('tiles').innerHTML = T.map(([k,v,c,s]) =>
    `<div class="tile"><p class="k">${k}</p><div class="v ${c}">${v}</div>
     <div class="s">${s}</div></div>`).join('');
}

tiles(); redraw();
let rt;
addEventListener('resize', () => {
  clearTimeout(rt);
  rt = setTimeout(() => document.querySelectorAll('.chart > div').forEach(el => {
    if (el._fullLayout) Plotly.Plots.resize(el);
  }), 120);
});

const mq = window.matchMedia('(prefers-color-scheme: dark)');
mq.addEventListener && mq.addEventListener('change', redraw);
new MutationObserver(redraw).observe(document.documentElement,
  { attributes: true, attributeFilter: ['data-theme'] });
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
    print(f"wrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()

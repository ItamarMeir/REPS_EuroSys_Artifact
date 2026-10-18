#!/usr/bin/env python3
"""
exp31 plots/interactive.html -- self-contained, zoomable Plotly view of the ring
all-reduce CCT results. Reuses exp29 _asciiify + the exp30 dashboard JS shape.

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

B_LADDER = [1, 2, 4]
B_COLOR = {1: "#440154", 2: "#21918c", 4: "#fde725"}   # viridis at {1,2,4}

SCENARIO_ROWS = [
    ("fail_one_cable", "One ToR&rarr;Agg cable direction fails.",
     "Picked by first traffic to reach it after t=0 (sim order, not random); skipped if it would disconnect the fabric. Recovery set to failure + 10&sup1;&sup4; ps (~100 s), effectively permanent. Max 1 &rarr; 1 cable (per-ToR rounding not verified in log)."),
    ("fail_one_switch", "One switch fails; packets through it are dropped.",
     "Picked by first traffic to reach it, same mechanism as cables. Max 1 &rarr; 1 switch (set to stop after the first)."),
    ("fail_one_switch_one_cable", "One switch and one cable fail.",
     "Same as the two rows above."),
    ("5_percent_failed_cables", "5% of cable pipes fail.",
     "Denominator = traversed pipes / 2 = 40 (from run log). 5% &times; 40 = 2 nominal. Seed 42 reps_b1 run: 2 pipes failed at 1.166 &micro;s (ids 93, 85), 1 more at 1.249 &micro;s (id 129). Failures start at first traffic, not t=0."),
    ("5_percent_failed_switches", "5% of switches fail, repeat period 10 &micro;s.",
     "Same first-hit check with the 5% threshold. With ~12 switches (denominator unverified), the first switch passes and the next exceeds 5%, so 1 switch fails (from code logic, not run-verified)."),
    ("5_percent_failed_switches_and_cables", "Both of the above together.",
     "Switch: 1 switch (as above). Cable: 5% of 40 = 2 nominal (as above)."),
    ("ber_cable_one_percent", "One cable is meant to drop ~1% of packets.",
     "Conflict: <code>cableBER()</code> only marks packets and always returns false, so the drop branch looks unreachable. But the seed-42 run logs ~25,700 total dropped packets, not attributed to this cable. Unresolved."),
    ("ber_switch_one_percent", "One switch drops ~1% of packets.",
     "Marked packets dropped in <code>dropPacketsSwitchBER</code> (called from <code>uec.cpp:5649</code>). Rate as set by Max 0.01 (not run-verified)."),
    ("degrade_one_cable", "One cable runs slow.",
     "Same first-hit selection as <code>fail_one_cable</code>. Degradation mechanics not checked in code."),
    ("10_percent_degraded_cables", "10% of cables run slow.",
     "10% of 40 pipes = 4 nominal (not run-verified)."),
    ("fail_all_cables_except_one_path", "Cables fail from 100 ns, repeating every 100 ns.",
     "Same first-hit selection, starting at 100 ns. Per README this resolves to 1 cable on this fabric (not checked in run)."),
]


def scenario_table_html():
    rows = "".join(f"<tr><td>{s}</td><td>{w}</td><td>{n}</td></tr>"
                   for s, w, n in SCENARIO_ROWS)
    return ("<table class=\"scen\"><thead><tr><th>Scenario</th><th>What happens</th>"
            "<th>Notes</th></tr></thead><tbody>" + rows + "</tbody></table>")


def payload():
    cct = pd.read_csv(D / "cct.csv")
    steps = pd.read_csv(D / "steps.csv")[["scenario", "arm", "step", "fct_mean_us"]]
    rv = pd.read_csv(D / "resolvable.csv")
    return {
        "B_LADDER": B_LADDER, "B_COLOR": B_COLOR,
        "cct": cct.round(3).to_dict(orient="records"),
        "steps": steps.round(1).to_dict(orient="records"),
        "rv": rv.to_dict(orient="records"),
    }


HTML = r"""<title>Ring All-Reduce CCT vs Buffer Size</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f6f7f9; --surface: #ffffff; --ink: #1a1f2b; --muted: #5b6472;
  --hairline: #e3e6ec; --accent: #0369a1; --accent-soft: #e0f2fe;
  --good: #15803d; --bad: #b91c1c;
  --shadow: 0 1px 2px rgba(20,25,40,.06), 0 8px 24px rgba(20,25,40,.05);
}
:root:not([data-theme="light"]) { @media (prefers-color-scheme: dark) {
  --ground: #101319; --surface: #191d26; --ink: #e6e9ef; --muted: #99a1b0;
  --hairline: #2b313d; --accent: #38bdf8; --accent-soft: #0c2b3d;
  --good: #4ade80; --bad: #f87171;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
} }
:root[data-theme="dark"] {
  --ground: #101319; --surface: #191d26; --ink: #e6e9ef; --muted: #99a1b0;
  --hairline: #2b313d; --accent: #38bdf8; --accent-soft: #0c2b3d;
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
.lede { color: var(--muted); max-width: 70ch; margin: 16px 0 0; }
.cfg { color: var(--muted); font-size: 12.5px; line-height: 1.7; max-width: 94ch; margin: 12px 0 0; }
.cfg code { font-size: .92em; background: none; padding: 0; color: var(--ink); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px; margin: 32px 0 8px; }
.tile { background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; padding: 18px 20px; box-shadow: var(--shadow); }
.tile .k { font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }
.tile .v { font: 500 24px/1.15 "IBM Plex Mono", monospace; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; }
.tile .v.good { color: var(--good); } .tile .v.bad { color: var(--bad); }
.tile .s { font-size: 13px; color: var(--muted); margin-top: 8px; }
section { margin-top: 54px; }
h2 { font-weight: 600; font-size: 21px; margin: 0 0 6px; padding-bottom: 8px;
  border-bottom: 1px solid var(--hairline); }
section > p { color: var(--muted); max-width: 72ch; margin: 12px 0 16px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 0 0 12px; font: 500 13px/1 "IBM Plex Mono", monospace; }
.controls label { color: var(--muted); letter-spacing: .04em; }
.controls button { font: inherit; color: var(--ink); background: var(--surface);
  border: 1px solid var(--hairline); border-radius: 7px; padding: 7px 12px; cursor: pointer; }
.controls button[aria-pressed="true"] { background: var(--accent); color: #fff;
  border-color: var(--accent); }
.chart { background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); padding: 10px; overflow-x: auto; }
.chart > div { min-width: 640px; height: 470px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin-top: 4px; }
.tblwrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 10px; box-shadow: var(--shadow); }
th, td { text-align: right; padding: 9px 14px; border-bottom: 1px solid var(--hairline);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
table.scen { table-layout: fixed; }
table.scen th, table.scen td { text-align: left; white-space: normal; vertical-align: top; overflow-wrap: anywhere; }
table.scen th:nth-child(1), table.scen td:nth-child(1) { width: 22%; }
table.scen th:nth-child(2), table.scen td:nth-child(2) { width: 28%; }
th { font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
.pill { display: inline-block; font: 500 11px/1 "IBM Plex Mono", monospace;
  padding: 4px 9px; border-radius: 999px; }
.pill.no { background: color-mix(in srgb, var(--muted) 20%, transparent); color: var(--muted); }
.pill.yes { background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
code { font: 500 .92em "IBM Plex Mono", monospace; background: var(--accent-soft);
  padding: 1px 5px; border-radius: 4px; }
footer { margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--hairline);
  color: var(--muted); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
<header>
  <p class="eyebrow">REPS EuroSys artifact &middot; exp31</p>
  <h1>Ring all-reduce: does buffer size B move CCT?</h1>
  <p class="lede">exp28&ndash;30 measured independent tornado flows and found B
  never resolves on FCT. A <strong>ring all-reduce</strong> is different: hop
  <em>k+1</em> starts only when hop <em>k</em> finishes, so one slow link stalls
  the whole ring on every one of its 2(N&minus;1) cyclic steps. Metric is
  <strong>CCT</strong> = the last constituent flow's completion (censored at
  <code>-end</code> = 90 ms when the ring never completes). 16-rank ring, 4 MB/hop,
  reproduces exp26 fig 7's <code>ai</code> workload with 3 seeds.</p>
  <p class="cfg" id="cfg"></p>
</header>

<div class="tiles" id="tiles"></div>

<section>
  <h2>1 &nbsp; CCT by failure scenario</h2>
  <p>Ring CCT, one bar per B, per scenario. Log y &mdash; failure blows CCT up
  5&ndash;45&times; healthy. Hatched bar = the ring did not complete inside the
  90 ms sim (CCT censored) &mdash; none here did. Healthy is the leftmost group.</p>
  <div class="controls" id="s1-ctl"><label>y</label></div>
  <div class="chart"><div id="s1"></div></div>
</section>

<section>
  <h2>2 &nbsp; CCT vs B &mdash; the knee</h2>
  <p>CCT against buffer size for one scenario, with 95 % CI (n=3 seeds). exp26
  fig 7's single seed hinted at a <strong>B=1 &rarr; B=2 knee</strong> (b2 best)
  and b4 sometimes <em>worse</em> than b2. Does it survive CI?</p>
  <div class="controls" id="s2-ctl"><label>scenario</label></div>
  <div class="chart"><div id="s2"></div></div>
</section>

<section>
  <h2>3 &nbsp; Per-ring-step FCT &mdash; the mechanism</h2>
  <p>FCT vs position within a 31-hop ring chain, averaged over the 16 chains.
  Healthy &rarr; flat at ~91 &micro;s. Under a cable failure a smooth mid-ring
  hump appears (~2.5&times;, peaking around hop 20 then draining by hop 30) and
  it is the same shape in every chain &mdash; congestion building and clearing
  each ring cycle, not a single catastrophic hop. B=1/2/4 traces stay tangled.
  Log y.</p>
  <div class="controls" id="s3-ctl"><label>scenario</label></div>
  <div class="chart"><div id="s3"></div></div>
</section>

<section>
  <h2>4 &nbsp; The verdict table</h2>
  <p><code>resolvable</code> = best-B vs worst-B CCT gap &gt; sum of their 95 % CI
  half-widths. <code>b1&minus;b2</code> = the knee; <code>b2&minus;b4</code> =
  "does a bigger buffer hurt the ring".</p>
  <div class="tblwrap"><table id="rvtbl"></table></div>
</section>

<section>
  <h2>5 &nbsp; Failure scenario definitions</h2>
  <p>What each scenario does in the sim, and what the 5% / 10% / Max-1 values
  resolve to. Values verified from <code>htsim/sim/failuregenerator.cpp</code>
  where noted; the rest is from the run log or README.</p>
  <div class="tblwrap">__SCENARIO_TABLE__</div>
</section>

<footer>
  Source: <code>experiments/exp31_ring_collective/data/*.csv</code> &middot;
  <code>fat_tree_32_1os_2t_400g</code>, 16-rank ring all-reduce (4 MB/hop),
  MPRDMA, seeds 42/43/44. Reproduces exp26 fig 7 <code>ai</code>.
</footer>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<script>
const DATA = __PAYLOAD__;
const B_LADDER = DATA.B_LADDER, BC = DATA.B_COLOR;
const CCT = DATA.cct, STEPS = DATA.steps, RV = DATA.rv;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function theme() {
  const ink = css('--ink'), grid = css('--hairline'), paper = css('--surface');
  return { paper_bgcolor: paper, plot_bgcolor: paper, height: 470,
    font: { family: 'IBM Plex Sans, sans-serif', color: ink, size: 13 },
    xaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    yaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid },
    margin: { l: 70, r: 20, t: 16, b: 90 },
    legend: { orientation: 'h', y: -0.28 }, hovermode: 'closest',
    modebar: { orientation: 'v' } };
}
const CFG = { displaylogo: false, responsive: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'] };
function draw(id, traces, layout) {
  Plotly.react(id, traces, layout, CFG);
  requestAnimationFrame(() => Plotly.Plots.resize(document.getElementById(id)));
}

const SCEN = ['healthy', ...[...new Set(CCT.map(r => r.scenario))]
  .filter(s => s !== 'healthy').sort()];

// --- 1: CCT by scenario, bars per B ---
let s1y = 'cct_us';
function drawS1() {
  const traces = B_LADDER.map(b => {
    const rows = SCEN.map(sc => CCT.find(r => r.scenario === sc && r.buf_size === b));
    return {
      type: 'bar', name: 'B=' + b, x: SCEN,
      y: rows.map(r => r ? r[s1y] : null),
      error_y: s1y === 'cct_us'
        ? { type: 'data', array: rows.map(r => r ? r.cct_us_ci : 0), visible: true } : {},
      marker: {
        color: BC[b],
        pattern: { shape: rows.map(r => (r && r.censored) ? 'x' : ''), size: 5 },
        line: { color: css('--ink'), width: 0.5 },
      },
    };
  });
  const t = theme();
  t.barmode = 'group';
  t.yaxis.type = 'log';
  t.yaxis.title = s1y === 'cct_us' ? 'CCT (us, log)' : 'CCT / healthy (%, log)';
  t.xaxis.tickangle = -35;
  t.margin.t = 40;
  t.margin.b = 170;
  t.height = 560;
  t.legend = { orientation: 'h', x: 0, xanchor: 'left', y: 1.02, yanchor: 'bottom' };
  document.getElementById('s1').style.height = '560px';
  draw('s1', traces, t);
}

// --- 2: CCT vs B, one scenario ---
let s2scen = 'fail_one_cable';
function drawS2() {
  const rows = B_LADDER.map(b => CCT.find(r => r.scenario === s2scen && r.buf_size === b));
  const traces = [{
    type: 'scatter', mode: 'lines+markers', x: B_LADDER,
    y: rows.map(r => r ? r.cct_us : null),
    error_y: { type: 'data', array: rows.map(r => r ? r.cct_us_ci : 0), visible: true },
    line: { color: css('--accent'), width: 2.5 },
    marker: { color: B_LADDER.map(b => BC[b]), size: 11,
              line: { color: css('--ink'), width: 1 } },
    name: s2scen,
  }];
  const t = theme();
  t.xaxis.title = 'buffer size B'; t.xaxis.tickvals = B_LADDER;
  t.yaxis.title = 'CCT (us, log)'; t.yaxis.type = 'log';
  t.showlegend = false;
  draw('s2', traces, t);
}

// --- 3: per-step FCT series ---
let s3scen = 'fail_one_cable';
function drawS3() {
  // .cm flowId order is chain-major (16 chains x 31 hops); fold onto hop = (step-1)%31
  // and average the chains so a recurring stall shows as a hump, not smeared noise.
  const CL = 31;
  const traces = B_LADDER.map(b => {
    const rs = STEPS.filter(r => r.scenario === s3scen && r.arm === 'reps_b' + b);
    const acc = {};
    rs.forEach(r => { const h = (r.step - 1) % CL; (acc[h] = acc[h] || []).push(r.fct_mean_us); });
    const hops = Object.keys(acc).map(Number).sort((x, y) => x - y);
    return {
      type: 'scatter', mode: 'lines', name: 'B=' + b,
      x: hops, y: hops.map(h => acc[h].reduce((a, v) => a + v, 0) / acc[h].length),
      line: { color: BC[b], width: 1.4 },
    };
  });
  const t = theme();
  t.xaxis.title = 'ring hop position (step-1 mod 31, averaged over 16 chains)';
  t.yaxis.title = 'hop FCT (us, log)'; t.yaxis.type = 'log';
  t.hovermode = 'x unified';
  draw('s3', traces, t);
}

// --- 4: table ---
function drawTable() {
  const rows = [...RV].sort((a, b) =>
    (a.scenario === 'healthy' ? -1 : b.scenario === 'healthy' ? 1
      : a.scenario.localeCompare(b.scenario)));
  const h = `<thead><tr><th>scenario</th><th>best B</th><th>worst B</th>
    <th>spread</th><th>&Sigma; CI</th><th>resolvable</th>
    <th>b1&minus;b2 (us)</th><th>b2&minus;b4 (us)</th></tr></thead>`;
  const body = rows.map(r => {
    const yes = r.resolvable === true || r.resolvable === 'True';
    const kneeYes = r.b1_b2_resolvable === true || r.b1_b2_resolvable === 'True';
    return `<tr><td>${r.scenario}</td>
      <td>B${r.best_b} (${(+r.best_cct).toFixed(0)})</td>
      <td>B${r.worst_b} (${(+r.worst_cct).toFixed(0)})</td>
      <td>${(+r.spread).toFixed(0)}</td><td>${(+r.ci_sum).toFixed(0)}</td>
      <td><span class="pill ${yes ? 'yes' : 'no'}">${yes ? 'yes' : 'no'}</span></td>
      <td>${Number.isFinite(+r.b1_minus_b2) ? (+r.b1_minus_b2).toFixed(0)
          + (kneeYes ? ' *' : '') : '-'}</td>
      <td>${Number.isFinite(+r.b2_minus_b4) ? (+r.b2_minus_b4).toFixed(0) : '-'}</td></tr>`;
  }).join('');
  document.getElementById('rvtbl').innerHTML = h + '<tbody>' + body + '</tbody>'
    + '<caption style="caption-side:bottom;color:var(--muted);font-size:12px;'
    + 'text-align:left;padding:8px 14px">* = b1&minus;b2 gap exceeds its CI '
    + '(the knee is real for that scenario)</caption>';
}

function tiles() {
  const heal = CCT.find(r => r.scenario === 'healthy' && r.buf_size === 2);
  const foc = s => CCT.filter(r => r.scenario === s);
  const knees = RV.filter(r => (r.b1_b2_resolvable === true || r.b1_b2_resolvable === 'True'));
  const anyRes = RV.filter(r => r.scenario !== 'healthy'
    && (r.resolvable === true || r.resolvable === 'True'));
  const T = [
    ['healthy ring CCT', heal ? (+heal.cct_us).toFixed(0) + ' us' : '?', 'good',
     'all B identical, 0 RTOs'],
    ['scenarios where B resolves', `${anyRes.length} / ${RV.length - 1}`,
     anyRes.length ? 'bad' : 'good', 'CCT best-B vs worst-B beyond CI'],
    ['b1->b2 knee real in', `${knees.length} scenario${knees.length === 1 ? '' : 's'}`,
     '', 'b1-b2 gap exceeds its 95% CI'],
    ['worst CCT seen',
     (Math.max(...CCT.map(r => r.cct_us)) / 1000).toFixed(1) + ' ms',
     'bad', (Math.max(...CCT.map(r => r.cct_us)) / (heal ? heal.cct_us : 91)).toFixed(0)
     + 'x healthy'],
  ];
  document.getElementById('tiles').innerHTML = T.map(([k, v, c, s]) =>
    `<div class="tile"><p class="k">${k}</p><div class="v ${c}">${v}</div>
     <div class="s">${s}</div></div>`).join('');
}

function cfgLine() {
  document.getElementById('cfg').innerHTML =
    '<code>fat_tree_32_1os_2t_400g</code> &middot; 16-rank ring all-reduce, 4 MB/hop '
    + '(<code>gen_allreduce 32 16 16</code>, locality 0) &middot; '
    + '<code>-use_srv6 -paths 4</code> &middot; <code>-sender_cc_algo mprdma</code> &middot; '
    + '<code>-q 101 -ecn 25 76 -cwnd 151 -other_location</code> &middot; '
    + 'seeds 42/43/44 &middot; reproduces exp26 fig 7 <code>ai</code> (+ healthy baseline, CI)';
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

radio('s1-ctl', ['cct_us', 'cct_pct_of_healthy'], s1y,
  v => { s1y = v; drawS1(); });
radio('s2-ctl', SCEN, s2scen, v => { s2scen = v; drawS2(); });
radio('s3-ctl', SCEN, s3scen, v => { s3scen = v; drawS3(); });

function drawAll() { cfgLine(); tiles(); drawS1(); drawS2(); drawS3(); drawTable(); }
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
    html = HTML.replace("__SCENARIO_TABLE__", scenario_table_html())
    html = html.replace("__PAYLOAD__", json.dumps(payload()))
    OUT.write_text(_asciiify(html), encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()

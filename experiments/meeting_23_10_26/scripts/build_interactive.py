#!/usr/bin/env python3
"""Emit self-contained Plotly pages for the meeting_23_10_26 plots (Plotly from cdnjs).

  M1/plots/interactive.html   cwnd(t), target-delay sweep, per-cell marking/random shares
  M4/plots/interactive.html   REPS buffer-size sweep at constant send rates (metric dropdown)

Inputs (committed): M1/data/m1_summary.csv, M1/data/m1_cwnd_series_25us.csv,
                    M4/data/m4_summary.csv (written by M4/scripts/plot_m4.py).
M2 and M3 are validation-only (tables in their READMEs), so they have no plots.
Note: experiments/**/*.html is gitignored; pages are published via the thesis repo on request.

    python3 build_interactive.py
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

HEAD = """<!doctype html>
<html><head><meta charset="utf-8">
<title>__TITLE__</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.note { font-size: 12px; color: #555; margin-bottom: 12px; max-width: 980px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; position: relative; }
.wide { grid-column: 1 / -1; }
.copy-btn { position: absolute; top: 6px; right: 6px; z-index: 10; opacity: 0;
  transition: opacity .15s; font-size: 11px; padding: 3px 8px; cursor: pointer;
  background: #fff; border: 1px solid #bbb; border-radius: 4px; color: #333; }
.panel:hover .copy-btn { opacity: 1; }
.copy-btn.copied { background: #dcfce7; border-color: #16a34a; color: #166534; }
select { font-size: 13px; padding: 2px 4px; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style></head>
<body>
"""

COMMON_JS = """
const TITLE_BY_ID = {};
function plotWithHeadline(divId, traces, layout, opts) {
  TITLE_BY_ID[divId] = (layout.title && layout.title.text || "").replace(/&gt;/g, ">").replace(/&lt;/g, "<");
  Plotly.react(divId, traces, layout, opts);
}
function copyTitle(divId, btn) {
  const text = TITLE_BY_ID[divId] || "";
  const done = () => { const p = btn.textContent; btn.textContent = "copied!"; btn.classList.add("copied");
    setTimeout(() => { btn.textContent = p; btn.classList.remove("copied"); }, 1200); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else { fallbackCopy(text, done); }
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {}
  document.body.removeChild(ta); done();
}
"""


def clean(v):
    return None if isinstance(v, float) and math.isnan(v) else v


def panel(div):
    return (f'<div class="panel"><button class="copy-btn" onclick="copyTitle(\'{div}\', this)">copy</button>'
            f'<div id="{div}"></div></div>')


def fill(html, divs):
    for k, div in zip(["__P1__", "__P2__", "__P3__", "__P4__"], divs):
        html = html.replace(k, panel(div))
    return html


# ----------------------------------------------------------------------------- M1
M1_BODY = """
<h1>M1: why NSCC keeps ECN marking near 50% on a degraded fabric</h1>
<div class="note">Tornado 16 MiB, 1024 flows, seed 42, REPS (freezing, B=8), trimming on. Degraded = ToR0 uplinks at 50%
(or every ToR uplink at 50%, "ALL"). Shares are over the post-warmup sends / ACKs of the traced ToR0 hosts.
NSCC holds the queue at its target delay (default 6 us; 4.17 us = the paper's 1.5 x base RTT rule), which sits inside the scaled
ECN ramp, so about half the ACKs are marked. Toggle traces via the legend.</div>
<div class="grid">
  __P1__ __P2__
  __P3__ __P4__
</div>
<script>
const DATA = __PAYLOAD__;
""" + COMMON_JS + """
const SWEEP = [["1us", "ToR0 x0.5, target 1us"], ["2us", "ToR0 x0.5, target 2us"], ["3us", "ToR0 x0.5, target 3us"],
               ["4.17us", "ToR0 x0.5, target 4.17us"], ["6us", "ToR0 x0.5, target 6us"]];
const SHOWN = ["healthy 400G (NSCC)", "ToR0 x0.5, target 4.17us", "ToR0 x0.5 (MPRDMA)", "native 200G fabric+NIC (NSCC)"];
const byCell = {}; DATA.summary.forEach(r => byCell[r.cell] = r);

(function () {
  const traces = DATA.series.cells.map(c => ({x: DATA.series.t_us, y: DATA.series.data[c], mode: "lines", name: c,
    line: {width: SHOWN.includes(c) ? 2.5 : 1.3}, visible: SHOWN.includes(c) ? true : "legendonly"}));
  plotWithHeadline("cwnd", traces, {title: {text: "Median cwnd of traced ToR0 hosts over time", font: {size: 13}},
    xaxis: {title: "time (us)"}, yaxis: {title: "median cwnd (pkts)"}, legend: {orientation: "h", y: -0.3},
    margin: {t: 40, b: 110}, height: 440,
    shapes: [{type: "line", xref: "paper", x0: 0, x1: 1, y0: 56, y1: 56, line: {dash: "dot", color: "#111", width: 1}}],
    annotations: [{xref: "paper", x: 0.99, xanchor: "right", y: 56, yanchor: "bottom", text: "degraded knee 56 pkts", showarrow: false, font: {size: 10}}]},
    {responsive: true});
})();

(function () {
  const x = SWEEP.map(s => s[0]);
  const ecn = SWEEP.map(s => byCell[s[1]].ecn_ack_pct), rnd = SWEEP.map(s => byCell[s[1]].pct_random);
  const h = byCell["healthy 400G (NSCC)"];
  plotWithHeadline("sweep", [
    {x, y: ecn, mode: "lines+markers", name: "% ACKs ECN-marked"},
    {x, y: rnd, mode: "lines+markers", name: "% sends with random EV"},
    {x, y: x.map(_ => h.pct_random), mode: "lines", name: "healthy random %", line: {dash: "dot", color: "#16a34a"}}],
    {title: {text: "NSCC target_q_delay sweep, ToR0 uplinks at 50%", font: {size: 13}},
     xaxis: {title: "target_q_delay", type: "category"}, yaxis: {title: "%", range: [0, 100]},
     legend: {orientation: "h", y: -0.3}, margin: {t: 40, b: 100}, height: 440}, {responsive: true});
})();

(function () {
  const x = SWEEP.map(s => s[0]);
  plotWithHeadline("tend", [
    {x, y: SWEEP.map(s => byCell[s[1]].t_end_us), type: "bar", name: "t_end (us)", marker: {color: "#2a788e"}},
    {x, y: SWEEP.map(s => byCell[s[1]].cwnd_med), mode: "lines+markers", yaxis: "y2", name: "median cwnd", line: {color: "#dc2626"}}],
    {title: {text: "Trace end time and median cwnd vs target (single seed)", font: {size: 13}},
     xaxis: {title: "target_q_delay", type: "category"}, yaxis: {title: "t_end (us)", range: [650, 790]},
     yaxis2: {title: "median cwnd (pkts)", overlaying: "y", side: "right", range: [40, 100]},
     legend: {orientation: "h", y: -0.3}, margin: {t: 40, b: 100}, height: 440}, {responsive: true});
})();

(function () {
  const cells = DATA.summary.map(r => r.cell);
  plotWithHeadline("cells", [
    {x: cells, y: DATA.summary.map(r => r.ecn_ack_pct), type: "bar", name: "% ACKs ECN-marked"},
    {x: cells, y: DATA.summary.map(r => r.pct_random), type: "bar", name: "% sends random EV"},
    {x: cells, y: DATA.summary.map(r => r.pct_valid), type: "bar", name: "% sends valid EV"}],
    {title: {text: "All M1 cells: ECN share, random-EV share, valid-EV share", font: {size: 13}}, barmode: "group",
     xaxis: {tickangle: -35, automargin: true}, yaxis: {title: "%", range: [0, 100]},
     legend: {orientation: "h", y: -0.9}, margin: {t: 40, b: 220}, height: 520}, {responsive: true});
})();
</script>
</body></html>
"""


def build_m1():
    d = ROOT / "M1" / "data"
    s = pd.read_csv(d / "m1_summary.csv")
    ser = pd.read_csv(d / "m1_cwnd_series_25us.csv", index_col=0)
    payload = {
        "summary": [{k: clean(v) for k, v in r.items()} for r in s.to_dict("records")],
        "series": {"t_us": [float(i * 25) for i in ser.index], "cells": list(ser.columns),
                   "data": {c: [clean(float(v)) for v in ser[c]] for c in ser.columns}},
    }
    html = fill(HEAD.replace("__TITLE__", "M1 NSCC ECN marking on degraded links") + M1_BODY,
                ["cwnd", "sweep", "tend", "cells"])
    html = html.replace("__PAYLOAD__", json.dumps(payload))
    out = ROOT / "M1" / "plots" / "interactive.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out)


# ----------------------------------------------------------------------------- M4
M4_BODY = """
<h1>M4: REPS buffer size B at known constant send rates</h1>
<div class="note">Constant-rate sender (<code>-rate_const_gbps</code>, no congestion control), REPS (freezing), SRv6 32 paths,
tornado 16 MiB, trimming on. Rate = 100 / 200 / 400 Gbps per source (under / matched / over the 200G degraded ToR0
capacity). Failure models: healthy; uniform50 (all 32 ToR0 uplinks at 50%); nonuniform (even agg 25%, odd agg 75%).
Points = mean over seeds 42-46, bars = 95% t-CI. Random-EV and k statistics are over the first 8 ToR0 sources; FCT over all flows
(ToR0 columns over the 32 ToR0 flows). Pick a metric below.</div>
<div class="note">Metric: <select id="metric"></select>
&nbsp; <label><input type="checkbox" id="logy"> log y</label></div>
<div class="grid">
  __P1__ __P2__
  __P3__ __P4__
</div>
<script>
const DATA = __PAYLOAD__;
""" + COMMON_JS + """
const RATES = ["under", "matched", "over"], FAILS = ["healthy", "uniform50", "nonuniform"];
const COL = {under: "#2a788e", matched: "#22a884", over: "#dc2626"};
const LAB = {under: "under (100G)", matched: "matched (200G)", over: "over (400G)"};
const FLAB = {healthy: "healthy", uniform50: "uniform 50%", nonuniform: "non-uniform 25/75%"};
const METRICS = DATA.metrics;
const sel = document.getElementById("metric");
METRICS.forEach(m => { const o = document.createElement("option"); o.value = m.key; o.textContent = m.label; sel.appendChild(o); });
const rowsOf = (f, r) => DATA.rows.filter(x => x.fail === f && x.rate === r).sort((a, b) => a.B - b.B);

function lines(fail, divId) {
  const m = METRICS.find(x => x.key === sel.value), log = document.getElementById("logy").checked;
  const traces = RATES.map(r => { const rs = rowsOf(fail, r);
    return {x: rs.map(x => x.B), y: rs.map(x => x[m.key + "_mean"]), mode: "lines+markers", name: LAB[r],
      error_y: {type: "data", array: rs.map(x => x[m.key + "_ci95"]), visible: true, thickness: 1, width: 3},
      line: {color: COL[r]}, marker: {color: COL[r]}}; });
  plotWithHeadline(divId, traces, {title: {text: m.label + " vs B -- " + FLAB[fail], font: {size: 13}},
    xaxis: {title: "REPS buffer size B", type: "log", tickvals: [1, 2, 4, 8, 16, 32, 64], ticktext: ["1", "2", "4", "8", "16", "32", "64"]},
    yaxis: {title: m.label, type: log ? "log" : "linear"}, legend: {orientation: "h", y: -0.3},
    margin: {t: 40, b: 100}, height: 400}, {responsive: true});
}
function heat() {
  const m = METRICS.find(x => x.key === sel.value);
  const ylab = [], z = [];
  FAILS.forEach(f => RATES.forEach(r => { ylab.push(FLAB[f] + " / " + LAB[r]);
    z.push(rowsOf(f, r).map(x => x[m.key + "_mean"])); }));
  plotWithHeadline("heat", [{z, x: [1, 2, 4, 8, 16, 32, 64].map(b => "B=" + b), y: ylab, type: "heatmap", colorscale: "Viridis",
    text: z.map(row => row.map(v => v == null ? "" : (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)))), texttemplate: "%{text}",
    colorbar: {title: m.label}}],
    {title: {text: m.label + ": every cell (mean over seeds)", font: {size: 13}}, yaxis: {autorange: "reversed", automargin: true},
     margin: {t: 40, b: 40, l: 230}, height: 420}, {responsive: true});
}
function draw() { lines("healthy", "p_healthy"); lines("uniform50", "p_uniform50"); lines("nonuniform", "p_nonuniform"); heat(); }
sel.onchange = draw; document.getElementById("logy").onchange = draw;
sel.value = "pct_random"; draw();
</script>
</body></html>
"""

M4_METRICS = [
    ("pct_random", "% sends with random EV"), ("k_mean", "mean k (valid EVs at send)"),
    ("k_ge1", "% sends with k >= 1"), ("k_ge2", "% sends with k >= 2"), ("k_ge3", "% sends with k >= 3"),
    ("k_ge4", "% sends with k >= 4"), ("k_max", "max k"), ("spray_width32", "distinct EVs per 32 sends"),
    ("distinct_ev_per_src", "distinct EVs per source"), ("fct_tor0_mean", "mean FCT of ToR0 flows (us)"),
    ("fct_tor0_max", "max FCT of ToR0 flows (us)"), ("fct_p50", "p50 FCT (us)"), ("fct_p99", "p99 FCT (us)"),
    ("fct_max", "max FCT (us)"), ("rtx", "retransmits per run"), ("ecn_acks", "ECN-marked ACKs per run"),
    ("rtos", "RTOs per run"), ("freeze_entries", "freeze entries per run"),
]


def build_m4():
    s = pd.read_csv(ROOT / "M4" / "data" / "m4_summary.csv")
    keep = ["rate", "fail", "B", "n_seeds"] + [f"{k}_{t}" for k, _ in M4_METRICS for t in ("mean", "ci95")]
    rows = [{k: clean(v) for k, v in r.items()} for r in s[keep].to_dict("records")]
    payload = {"rows": rows, "metrics": [{"key": k, "label": l} for k, l in M4_METRICS]}
    html = fill(HEAD.replace("__TITLE__", "M4 REPS buffer size at constant rate") + M4_BODY,
                ["p_healthy", "p_uniform50", "p_nonuniform", "heat"])
    html = html.replace("__PAYLOAD__", json.dumps(payload))
    out = ROOT / "M4" / "plots" / "interactive.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    build_m1()
    build_m4()

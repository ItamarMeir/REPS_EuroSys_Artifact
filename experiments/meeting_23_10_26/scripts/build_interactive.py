#!/usr/bin/env python3
"""Emit self-contained Plotly pages for the meeting_23_10_26 plots (Plotly from cdnjs).

  M1/plots/interactive.html   cwnd(t), target-delay sweep, per-cell marking/random shares
  M4/plots/interactive.html   REPS buffer-size sweep, one section per sending rate (under/matched/over)

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
<h1>M4: does the REPS buffer size B matter, at each sending rate?</h1>
<div class="note">Constant-rate sender (<code>-rate_const_gbps</code>, no congestion control), REPS (freezing), SRv6 32 paths,
tornado 16 MiB, 1024 flows, trimming on, seeds 42-46 (means; FCT error bars = 95% t-CI). One section per sending rate
per source: <b>under</b> 100G, <b>matched</b> 200G, <b>over</b> 400G, relative to the 200G that a 50%-degraded ToR0 uplink
leaves per host. Columns = failure model: healthy; uniform 50% (all 32 ToR0 uplinks); non-uniform (even agg 25%, odd agg 75%).<br>
<b>Split</b>: share of sends that used a random EV vs a valid EV from the buffer (stale = 0: no RTOs and no freezing in any run).
<b>k</b>: valid EVs in the buffer immediately before each draw (the previous trace row's post-event count), after the source's first ACK
(same definition as the C1 page), ToR0 sources 0-7 event traces; draws = SEND/RTX/RTS. The split uses the same post-warmup draws. <b>FCT</b>: p50/p99/max over all 1024 flows and mean over the
32 ToR0 flows. Loss: retransmits and ECN-marked ACKs per run (RTOs are 0 everywhere).
The acks-per-window panel from the C1 page is not reproduced: those traces were analysed and deleted in the sweep.</div>
__SECTIONS__
<script>
const DATA = __PAYLOAD__;
""" + COMMON_JS + """
const RATES = [["under", "UNDER capacity: 100 Gbps per source"], ["matched", "MATCHED to degraded capacity: 200 Gbps per source"],
               ["over", "OVER capacity: 400 Gbps per source"]];
const FAILS = [["healthy", "healthy"], ["uniform50", "uniform 50%"], ["nonuniform", "non-uniform 25/75%"]];
const BS = [1, 2, 4, 8, 16, 32, 64], BCAT = BS.map(b => "B=" + b);
const rows = (r, f) => DATA.rows.filter(x => x.rate === r && x.fail === f).sort((a, b) => a.B - b.B);
const at = (rs, b) => rs.find(x => x.B === b);
const F = (v, d) => v == null ? "-" : v.toFixed(d);

function splitPlot(r, f, id) {
  const rs = rows(r, f);
  plotWithHeadline(id, [
    {x: BCAT, y: rs.map(x => 100 - x.pct_random_mean), type: "bar", name: "valid", marker: {color: "#22a884"}},
    {x: BCAT, y: rs.map(x => x.pct_random_mean), type: "bar", name: "random", marker: {color: "#94a3b8"}}],
    {title: {text: "EV source split -- " + r + " / " + f, font: {size: 12}}, barmode: "stack",
     xaxis: {type: "category"}, yaxis: {title: "% of sends", range: [0, 100]}, legend: {orientation: "h", y: -0.25},
     margin: {t: 36, b: 70, l: 50, r: 10}, height: 320}, {responsive: true});
}
function kPlot(r, f, id) {
  const rs = rows(r, f);
  const sum = (x, lo, hi) => { let s = 0; for (let i = lo; i <= hi; i++) s += x["kdist_" + i] || 0; return s; };
  const parts = [["k=0", x => sum(x, 0, 0), "#94a3b8"], ["k=1", x => sum(x, 1, 1), "#bde0d0"],
    ["k=2", x => sum(x, 2, 2), "#7ad151"], ["k=3", x => sum(x, 3, 3), "#22a884"],
    ["k=4-7", x => sum(x, 4, 7), "#2a788e"], ["k>=8", x => sum(x, 8, 32), "#440154"]];
  const traces = parts.map(([n, fn, c]) => ({x: BCAT, y: rs.map(fn), type: "bar", name: n, marker: {color: c}}));
  plotWithHeadline(id, traces, {title: {text: "Valid EVs in buffer just before a send (k) -- " + r + " / " + f, font: {size: 12}}, barmode: "stack",
    xaxis: {type: "category"}, yaxis: {title: "% of sends", range: [0, 100]}, legend: {orientation: "h", y: -0.3},
    margin: {t: 36, b: 90, l: 50, r: 10}, height: 320}, {responsive: true});
}
function fctPlot(r, f, id) {
  const rs = rows(r, f);
  const ser = [["fct_p50", "p50 (all)", "#2a788e"], ["fct_p99", "p99 (all)", "#f59e0b"], ["fct_max", "max (all)", "#dc2626"],
               ["fct_tor0_mean", "mean (ToR0 flows)", "#111"]];
  const traces = ser.map(([k, n, c]) => ({x: BCAT, y: rs.map(x => x[k + "_mean"]), mode: "lines+markers", name: n, line: {color: c, width: 1.6},
    error_y: {type: "data", array: rs.map(x => x[k + "_ci95"]), visible: true, thickness: 1, width: 3}}));
  plotWithHeadline(id, traces, {title: {text: "FCT (us) -- " + r + " / " + f, font: {size: 12}},
    xaxis: {type: "category"}, yaxis: {title: "us"}, legend: {orientation: "h", y: -0.3},
    margin: {t: 36, b: 90, l: 55, r: 10}, height: 320}, {responsive: true});
}
function lossPlot(r, f, id) {
  const rs = rows(r, f);
  plotWithHeadline(id, [
    {x: BCAT, y: rs.map(x => x.rtx_mean), type: "bar", name: "retransmits / run", marker: {color: "#dc2626"}},
    {x: BCAT, y: rs.map(x => x.ecn_acks_mean), type: "bar", name: "ECN-marked ACKs / run", marker: {color: "#f59e0b"}}],
    {title: {text: "Loss and marking per run -- " + r + " / " + f, font: {size: 12}}, barmode: "group",
     xaxis: {type: "category"}, yaxis: {title: "count"}, legend: {orientation: "h", y: -0.3},
     margin: {t: 36, b: 90, l: 55, r: 10}, height: 320}, {responsive: true});
}
function verdict(r, id) {
  let h = "<table><tr><th>failure model</th><th>% random B=1</th><th>B=2</th><th>B=4</th><th>B=8</th><th>B=64</th>" +
          "<th>ToR0 mean FCT B=1 (us)</th><th>B=8</th><th>B=64</th><th>FCT change B=1&rarr;8</th><th>FCT change B=8&rarr;64</th></tr>";
  FAILS.forEach(([f, lab]) => { const rs = rows(r, f), g = b => at(rs, b);
    const a = g(1).fct_tor0_mean_mean, c = g(8).fct_tor0_mean_mean, d = g(64).fct_tor0_mean_mean;
    h += "<tr><td>" + lab + "</td>" + [1, 2, 4, 8, 64].map(b => "<td>" + F(g(b).pct_random_mean, 1) + "</td>").join("") +
         "<td>" + F(a, 1) + "</td><td>" + F(c, 1) + "</td><td>" + F(d, 1) + "</td><td>" + F(100 * (c - a) / a, 2) + "%</td><td>" + F(100 * (d - c) / c, 2) + "%</td></tr>"; });
  document.getElementById(id).innerHTML = h + "</table>";
}
RATES.forEach(([r]) => { verdict(r, "verdict_" + r);
  FAILS.forEach(([f]) => { splitPlot(r, f, "split_" + r + "_" + f); kPlot(r, f, "k_" + r + "_" + f);
    fctPlot(r, f, "fct_" + r + "_" + f); lossPlot(r, f, "loss_" + r + "_" + f); }); });
</script>
</body></html>
"""

M4_EXTRA_CSS = """<style>
h2 { font-size: 16px; margin: 22px 0 4px; padding-top: 10px; border-top: 2px solid #111; }
h3 { font-size: 13px; margin: 8px 0 2px; color: #333; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
table { border-collapse: collapse; font-size: 12px; margin: 4px 0 8px; }
th, td { border: 1px solid #ddd; padding: 3px 7px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { background: #f3f4f6; }
@media (max-width: 1100px) { .grid3 { grid-template-columns: 1fr; } }
</style>
"""

M4_RATES = [("under", "UNDER capacity: 100 Gbps per source"),
            ("matched", "MATCHED to degraded capacity: 200 Gbps per source"),
            ("over", "OVER capacity: 400 Gbps per source")]
M4_FAILS = ["healthy", "uniform50", "nonuniform"]
M4_METRICS = ["pct_random", "pct_random_incl_warmup", "k_ge1", "k_ge2", "k_ge3", "k_ge4", "k_ge8", "fct_p50", "fct_p99", "fct_max",
              "fct_tor0_mean", "rtx", "ecn_acks"]


def build_m4():
    s = pd.read_csv(ROOT / "M4" / "data" / "m4_summary.csv")
    keep = (["rate", "fail", "B", "n_seeds"] + [f"{k}_{t}" for k in M4_METRICS for t in ("mean", "ci95")]
            + [f"kdist_{i}" for i in range(33)])
    rows = [{k: clean(v) for k, v in r.items()} for r in s[keep].to_dict("records")]
    sections = ""
    for r, title in M4_RATES:
        sections += f'<h2>{title}</h2>\n<div id="verdict_{r}"></div>\n'
        for kind, label in [("split", "valid vs random EV"), ("k", "k distribution"), ("fct", "FCT statistics"),
                            ("loss", "retransmits and ECN marks")]:
            sections += f'<h3>{label}</h3>\n<div class="grid3">' + "".join(
                panel(f"{kind}_{r}_{f}") for f in M4_FAILS) + "</div>\n"
    html = HEAD.replace("__TITLE__", "M4 REPS buffer size per sending rate").replace("</head>", M4_EXTRA_CSS + "</head>")
    html += M4_BODY.replace("__SECTIONS__", sections)
    html = html.replace("__PAYLOAD__", json.dumps({"rows": rows}))
    out = ROOT / "M4" / "plots" / "interactive.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    build_m1()
    build_m4()

#!/usr/bin/env python3
"""Emit plots/interactive.html -- self-contained Plotly view of T1's
ratio.csv (FCT ratio vs lost ToR0 bandwidth, NSCC). Plotly from cdnjs.

    python3 build_interactive.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent.parent / "plots" / "interactive.html"

N_ORDER = [0, 1, 2, 4, 8, 16, 32]

NUM_FIELDS = {"size", "n", "model_ratio", "max_ratio_mean", "max_ratio_ci"}


def payload():
    rows = []
    with open(D / "ratio.csv", newline="") as f:
        for row in csv.DictReader(f):
            out = {}
            for k, v in row.items():
                if v == "" or v is None:
                    out[k] = None
                elif k in NUM_FIELDS:
                    out[k] = float(v) if "." in v or "e" in v.lower() else int(v)
                else:
                    out[k] = v
            rows.append(out)
    return rows


HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<title>T1 - FCT vs lost bandwidth (NSCC)</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.note { font-size: 12px; color: #555; margin-bottom: 12px; max-width: 980px; }
.tabs { margin-bottom: 10px; }
.tabs button { font: inherit; font-size: 13px; padding: 5px 14px; margin-right: 6px;
  border: 1px solid #ccc; border-radius: 6px; background: #f5f5f5; cursor: pointer; }
.tabs button.active { background: #2a78d6; color: #fff; border-color: #2a78d6; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; max-width: 900px; position: relative; }
.copy-btn { position: absolute; top: 6px; right: 6px; z-index: 10; opacity: 0;
  transition: opacity .15s; font-size: 11px; padding: 3px 8px; cursor: pointer;
  background: #fff; border: 1px solid #bbb; border-radius: 4px; color: #333; }
.panel:hover .copy-btn { opacity: 1; }
.copy-btn.copied { background: #dcfce7; border-color: #16a34a; color: #166534; }
table { border-collapse: collapse; font-size: 12px; margin-top: 10px; }
th, td { text-align: right; padding: 4px 10px; border-bottom: 1px solid #ddd; }
th:first-child, td:first-child { text-align: left; }
th { color: #666; font-weight: 600; }
#toggleTable { font-size: 12px; color: #2a78d6; cursor: pointer; background: none;
  border: none; font-family: inherit; padding: 0; margin-top: 8px; }
</style></head>
<body>
<h1>T1: FCT vs lost bandwidth (NSCC)</h1>
<div class="note">ToR0's uplinks (n of 32) degraded to 50% speed, NSCC. Ratio = <b>max</b> FCT at that n
over max FCT at n=0 (healthy), across the 32 ToR0 flows. Dashed grey = bandwidth-loss model
64/(64-n). reps_b8_nscc sprays across all 32 paths, so its max tracks the model directly as n
rises, though max is a single-flow statistic and noisier seed to seed than a percentile (see
T1/RESULTS.md).</div>
<div class="tabs">
  <button id="tab4" class="active">4 MiB</button>
  <button id="tab16">16 MiB</button>
</div>
<div class="panel"><button class="copy-btn" onclick="copyTitle('plot', this)">copy</button><div id="plot" style="height:480px;"></div></div>
<button id="toggleTable">Show data table &#9662;</button>
<div id="tableWrap" style="display:none;"></div>
<script>
const ROWS = __DATA__;
const N_ORDER = [0, 1, 2, 4, 8, 16, 32];
const COL = {model: "#9ca3af", nscc: "#1baf7a"};

const TITLE_BY_ID = {};
function plotWithHeadline(divId, traces, layout, opts) {
  TITLE_BY_ID[divId] = layout.title.text.replace(/&gt;/g, ">").replace(/&lt;/g, "<");
  Plotly.newPlot(divId, traces, layout, opts);
}
function copyTitle(divId, btn) {
  const text = TITLE_BY_ID[divId] || "";
  const done = () => {
    const prev = btn.textContent;
    btn.textContent = "copied!";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = prev; btn.classList.remove("copied"); }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); } catch (e) {}
  document.body.removeChild(ta);
  done();
}

function rowsFor(size) { return ROWS.filter(r => r.size === size); }

function traces(size) {
  const rs = rowsFor(size);
  const byN = (arm, n) => rs.find(r => r.n === n && r.arm === arm);
  const x = N_ORDER.map(String);
  const modelY = N_ORDER.map(n => { const r = byN("reps_b8_nscc", n); return r ? r.model_ratio : null; });
  const nsccY = N_ORDER.map(n => { const r = byN("reps_b8_nscc", n); return r ? r.max_ratio_mean : null; });
  const nsccErr = N_ORDER.map(n => { const r = byN("reps_b8_nscc", n); return r ? r.max_ratio_ci : 0; });
  return [
    { type: "scatter", x, y: modelY, name: "model 64/(64-n)", mode: "lines",
      line: { color: COL.model, dash: "dash", width: 2 },
      hovertemplate: "n=%{x}<br>model %{y:.3f}x<extra></extra>" },
    { type: "scatter", x, y: nsccY, name: "reps_b8_nscc (max FCT)", mode: "lines+markers",
      line: { color: COL.nscc, width: 2 }, marker: { size: 7 },
      error_y: { type: "data", array: nsccErr, color: COL.nscc, thickness: 1.3, width: 3 },
      hovertemplate: "n=%{x}<br>%{y:.3f}x +- CI<extra></extra>" },
  ];
}

function draw(size) {
  plotWithHeadline("plot", traces(size), {
    title: { text: "FCT ratio vs n degraded ToR0 uplinks -- " + (size === 4194304 ? "4 MiB" : "16 MiB"), font: { size: 14 } },
    xaxis: { title: "degraded ToR0 uplinks (n of 32)", type: "category", categoryorder: "array",
             categoryarray: N_ORDER.map(String) },
    yaxis: { title: "FCT ratio vs n=0", rangemode: "tozero" },
    legend: { orientation: "h", y: -0.25 },
    margin: { t: 40, b: 110 }, height: 480,
  }, { responsive: true });
}

function drawTable(size) {
  const rs = rowsFor(size);
  const byN = (arm, n) => rs.find(r => r.n === n && r.arm === arm);
  const fmt = v => (v == null || Number.isNaN(v)) ? "-" : v.toFixed(3) + "x";
  let html = "<table><thead><tr><th>n</th><th>model</th>" +
    "<th>reps_b8_nscc max FCT +- CI</th></tr></thead><tbody>";
  for (const n of N_ORDER) {
    const ns = byN("reps_b8_nscc", n);
    html += "<tr><td>" + n + "</td><td>" + fmt(ns ? ns.model_ratio : null) + "</td>" +
      "<td>" + fmt(ns ? ns.max_ratio_mean : null) + " +- " + (ns ? ns.max_ratio_ci.toFixed(3) : "0.000") + "</td></tr>";
  }
  html += "</tbody></table>";
  document.getElementById("tableWrap").innerHTML = html;
}

let currentSize = 4194304;
document.getElementById("tab4").addEventListener("click", () => {
  currentSize = 4194304;
  document.getElementById("tab4").classList.add("active");
  document.getElementById("tab16").classList.remove("active");
  draw(currentSize);
  if (document.getElementById("tableWrap").style.display !== "none") drawTable(currentSize);
});
document.getElementById("tab16").addEventListener("click", () => {
  currentSize = 16777216;
  document.getElementById("tab16").classList.add("active");
  document.getElementById("tab4").classList.remove("active");
  draw(currentSize);
  if (document.getElementById("tableWrap").style.display !== "none") drawTable(currentSize);
});
document.getElementById("toggleTable").addEventListener("click", () => {
  const wrap = document.getElementById("tableWrap");
  const showing = wrap.style.display !== "none";
  wrap.style.display = showing ? "none" : "block";
  document.getElementById("toggleTable").innerHTML = showing ? "Show data table &#9662;" : "Hide data table &#9652;";
  if (!showing) drawTable(currentSize);
});

draw(currentSize);
</script>
</body></html>
"""


def main() -> None:
    data = json.dumps(payload())
    html = HTML.replace("__DATA__", data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

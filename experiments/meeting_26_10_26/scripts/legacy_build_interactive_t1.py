#!/usr/bin/env python3
"""T1/plots/interactive.html: Plotly page for T1 (matched 200G, ToR0 uplinks even agg r / odd agg 1-r).
Reuses the M4 page (meeting_23_10_26/scripts/build_interactive.py): its head, CSS, panel markup and JS panel functions
(split, k, ACKs per window, FCT, overwrites, loss, verdict table) are imported and only the rate/failure/B constants are
swapped; extra panels (gate table, overlays) are appended.
Input: T1/data/t1_summary.csv (T1/scripts/aggregate_t1.py). experiments/**/*.html is gitignored.
"""
import importlib.util, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
T1 = HERE.parent / "T1"
spec = importlib.util.spec_from_file_location("bi23", HERE.parents[1] / "meeting_23_10_26" / "scripts" / "build_interactive.py")
bi = importlib.util.module_from_spec(spec); spec.loader.exec_module(bi)

FAILS = [("uniform50", "uniform 50/50"), ("nonuniform", "non-uniform 25/75"), ("r010", "non-uniform 10/90"),
         ("r005", "non-uniform 5/95")]   # r001 (1/99) left out of the page: it entered Freezing Mode (gate failed); data stays in t1_summary.csv

NOTE = """
<h1>T1: extreme non-uniform degradation, does the REPS buffer size B keep mattering?</h1>
<div class="note">Constant-rate sender at 200G per host (matched: NIC egress of data + ACKs, no congestion control), REPS (freezing), SRv6 32 paths, tornado 16 MiB, 1024 flows, trimming on,
seeds 42-44 (mean of 3; error bars = 95% t-CI). ToR0 uplinks: even agg at ratio r, odd agg at 1 - r (mean 0.5 in every row, so the 200G per host stays matched).
r = 0.5 and r = 0.25 are the M4 cells (r = 0.25 at B = 8 and 128 rerun here). Every metric has the M4 definition (see <code>meeting_23_10_26/M4/README.md</code>).
<b>Freezing Mode gate</b>: a cell is clear only if no flow had an RTO or entered Freezing Mode (whole run, 1024 flows). Gate-failing cells stay in every plot and are marked in the gate table;
read their FCT and EV statistics as a different mechanism (Freezing Mode), not as a pure buffer-size effect.</div>
<h2>Freezing Mode gate (RTOs / freeze entries, mean over seeds, whole run)</h2><div id="gate"></div>
<h2>All r overlaid</h2>
<div class="grid3">__OV1__</div>
<div class="grid3">__OV2__</div>
__SECTIONS__
"""

EXTRA_JS = """
const ALLF = FAILS.map(f => f[0]), LAB = Object.fromEntries(FAILS);
const col = ["#111", "#2a788e", "#22a884", "#f59e0b", "#dc2626"];
const failed = x => (x.rtos_mean || 0) > 0 || (x.freeze_entries_mean || 0) > 0;
function gateTable() {
  let h = "<table><tr><th>failure / B</th>" + BS.map(b => "<th>" + b + "</th>").join("") + "</tr>";
  ALLF.forEach(f => { h += "<tr><td>" + LAB[f] + "</td>" + BS.map(b => { const x = at(rows("matched", f), b);
    if (!x) return "<td>-</td>";
    return "<td style='background:" + (failed(x) ? "#fecaca" : "#dcfce7") + "'>" + F(x.rtos_mean, 1) + " / " + F(x.freeze_entries_mean, 1) + "</td>"; }).join("") + "</tr>"; });
  document.getElementById("gate").innerHTML = h + "</table><div class='note'>cell = RTOs / freeze entries per run; red = gate failed.</div>";
}
function overlay(id, key, title, ylab, ci) {
  const tr = ALLF.map((f, i) => { const rs = rows("matched", f); return {x: rs.map(x => "B=" + x.B), y: rs.map(x => x[key + "_mean"]), mode: "lines+markers", name: LAB[f],
    line: {color: col[i], width: 1.6}, error_y: ci ? {type: "data", array: rs.map(x => x[key + "_ci95"]), visible: true, thickness: 1, width: 3} : undefined,
    marker: {symbol: rs.map(x => failed(x) ? "x" : "circle"), size: 8}}; });
  plotWithHeadline(id, tr, {title: {text: title + " -- matched / all shapes (x = gate failed)", font: {size: 12}}, xaxis: {type: "category"}, yaxis: {title: ylab},
    legend: {orientation: "h", y: -0.3}, margin: {t: 36, b: 90, l: 55, r: 10}, height: 320}, {responsive: true});
}
gateTable();
overlay("ov_fct", "fct_max", "Max FCT, all flows", "us", true); overlay("ov_p99", "fct_p99", "p99 FCT", "us", true);
overlay("ov_ow", "pct_overwrite", "Valid-EV overwrites (% of clean ACKs)", "%", true); overlay("ov_rand", "pct_random", "Random draws", "%", false);
"""


def main():
    s = pd.read_csv(T1 / "data/t1_summary.csv")
    s = s[s.fail.isin([f for f, _ in FAILS] + ["healthy"])]
    metrics = list(dict.fromkeys(list(bi.M4_METRICS) + ["fct_max", "rtos", "freeze_entries", "n_freeze_events"]))
    keep = (["rate", "fail", "B", "n_seeds"] + [f"{k}_{t}" for k in metrics for t in ("mean", "ci95")]
            + [f"kdist_{i}" for i in range(65)] + [f"awdist_{i}" for i in range(9)])
    rows = [{k: bi.clean(v) for k, v in r.items()} for r in s[[c for c in keep if c in s.columns]].to_dict("records")]
    body = bi.M4_BODY
    js = body[body.index("const RATES"):]
    old_rates = 'const RATES = [["under", "UNDER capacity: 100 Gbps per source"], ["matched", "MATCHED to degraded capacity: 200 Gbps per source"],\n               ["over", "OVER capacity: 400 Gbps per source"]];'
    old_fails = 'const FAILS = [["healthy", "healthy"], ["uniform50", "uniform 50%"], ["nonuniform", "non-uniform 25/75%"]];'
    assert old_rates in js and old_fails in js and "const BS = [1, 2, 4, 8, 16, 32, 64]" in js, "M4 constants changed, update the swap"
    js = js.replace(old_rates, 'const RATES = [["matched", "MATCHED: 200 Gbps per source"]];')
    js = js.replace(old_fails, "const FAILS = " + json.dumps(FAILS) + ";")
    js = js.replace("const BS = [1, 2, 4, 8, 16, 32, 64]", "const BS = [1, 2, 4, 8, 16, 32, 64, 128]")
    # panel headlines: show the failure label (e.g. "non-uniform 25/75"), not the internal key ("nonuniform")
    flab = '(Object.fromEntries(FAILS)[f] || f)'
    assert js.count('" + r + " / " + f') == 5 and js.count('" + r + "/" + f') == 1, "M4 headline format changed, update the swap"
    js = js.replace('" + r + " / " + f', '" + r + " / " + ' + flab).replace('" + r + "/" + f', '" + r + " / " + ' + flab)
    fct_call = 'fctPlot(r, f, "fct_" + r + "_" + f); '
    assert fct_call in js, "M4 panel-draw line changed, update the swap"
    js = js.replace(fct_call, "")      # FCT statistics section removed from the page
    js = js.replace("</script>\n</body></html>", EXTRA_JS + "</script>\n</body></html>")
    sections = '<h2>MATCHED: 200 Gbps per source, one panel per failure shape</h2>\n<div id="verdict_matched"></div>\n'
    for kind, label in [("split", "valid vs random EV"), ("k", "k distribution"), ("ackwin", "ACKs per SEND-to-SEND window"), ("overwrite", "valid EVs overwritten by a clean ACK"), ("loss", "retransmits and ECN marks")]:
        sections += f"<h3>{label}</h3>\n"
        for part in (FAILS[:3], FAILS[3:]):
            sections += '<div class="grid3">' + "".join(bi.panel(f"{kind}_matched_{f}") for f, _ in part) + "</div>\n"
    html = bi.HEAD.replace("__TITLE__", "T1 extreme non-uniform degradation").replace("</head>", bi.M4_EXTRA_CSS + "</head>")
    html += NOTE.replace("__SECTIONS__", sections).replace("__OV1__", "".join(bi.panel(d) for d in ("ov_fct", "ov_p99", "ov_ow"))).replace("__OV2__", "".join(bi.panel(d) for d in ("ov_rand",))) + "<script>\nconst DATA = " + json.dumps({"rows": rows}) + ";\n" + bi.COMMON_JS + js
    out = T1 / "plots" / "interactive.html"
    out.write_text(html, encoding="utf-8"); print("wrote", out)


if __name__ == "__main__":
    main()

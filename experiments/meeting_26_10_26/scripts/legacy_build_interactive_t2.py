#!/usr/bin/env python3
"""T2/plots/interactive.html: one Plotly page for T2 (3-tier k=8, matched 200G, pod0 uplinks degraded 50% on average), laid out like the T1 page
(scripts/build_interactive.py): gate table, overlays of all shapes, then one panel per shape for EV split, k, ACKs per window, overwrites, loss.
Both sub-experiments are on the page (A: pod0 ToR->agg uplinks, B: pod0 agg->core uplinks); every headline names the scope.
Head, CSS, panel markup (with the headline copy button) and JS panel functions come from the M4 page (meeting_23_10_26/scripts/build_interactive.py);
only the rate/failure/B constants are swapped. Input: T2/{tor_agg,agg_core}/data/t2_summary.csv (scripts/aggregate_t2.py). experiments/**/*.html is gitignored."""
import importlib.util, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
T2 = HERE.parent / "T2"
spec = importlib.util.spec_from_file_location("bi23", HERE.parents[1] / "meeting_23_10_26" / "scripts" / "build_interactive.py")
bi = importlib.util.module_from_spec(spec); spec.loader.exec_module(bi)

SHAPES = [("u50", "uniform 50/50"), ("r025", "non-uniform 25/75"), ("r010", "non-uniform 10/90"), ("r005", "non-uniform 5/95")]
SCOPES = [("a", "tor_agg", "pod0 ToR->agg"), ("b", "agg_core", "pod0 agg->core")]
FAILS = [("healthy", "healthy (no degradation)")] + [(f"{p}_{k}", f"{tag}, {lab}") for p, _, tag in SCOPES for k, lab in SHAPES]

NOTE = """
<h1>T2: 3-tier fat tree k=8, degradation on pod0 uplinks, does the REPS buffer size B keep mattering?</h1>
<div class="note">3-tier fat tree k=8 (128 hosts, 8 pods x 4 ToRs x 4 hosts, 16 paths), tornado 16 MiB (host i sends to i + 64, every flow crosses the core), 128 flows, trimming on.
Constant-rate sender at 200G per host (matched: NIC egress of data + ACKs, no congestion control), REPS (freezing), SRv6 16 paths, seeds 42-46 (mean of 5; error bars = 95% t-CI).
Degraded links: <b>A, pod0 ToR->agg</b> = the 16 ToR->agg uplinks of pod0 (4 ToRs x 4 aggs); <b>B, pod0 agg->core</b> = the 16 agg->core uplinks of pod0 (4 aggs x 4 cores).
In every ToR (A) or agg (B) 2 uplinks run at ratio r and 2 at 1 - r (mean 0.5 in every row, so the 200G per host stays matched). Every metric has the M4 definition (see <code>meeting_23_10_26/M4/README.md</code>);
k, overwrites and ACKs per window come from the 16 traced pod0 hosts, FCT and counts from all 128 flows.
<b>Freezing Mode gate</b>: a cell is clear only if no flow had an RTO or entered Freezing Mode (whole run, 128 flows). Gate-failing cells stay in every plot and are marked in the gate table;
read their FCT and EV statistics as a different mechanism (Freezing Mode), not as a pure buffer-size effect (none failed in T2).</div>
<h2>Freezing Mode gate (RTOs / freeze entries, mean over seeds, whole run)</h2><div id="gate"></div>
<h2>All shapes overlaid: A (pod0 ToR->agg) left, B (pod0 agg->core) right</h2>
__OVERLAYS__
__SECTIONS__
"""

EXTRA_JS = """
const ALLF = FAILS.map(f => f[0]), LAB = Object.fromEntries(FAILS);
const SHCOL = {healthy: "#6b7280", u50: "#111", r025: "#2a788e", r010: "#22a884", r005: "#dc2626"};
const shapeOf = f => f === "healthy" ? "healthy" : f.slice(2);
const SCOPE_NAME = {a: "pod0 ToR->agg", b: "pod0 agg->core"};
const failed = x => (x.rtos_mean || 0) > 0 || (x.freeze_entries_mean || 0) > 0;
function gateTable() {
  let h = "<table><tr><th>scope, shape / B</th>" + BS.map(b => "<th>" + b + "</th>").join("") + "</tr>";
  ALLF.forEach(f => { h += "<tr><td>" + LAB[f] + "</td>" + BS.map(b => { const x = at(rows("matched", f), b);
    if (!x) return "<td>-</td>";
    return "<td style='background:" + (failed(x) ? "#fecaca" : "#dcfce7") + "'>" + F(x.rtos_mean, 1) + " / " + F(x.freeze_entries_mean, 1) + "</td>"; }).join("") + "</tr>"; });
  document.getElementById("gate").innerHTML = h + "</table><div class='note'>cell = RTOs / freeze entries per run; red = gate failed.</div>";
}
function overlay(id, key, title, ylab, ci, sc) {
  const tr = ALLF.filter(f => f === "healthy" || f.startsWith(sc + "_")).map(f => { const rs = rows("matched", f); return {x: rs.map(x => "B=" + x.B), y: rs.map(x => x[key + "_mean"]), mode: "lines+markers", name: LAB[f],
    line: {color: SHCOL[shapeOf(f)], width: 1.6}, error_y: ci ? {type: "data", array: rs.map(x => x[key + "_ci95"]), visible: true, thickness: 1, width: 3} : undefined,
    marker: {symbol: rs.map(x => failed(x) ? "x" : "circle"), size: 8}}; });
  plotWithHeadline(id, tr, {title: {text: title + " -- matched / 3-tier " + SCOPE_NAME[sc] + " / all shapes (x = gate failed)", font: {size: 12}}, xaxis: {type: "category"}, yaxis: {title: ylab},
    legend: {orientation: "h", y: -0.3}, margin: {t: 36, b: 110, l: 55, r: 10}, height: 340}, {responsive: true});
}
gateTable();
["a", "b"].forEach(sc => {
  overlay("ov_fct_" + sc, "fct_max", "Max FCT, all flows", "us", true, sc); overlay("ov_p99_" + sc, "fct_p99", "p99 FCT", "us", true, sc);
  overlay("ov_ow_" + sc, "pct_overwrite", "Valid-EV overwrites (% of clean ACKs)", "%", true, sc); overlay("ov_rand_" + sc, "pct_random", "Random draws", "%", false, sc);
});
"""


def load():
    keep_cols = None
    parts = []
    for p, d, _ in SCOPES:
        s = pd.read_csv(T2 / d / "data/t2_summary.csv")
        s = s[s["shape"] != "healthy"] if p == "b" else s
        s = s.copy(); s["rate"] = "matched"
        s["fail"] = [("healthy" if sh == "healthy" else f"{p}_{sh}") for sh in s["shape"]]
        parts.append(s)
    return pd.concat(parts, ignore_index=True)


def main():
    s = load()
    metrics = list(dict.fromkeys(list(bi.M4_METRICS) + ["fct_max", "rtos", "freeze_entries", "n_freeze_events", "rtx"]))
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
    # panel headlines: show the scope and shape label (e.g. "pod0 ToR->agg, non-uniform 5/95"), not the internal key
    flab = '(Object.fromEntries(FAILS)[f] || f)'
    assert js.count('" + r + " / " + f') == 5 and js.count('" + r + "/" + f') == 1, "M4 headline format changed, update the swap"
    js = js.replace('" + r + " / " + f', '" + r + " / " + ' + flab).replace('" + r + "/" + f', '" + r + " / " + ' + flab)
    fct_call = 'fctPlot(r, f, "fct_" + r + "_" + f); '
    assert fct_call in js, "M4 panel-draw line changed, update the swap"
    js = js.replace(fct_call, "")      # FCT statistics section is not part of the T1-style page
    js = js.replace("</script>\n</body></html>", EXTRA_JS + "</script>\n</body></html>")
    sections = '<h2>MATCHED: 200 Gbps per source, one panel per shape, A (pod0 ToR->agg) left and B (pod0 agg->core) right</h2>\n<div id="verdict_matched"></div>\n'
    for kind, label in [("split", "valid vs random EV"), ("k", "k distribution"), ("ackwin", "ACKs per SEND-to-SEND window"), ("overwrite", "valid EVs overwritten by a clean ACK"), ("loss", "retransmits and ECN marks")]:
        sections += f"<h3>{label}</h3>\n"
        sections += '<div class="grid">' + bi.panel(f"{kind}_matched_healthy") + '<div class="note">healthy matched reference (no degradation), the same for both scopes</div></div>\n'
        for k, _ in SHAPES:
            sections += '<div class="grid">' + "".join(bi.panel(f"{kind}_matched_{p}_{k}") for p, _, _ in SCOPES) + "</div>\n"
    overlays = "".join('<div class="grid">' + bi.panel(f"{m}_a") + bi.panel(f"{m}_b") + "</div>\n" for m in ("ov_fct", "ov_p99", "ov_ow", "ov_rand"))
    note = NOTE.replace("__SECTIONS__", sections).replace("__OVERLAYS__", overlays)
    html = bi.HEAD.replace("__TITLE__", "T2 3-tier pod0 degradation").replace("</head>", bi.M4_EXTRA_CSS + "</head>")
    html += note + "<script>\nconst DATA = " + json.dumps({"rows": rows}) + ";\n" + bi.COMMON_JS + js
    out = T2 / "plots" / "interactive.html"; out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8"); print("wrote", out)


if __name__ == "__main__":
    main()

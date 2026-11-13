#!/usr/bin/env python3
"""T3/plots/interactive.html: Plotly page for T3 (matched 200G, ToR0 uplinks 5/95, topology / paths / latency / ACK spacing varied).
Same approach as build_interactive.py (T1): imports the M4 page pieces from meeting_23_10_26/scripts/build_interactive.py (head, CSS,
panel markup, JS panel functions) and swaps the constants; the verdict table is replaced (it needs B=1 and B=64, absent here).
Input: T3/data/t3_summary.csv, t3_knees.csv, t3_uplinks.json (T3/scripts/aggregate_t3.py), data/configs/configs.json.
experiments/**/*.html is gitignored."""
import importlib.util, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
T3 = HERE.parent / "T3"
spec = importlib.util.spec_from_file_location("bi23", HERE.parents[1] / "meeting_23_10_26" / "scripts" / "build_interactive.py")
bi = importlib.util.module_from_spec(spec); spec.loader.exec_module(bi)

CFGS = json.loads((T3 / "data/configs/configs.json").read_text())
AXES = [("base", "Baseline"), ("A", "A. Hosts / radix (2-tier, paths = radix)"), ("B", "B. Path count at 1024 hosts"), ("C", "C. Tiers (3-tier, 6 hops)"),
        ("D", "D. Link latency, q/ECN fixed at the 1 us BDP"), ("D2", "D2. Link latency, q/ECN scaled to the BDP"), ("E", "E. ACK spacing (-sack_threshold)")]
LABEL = {c["name"]: "5/95, " + c["note"] for c in CFGS}

NOTE = """
<h1>T3: where does "8" come from? REPS buffer size B at 5/95 degradation, topology, paths, RTT and ACK spacing varied</h1>
<div class="note">Constant-rate sender at 200G per host (matched; NIC egress of data + ACKs, no congestion control), REPS (freezing), SRv6, tornado 16 MiB, trimming on.
ToR0 uplinks: even agg at 0.05, odd agg at 0.95 (non-uniform 5/95, mean 0.5, so 200G stays matched in every config). One variable moves per axis from the baseline
(1024 hosts, 2-tier, 32 paths, 1 us links, ACK every ~1 packet). Metrics have the M4 definitions (<code>meeting_23_10_26/M4/README.md</code>). Seeds and error bars: see the
<i>seeds</i> column of the knee table (error bars = 95% t-CI where there is more than one seed; none for single-seed screens).
<b>Freezing Mode gate</b>: a cell is clear only if no flow had an RTO or entered Freezing Mode; failing cells stay in every plot and are marked.
<b>Knees</b> (one-sided: smallest B from which every larger B is within the CI, or 0.2%, of the largest B or better): <code>B_fct</code> on max FCT, <code>B_fct (p99)</code> on p99 FCT.
<code>B_ow</code> = smallest B with &lt; 0.1% valid-EV overwrites. <code>B_ks99</code> = smallest B at or above the <b>steady-state</b> uncapped k p99 (k at B=128; the first and last 15% of each traced source span are dropped; 8 traced hosts of ToR0).
Whole-run k max is dominated by the flow drain (retransmits after the last send meet a full buffer): see the "drain k max" column and the k-vs-time panel.
<b>Confounds</b>: latency x4/x16 (axis D) keep <code>-q/-ecn</code> at the 1 us BDP (more ECN marks, 22-31% random EVs, thousands of retransmits); axis D2 scales them to the BDP. The p50 FCT rise in both is the extra propagation RTT, not a threshold effect; the ACK-spacing cells change how many EVs are recycled
(60-74% random EVs), not how variable the supply is; 3-tier degrades the first hop only. Those rows are not clean knee measurements.</div>
<h2>Knee summary</h2><div id="knees"></div><div class="grid3"><div id="knee_bars"></div><div id="knee_k"></div><div id="knee_slow"></div></div>
<h2>Why 8: steady-state uncapped k and the knees against the axis variable</h2><div class="grid3"><div id="why_A"></div><div id="why_B"></div><div id="why_C"></div></div>
<div class="grid3"><div id="why_D"></div><div id="why_D2"></div><div id="why_E"></div></div><div class="grid3"><div id="why_ow"></div></div>
<h2>Uncapped k against time (B=128, seed 42, max over traced sources per 20 us bin)</h2>
<div>config: <select id="tsF"></select></div><div id="kts"></div>
<h2>Freezing Mode gate (RTOs / freeze entries, mean over seeds, whole run)</h2><div id="gate"></div>
<h2>Max FCT by axis (baseline repeated in each panel)</h2>
<div class="grid3"><div id="ax_A"></div><div id="ax_B"></div><div id="ax_C"></div></div>
<div class="grid3"><div id="ax_D"></div><div id="ax_D2"></div><div id="ax_E"></div></div><div class="grid3"><div id="ax_ow"></div></div>
<h2>Per-uplink behaviour of ToR0 (seed-mean, from -log_queue_stats)</h2>
<div>config: <select id="upF"></select> B: <select id="upB"></select></div><div id="uplinks"></div>
__SECTIONS__
"""

VERDICT_JS = """function verdict(r, id) {
  let h = "<table><tr><th>config</th><th>% random B=2</th><th>B=8</th><th>B=128</th><th>ToR0 mean FCT B=2 (us)</th><th>B=8</th><th>B=128</th><th>FCT change B=2&rarr;8</th><th>FCT change B=8&rarr;128</th></tr>";
  FAILS.forEach(([f, lab]) => { const rs = rows(r, f), g = b => at(rs, b) || {};
    const a = g(2).fct_tor0_mean_mean, c = g(8).fct_tor0_mean_mean, d = g(128).fct_tor0_mean_mean;
    h += "<tr><td>" + lab + "</td>" + [2, 8, 128].map(b => "<td>" + F(g(b).pct_random_mean, 1) + "</td>").join("") +
         "<td>" + F(a, 1) + "</td><td>" + F(c, 1) + "</td><td>" + F(d, 1) + "</td><td>" + F(100 * (c - a) / a, 2) + "%</td><td>" + F(100 * (d - c) / c, 2) + "%</td></tr>"; });
  document.getElementById(id).innerHTML = h + "</table>";
}
"""

EXTRA_JS = """
const ALLF = FAILS.map(f => f[0]), LAB = Object.fromEntries(FAILS), AXOF = Object.fromEntries(DATA.cfgs.map(c => [c.name, c.axis]));
const col = ["#111", "#2a788e", "#22a884", "#f59e0b", "#dc2626", "#7c3aed", "#0ea5e9"];
const failed = x => (x.rtos_mean || 0) > 0 || (x.freeze_entries_mean || 0) > 0;
const lay = (t, h) => ({title: {text: t, font: {size: 12}}, xaxis: {type: "category"}, legend: {orientation: "h", y: -0.3}, margin: {t: 36, b: 90, l: 55, r: 10}, height: h || 320});
const FLAGS = {lat4_bdpq: "q/ECN scaled to BDP", lat16_bdpq: "q/ECN scaled to BDP; 19% random EVs remain", lat4_h1024_p32: "q/ECN fixed at 1 us BDP", lat16_h1024_p32: "q/ECN fixed at 1 us BDP; k tail at cap in drain", sack8000: "fewer ACKs: EV supply cut", sack16384: "fewer ACKs: EV supply cut",
  t3_h128_p16: "3-tier, first-hop degrade", t3_h1024_p64: "3-tier, first-hop degrade"};
function kneeTable() {
  let h = "<table><tr><th>config</th><th>seeds</th><th>gate</th><th>steady k p50</th><th>p99</th><th>max</th><th>drain k max</th><th>B_ks99</th><th>B_ow</th><th>B_fct</th><th>B_fct (p99)</th>" +
          "<th>max FCT B=8 (us)</th><th>B=128</th><th>p50 FCT (us)</th><th>% random EVs B=8</th><th>ECN ACKs B=8</th><th>retransmits B=8</th><th>% sends on degraded uplinks, B=8</th><th>flag</th></tr>";
  DATA.knees.forEach(k => { h += "<tr><td>" + LAB[k.cfg] + "</td><td>" + k.n_seeds + "</td><td style='background:" + (k.gate_clear ? "#dcfce7" : "#fecaca") + "'>" + (k.gate_clear ? "clear" : "FAILED") + "</td>" +
    [k.k_steady_p50, k.k_steady_p99, k.k_steady_max, k.k_trace_last_max].map(v => "<td>" + F(v, 1) + "</td>").join("") +
    [k.B_ks99, k.B_ow, k.B_fct, k.B_fct_p99].map(v => "<td>" + (v == null ? "-" : v) + "</td>").join("") +
    "<td>" + F(k.fct_max_B8, 1) + "</td><td>" + F(k.fct_max_top, 1) + "</td><td>" + F(k.fct_p50_top, 1) + "</td><td>" + F(k.pct_random_B8, 1) + "</td><td>" + F(k.ecn_acks_B8, 0) +
    "</td><td>" + F(k.rtx_B8, 0) + "</td><td>" + F(k.slow_share_B8, 1) + "</td><td>" + (FLAGS[k.cfg] || "") + (k.n_seeds < 3 ? " (" + k.n_seeds + " seed)" : "") + "</td></tr>"; });
  document.getElementById("knees").innerHTML = h + "</table>";
}
function kneeBars() {
  const x = DATA.knees.map(k => LAB[k.cfg].replace("5/95, ", ""));
  const tr = [["k_steady_p99", "steady k p99", "#94a3b8"], ["B_ks99", "B_ks99", "#2a788e"], ["B_ow", "B_ow", "#7c3aed"], ["B_fct", "B_fct", "#dc2626"]]
    .map(([k, n, c]) => ({x, y: DATA.knees.map(r => r[k]), type: "bar", name: n, marker: {color: c}}));
  plotWithHeadline("knee_bars", tr, {title: {text: "Knees vs steady k p99 -- matched / 5/95 / all configs", font: {size: 12}}, barmode: "group", yaxis: {type: "log", title: "buffer entries"},
    legend: {orientation: "h", y: -0.5}, margin: {t: 36, b: 150, l: 55, r: 10}, height: 360}, {responsive: true});
  plotWithHeadline("knee_k", [{x, y: DATA.knees.map(r => r.k_steady_max), type: "bar", marker: {color: "#0ea5e9"}, name: "steady k max"},
                              {x, y: DATA.knees.map(r => r.k_trace_last_max), type: "bar", marker: {color: "#f59e0b"}, name: "drain k max"}],
    {title: {text: "k max, steady state vs flow drain (B=128) -- matched / 5/95 / all configs", font: {size: 12}}, barmode: "group", yaxis: {title: "valid EVs", type: "log"},
     legend: {orientation: "h", y: -0.5}, margin: {t: 36, b: 150, l: 55, r: 10}, height: 360}, {responsive: true});
  plotWithHeadline("knee_slow", [{x, y: DATA.knees.map(r => r.slow_share_B8), type: "bar", marker: {color: "#dc2626"}, name: "% of ToR0 data packets on degraded uplinks"}],
    {title: {text: "Share of data on degraded uplinks, B=8 (capacity share 2.5%) -- matched / 5/95 / all configs", font: {size: 12}}, yaxis: {title: "%", rangemode: "tozero"},
     margin: {t: 36, b: 150, l: 55, r: 10}, height: 360}, {responsive: true});
}
const AXVAR = {A: c => c.hosts, B: c => c.P, C: c => c.tiers + "-tier " + c.hosts + "h", D: c => c.latency_ns / 1000 + " us", D2: c => c.latency_ns / 1000 + " us", E: c => c.sack};
function whyPlot(id, ax, title, xt) {
  const ks = DATA.knees.filter(k => AXOF[k.cfg] === ax || k.cfg === "base_h1024_p32").map(k => [DATA.cfgs.find(c => c.name === k.cfg), k]);
  ks.sort((a, b) => (typeof AXVAR[ax](a[0]) === "number" ? AXVAR[ax](a[0]) - AXVAR[ax](b[0]) : 0));
  const x = ks.map(([c]) => String(AXVAR[ax](c)));
  const tr = [["k_steady_p99", "steady k p99", "#2a788e"], ["k_steady_max", "steady k max", "#0ea5e9"], ["B_ow", "B_ow", "#7c3aed"], ["B_fct", "B_fct", "#dc2626"]]
    .map(([m, n, c]) => ({x, y: ks.map(([, k]) => k[m]), mode: "lines+markers", name: n, line: {color: c}}));
  tr.push({x, y: x.map(() => 8), mode: "lines", name: "B = 8", line: {color: "#111", dash: "dot", width: 1}});
  plotWithHeadline(id, tr, Object.assign(lay("Steady k and knees vs " + xt + " -- matched / 5/95 / " + title, 320), {yaxis: {title: "buffer entries", rangemode: "tozero"}}), {responsive: true});
}
function whyOw() {
  plotWithHeadline("why_ow", [{x: DATA.knees.map(k => LAB[k.cfg].replace("5/95, ", "")), y: DATA.knees.map(k => k.pct_random_B8), type: "bar", marker: {color: "#f59e0b"}, name: "% random EVs, B=8"}],
    {title: {text: "Random EV share at B=8 (regime check) -- matched / 5/95 / all configs", font: {size: 12}}, yaxis: {title: "%"}, margin: {t: 36, b: 150, l: 55, r: 10}, height: 320}, {responsive: true});
}
function ktsPlot() {
  const f = document.getElementById("tsF").value, ser = DATA.kts.series[f + "|42"];
  if (!ser) { document.getElementById("kts").innerHTML = "<i>no trace</i>"; return; }
  const x = ser.map((_, i) => i * DATA.kts.bin_us);
  plotWithHeadline("kts", [{x, y: ser, mode: "lines", line: {color: "#2a788e"}, name: "max k in bin"}, {x: [0, x[x.length - 1]], y: [8, 8], mode: "lines", line: {color: "#111", dash: "dot"}, name: "B = 8"}],
    {title: {text: "Max k per 20 us bin (spikes at the end are the flow drain) -- matched / " + LAB[f] + " / B=128", font: {size: 12}}, xaxis: {title: "us since first send"}, yaxis: {title: "valid EVs"},
     margin: {t: 36, b: 60, l: 55, r: 10}, height: 320}, {responsive: true});
}
function gateTable() {
  const bs = BS;
  let h = "<table><tr><th>config / B</th>" + bs.map(b => "<th>" + b + "</th>").join("") + "</tr>";
  ALLF.forEach(f => { h += "<tr><td>" + LAB[f] + "</td>" + bs.map(b => { const x = at(rows("matched", f), b);
    if (!x) return "<td>-</td>";
    return "<td style='background:" + (failed(x) ? "#fecaca" : "#dcfce7") + "'>" + F(x.rtos_mean, 1) + " / " + F(x.freeze_entries_mean, 1) + "</td>"; }).join("") + "</tr>"; });
  document.getElementById("gate").innerHTML = h + "</table><div class='note'>cell = RTOs / freeze entries per run; red = gate failed; - = not run.</div>";
}
function axisPlot(id, ax, title) {
  const fs = ALLF.filter(f => AXOF[f] === ax || f === "base_h1024_p32");
  const tr = fs.map((f, i) => { const rs = rows("matched", f); return {x: rs.map(x => "B=" + x.B), y: rs.map(x => x.fct_max_mean), mode: "lines+markers", name: LAB[f].replace("5/95, ", ""),
    line: {color: col[i], width: 1.6}, error_y: {type: "data", array: rs.map(x => x.fct_max_ci95), visible: true, thickness: 1, width: 3},
    marker: {symbol: rs.map(x => failed(x) ? "x" : "circle"), size: 8}}; });
  plotWithHeadline(id, tr, Object.assign(lay("Max FCT, all flows (x = gate failed) -- matched / 5/95 / " + title), {yaxis: {title: "us"}}), {responsive: true});
}
function owPlot() {
  const tr = ALLF.map((f, i) => { const rs = rows("matched", f); return {x: rs.map(x => "B=" + x.B), y: rs.map(x => x.pct_overwrite_mean), mode: "lines+markers", name: LAB[f].replace("5/95, ", ""), line: {width: 1.2}}; });
  plotWithHeadline("ax_ow", tr, Object.assign(lay("Valid-EV overwrites (% of clean ACKs) -- matched / 5/95 / all configs", 320), {yaxis: {title: "%", type: "log"}}), {responsive: true});
}
function uplinkPlot() {
  const B = document.getElementById("upB").value, f = document.getElementById("upF").value, d = DATA.uplinks[f + "|" + B];
  if (!d) { document.getElementById("uplinks").innerHTML = "<i>no queue stats for this cell</i>"; return; }
  document.getElementById("uplinks").innerHTML = "<div class='grid3'><div id='u1'></div><div id='u2'></div><div id='u3'></div></div>";
  const x = d.trims.map((_, i) => "agg " + i), c = d.trims.map((_, i) => i % 2 ? "#22a884" : "#dc2626");
  const l = t => ({title: {text: t + " -- matched / " + LAB[f] + " / B=" + B, font: {size: 12}}, margin: {t: 36, b: 60, l: 55, r: 10}, height: 300});
  plotWithHeadline("u1", [{x, y: d.data_pkts, type: "bar", marker: {color: c}}], l("Data packets forwarded per uplink (red = degraded, even agg)"), {responsive: true});
  plotWithHeadline("u2", [{x, y: d.trims, type: "bar", marker: {color: c}}], l("Packets trimmed per uplink"), {responsive: true});
  plotWithHeadline("u3", [{x, y: d.max_q, type: "bar", marker: {color: c}}], l("Max queue per uplink (bytes)"), {responsive: true});
}
kneeTable(); kneeBars(); gateTable();
whyPlot("why_A", "A", "hosts / radix", "hosts"); whyPlot("why_B", "B", "path count", "paths"); whyPlot("why_C", "C", "tiers", "tiers"); whyPlot("why_D", "D", "link latency (q/ECN fixed)", "link latency");
whyPlot("why_D2", "D2", "link latency (q/ECN scaled to BDP)", "link latency"); whyPlot("why_E", "E", "ACK spacing", "-sack_threshold"); whyOw();
const tsF = document.getElementById("tsF"); Object.keys(DATA.kts.series).filter(k => k.endsWith("|42")).forEach(k => tsF.add(new Option(LAB[k.split("|")[0]] || k, k.split("|")[0]))); tsF.onchange = ktsPlot; ktsPlot();
axisPlot("ax_A", "A", "hosts / radix"); axisPlot("ax_B", "B", "path count"); axisPlot("ax_C", "C", "tiers"); axisPlot("ax_D", "D", "link latency"); axisPlot("ax_D2", "D2", "link latency, q/ECN scaled"); axisPlot("ax_E", "E", "ACK spacing"); owPlot();
const upB = document.getElementById("upB"), upF = document.getElementById("upF");
BS.forEach(b => upB.add(new Option("B=" + b, b))); upB.value = 8; ALLF.forEach(f => upF.add(new Option(LAB[f], f))); upF.value = ALLF[0];
upB.onchange = upF.onchange = uplinkPlot; uplinkPlot();
"""


def main():
    s = pd.read_csv(T3 / "data/t3_summary.csv")
    kn = pd.read_csv(T3 / "data/t3_knees.csv")
    present = [c["name"] for c in CFGS if c["name"] in set(s.cfg)]
    metrics = list(dict.fromkeys(list(bi.M4_METRICS) + ["fct_max", "rtos", "freeze_entries", "n_freeze_events", "slow_share"]))
    keep = (["cfg", "B", "n_seeds"] + [f"{k}_{t}" for k in metrics for t in ("mean", "ci95")]
            + [f"kdist_{i}" for i in range(65)] + [f"awdist_{i}" for i in range(9)])
    rows = [dict({k: bi.clean(v) for k, v in r.items() if k != "cfg"}, rate="matched", fail=r["cfg"])
            for r in s[[c for c in keep if c in s.columns]].to_dict("records")]
    knees = [{k: bi.clean(v) for k, v in r.items()} for r in kn.to_dict("records")]
    # keep config order from configs.json
    knees.sort(key=lambda k: present.index(k["cfg"]))
    up = json.loads((T3 / "data/t3_uplinks.json").read_text())
    fails = [(n, LABEL[n]) for n in present]
    body = bi.M4_BODY
    js = body[body.index("const RATES"):]
    old_rates = 'const RATES = [["under", "UNDER capacity: 100 Gbps per source"], ["matched", "MATCHED to degraded capacity: 200 Gbps per source"],\n               ["over", "OVER capacity: 400 Gbps per source"]];'
    old_fails = 'const FAILS = [["healthy", "healthy"], ["uniform50", "uniform 50%"], ["nonuniform", "non-uniform 25/75%"]];'
    assert old_rates in js and old_fails in js and "const BS = [1, 2, 4, 8, 16, 32, 64]" in js, "M4 constants changed, update the swap"
    js = js.replace(old_rates, 'const RATES = [["matched", "MATCHED: 200 Gbps per source"]];')
    js = js.replace(old_fails, "const FAILS = " + json.dumps(fails) + ";")
    bs = sorted(set(s.B.astype(int)))
    js = js.replace("const BS = [1, 2, 4, 8, 16, 32, 64]", "const BS = " + json.dumps(bs))
    flab = '(Object.fromEntries(FAILS)[f] || f)'
    assert js.count('" + r + " / " + f') == 5 and js.count('" + r + "/" + f') == 1, "M4 headline format changed, update the swap"
    js = js.replace('" + r + " / " + f', '" + r + " / " + ' + flab).replace('" + r + "/" + f', '" + r + " / " + ' + flab)
    a, b = js.index("function verdict(r, id)"), js.index("RATES.forEach(([r]) => { verdict(")
    js = js[:a] + VERDICT_JS + js[b:]
    js = js.replace("</script>\n</body></html>", EXTRA_JS + "</script>\n</body></html>")
    sections = '<h2>One panel per config</h2>\n<div id="verdict_matched"></div>\n'
    for kind, label in [("split", "valid vs random EV"), ("k", "k distribution"), ("ackwin", "ACKs per SEND-to-SEND window"), ("fct", "FCT statistics"),
                        ("overwrite", "valid EVs overwritten by a clean ACK"), ("loss", "retransmits and ECN marks")]:
        sections += f"<h3>{label}</h3>\n"
        for axkey, axlabel in AXES:
            names = [c["name"] for c in CFGS if c["axis"] == axkey and c["name"] in present]
            for i in range(0, len(names), 3):
                sections += '<div class="grid3">' + "".join(bi.panel(f"{kind}_matched_{n}") for n in names[i:i + 3]) + "</div>\n"
    html = bi.HEAD.replace("__TITLE__", "T3 where does 8 come from").replace("</head>", bi.M4_EXTRA_CSS + "</head>")
    html += NOTE.replace("__SECTIONS__", sections) + "<script>\nconst DATA = " + json.dumps(
        {"rows": rows, "knees": knees, "uplinks": up, "cfgs": CFGS, "kts": json.loads((T3 / "data/t3_k_timeseries.json").read_text())}) + ";\n" + bi.COMMON_JS + js
    out = T3 / "plots" / "interactive.html"
    out.write_text(html, encoding="utf-8"); print("wrote", out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""M5 interactive page (Plotly from cdnjs): REPS B=1,2,4 vs OPS. Writes M5/plots/interactive.html (gitignored).
Inputs: M5/data/results_ops.jsonl, results_reps_rerun.jsonl.   python3 build_m5_interactive.py"""
import json
import numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "M5" / "data"; T = 4.303
rows = [json.loads(l) for f in ("results_ops.jsonl", "results_reps_rerun.jsonl") for l in open(D / f)]
ARMS = ["REPS B=1", "REPS B=2", "REPS B=4", "OPS"]; RATES = ["under", "matched", "over"]; FAILS = ["healthy", "uniform50", "nonuniform"]
MET = {"fct_tor0_mean": "ToR0 mean FCT (us)", "fct_tor0_max": "ToR0 max FCT (us)", "fct_p99": "p99 FCT, all flows (us)", "ecn_acks": "ECN-marked ACKs (whole run)",
       "trims_total": "Trimmed packets (whole run)", "rtx_traced": "Retransmissions (traced hosts 0-7)", "maxq_E->A": "Max ToR uplink queue (bytes)"}
def arm(r): return "OPS" if r["lb"] == "oblivious" else f"REPS B={r['B']}"
agg = {}
for r in rows:
    k = (r["rate"], r["fail"], arm(r)); agg.setdefault(k, []).append(r)
data = {}
for (rate, fail, a), v in agg.items():
    for m in MET:
        x = np.array([q[m] for q in v], float)
        data.setdefault(m, {}).setdefault(rate, {}).setdefault(a, {})[fail] = [float(x.mean()), float(x.std(ddof=1) * T / np.sqrt(len(x)))]
up = {}   # matched/nonuniform per-uplink (mean over seeds): trims and max queue, even agg = 25% link, odd = 75% link
for a in ARMS:
    v = agg[("matched", "nonuniform", a)]
    up[a] = dict(trims=np.mean([q["tor0_up_trims"] for q in v], 0).round(1).tolist(), maxq=np.mean([q["tor0_up_maxq"] for q in v], 0).round(0).tolist())
html = """<title>REPS vs OPS</title>
<meta name="claude:viewport-fit-sides" content="cover">
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 0; padding-block: 16px; padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px)); color: #111; background: #fff; color-scheme: light; }
h1 { font-size: 18px; margin: 0 0 4px; } h2 { font-size: 15px; margin: 18px 0 6px; }
.note { font-size: 13px; color: #444; margin-bottom: 12px; max-width: 980px; line-height: 1.45; }
.ctl { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; margin: 8px 0 12px; font-size: 14px; }
select { font-size: 14px; padding: 3px 6px; }
.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; min-width: 0; }
.wide { grid-column: 1 / -1; }
.win { background: #f4f8ff; border-left: 4px solid #2171b5; padding: 8px 12px; font-size: 14px; line-height: 1.5; max-width: 980px; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
<h1>REPS (B = 1, 2, 4) vs OPS on the M4 network</h1>
<div class="note">Tornado 16 MiB, 1024 flows, 2-tier fat tree 400G, constant sender (rate = NIC egress incl. ACKs: under 100G / matched 200G / over 400G), trimming on, no CC.
Failure models degrade the 32 ToR0 uplinks: uniform50 = all at 50%, nonuniform = 25% / 75% alternating. OPS = oblivious per-packet random path over the same 32 SRv6 paths.
Bars are means of 3 seeds, whiskers 95% t-CI (lower whisker clipped at the mean). Count metrics are whole-run unless stated. Source: <code>experiments/meeting_23_10_26/M5</code>.</div>
<div class="win"><b>Takeaway.</b> Memory matters when load is unbalanced across links. matched / nonuniform: OPS 941 us vs REPS 704 us (B=4), 44k vs 0.2k trims; even B=1 beats OPS by 24%.
With symmetric degradation or below capacity OPS is within ~1%; over / healthy shows a small OPS cost (+6 us, 6.3k trims vs 0). Over capacity on degraded links neither helps.</div>
<div class="ctl"><label>Metric <select id="met"></select></label><label><input type="checkbox" id="logy"> log y-axis</label></div>
<div class="grid" id="g"></div>
<h2>matched / nonuniform: per-uplink view of ToR0's 32 uplinks (mean of 3 seeds)</h2>
<div class="note">Even uplinks run at 25% (100G), odd at 75% (300G). OPS sprays the same load on all of them, so the 100G links overflow and trim; REPS moves load to the 300G links (higher queue there).</div>
<div class="grid"><div class="panel wide"><div id="p_trim"></div></div><div class="panel wide"><div id="p_q"></div></div></div>
<script>
const D = __DATA__, UP = __UP__, MET = __MET__, ARMS = __ARMS__, RATES = __RATES__, FAILS = __FAILS__;
const COL = {"REPS B=1": "#c6dbef", "REPS B=2": "#6baed6", "REPS B=4": "#2171b5", "OPS": "#e6550d"};
const sel = document.getElementById("met"), logy = document.getElementById("logy"), g = document.getElementById("g");
Object.entries(MET).forEach(([k, v]) => { const o = document.createElement("option"); o.value = k; o.textContent = v; sel.appendChild(o); });
const cfg = {displaylogo: false, responsive: true};
RATES.forEach(r => { const p = document.createElement("div"); p.className = "panel"; p.innerHTML = '<div id="r_' + r + '"></div>'; g.appendChild(p); });
function draw() {
  const m = sel.value;
  RATES.forEach(r => {
    const tr = ARMS.map(a => { const c = FAILS.map(f => D[m][r][a][f]);
      return {type: "bar", name: a, x: FAILS, y: c.map(x => x[0]), marker: {color: COL[a]},
        error_y: {type: "data", symmetric: false, array: c.map(x => x[1]), arrayminus: c.map(x => Math.min(x[1], x[0])), visible: true, thickness: 1, width: 3},
        hovertemplate: a + " %{x}: %{y:,.1f}<extra></extra>"}; });
    Plotly.react("r_" + r, tr, {title: {text: r + " rate - " + MET[m], font: {size: 13}}, barmode: "group", margin: {t: 36, l: 56, r: 8, b: 40},
      yaxis: {type: logy.checked ? "log" : "linear", rangemode: "tozero"}, legend: {orientation: "h", y: -0.18}}, cfg);
  });
}
sel.onchange = logy.onchange = draw; draw();
const idx = Array.from({length: 32}, (_, i) => i);
function up(id, key, title) {
  Plotly.react(id, ARMS.map(a => ({type: "bar", name: a, x: idx, y: UP[a][key], marker: {color: COL[a]}, hovertemplate: a + " uplink %{x}: %{y:,.0f}<extra></extra>"})),
    {title: {text: title, font: {size: 13}}, barmode: "group", margin: {t: 36, l: 56, r: 8, b: 40}, xaxis: {title: "ToR0 uplink (even = 25%, odd = 75%)", dtick: 2}, yaxis: {rangemode: "tozero"}, legend: {orientation: "h", y: -0.3}}, cfg);
}
up("p_trim", "trims", "Trimmed packets per uplink"); up("p_q", "maxq", "Max queue per uplink (bytes)");
</script>
"""
for k, v in {"__DATA__": data, "__UP__": up, "__MET__": MET, "__ARMS__": ARMS, "__RATES__": RATES, "__FAILS__": FAILS}.items():
    html = html.replace(k, json.dumps(v))
out = ROOT / "M5" / "plots"; out.mkdir(exist_ok=True); (out / "interactive.html").write_text(html, encoding="utf-8")
print(len(html))

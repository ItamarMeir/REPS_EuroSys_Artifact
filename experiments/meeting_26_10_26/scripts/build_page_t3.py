#!/usr/bin/env python3
"""
T3/plots/interactive.html in the plot_common.py style (skill interactive-plotter).
Input: T3/data/{t3_summary,t3_knees}.csv, t3_k_timeseries.json, configs/configs.json.
experiments/**/*.html is gitignored.

    python3 build_page_t3.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
T3 = HERE.parent / "T3"
sys.path.insert(0, str(HERE.parents[1] / "tools"))
from plot_common import (aside, build_page, callout, chip, controls, end, h2,  # noqa: E402
                         note, plot, question, records, table, tile)

OUT = T3 / "plots" / "interactive.html"
D = T3 / "data"

CFGS = json.loads((D / "configs" / "configs.json").read_text())
S = pd.read_csv(D / "t3_summary.csv")
KN = pd.read_csv(D / "t3_knees.csv")
KTS = json.loads((D / "t3_k_timeseries.json").read_text())

present = [c["name"] for c in CFGS if c["name"] in set(S.cfg)]
CFG = {c["name"]: c for c in CFGS}
LABEL = {n: CFG[n]["note"] for n in present}

# which configs belong to which axis (baseline joins every axis, as in the old page)
AXES = [("A", "hosts / radix (2-tier, paths = radix)", lambda c: c["hosts"]),
        ("B", "path count at 1024 hosts", lambda c: c["P"]),
        ("C", "tiers (3-tier, first-hop degrade)", lambda c: f'{c["tiers"]}-tier {c["hosts"]}h'),
        ("D", "link latency, q/ECN fixed at the 1 us BDP", lambda c: f'{c["latency_ns"] / 1000:g} us'),
        ("D2", "link latency, q/ECN scaled to the BDP", lambda c: f'{c["latency_ns"] / 1000:g} us'),
        ("E", "ACK spacing (-sack_threshold)", lambda c: c["sack"]),
        ("D3", "queue depth control (1 us links)", lambda c: f'q {c["q"]}, ECN {c["ecn"][0]}/{c["ecn"][1]}')]
BASE = "base_h1024_p32"
FLAGS = {"lat4_bdpq": "q/ECN scaled to BDP", "lat16_bdpq": "q/ECN scaled; 19% random EVs remain",
         "lat4_h1024_p32": "q/ECN fixed: other regime", "lat16_h1024_p32": "q/ECN fixed: other regime",
         "sack8000": "fewer ACKs: EV supply cut", "sack16384": "fewer ACKs: EV supply cut",
         "t3_h128_p16": "3-tier, first-hop degrade", "t3_h1024_p64": "3-tier, first-hop degrade",
         "h2048_p32": "1 seed, no CI"}


def num(v):
    return None if pd.isna(v) else float(v)


kn = KN.set_index("cfg").loc[present].reset_index()
knees = [{"cfg": r.cfg, "label": LABEL[r.cfg], "seeds": int(r.n_seeds), "k99": num(r.k_steady_p99),
          "bks": num(r.B_ks99), "bow": num(r.B_ow), "bfct": num(r.B_fct),
          "fct8": num(r.fct_max_B8), "rand8": num(r.pct_random_B8), "flag": FLAGS.get(r.cfg, "")}
         for r in kn.itertuples()]
K = {k["cfg"]: k for k in knees}

why, fct = {}, {}
for ax, title, var in AXES:
    names = [n for n in present if CFG[n]["axis"] in (ax, ax + "b") or n == BASE]
    pts = sorted(((var(CFG[n]), n) for n in names), key=lambda t: (isinstance(t[0], str), t[0]))
    why[ax] = {"title": title, "rows": [{"x": str(v), "k99": K[n]["k99"], "bks": K[n]["bks"],
                                          "bow": K[n]["bow"], "bfct": K[n]["bfct"]} for v, n in pts]}
    series = []
    for n in names:
        g = S[S.cfg == n].sort_values("B")
        series.append({"label": LABEL[n], "bfct": K[n]["bfct"], "rows": [
            {"x": f"B={int(r.B)}", "y": round(float(r.fct_max_mean), 2),
             "ci": round(float(r.fct_max_ci95) if pd.notna(r.fct_max_ci95) else 0.0, 2), "n": int(r.n_seeds)}
            for r in g.itertuples()]})
    fct[ax] = {"title": title, "series": series}

kts = {"bin_us": KTS["bin_us"],
       "series": {n: KTS["series"][f"{n}|42"] for n in present if f"{n}|42" in KTS["series"]}}

# ---- numbers for chips / tiles / callouts, all from the CSVs -------------------
n_cells = int(S.n_seeds.sum())
gate_ok = bool((S.gate_clear_mean == 1).all())
single = [n for n in present if int(S[S.cfg == n].n_seeds.max()) == 1]
# clean = under 10% random EVs at B=8 and a B_fct exists
clean = [k for k in knees if k["bfct"] is not None and (k["rand8"] or 0) < 10]
for k in knees:
    k["regime"] = "clean" if k in clean else "other"
core = [k for k in clean if k["bfct"] <= 8]
f_lo, f_hi = min(k["bfct"] for k in core), max(k["bfct"] for k in core)
base = S[S.cfg == BASE].set_index("B").fct_max_mean
pen2 = 100 * (base[2] - base[8]) / base[8]
moved = K["lat4_bdpq"]
mv = S[S.cfg == "lat4_bdpq"].set_index("B").fct_max_mean
gain_12 = 100 * (mv[8] - mv[12]) / mv[8]

chips = [
    chip("ok" if gate_ok else "bad", f"Freezing gate clear in all {n_cells} cells (0 RTOs, 0 freeze entries)"),
    chip("ok", "config proven from output in every cell (T3/README.md)"),
    chip("warn", f"1 seed, no CI: {', '.join(single)}"),
    chip("warn", "latency (q/ECN fixed) and ACK-spacing cells run in another regime: 20-74% random EVs at B=8"),
]
tiles = [
    tile("baseline max FCT, B=2 vs B=8", f"+{pen2:.1f}%", "1024h, 32 paths, 3 seeds"),
    tile("max-FCT knee B_fct, clean configs", f"{f_lo:.0f} to {f_hi:.0f}", f"{len(core)} configs vs B=128"),
    tile("max-FCT knee moved", f"B = {moved['bfct']:.0f}",
         f"one config: latency x4, q/ECN scaled; max FCT -{gain_12:.1f}% from B=8", "bad"),
]

body = [
    h2("Does any variable move the max-FCT knee?", 1),
    controls("fct-ctl", "axis"),
    plot("fct"),
    note("One line per config, band = 95% t-CI over seeds, ring = the knee B_fct. A filled marker is a single seed "
         "(no CI). The baseline is repeated in every axis."),
    end(),

    h2("B_fct against B=8, every config", 2),
    plot("knees"),
    callout("Prediction", "Written before any run: the knee stays near 8 at latency x4 and x16."),
    callout("Result", f"Held in {len(core)} clean configs (B_fct {f_lo:.0f} to {f_hi:.0f}). Missed at x4 with "
                      f"scaled q/ECN: B_fct = {moved['bfct']:.0f}, max FCT {gain_12:.1f}% lower at B=12 than at B=8."),
    callout("Caveat", "Fixed-threshold latency and ACK-spacing cells are another regime (20 to 74% random EVs at B=8); "
                      "their B_fct is not comparable and is drawn grey."),
    end(),

    h2("Mechanism: what the buffer must hold", 3),
    controls("why-ctl", "axis"),
    plot("why"),
    note("Steady-state k p99 is the typical valid-EV backlog, B_ow the smallest B with under 0.1% overwrites. "
         "They explain the max-FCT knee above; they are not the result."),
    aside("What could move the knee at x4",
          "A deeper queue with higher ECN thresholds lets ACKs arrive in larger bursts, and a larger buffer keeps "
          "more of them. A hypothesis only: no run isolates it. The 1 us-link control with q=394 would."),
    end(),

    h2("Why the knees use a steady-state window", 4, tag="supporting check"),
    controls("kts-ctl", "config"),
    plot("kts"),
    note("Pick a config. Spikes at the end are retransmit draws meeting a full buffer after the last send "
         "(see x4 and x16 latency), so the knees use the steady-state window instead."),
    end(),

    h2("Knee table", 5),
    table("ktbl"),
    end(),
]

PAGE_JS = r"""
const K = DATA.knees, WHY = DATA.why, FCT = DATA.fct, KTS = DATA.kts;
const US = ' (µs)';
const refB8 = () => ({
  shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 8, y1: 8,
    line: { color: PC.css('--muted'), width: 1, dash: 'dot' } }],
  annotations: [{ xref: 'paper', x: 1, y: 8, xanchor: 'right', yanchor: 'bottom', showarrow: false,
    text: 'B = 8', font: { size: 10, color: PC.css('--muted') } }] });
const METRICS = [['bfct', 'B_fct (max FCT)'], ['bow', 'B_ow (overwrites < 0.1%)'],
  ['bks', 'B_ks99 (steady k p99)'], ['k99', 'steady k p99']];

// headline: B_fct per config; configs outside the clean regime are drawn grey
function drawKnees() {
  const pts = K.map((k, i) => ({ x: i, y: k.bfct, ok: k.regime === 'clean' }));
  const traces = [
    ...PC.lineTrace('bfct', pts.filter(r => r.ok), 'B_fct, clean configs', { markers: true }),
    ...PC.lineTrace('other', pts.filter(r => !r.ok), 'B_fct, other regime', { markers: true })];
  const t = PC.theme(), r = refB8();
  t.shapes = r.shapes; t.annotations = r.annotations;
  t.xaxis.tickvals = K.map((_, i) => i); t.xaxis.ticktext = K.map(k => k.label); t.xaxis.tickangle = -35;
  t.xaxis.range = [-0.6, K.length - 0.4];
  t.yaxis.type = 'log'; t.yaxis.range = [0, Math.log10(200)];
  t.yaxis.tickvals = [1, 2, 4, 8, 16, 32, 64, 128]; t.yaxis.ticktext = ['1', '2', '4', '8', '16', '32', '64', '128'];
  t.yaxis.title.text = 'B_fct (buffer entries)'; t.margin.b = 150; t.legend.y = -0.62;
  t.hovermode = 'closest'; t.height = 440;
  PC.draw('knees', traces, t, 'Max-FCT knee B_fct vs B=8 - matched 200G, 5/95, every config (3 seeds)');
}

let axWhy = 'A';
function drawWhy() {
  const w = WHY[axWhy], traces = [];
  for (const [key, name] of METRICS)
    traces.push(...PC.lineTrace(key, w.rows.map(r => ({ x: r.x, y: r[key] })), name, { hover: '%{y:.3g}' }));
  const t = PC.theme(), r = refB8();
  t.shapes = r.shapes; t.annotations = r.annotations;
  t.xaxis.type = 'category'; t.xaxis.title.text = w.title; t.yaxis.title.text = 'buffer entries';
  t.yaxis.rangemode = 'tozero';
  PC.draw('why', traces, t, 'Mechanism vs ' + w.title + ', max-FCT knee for reference - matched 200G, 5/95');
}

let axFct = 'A';
function drawFct() {
  const w = FCT[axFct];
  PC.fctVsB('fct', w.series, 'Max FCT vs B - ' + w.title + ' (3 seeds, 95% CI)');
}

let ktsCfg = 'lat4_h1024_p32';
function drawKts() {
  const ser = KTS.series[ktsCfg];
  const rows = ser.map((y, i) => ({ x: i * KTS.bin_us, y }));
  const traces = PC.lineTrace('c1', rows, 'max k in bin', { hover: '%{y:.3g}' });
  const t = PC.theme(), r = refB8();
  t.shapes = r.shapes; t.annotations = r.annotations;
  t.xaxis.title.text = 'time since first send (µs)'; t.yaxis.title.text = 'valid EVs (k)';
  PC.draw('kts', traces, t, 'Max k per ' + KTS.bin_us + ' µs bin - ' + KLAB[ktsCfg] + ', B=128, seed 42');
}
const KLAB = Object.fromEntries(K.map(k => [k.cfg, k.label]));

function drawTable() {
  const f = (v, d) => v == null ? '-' : (+v).toFixed(d);
  document.getElementById('ktbl').innerHTML =
    '<thead><tr><th>config</th><th>seeds</th><th>B_fct</th><th>max FCT B=8' + US + '</th><th>B_ow</th><th>B_ks99</th>'
    + '<th>steady k p99</th><th>% random EVs B=8</th><th>note</th></tr></thead><tbody>'
    + K.map(k => `<tr><td>${k.label}</td><td>${k.seeds}</td><td>${f(k.bfct, 0)}</td><td>${f(k.fct8, 1)}</td>
      <td>${k.bow == null ? 'never' : f(k.bow, 0)}</td><td>${f(k.bks, 0)}</td><td>${f(k.k99, 1)}</td>
      <td>${f(k.rand8, 1)}</td><td style="text-align:left">${k.flag}</td></tr>`).join('') + '</tbody>';
}

PC.select('why-ctl', Object.entries(WHY).map(([k, v]) => [k, v.title]), axWhy, v => { axWhy = v; drawWhy(); });
PC.select('fct-ctl', Object.entries(FCT).map(([k, v]) => [k, v.title]), axFct, v => { axFct = v; drawFct(); });
PC.select('kts-ctl', Object.keys(KTS.series).map(k => [k, KLAB[k]]), ktsCfg, v => { ktsCfg = v; drawKts(); });
function drawAll() { drawKnees(); drawWhy(); drawFct(); drawKts(); }
drawTable(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        OUT,
        title="T3: where does 8 come from?",
        eyebrow="meeting 26/10/26 · T3",
        h1="Where does 8 come from? Max FCT stops improving at B=4 to 8, except in one latency cell",
        lede=f"At 5/95 degradation max FCT stops improving at B = {f_lo:.0f} to {f_hi:.0f} in every clean config. "
             f"The knee reaches {moved['bfct']:.0f} once: link latency x4 with queue and ECN scaled to the BDP.",
        cfg="primary metric: max FCT over all flows · constant-rate 200G (matched) · ToR0 uplinks 5/95 · tornado 16 MiB · freezing, SRv6, trimming on · "
            "seeds 42-44 · B in {2,4,6,8,12,16,32,128} · B=128 is the reference",
        full_cmd="run_m4.flags('matched', 'healthy', B, seed) with per-config overrides of "
                 "-topo -tm -paths -rate_const_gbps -q -ecn -sack_threshold, plus -degrade_links_file. "
                 "Details: experiments/meeting_26_10_26/T3/README.md (Setup).",
        brief=question(
            "Why the REPS buffer knee sits at B=8: radix, path count, tiers, RTT or ACK spacing?",
            "Fix the failure at 5/95 on ToR0 uplinks, change one variable per axis from the 1024-host baseline, sweep B.",
            "Max FCT against B per config and the knee B_fct against B=8; mechanism metrics only as explanation."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"knees": knees, "why": why, "fct": fct, "kts": kts},
        footer="Source `experiments/meeting_26_10_26/T3/data/*.csv|json`. Regenerate: "
               "`python3 experiments/meeting_26_10_26/scripts/build_page_t3.py`.",
    )

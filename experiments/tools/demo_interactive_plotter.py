#!/usr/bin/env python3
"""
Demo page for plot_common.py: every element a repo interactive page should
have, on REAL exp29 data where a small real dataset exists and clearly-bannered
SYNTHETIC data only for styles no small real data covers (B=64/inf, a
single-seed point, vanilla vs state-aware).

    python3 demo_interactive_plotter.py
    -> experiments/tools/demo_plots/interactive_plotter_demo.html (gitignored)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
EXP29 = HERE.parent / "exp29_failure_response"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(EXP29 / "scripts"))
import common29  # noqa: E402  (real flags, so the config banner is proven, not retyped)
from plot_common import (aside, build_page, callout, chip, controls, end, h2,  # noqa: E402
                         note, plot, records, synthetic_banner, table, tile)

D = EXP29 / "data"
OUT = HERE / "demo_plots" / "interactive_plotter_demo.html"
F_TS = 8

fct = pd.read_csv(D / "fct.csv")
diag = pd.read_csv(D / "diagnostics.csv")
ts = pd.read_csv(D / "timeseries.csv")
rv = pd.read_csv(D / "resolvable.csv")

fct = fct[(fct.group == "affected") & (fct.ef == 100)]
diag = diag[(diag.group == "affected") & (diag.ef == 100)]
ts = ts[(ts.group == "affected") & (ts.ef == 100) & (ts.F == F_TS)
        & ts.arm.isin(["reps_b1", "reps_b8"])][
    ["arm", "t_us", "d_rto", "d_ecn_acks", "frozen_frac"]].round(4)
rv = rv[(rv.ef == 100) & (rv.F == F_TS)]


# ---- synthetic, deterministic ------------------------------------------------
def synthetic() -> dict:
    rng = np.random.default_rng(7)
    xs = [1, 2, 4, 8, 16, 32]
    ladder = {}
    for b, base in zip(["1", "2", "4", "8", "16", "32", "64", "inf"],
                       [520, 470, 430, 400, 385, 375, 372, 370]):
        rows = []
        for x in xs:
            y = base * (1 + 0.04 * np.log2(x)) + rng.normal(0, 3)
            rows.append({"x": x, "y": round(float(y), 1),
                         "ci": round(float(abs(rng.normal(9, 2))), 1), "n": 5})
        ladder[b] = rows
    ladder["4"][3].update(ci=0, n=1)        # a single-seed point
    pair = {}
    for k, off in [("vanilla", 0), ("sa", -35)]:
        pair[k] = [{"x": x, "y": round(float(300 + 18 * x + off * np.log2(x + 1)), 1),
                    "ci": round(float(abs(rng.normal(7, 1.5))), 1), "n": 5} for x in range(1, 9)]
    return {"ladder": ladder, "pair": pair}


# ---- numbers for tiles / callouts, all from the CSVs --------------------------
fct_rv = rv[rv.metric.isin(["p50_fct_us", "p99_fct_us", "max_fct_us"])]
rv_all = pd.read_csv(D / "resolvable.csv")
rv_all = rv_all[(rv_all.ef == 100) & rv_all.metric.isin(["p50_fct_us", "p99_fct_us", "max_fct_us"])]
n_res = int(rv_all.resolvable.astype(str).eq("True").sum())
p99_31 = fct[(fct.F == 31) & (fct.arm == "reps_b8")].p99_fct_us.iloc[0]
ev = lambda a: diag[(diag.F == F_TS) & (diag.arm == a)].ev_random_per_host.iloc[0]  # noqa: E731
seeds_ok = bool((pd.read_csv(D / "fct.csv").n_seed == 3).all())

flags = common29.base_flags("reps_b8", F_TS, 42, "win.csv")
tor_ecn_bad = "-sender_cc_only" in flags and "-disable_tor_ecn" not in flags

chips = [
    chip("ok" if seeds_ok else "bad", "3 seeds at every point (n_seed = 3, all rows)"),
    chip("warn" if tor_ecn_bad else "ok",
         "-disable_tor_ecn omitted: ToR-downlink ECN on (paper-faithful)" if tor_ecn_bad
         else "-disable_tor_ecn set"),
    chip("warn", "n_flows / unfinished not in exp29 CSVs: cannot be checked here"),
    chip("ok", "LB: freezing, CC: mprdma (from base_flags)"),
]
tiles = [
    tile("B resolvable on FCT", f"{n_res} of {len(rv_all)}", "p50 / p99 / max, all F", "good" if n_res == 0 else ""),
    tile("affected p99 FCT, F=31", f"{p99_31:.0f} us", "B=8; healthy baseline 356 us", "bad"),
    tile("random-EV draws / host", f"{ev('reps_b1'):.0f} vs {ev('reps_b8'):.0f}", f"B=1 vs B=8 at F={F_TS}"),
]

body = [
    h2("Max FCT climbs with F; B does not move it", 1),
    controls("fct-ctl", "metric"),
    plot("fct", footnotes=None),
    note("Each line is one buffer size B, shaded band = 95% CI over 3 seeds. "
         "The two dashed lines are the dual-window variants at B=8."),
    callout("Prediction", "Demo placeholder: this is where the pre-run prediction goes, "
                          "written before the data was opened."),
    callout("Result", f"B is resolvable in {n_res} of {len(rv_all)} FCT cells (p50, p99, max, every F) "
                      "per `resolvable.csv`."),
    end(),

    h2("B only matters for random-EV draws", 2),
    controls("diag-ctl", "metric"),
    plot("diag"),
    callout("Caveat", "Per-host counts are means over affected hosts only; "
                      "unaffected hosts are in `diagnostics.csv` but not drawn."),
    aside("Why B=1 splits here",
          "Consistent with B=1 emptying its buffer on thaw and re-exploring; "
          "B=8 replays cached EVs. Not isolated by an intervention in this page."),
    end(),

    h2(f"RTO storm stops once hosts freeze (F={F_TS})", 3),
    controls("ts-ctl", "metric"),
    plot("ts", footnotes=["Links fail at t = 100 us.", "Links recover at t = 200 us."]),
    note("Each point is one 10 us bin, meaned over hosts and seeds. "
         "Only B=1 and B=8 are drawn, so lines are labelled directly."),
    end(),

    h2("Style check: B=64, B=inf, single seed, vanilla vs state-aware", 4),
    synthetic_banner(),
    controls("syn-ctl", "y-axis"),
    plot("syn1"),
    note("The filled marker on the B=4 line at x=8 is a single-seed point (n=1, no CI). "
         "B=64 and B=inf are new styles, proposed here."),
    synthetic_banner(),
    plot("syn2"),
    end(),

    h2(f"Verdict: is B resolvable? (F={F_TS})", 5),
    table("rvtbl"),
    end(),
]

PAGE_JS = r"""
const FCT = DATA.fct, DIAG = DATA.diag, TS = DATA.ts, RV = DATA.rv, SYN = DATA.syn;
const armFor = k => k === 'dual' ? 'reps_b8_dual' : k === 'dualcap' ? 'reps_b8_dual_cap' : `reps_b${k}`;
const labelFor = k => k === 'dual' ? 'B=8 dual-window' : k === 'dualcap' ? 'B=8 dual-window (cwnd-capped)' : 'B=' + k;
const KEYS = ['1', '2', '4', '8', '32', 'dual', 'dualcap'];
const Fs = [...new Set(FCT.map(r => r.F))].sort((a, b) => a - b);
const U = ' (µs)';

function vsF(div, src, col, ylab, title, extra) {
  const traces = [];
  for (const k of KEYS) {
    const rs = src.filter(r => r.arm === armFor(k)).sort((a, b) => a.F - b.F);
    if (!rs.length) continue;
    traces.push(...PC.lineTrace(k, rs.map(r => ({ x: r.F, y: r[col], ci: r[col + '_ci'], n: r.n_seed })), labelFor(k)));
  }
  const t = PC.theme();
  t.xaxis.title.text = '# failed ToR0 spine uplinks (F)'; t.xaxis.tickvals = Fs;
  t.yaxis.title.text = ylab;
  Object.assign(t, extra || {});
  PC.draw(div, traces, t, title);
}
const FCT_M = { 'max': 'max_fct_us', 'p99': 'p99_fct_us', 'p50': 'p50_fct_us' };
function drawFct(m) {
  vsF('fct', FCT, FCT_M[m], m + ' FCT' + U, `${m} FCT vs F - tornado 16 MiB, affected hosts (3 seeds, 95% CI)`, {
    shapes: [{ type: 'line', x0: Fs[0], x1: Fs[Fs.length - 1], y0: 356, y1: 356,
      line: { color: PC.css('--muted'), width: 1, dash: 'dot' } }],
    annotations: [{ x: Fs[Fs.length - 1], y: 356, xanchor: 'right', yanchor: 'bottom', showarrow: false,
      text: 'healthy 356 µs', font: { size: 10, color: PC.css('--muted') } }] });
}
const DIAG_M = { 'random-EV draws / host': 'ev_random_per_host', 'RTOs / host': 'rto_per_host',
  'ECN acks / host': 'ecn_per_host', 'time frozen (µs)': 'freeze_us_mean' };
function drawDiag(m) {
  vsF('diag', DIAG, DIAG_M[m], m, `${m} vs F - whole flow, per affected host (3 seeds, 95% CI)`);
}
const TS_M = { 'RTOs / host / 10 µs': 'd_rto', 'ECN acks / host / 10 µs': 'd_ecn_acks',
  'frozen fraction': 'frozen_frac' };
function drawTs(m) {
  const col = TS_M[m], traces = [];
  for (const k of ['1', '8']) {
    const rs = TS.filter(r => r.arm === armFor(k)).sort((a, b) => a.t_us - b.t_us);
    traces.push(...PC.lineTrace(k, rs.map(r => ({ x: r.t_us, y: r[col] })), labelFor(k),
      { endLabel: true, hover: '%{y:.3g}' }));
  }
  const t = PC.theme(), mk = PC.vmarks([{ x: 100, n: 1 }, { x: 200, n: 2, dash: 'dot' }]);
  t.shapes = mk.shapes; t.annotations = mk.annotations;
  t.xaxis.title.text = 't (µs)'; t.yaxis.title.text = m;
  PC.draw('ts', traces, t, `${m} vs time - F=8, B=1 vs B=8 (mean over hosts, 3 seeds)`);
}

let logY = false;
function drawSyn() {
  const traces = [];
  for (const k of ['1', '2', '4', '8', '16', '32', '64', 'inf'])
    traces.push(...PC.lineTrace(k, SYN.ladder[k], k === 'inf' ? 'B=inf' : 'B=' + k));
  const t = PC.theme();
  t.xaxis.title.text = 'sweep x (synthetic)'; t.yaxis.title.text = 'p99 FCT' + U;
  t.yaxis.type = logY ? 'log' : 'linear';
  PC.draw('syn1', traces, t, 'p99 FCT vs x - full B ladder (5 seeds, 95% CI)');
  const t2 = PC.theme(), tr2 = [];
  tr2.push(...PC.lineTrace('vanilla', SYN.pair.vanilla, 'vanilla REPS', { endLabel: true }));
  tr2.push(...PC.lineTrace('sa', SYN.pair.sa, 'state-aware REPS', { endLabel: true }));
  t2.xaxis.title.text = 'sweep x (synthetic)'; t2.yaxis.title.text = 'p99 FCT' + U;
  PC.draw('syn2', tr2, t2, 'p99 FCT vs x - vanilla vs state-aware (5 seeds, 95% CI)');
}

function drawTable() {
  const yes = r => r.resolvable === true || r.resolvable === 'True';
  const rows = RV.slice().sort((a, b) => a.metric.localeCompare(b.metric) || a.phase.localeCompare(b.phase));
  document.getElementById('rvtbl').innerHTML =
    '<thead><tr><th>metric</th><th>phase</th><th>best B</th><th>worst B</th><th>spread</th><th>sum CI</th><th>resolvable</th></tr></thead><tbody>'
    + rows.map(r => `<tr><td>${r.metric}</td><td>${r.phase === '-' ? '' : r.phase}</td>
      <td>B${r.best_b} (${(+r.best_val).toFixed(1)})</td><td>B${r.worst_b} (${(+r.worst_val).toFixed(1)})</td>
      <td>${(+r.spread).toFixed(1)}</td><td>${(+r.ci_sum).toFixed(1)}</td>
      <td><span class="pill ${yes(r) ? 'yes' : 'no'}">${yes(r) ? 'yes' : 'no'}</span></td></tr>`).join('') + '</tbody>';
}

PC.radio('fct-ctl', Object.keys(FCT_M), 'max', drawFct);
PC.radio('diag-ctl', Object.keys(DIAG_M), 'random-EV draws / host', drawDiag);
PC.radio('ts-ctl', Object.keys(TS_M), 'RTOs / host / 10 µs', drawTs);
PC.radio('syn-ctl', ['linear', 'log'], 'linear', v => { logY = v === 'log'; drawSyn(); });
const sel = id => document.querySelector(`#${id} [aria-pressed="true"]`).textContent;
function drawAll() { drawFct(sel('fct-ctl')); drawDiag(sel('diag-ctl')); drawTs(sel('ts-ctl')); drawSyn(); }
drawTable(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        OUT,
        title="Interactive plotter demo",
        eyebrow="Demo · interactive-plotter skill · exp29 data",
        h1="REPS failure response: B does not move FCT, only random-EV draws",
        lede="One ToR loses F of 32 uplinks for 100 us. FCT climbs with F at every B; "
             "buffer size only changes how often hosts fall back to random EVs.",
        cfg="`fat_tree_1024_1os_2t_400g` &middot; tornado 16 MiB &middot; mprdma &middot; "
            "`-q 101 -ecn 25 76 -cwnd 151` &middot; exit_freeze 100 us &middot; seeds 42/43/44".replace("&middot;", "·"),
        full_cmd=" ".join(flags),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={
            "fct": records(fct), "diag": records(diag), "ts": records(ts),
            "rv": records(rv), "syn": synthetic(),
        },
        footer="Source `experiments/exp29_failure_response/data/*.csv` (synthetic block: "
               "`tools/demo_interactive_plotter.py`). Regenerate: `python3 experiments/tools/demo_interactive_plotter.py`.",
    )

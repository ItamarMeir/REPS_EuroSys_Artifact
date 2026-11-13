#!/usr/bin/env python3
"""
T2/plots/interactive.html in the plot_common.py style (skill interactive-plotter).
One page for both scopes: A = pod0 ToR->agg uplinks (T2/tor_agg), B = pod0 agg->core (T2/agg_core).
Input: T2/<sub>/data/t2_summary.csv, t2_knees.csv (T2/scripts/aggregate_t2.py).
experiments/**/*.html is gitignored.

    python3 build_page_t2.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
T2 = HERE.parent / "T2"
sys.path.insert(0, str(HERE.parents[1] / "tools"))
from plot_common import (aside, build_page, callout, chip, controls, end, fct_series, h2,  # noqa: E402
                         note, plot, question, table, tile)
import page_random as PR  # noqa: E402
from page_random import fn_list  # noqa: E402

OUT = T2 / "plots" / "interactive.html"
SCOPES = {"A": ("tor_agg", "pod0 ToR->agg uplinks"), "B": ("agg_core", "pod0 agg->core uplinks")}
SHAPES = [("healthy", "healthy (no degrade)", "c0"), ("u50", "uniform 50/50", "c2"), ("r025", "25/75", "c1"),
          ("r010", "10/90", "c3"), ("r005", "5/95", "c4")]
SH_LABEL = {k: lab for k, lab, _ in SHAPES}
SH_STYLE = {k: st for k, _, st in SHAPES}
DEG = [k for k, _, _ in SHAPES if k != "healthy"]

summ = {sc: pd.read_csv(T2 / sub / "data" / "t2_summary.csv") for sc, (sub, _) in SCOPES.items()}
knee = {sc: pd.read_csv(T2 / sub / "data" / "t2_knees.csv").set_index("shape") for sc, (sub, _) in SCOPES.items()}
KP = {sc: pd.read_csv(T2 / sub / "data" / "t2_knees_paired.csv").set_index("shape") for sc, (sub, _) in SCOPES.items()}   # T2/scripts/knee_paired.py


def num(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


fct = {}
for sc, (_, title) in SCOPES.items():
    fct[sc] = {"title": f"3-tier k=8, {title}",
               "series": []}
    for k, lab, st in SHAPES:
        sk = summ[sc][summ[sc]["shape"] == k].sort_values("B")
        ser = fct_series(sk, lab, st)
        ser.update(PR.tol_info(sk))
        ser["bunp"] = ser["bfct"]                       # unpaired page rule (plot_common.knee_fct)
        ser["bfct"] = int(KP[sc].loc[k, "B_fct_paired"]) if pd.notna(KP[sc].loc[k, "B_fct_paired"]) else ser["bunp"]   # paired: rings, tiles, callouts
        fct[sc]["series"].append(ser)
knee_rows = []
for sc in SCOPES:
    for ser, (k, lab, st) in zip(fct[sc]["series"], SHAPES):
        at = summ[sc][summ[sc]["shape"] == k].set_index("B")
        knee_rows.append({"label": f"{sc}: {lab}", "ref": ser["ref"], "ci128": ser["ci128"], "tol": ser["tol"],
                          "ex": {int(B): round(float(at.loc[B, "fct_max_mean"]) - ser["ref"], 3) for B in (5, 6, 7, 8)},
                          "bfct": ser["bfct"], "bunp": ser["bunp"], "brand": None, "brand0a": None, "brand0d": None})

# random-draw series per scope (same shapes, styles and knees as the max-FCT plot) and correlation points
cells = {sc: pd.read_csv(T2 / sub / "data" / "t2_random_stats_cells.csv") for sc, (sub, _) in SCOPES.items()}
rnd, corr, brand_tab, b0_tab, cost = {}, {"A": [], "B": [], "P": []}, {}, {}, []
for sc, (_, title) in SCOPES.items():
    rnd[sc] = []
    for ser, (k, lab, st) in zip(fct[sc]["series"], SHAPES):
        sk = summ[sc][summ[sc]["shape"] == k]
        extra = PR.paired_extra(cells[sc][cells[sc]["shape"] == k])
        rnd[sc].append(PR.rnd_series(sk, lab, st, ser["bfct"], extra))
        if k not in ("healthy", "u50"):
            corr[sc].append(PR.corr_points(sk, lab, st, sc, extra))
            corr["P"].append(PR.corr_points(sk, f"{lab} ({sc})", st, sc, extra))
            cost.append(PR.cost_model(sk, f"{sc}: {lab}", st, extra, sc))
    brand_tab[sc] = {r["label"]: r["brand"] for r in rnd[sc]}
    b0_tab[sc] = {r["label"]: (r["brand0a"], r["brand0d"]) for r in rnd[sc]}
for kr in knee_rows:
    sc, lab = kr["label"].split(": ", 1)
    kr["brand"] = brand_tab[sc][lab]
    kr["brand0a"], kr["brand0d"] = b0_tab[sc][lab]
corr_stats = {g: PR.corr_stats(v) for g, v in corr.items()}
cs = {g: next(r for r in corr_stats[g]["extra_degraded"]["rows"] if r["name"] == "pooled over B") for g in corr}
wp = {g: {w["name"]: w for w in corr_stats[g]["extra_degraded"]["within"]} for g in corr}
def _c(w):
    return "n/a" if w["pearson"] is None else f"{w['pearson']}/{w['spearman']} (n={w['n']})"
def within_txt(g):
    return "; ".join(f"B={B} {_c(wp[g][f'across configs at B={B}'])}" for B in (4, 5, 6, 8))
cost_txt = "; ".join(f"{c['label']}: band from B={c['b_pred']} (pred) vs {c['b_meas']} (meas)" for c in cost)
n_same = sum(c["b_pred"] == c["b_meas"] for c in cost)

# scope gap: agg->core minus ToR->agg, per shape, with the CIs added in quadrature
diff = []
for k in DEG:
    a = summ["A"][summ["A"]["shape"] == k].set_index("B")
    b = summ["B"][summ["B"]["shape"] == k].set_index("B")
    rows = [{"x": f"B={int(B)}", "y": round(float(b.loc[B, "fct_max_mean"] - a.loc[B, "fct_max_mean"]), 2),
             "ci": round(math.hypot(b.loc[B, "fct_max_ci95"], a.loc[B, "fct_max_ci95"]), 2), "n": 5}
            for B in sorted(a.index)]
    diff.append({"label": SH_LABEL[k], "style": SH_STYLE[k], "rows": rows})
big8 = max(abs(r["y"]) for d in diff for r in d["rows"] if int(r["x"][2:]) >= 8)
big4 = max(r["y"] for d in diff for r in d["rows"] if r["x"] == "B=4")

# mechanism: knees and steady k per shape, one view per scope
why = {sc: {"title": f"3-tier k=8, {SCOPES[sc][1]}",
            "rows": [{"x": SH_LABEL[k], "bfct": num(KP[sc].loc[k, "B_fct_paired"]), "bow": num(knee[sc].loc[k, "B_ow"]),
                      "bks": num(knee[sc].loc[k, "B_ks99"]), "k99": num(knee[sc].loc[k, "k_steady_p99"])}
                     for k in DEG]} for sc in SCOPES}

# overwrites at B=8 per shape, both scopes
ow = []
for sc, st in (("A", "c1"), ("B", "c4")):
    s = summ[sc].set_index(["shape", "B"])
    ow.append({"label": f"{sc}: {SCOPES[sc][1]}", "style": st,
               "rows": [{"x": SH_LABEL[k], "y": float(s.loc[(k, 8), "pct_overwrite_mean"]),
                         "ci": float(s.loc[(k, 8), "pct_overwrite_ci95"]), "n": 5} for k in DEG]})

tbl = []
for k in DEG:
    row = {"shape": SH_LABEL[k]}
    for sc in SCOPES:
        kk, s = knee[sc].loc[k], summ[sc].set_index(["shape", "B"])
        row[sc] = {"bfct": num(KP[sc].loc[k, "B_fct_paired"]), "fct8": float(s.loc[(k, 8), "fct_max_mean"]),
                   "fct8ci": float(s.loc[(k, 8), "fct_max_ci95"]), "ex1": float(s.loc[(k, 1), "fct_max_mean"] - s.loc[(k, 8), "fct_max_mean"]),
                   "bow": num(kk.B_ow), "k99": num(kk.k_steady_p99), "ow8": float(s.loc[(k, 8), "pct_overwrite_mean"])}
    tbl.append(row)

# ---- numbers for chips / tiles / callouts -------------------------------------
cells = int(summ["A"].n_seeds.sum() + summ["B"][summ["B"]["shape"] != "healthy"].n_seeds.sum())
gate_ok = all(bool((summ[sc].gate_clear_mean == 1).all()) for sc in SCOPES)
proof_ok = all(bool(knee[sc].config_proof.all()) and bool(knee[sc].speed_proof.dropna().all()) for sc in SCOPES)
seeds_ok = all(bool((summ[sc].n_seeds == 5).all()) for sc in SCOPES)
nonu = ["r025", "r010", "r005"]
bf = {sc: {k: int(KP[sc].loc[k, "B_fct_paired"]) for k in ["u50"] + nonu} for sc in SCOPES}
bu = {sc: {k: int(knee[sc].loc[k, "B_fct"]) for k in ["u50"] + nonu} for sc in SCOPES}
all_nonu_8 = all(bf[sc][k] == 8 for sc in SCOPES for k in nonu)
k99s = [float(knee[sc].loc[k, "k_steady_p99"]) for sc in SCOPES for k in nonu]
bks = [float(knee[sc].loc[k, "B_ks99"]) for sc in SCOPES for k in nonu]
ow8 = {sc: [float(summ[sc].set_index(["shape", "B"]).loc[(k, 8), "pct_overwrite_mean"]) for k in DEG] for sc in SCOPES}
b_larger = all(ow8["B"][i] > ow8["A"][i] for i in range(len(DEG)))
a5 = summ["A"][(summ["A"]["shape"] == "r005")].set_index("B").fct_max_mean
ex1_5 = a5[1] - a5[8]

brand_gate = {sc: {k: brand_tab[sc][SH_LABEL[k]] for k in DEG} for sc in SCOPES}
b0_gate = {sc: {k: b0_tab[sc][SH_LABEL[k]][0] for k in DEG} for sc in SCOPES}
SAME = [f"{sc} {SH_LABEL[k]}" for sc in SCOPES for k in nonu if b0_gate[sc][k] == bf[sc][k]]
LATER = [f"{sc} {SH_LABEL[k]}" for sc in SCOPES for k in nonu if b0_gate[sc][k] != bf[sc][k]]
_a5 = summ["A"][(summ["A"]["shape"] == "r005")].set_index("B")
_a8 = KP["A"]
KNEE_EX = (f"Example: T2 A 5/95 has unpaired knee {bu['A']['r005']} and paired knee {bf['A']['r005']} (B=6: {_a5.loc[6, 'fct_max_mean']:.1f} +- "
           f"{_a5.loc[6, 'fct_max_ci95']:.1f} against B=128: {_a5.loc[128, 'fct_max_mean']:.1f} +- {_a5.loc[128, 'fct_max_ci95']:.1f}).")
def _cost_result():
    t = []
    for c in cost:
        r = {x["B"]: x for x in c["rows"]}
        t.append(f"{c['label']} slope {c['slope']:.4f}, B=4 {r[4]['pred']:.1f} vs {r[4]['meas']:.1f} us")
    return (f"Same B in {n_same} of {len(cost)} configs. " + "; ".join(t) + " (predicted vs measured).")
COST_RESULT = _cost_result()
chips = [
    chip("ok", "load balancer freezing, constant 200G rate (no CC), -disable_tor_ecn, 128 flows per cell"),
    chip("warn", "degraded-path counts exist for the three non-uniform shapes only: uniform 50/50 degrades every path and "
                 "healthy has none, so neither enters the correlation"),
    chip("ok" if gate_ok else "bad", f"gate clear (0 RTOs, 0 freeze entries) in all {cells} cells"),
    chip("ok" if proof_ok else "bad", "config and link-speed proofs pass in every cell (T2/README.md, Checks)"),
    chip("ok" if seeds_ok else "bad", "5 seeds at every point"),
    chip("warn", "max FCT rests on the 16 pod0 flows; k and overwrites come from 16 traced pod0 hosts only"),
]
tiles = [
    tile("max-FCT knee B_fct, 25/75 to 5/95", f"{min(bf[sc][k] for sc in SCOPES for k in nonu)} to {max(bf[sc][k] for sc in SCOPES for k in nonu)}", "finer grid; 6 vs 8 moves are within noise"),
    tile("5/95: B=1 over B=8", f"+{ex1_5:.0f} us", "ToR->agg scope, 5 seeds", "bad"),
    tile("random draws flatten, B_rand0", f"{min(v for sc in SCOPES for v in b0_gate[sc].values() if v)} to {max(v for sc in SCOPES for v in b0_gate[sc].values() if v)}", "25/75 to 5/95, both scopes; paired extra draws inside CI of zero"),
    tile("scope gap at B >= 8", f"<= {big8:.1f} us", f"agg->core minus ToR->agg; at B=4 up to +{big4:.1f} us"),
]

_sp, _ci = [], []
for sc in SCOPES:
    for k in nonu:
        g = summ[sc][(summ[sc]["shape"] == k) & summ[sc].B.isin([6, 7, 8])]
        _sp.append(float(g.fct_max_mean.max() - g.fct_max_mean.min()))
        _ci.append(float(g.fct_max_ci95.median()))
SPREAD = f"{min(_sp):.1f} to {max(_sp):.1f} us (median CI {min(_ci):.1f} to {max(_ci):.1f})"

body = [
    note(PR.KNEE_NOTE),
    aside("Paired against unpaired knee, tolerance, and how to read one grid step", PR.knee_aside(KNEE_EX)),

    h2("Does the max-FCT knee stay at B=6 to 8 on a 3-tier fat tree?", 1),
    controls("fct-ctl", "scope"),
    controls("fct-y", "y range"),
    plot("fct"),
    note("One line per shape (even position r, odd 1 - r inside each switch, mean 0.5), band = 95% t-CI over 5 seeds, "
         "ring = paired knee B_fct, tinted strip = knee tolerance above each B=128 value."),
    callout("Prediction", "Written in the plan: A behaves like T1/T3, knee at 6-8 (B=5, 6 predicted before they ran)."),
    callout("Result", f"Mostly held. On the finer grid B_fct is {bf['A']['r025']}, {bf['A']['r010']}, {bf['A']['r005']} for 25/75, 10/90, 5/95 "
                      f"in A and {bf['B']['r025']}, {bf['B']['r010']}, {bf['B']['r005']} in B (uniform: {bf['A']['u50']} for A, {bf['B']['u50']} for B), paired rule; "
                      f"unpaired: {bu['A']['r025']}, {bu['A']['r010']}, {bu['A']['r005']} and {bu['B']['r025']}, {bu['B']['r010']}, {bu['B']['r005']}."),
    callout("Caveat", f"B=7 was added and B_fct moves by one grid step (6, 7, 8) between shapes and grids. Over B = 6 to 8 the means "
                      f"differ by {SPREAD} for the non-uniform shapes, so these moves are inside the 5-seed noise. Read the knee as 6 to 8."),
    table("kneetbl"),
    note("Knee table: B=128 CI and tolerance per config (A = ToR->agg, B = agg->core), excess of B=5 to 8 over B=128, B_fct from the rule, "
         "B_rand0: the paired extra random draws over B=128 inside their CI of zero; B_rand: share within 10%."),
    end(),

    h2("Do random EV draws flatten at the same B as max FCT?", 2),
    controls("rnd-ctl", "y metric"),
    plot("rnd"),
    fn_list("rnd-fn"),
    note("Same scope as the plot above, same x axis, colors and rings; dashed numbered lines mark the max-FCT knees. Healthy and "
         "uniform 50/50 have random draws too (their cost is nil); degraded-path counts exist for the three non-uniform shapes only."),
    callout("Prediction", "Written before the plot: the random-draw curve flattens at the max-FCT knee, because random draws cost FCT "
                          "when the load is critical (matched rate) and unevenness raises the cost per draw."),
    callout("Result", f"Tolerance-dependent. B_rand0 (all draws) equals the paired B_fct in {len(SAME)} of {len(SAME) + len(LATER)} non-uniform configs "
                      f"({', '.join(SAME) or 'none'}) and is later in the others ({', '.join(LATER) or 'none'}); the share still falls between B=6 and 8 "
                      "while max FCT is within noise."),
    callout("Caveat", "Why random draws cost FCT is not isolated here: the rate is matched (load is critical), and unevenness probably raises the cost per draw. "
                      "Uniform 50/50 and healthy also draw randomly, with a smaller or no FCT cost, so landing on a degraded path is not the whole story."),
    aside("Knees side by side", f"B_fct paired A / B for 25/75, 10/90, 5/95: {bf['A']['r025']}, {bf['A']['r010']}, {bf['A']['r005']} / {bf['B']['r025']}, {bf['B']['r010']}, {bf['B']['r005']}. "
          f"B_rand0 (all draws): {b0_gate['A']['r025']}, {b0_gate['A']['r010']}, {b0_gate['A']['r005']} / {b0_gate['B']['r025']}, {b0_gate['B']['r010']}, {b0_gate['B']['r005']}. "
          f"Share within 10% of B=128: {brand_gate['A']['r025']}, {brand_gate['A']['r010']}, {brand_gate['A']['r005']} / {brand_gate['B']['r025']}, {brand_gate['B']['r010']}, {brand_gate['B']['r005']}."),
    end(),

    h2("Does the number of draws on degraded paths track the max-FCT excess?", 3),
    controls("corr-ctl", "scope and x metric"),
    controls("corr-b", "B range"),
    plot("corr"),
    '<table id="corrtbl"></table>',
    note(f"One point per (shape, B), 5 seeds, 95% CI on both axes; x = extra degraded draws over B=128 (same seeds). "
         f"**Pooled over B the correlation is inflated: B drives both axes** (both scopes Pearson {cs['P']['all']['pearson']}, Spearman {cs['P']['all']['spearman']}, n={cs['P']['all']['n']}). "
         f"Paired differences, B >= 4, both scopes: {_c(wp['P']['paired, pooled over B 4-64'])}."),
    aside("Correlation across shapes at fixed B (n = 3 per scope)", f"Pearson/Spearman for A: {within_txt('A')}. For B: {within_txt('B')}. Negative values in scope B mean that, at a fixed B, the shape with more extra degraded draws does not have the larger excess."),
    '<table id="corrtbl2"></table>',
    callout("Caveat", "Correlational. Both quantities fall with B, so B drives both; the plot does not show that the draws "
                      "cause the excess; with 3 shapes per scope at fixed B it cannot support a trend. Open-dot markers are scope B (agg->core)."),
    end(),

    h2("Cost model check: does extra degraded draws x slope reproduce the FCT excess?", 4),
    controls("cost-ctl", "scope and shape"),
    controls("cost-b", "B range"),
    plot("cost"),
    '<table id="costtbl"></table>',
    note(f"Slope (us per extra degraded-path draw) is fitted on B = 1, 2 only (no B=3 was run), through the origin; B >= 4 is out of sample. "
         f"Band = 0.2% of the B=128 value. Predicted enters the band at the same B as measured in {n_same} of {len(cost)} configs."),
    aside("Smallest B from which the excess stays in the band", cost_txt + "."),
    callout("Prediction", "Written before the check: the predicted excess falls into the band at the same B as the measured one."),
    callout("Result", COST_RESULT),
    end(),

    h2("Does the scope (ToR->agg vs agg->core) change max FCT?", 5),
    plot("diff"),
    note("Difference of the two scopes' mean max FCT per B and shape; band adds the two CIs. Zero = same curve."),
    callout("Prediction", "Written in the plan, low confidence: agg->core has a larger k tail and more overwrites, "
                          "knee still 8 or 12."),
    callout("Result", f"Knee 6 to 8 in both and the curves agree within {big8:.1f} us for B >= 8; at B=4 agg->core is up to "
                      f"{big4:.1f} us higher. The overwrite and k-tail part is in the next two sections."),
    end(),

    h2("Mechanism: the k tail is above 8, FCT does not follow", 6),
    controls("why-ctl", "scope"),
    plot("why"),
    callout("Result", f"Steady k p99 is {min(k99s):.1f} to {max(k99s):.1f} for the non-uniform shapes (T1: 6 to 12), "
                      f"so B_ks99 is {min(bks):.0f} to {max(bks):.0f}, yet B_fct is 6 to 8. Why overwrites beyond the knee cost so little FCT is not shown."),
    aside("Where the larger tail comes from",
          "Not isolated between 3 tiers, 128 hosts with 4 uplinks per ToR, and degrading all four pod0 ToRs instead "
          "of one. The same-topology T3 cell at 5/95 sits within the seed spread of this one."),
    end(),

    h2("Overwrites at B=8 are larger for agg->core", 7),
    plot("ow"),
    callout("Result", ("Agg->core is higher for every shape " if b_larger else "Not higher for every shape ") +
            "(valid-EV overwrites at B=8, 16 traced pod0 hosts). This does not show up in max FCT."),
    end(),

    h2("Summary per shape and scope", 8, tag="supporting check"),
    table("tbl"),
    note("The slowest flow is a pod0 source sending to pod4 in all 320 degraded cells, so max FCT over all 128 flows "
         "equals the max over pod0 sources."),
    end(),
]

PAGE_JS = PR.RND_JS + r"""
const US = ' (µs)';
const METRICS = [['bfct', 'B_fct (max FCT, paired)'], ['bow', 'B_ow (overwrites < 0.1%)'],
  ['bks', 'B_ks99 (steady k p99)'], ['k99', 'steady k p99']];
let scF = 'A', scW = 'A', rKey = 'pct_random', cGrp = 'A', cKey = 'extra_degraded', cMin = 1, costI = 0, costMin = 1;
function drawFct() {
  const w = DATA.fct[scF];
  drawFctTol('fct', w.series, 'Max FCT vs B - ' + w.title + ' (5 seeds, 95% CI)', yzoom, undefined);
  fillKneeTable('kneetbl', DATA.knee);
}
function drawDiff() {
  const traces = DATA.diff.flatMap(s => PC.lineTrace(s.style, s.rows, s.label, { signed: true }));
  const t = PC.theme(), r = PC.hline(0, 'same curve');
  t.shapes = r.shapes; t.annotations = r.annotations;
  t.xaxis.type = 'category'; t.yaxis.title.text = 'max FCT, agg->core minus ToR->agg' + US;
  PC.draw('diff', traces, t, 'Scope gap in max FCT vs B - 3-tier k=8, pod0 (5 seeds, 95% CI of the difference)');
}
function drawWhy() {
  const w = DATA.why[scW];
  const traces = METRICS.flatMap(([key, name]) =>
    PC.lineTrace(key, w.rows.map(r => ({ x: r.x, y: r[key] })), name, { hover: '%{y:.3g}', noBand: true }));
  const t = PC.theme(), r = PC.hline(8, 'B = 8');
  t.shapes = r.shapes; t.annotations = r.annotations;
  t.xaxis.type = 'category'; t.yaxis.title.text = 'buffer entries'; t.yaxis.rangemode = 'tozero';
  PC.draw('why', traces, t, 'Knees and steady k vs shape - ' + w.title + ', max-FCT knee for reference');
}
function drawOw() {
  const traces = DATA.ow.flatMap(s => PC.lineTrace(s.style, s.rows, s.label, { markers: true, err: true }));
  const t = PC.theme();
  t.xaxis.type = 'category'; t.hovermode = 'closest'; t.yaxis.rangemode = 'tozero';
  t.yaxis.title.text = 'valid-EV overwrites (% of clean ACKs)';
  PC.draw('ow', traces, t, 'Overwrites at B=8 vs shape - 3-tier k=8, pod0 (5 seeds, 95% CI)');
}
function drawTable() {
  const f = (v, d) => v == null ? '-' : (+v).toFixed(d);
  const cols = sc => `<td>${f(sc.bfct, 0)}</td><td>${f(sc.fct8, 1)} ±${f(sc.fct8ci, 1)}</td><td>${f(sc.ex1, 0)}</td>
    <td>${f(sc.bow, 0)}</td><td>${f(sc.k99, 1)}</td><td>${f(sc.ow8, 3)}</td>`;
  const hd = n => `<th>${n} B_fct (paired)</th><th>${n} max FCT B=8${US}</th><th>${n} B=1 over B=8</th><th>${n} B_ow</th><th>${n} steady k p99</th><th>${n} overwrite % B=8</th>`;
  document.getElementById('tbl').innerHTML = '<thead><tr><th>shape</th>' + hd('A') + hd('B') + '</tr></thead><tbody>'
    + DATA.table.map(r => `<tr><td>${r.shape}</td>${cols(r.A)}${cols(r.B)}</tr>`).join('') + '</tbody>';
}
function drawRndT() {
  drawRnd('rnd', 'rnd-fn', DATA.rnd[scF], rKey, RND_META[rKey][0].replace(/^./, c => c.toUpperCase()) + ' vs B - ' + DATA.fct[scF].title + ' (5 seeds, 95% CI)');
}
function drawCorrT() {
  const g = { A: 'ToR->agg', B: 'agg->core', P: 'both scopes' }[cGrp];
  drawCorr('corr', 'corrtbl', DATA.corr[cGrp], cKey, cMin, 'Max-FCT excess vs ' + CORR_META[cKey][0] + ' - 3-tier k=8, ' + g + ', B 1 to 64 (5 seeds, 95% CI)');
  fillCorrTable('corrtbl', 'corrtbl2', DATA.corrStats[cGrp][cKey]);
}
function drawCostT() {
  const c = DATA.cost[costI];
  drawCost('cost', c, costMin, 'Max-FCT excess, predicted vs measured - ' + c.label + ', 3-tier k=8 (5 seeds, 95% CI)');
  fillCostTable('costtbl', DATA.cost);
}
PC.select('cost-ctl', DATA.cost.map((c, i) => [i, c.label]), costI, v => { costI = +v; drawCostT(); });
PC.select('cost-b', [[1, 'B 1 to 64'], [4, 'B 4 to 64 (zoom)']], costMin, v => { costMin = +v; drawCostT(); });
let yzoom = false;
PC.select('fct-y', [['full', 'full range'], ['zoom', 'zoom on the B=128 level']], 'full', v => { yzoom = v === 'zoom'; drawFct(); });
PC.select('fct-ctl', [['A', 'A: pod0 ToR->agg uplinks'], ['B', 'B: pod0 agg->core uplinks']], scF, v => { scF = v; drawFct(); drawRndT(); });
PC.select('rnd-ctl', Object.entries(RND_META).map(([k, v]) => [k, v[0]]), rKey, v => { rKey = v; drawRndT(); });
PC.select('corr-ctl', [['A', 'A: ToR->agg'], ['B', 'B: agg->core'], ['P', 'pooled A + B']], cGrp, v => { cGrp = v; drawCorrT(); });
PC.select('corr-ctl', Object.entries(CORR_META).map(([k, v]) => [k, v[0]]), cKey, v => { cKey = v; drawCorrT(); });
PC.select('corr-b', [[1, 'B 1 to 64'], [4, 'B 4 to 64 (zoom)']], cMin, v => { cMin = +v; drawCorrT(); });
PC.select('why-ctl', [['A', 'A: pod0 ToR->agg uplinks'], ['B', 'B: pod0 agg->core uplinks']], scW, v => { scW = v; drawWhy(); });
function drawAll() { drawFct(); drawRndT(); drawCorrT(); drawCostT(); drawDiff(); drawWhy(); drawOw(); }
drawTable(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        OUT,
        title="T2: 3-tier fat tree k=8, pod0 degradation",
        eyebrow="meeting 26/10/26 · T2",
        h1="Max FCT stops improving at B=6 to 8 on a 3-tier fat tree, for ToR->agg and agg->core degradation alike",
        lede=f"With pod0's uplinks degraded 25/75, 10/90 or 5/95, the max-FCT knee is B = 6 to 8 in both scopes. "
             f"The k tail is above 8 (p99 {min(k99s):.0f} to {max(k99s):.0f}) but FCT does not follow it.",
        cfg="primary metric: max FCT over all 128 flows · matched 200G constant-rate sender · tornado 16 MiB · "
            "freezing, 16 SRv6 paths, trimming on, -disable_tor_ecn · -q 152 -ecn 38 114 · seeds 42-46 · B in {1..128}",
        full_cmd="run_m4.flags('matched', 'healthy', B, seed) with key substitutions in scripts/run_t2.py "
                 "(-topo fat_tree_128_1os_3t_400g -tm tornado_128n_16mb -paths 16 -degrade_links_file "
                 "[tor agg ratio | agg_core agg core ratio]). Details: experiments/meeting_26_10_26/T2/README.md (Setup).",
        brief=question(
            "Does the T1 knee at B=8 survive on a 3-tier k=8 fat tree, with pod0's degradation on ToR->agg or on agg->core uplinks?",
            "Pairs (r, 1 - r) inside each switch keep mean capacity 0.5 (uniform, 25/75, 10/90, 5/95); sweep B 1 to 128, 5 seeds.",
            "Max FCT vs B per shape in each scope, the two scopes side by side, then the mechanism."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"knee": knee_rows, "rnd": rnd, "corr": corr, "corrStats": corr_stats, "cost": cost, "bAll": [f"B={int(b)}" for b in sorted(summ["A"].B.unique())], **PR.META, "fct": fct, "diff": diff, "why": why, "ow": ow, "table": tbl},
        footer="Source `experiments/meeting_26_10_26/T2/{tor_agg,agg_core}/data/*.csv`. Regenerate: "
               "`python3 experiments/meeting_26_10_26/scripts/build_page_t2.py`.",
    )

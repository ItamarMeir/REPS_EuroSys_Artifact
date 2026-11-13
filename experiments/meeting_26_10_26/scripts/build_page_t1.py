#!/usr/bin/env python3
"""
T1/plots/interactive.html in the plot_common.py style (skill interactive-plotter).
Input: T1/data/t1_summary.csv, t1_slow_share.csv, t1_random_stats_cells.csv, t1_knees.csv (T1/scripts/aggregate_t1.py,
add_random_stats.py, knee_t1.py) and t1_maxhost_stats.csv (T1/scripts/maxhost_stats.py).
r = 0.01 is not plotted: it enters Freezing Mode (26 of its 30 cells). experiments/**/*.html is gitignored.

    python3 build_page_t1.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
T1 = HERE.parent / "T1"
sys.path.insert(0, str(HERE.parents[1] / "tools"))
from plot_common import (aside, build_page, callout, chip, controls, end, fct_series, h2,  # noqa: E402
                         note, plot, question, table, tile)
import page_random as PR  # noqa: E402
from page_random import fn_list  # noqa: E402

OUT = T1 / "plots" / "interactive.html"
S = pd.read_csv(T1 / "data" / "t1_summary.csv")
SS = pd.read_csv(T1 / "data" / "t1_slow_share.csv")
CELLS = pd.read_csv(T1 / "data" / "t1_random_stats_cells.csv")
KNEES = pd.read_csv(T1 / "data" / "t1_knees.csv").set_index("fail")
KP = pd.read_csv(T1 / "data" / "t1_knees_paired.csv").set_index("fail")   # T1/scripts/knee_paired.py
MH = pd.read_csv(T1 / "data" / "t1_maxhost_stats.csv")
RES = pd.DataFrame([json.loads(ln) for ln in (T1 / "data" / "results.jsonl").read_text().splitlines()])

# r = 0.01 (file key r001) enters Freezing Mode: counted for the chip, then left out of every plot, table and correlation.
r001 = RES[RES.fail == "r001"]
n001, bad001 = len(r001), int(((r001.rtos > 0) | (r001.freeze_entries > 0)).sum())
S = S[S.fail != "r001"]
CELLS = CELLS[CELLS.fail != "r001"]

# (file key, r on the even agg, style, label, is control)
SHAPES = [("nonuniform", 0.25, "c1", "r = 0.25", False), ("r010", 0.10, "c3", "r = 0.1", False),
          ("r005", 0.05, "c4", "r = 0.05", False), ("uniform50", 0.5, "c2", "r=0.5 (uniform, control)", True)]

fct, ow, spray, rows, rnd, corr, cost, kneerows = [], [], [], [], [], [], [], []
gate_cells = {}
for key, r, style, label, ctrl in SHAPES:
    s = S[S.fail == key].sort_values("B")
    rr = RES[RES.fail == key]
    gate_cells[label] = (len(rr), int(((rr.rtos == 0) & (rr.freeze_entries == 0)).sum()))
    assert gate_cells[label][0] == gate_cells[label][1], f"{label} has gate-failing cells"
    ser = fct_series(s, label, style)
    ser.update(PR.tol_info(s))
    if int(KNEES.loc[key, "B_fct"]) != ser["bfct"]:
        print(f"[warn] {label}: page knee {ser['bfct']} != t1_knees.csv {int(KNEES.loc[key, 'B_fct'])}")
    ser["bunp"] = ser["bfct"]                                       # unpaired page rule (plot_common.knee_fct)
    ser["bfct"] = int(KP.loc[key, "B_fct_paired"]) if pd.notna(KP.loc[key, "B_fct_paired"]) else ser["bunp"]   # paired: rings, tiles, callouts
    fct.append(ser)
    extra = PR.paired_extra(CELLS[CELLS.fail == key])
    rnd.append(PR.rnd_series(s, label, style, ser["bfct"], extra))
    corr.append(PR.corr_points(s, label, style, "", extra))
    cost.append(PR.cost_model(s, label, style, extra))
    # zeros cannot sit on a log axis: dropped, said in the note
    o = [{"x": f"B={int(b.B)}", "y": float(b.pct_overwrite_mean), "ci": float(b.pct_overwrite_ci95),
          "n": int(b.n_seeds)} for b in s.itertuples() if b.pct_overwrite_mean > 0]
    ow.append({"label": label, "style": style, "rows": o})
    sp = SS[(SS.fail == key) & (SS.B == 8)]
    if len(sp):                                   # the uniform control has no degraded paths
        spray.append({"label": label, "style": style,
                      "rows": [{"x": r * 100, "y": float(sp.iloc[0]["mean"]), "ci": float(sp.iloc[0]["std"]), "n": 3}]})
    at = s.set_index("B")
    ex = {int(B): round(float(at.loc[B, "fct_max_mean"] - ser["ref"]), 3) for B in (5, 6, 7, 8)}
    kneerows.append({"label": label, "ref": ser["ref"], "ci128": ser["ci128"], "tol": ser["tol"], "ex": ex,
                     "bfct": ser["bfct"], "bunp": ser["bunp"], "brand": rnd[-1]["brand"],
                     "brand0a": rnd[-1]["brand0a"], "brand0d": rnd[-1]["brand0d"]})
    rows.append({"label": label, "gate": "clear", "ctrl": ctrl, "bfct": ser["bfct"], "bunp": ser["bunp"], "fct8": float(at.loc[8, "fct_max_mean"]),
                 "fct8ci": float(at.loc[8, "fct_max_ci95"]),
                 "ex1": float(at.loc[1, "fct_max_mean"] - at.loc[8, "fct_max_mean"]),
                 "ex2": float(at.loc[2, "fct_max_mean"] - at.loc[8, "fct_max_mean"]),
                 "ow8": float(at.loc[8, "pct_overwrite_mean"]), "rand8": float(at.loc[8, "pct_random_mean"]),
                 "brand": rnd[-1]["brand"], "brand0a": rnd[-1]["brand0a"], "brand0d": rnd[-1]["brand0d"], "rand4": float(at.loc[4, "pct_random_mean"]),
                 "rand5": float(at.loc[5, "pct_random_mean"]), "rand6": float(at.loc[6, "pct_random_mean"]),
                 "rand7": float(at.loc[7, "pct_random_mean"]),
                 "rtos": float(s.rtos_mean.max()), "freeze": float(s.freeze_entries_mean.max())})

rrows = [r for r in rows if not r["ctrl"]]          # the three degraded r
crow = next(r for r in rows if r["ctrl"])           # the uniform control
# B values where every plotted series has zero overwrites: a log axis cannot draw a zero, so the page labels them
ow_zero = [f"B={int(b)}" for b in sorted(S.B.unique())
           if all(S[(S.fail == k) & (S.B == b)].pct_overwrite_mean.fillna(0).le(0).all()
                  for k, *_ in SHAPES if len(S[(S.fail == k) & (S.B == b)]))]
ex1 = ", ".join(f"{r['ex1']:.0f}" for r in rrows)
ex2 = ", ".join(f"{r['ex2']:.0f}" for r in rrows)
ow8 = ", ".join(f"{r['ow8']:.2f}" for r in rrows)
rs = ", ".join(f"{r[1]:g}" for r in SHAPES if not r[4])
knees = sorted({r["bfct"] for r in rrows})
KNEE_TXT = ", ".join(f"{r['label']}: {r['bfct']}" for r in rows)
UNP_TXT = ", ".join(f"{r['label']}: {r['bunp']}" for r in rows)
BRAND_TXT = ", ".join(f"{r['label']}: {r['brand0a']}" + (f"/{r['brand0d']}" if r['brand0d'] else "") for r in rows)
SAME_TXT = ", ".join(r["label"] for r in rows if r["brand0a"] == r["bfct"]) or "none"
LATER_TXT = ", ".join(r["label"] for r in rows if r["brand0a"] != r["bfct"]) or "none"
BRAND10_TXT = ", ".join(f"{r['label']}: {r['brand']}" for r in rows)
_r5 = next(r for r in rows if r["label"] == "r = 0.05")
_b5 = S[(S.fail == "r005") & (S.B == 5)].iloc[0]
_b128 = S[(S.fail == "r005") & (S.B == 128)].iloc[0]
KNEE_EX = (f"Example: T1 r = 0.05 has unpaired knee {_r5['bunp']} because B=5 ({_b5.fct_max_mean:.1f} +- {_b5.fct_max_ci95:.1f}) is compared with "
           f"B=128 ({_b128.fct_max_mean:.1f} +- {_b128.fct_max_ci95:.1f}); the paired knee is {_r5['bfct']}.")
# spread of the means over B = 5..8 against the CI: the evidence that one grid step of the knee is noise
fm = S[S.B.isin([6, 7, 8])].groupby("fail").fct_max_mean.agg(lambda x: x.max() - x.min())
fci = S[S.B.isin([6, 7, 8])].groupby("fail").fct_max_ci95.median()
SPREAD = ", ".join(f"{lab} {fm[k]:.1f} us vs CI {fci[k]:.1f}" for k, _, _, lab, ctrl in SHAPES if not ctrl)
_u = S[S.fail == "uniform50"].set_index("B")
CSTEP = f"{_u.loc[5, 'fct_max_mean']:.1f} to {_u.loc[6, 'fct_max_mean']:.1f} us, CI {_u.loc[5, 'fct_max_ci95']:.1f} and {_u.loc[6, 'fct_max_ci95']:.1f}"
ymax = max(p["y"] for s in fct for p in s["rows"])
ymin = min(p["y"] for s in fct for p in s["rows"])

# ---- max-FCT host view ---------------------------------------------------------------------------------------
mh = {"max": [], "all": []}
for key, r, style, label, ctrl in SHAPES:
    bf = next(f["bfct"] for f in fct if f["label"] == label)
    for sc in mh:
        mh[sc].append(PR.maxhost_series(MH, key, label, style, bf, sc))
mh_b = [f"B={int(b)}" for b in sorted(MH.B.unique())]
# which host was slowest: rows (config, B) with the host id per seed
hosttbl = []
for key, r, style, label, ctrl in SHAPES:
    for B, g in MH[MH.fail == key].groupby("B"):
        g = g.sort_values("seed")
        hosttbl.append({"label": label, "B": int(B), "hosts": [int(h) for h in g.max_host],
                        "maxrand": round(float(g.max_pct_random.mean()), 2), "allrand": round(float(g.all_pct_random.mean()), 2)})
n_cells_mh = len(MH)
same_host = int(MH.groupby(["fail", "B"]).max_host.nunique().gt(1).sum())
n_cfgB = int(MH.groupby(["fail", "B"]).ngroups)
# does the max-FCT host draw random EVs more often than the average ToR0 host? paired per cell at B >= 4
q = MH[MH.B >= 4]
above = (q.max_pct_random > q.all_pct_random)
ABOVE_TXT = f"{int(above.sum())} of {len(q)} cells (B >= 4) have the max-FCT host above the 32-host average"
diff_by_cfg = q.assign(d=q.max_pct_random - q.all_pct_random).groupby("fail").d.mean()
DIFF_TXT = ", ".join(f"{lab} {diff_by_cfg[k]:+.2f} points" for k, _, _, lab, _ in SHAPES)
MH_BRAND = "; ".join(f"{m['label'].replace('r=0.5 (uniform, control)', 'control')}: max-host {m['brand0a']}, avg host {a['brand0a']}, B_fct {m['bfct']}"
                     for m, a in zip(mh["max"], mh["all"]))

MH_EQ = sum(m["brand0a"] == a["brand0a"] for m, a in zip(mh["max"], mh["all"]))
corr_stats = PR.corr_stats(corr)
pool = {k: next(r for r in corr_stats[k]["rows"] if r["name"] == "pooled over B") for k in corr_stats}
cd = pool["extra_degraded"]
wp = {w["name"]: w for w in corr_stats["extra_degraded"]["within"]}


def _c(w):
    return "n/a" if w["pearson"] is None else f"{w['pearson']}/{w['spearman']} (n={w['n']})"


within_txt = "; ".join(f"B={B}: {_c(wp[f'across configs at B={B}'])}" for B in (4, 5, 6, 8))
cost_txt = "; ".join(f"{c['label']}: predicted in band from B={c['b_pred']}, measured from B={c['b_meas']}" for c in cost)
n_same = sum(c["b_pred"] == c["b_meas"] for c in cost)

n_all = sum(v[0] for v in gate_cells.values())
chips = [
    chip("ok", f"gate clear (0 RTOs, 0 freeze entries) in all {n_all} cells of r = 0.25, 0.1, 0.05 and the r=0.5 control"
               f" (r = 0.05: {gate_cells['r = 0.05'][1]} of {gate_cells['r = 0.05'][0]})"),
    chip("warn", f"r = 0.01 excluded from every plot and table: it enters Freezing Mode in {bad001} of {n001} cells"),
    chip("ok", "n_seeds = 3 in every cell" if bool((S.n_seeds == 3).all()) else "seed count varies"),
    chip("ok", "load balancer freezing, sender CC off (constant 200G rate), -disable_tor_ecn, 1024 flows per cell"),
    chip("warn", "degraded-path counts exist only for B = 5, 6, 7, 8, 128 at r = 0.25 (older M4 cells kept no ToR0 trace); "
                 "r=0.5 has no degraded set"),
    chip("warn", "random-draw plots use ToR0 hosts 0-7; the max-FCT-host view uses all 32 ToR0 hosts "
                 f"({n_cells_mh} cells at B in 1, 2, 4, 5, 6, 7, 8, 16, 128)"),
    chip("ok", "reproduction: r = 0.25, B=8, seed 42 matches the M4 cell (0 differing flow lines)"),
]
tiles = [
    tile("max-FCT knee B_fct", " / ".join(str(k) for k in knees), f"r = {rs}; control {crow['bfct']}; rule below"),
    tile("B=1 costs over B=8", f"+{ex1} us", f"max FCT, r = {rs}", "bad"),
    tile("random draws flatten, B_rand0", f"{min(r['brand0a'] for r in rows)}-{max(r['brand0a'] for r in rows)}",
         f"paired extra draws inside CI of zero; B_fct (paired) {min(r['bfct'] for r in rows)}-{max(r['bfct'] for r in rows)}; tolerance-dependent"),
    tile("lowest r that stays clear", "0.05", f"r = 0.01 excluded: Freezing Mode in {bad001} of {n001} cells"),
]


def _cost_result():
    t = []
    for c in cost:
        r = {x["B"]: x for x in c["rows"]}
        t.append(f"{c['label']}: slope {c['slope']:.4f}, B=4 predicted {r[4]['pred']:.1f} vs measured {r[4]['meas']:.1f} us")
    return f"Same B in {n_same} of {len(cost)} configs. " + "; ".join(t) + "."


COST_RESULT = _cost_result()
HOST_ROWS_NOTE = f"The slowest host changes between seeds in {same_host} of {n_cfgB} (r, B) groups."

body = [
    note(PR.KNEE_NOTE),
    aside("Paired against unpaired knee, tolerance, and how to read one grid step", PR.knee_aside(KNEE_EX)),

    h2("Does the max-FCT knee move above B=8 as r falls?", 1),
    controls("fct-y", "y range"),
    plot("fct"),
    note("One line per r (even agg r, odd agg 1 - r, mean 0.5), CI band = 95% t-CI over 3 seeds, ring = paired knee B_fct, "
         "grey-tinted strip = knee tolerance above each B=128 value. The r=0.5 line is the uniform control (no degraded paths)."),
    callout("Prediction", "Written before the grid: the smaller r, the larger the max-FCT gap between B=2 and B=64."),
    callout("Result", f"Half right. The gap grows (B=2 over B=8: {ex2} us for r = {rs}) but the knee does not move up: "
                      f"B_fct (paired) = {KNEE_TXT}; unpaired: {UNP_TXT}. The uniform control has a knee too, so the knee is not specific to degradation."),
    callout("Caveat", f"B=7 was added; B_fct moves by one grid step between grids and rules for the three r. That is inside the noise: over "
                      f"B = 6 to 8 the means differ by {SPREAD}. The control's step from B=5 to 6 ({CSTEP}) is resolved."),
    callout("Caveat", f"r = 0.01 was also run and is excluded: it enters Freezing Mode in {bad001} of {n001} cells, a different "
                      "mechanism (see T1/README.md)."),
    table("kneetbl"),
    note("Knee table: B=128 CI and tolerance per config, excess of B=5 to 8 over B=128 (a value under the tolerance is inside "
         "the knee). B_fct unpaired and paired, then B_rand0: the paired extra random draws over B=128 inside their CI of zero; B_rand: share within 10%."),
    end(),

    h2("Do random EV draws flatten at the same B as max FCT?", 2),
    controls("rnd-ctl", "y metric"),
    plot("rnd"),
    fn_list("rnd-fn"),
    note("Same x axis, colors and ring as the plot above; dashed numbered lines mark the max-FCT knees. Hosts 0-7 of ToR0. "
         "Zeros are not drawn on the log axis; error bars = 95% CI over 3 seeds. No degraded-path count exists for r=0.5, "
         "nor for r = 0.25 at B = 1, 2, 4, 16-64."),
    note("**Same plot for the host that set the max FCT** (same y options, styles, B axis and knee marks):"),
    controls("mh-ctl", "y metric"),
    controls("mh-host", "hosts"),
    plot("mh"),
    fn_list("mh-fn"),
    note(f"Per run, only the source host of the slowest of the 1024 flows (all 32 ToR0 hosts were traced), mean and 95% CI over 3 seeds. "
         f"{HOST_ROWS_NOTE} It is the max-FCT host of each run, not one fixed host. Choosing the slowest of 1024 flows biases its "
         "statistics, so the dotted line is the average ToR0 host from the same traces."),
    '<details class="aside"><summary>Which host was slowest, per (r, B) and seed</summary><p>The three host ids per row are seeds 42, 43, 44; '
    'the last two columns are the mean random share of that host and of the average ToR0 host.</p>'
    '<div class="tblwrap"><table id="hosttbl"></table></div></details>',
    callout("Prediction", "Written before the plots: the random-draw curve flattens at the max-FCT knee (5 to 8), because random draws cost "
                          "FCT when the load is critical (matched rate) and unevenness raises the cost per draw; the max-FCT host draws "
                          "randomly more often than the average host."),
    callout("Result", f"Tolerance-dependent. B_rand0 (all draws) equals the paired B_fct for {SAME_TXT} and is one grid step later for {LATER_TXT}. "
                      f"The share itself is still falling between B=6 and 8 ({rrows[0]['rand6']:.1f}, {rrows[0]['rand7']:.1f}, {rrows[0]['rand8']:.1f} % at r = 0.25)."),
    callout("Result", f"Max-FCT host (extra draws paired with the same host at B=128): its B_rand0 equals the average host's in {MH_EQ} of 4 configs; "
                      f"its share is only slightly higher than the average host's ({ABOVE_TXT})."),
    callout("Caveat", "Why random draws cost FCT: the rate is matched (load is critical) and unevenness raises the cost per draw. Evidence: "
                      "the uniform control r=0.5 has a knee at 6 although no path is degraded relative to another. Not shown as causal."),
    aside("Knees side by side", f"B_fct paired: {KNEE_TXT}. B_fct unpaired: {UNP_TXT}. B_rand0 (all / degraded draws, hosts 0-7): {BRAND_TXT}. "
          f"Share within 10% of B=128: {BRAND10_TXT}. Max-FCT host and average host, B_rand0 (all draws): {MH_BRAND}. "
          f"Mean difference max-FCT host minus average host, random share: {DIFF_TXT}."),
    end(),

    h2("Does the number of draws on degraded paths track the max-FCT excess?", 3),
    controls("corr-ctl", "x metric"),
    controls("corr-b", "B range"),
    plot("corr"),
    '<table id="corrtbl"></table>',
    note(f"One point per (r, B), mean of 3 seeds, 95% CI on both axes; x = extra degraded draws over B=128 (same seeds). "
         f"**Pooled over B the correlation is inflated: B drives both axes** (Pearson {cd['all']['pearson']}, Spearman {cd['all']['spearman']}, n={cd['all']['n']}). "
         f"Paired differences, B >= 4: {_c(wp['paired, pooled over B 4-64'])}."),
    aside("Correlation across r at fixed B", f"Pearson/Spearman: {within_txt}. The r=0.5 control has no degraded count, so it enters only the all-draws and share options."),
    '<table id="corrtbl2"></table>',
    callout("Caveat", "Correlational, and with n = 2 or 3 configs per fixed B it cannot support a trend. r = 0.01 (Freezing Mode) is left out."),
    end(),

    h2("Cost model check: does extra degraded draws x slope reproduce the FCT excess?", 4),
    controls("cost-ctl", "config"),
    controls("cost-b", "B range"),
    plot("cost"),
    '<table id="costtbl"></table>',
    note("Slope (us per extra draw) is fitted on B = 1, 2 only (no B=3 was run), through the origin; B >= 4 is out of sample. "
         "Band = 0.2% of the B=128 value. r = 0.25 and the control use all random draws (no degraded count at B=1, 2)."),
    aside("Smallest B from which the excess stays in the band", cost_txt + "."),
    callout("Prediction", "Written before the check: the predicted excess falls into the tolerance band at the same B as the measured one."),
    callout("Result", COST_RESULT),
    end(),

    h2("Mechanism: the overwrite proxy is already small at B=8", 5),
    plot("ow"),
    note("Share of valid EVs overwritten by a clean ACK at a full buffer, 8 traced ToR0 hosts. Bars are the mean over 3 "
         "seeds with the 95% CI. A zero cannot be drawn on a log axis: the groups where every series is 0 say so. "
         "Dotted line: 0.1%."),
    callout("Prediction", "Written before the grid: overwrites at B=8 rise as r falls."),
    callout("Result", f"Missed: {ow8} % at B=8 for r = {rs}. FCT is flat from B=8 regardless, so there is no gate-clear "
                      "cell where overwrites at B=8 are large and FCT follows."),
    end(),

    h2("REPS sends in proportion to capacity", 6),
    plot("spray"),
    note("Share of ToR0 sends on the degraded (even-agg) paths at B=8 against the capacity share r; the diagonal is "
         "a proportional split. Bars are the std over 3 seeds. The uniform control has no degraded paths and is not shown."),
    aside("What this does and does not show",
          "Consistent with REPS avoiding an even 1/32 spray onto the slow links; not shown to be the cause of the "
          "flat knee. Measured on 8 of 32 ToR0 hosts."),
    end(),

    h2("Summary per r", 7, tag="supporting check"),
    table("tbl"),
    end(),
]

PAGE_JS = PR.RND_JS + r"""
const US = ' (µs)';
let yzoom = false;
function drawFct() {
  drawFctTol('fct', DATA.fct, 'Max FCT vs B - matched 200G, ToR0 uplinks r / 1-r (3 seeds, 95% CI)', yzoom,
    [DATA.ymin - 6, DATA.ymax + 25]);
  fillKneeTable('kneetbl', DATA.knee);
}
function drawOw() {
  const traces = DATA.ow.map(s => PC.barTrace(s.style, s.rows, s.label));
  const t = PC.theme(), r = PC.hline(0.1, '0.1%');
  t.shapes = r.shapes; t.annotations = r.annotations;
  t.barmode = 'group'; t.hovermode = 'closest';
  // groups with no bar because every series is 0 (not drawable on a log axis)
  DATA.owZero.forEach(b => t.annotations.push({ x: b, xref: 'x', y: 0.05, yref: 'paper', showarrow: false,
    text: 'all 0', font: { size: 11, color: PC.css('--muted') } }));
  t.xaxis.type = 'category'; t.xaxis.categoryorder = 'array'; t.xaxis.categoryarray = DATA.bAll;   // keep empty B groups on the axis
  t.yaxis.type = 'log'; t.yaxis.title.text = 'valid-EV overwrites (% of clean ACKs)';
  t.yaxis.tickvals = [0.01, 0.1, 1, 10]; t.yaxis.ticktext = ['0.01', '0.1', '1', '10'];
  PC.draw('ow', traces, t, 'Valid-EV overwrites vs B - matched 200G, ToR0 uplinks r / 1-r (3 seeds, 95% CI)');
}
function drawSpray() {
  const traces = DATA.spray.flatMap(s => PC.lineTrace(s.style, s.rows, s.label,
    { markers: true, err: true, hover: '%{y:.1f}% (std %{customdata[0]:.1f})' }));
  const t = PC.theme();
  t.shapes = [{ type: 'line', xref: 'x', yref: 'y', x0: 0, y0: 0, x1: 28, y1: 28,
    line: { color: PC.css('--muted'), width: 1, dash: 'dot' } }];
  t.hovermode = 'closest';
  t.xaxis.range = [0, 28]; t.yaxis.range = [0, 28];
  t.xaxis.title.text = 'capacity share of the degraded paths, r (%)';
  t.yaxis.title.text = 'share of ToR0 sends on them (%)';
  PC.draw('spray', traces, t, 'Spray share on degraded paths vs capacity share - B=8 (3 seeds)');
}
function drawTable() {
  const f = (v, d) => v == null ? '-' : (+v).toFixed(d);
  document.getElementById('tbl').innerHTML =
    '<thead><tr><th>config</th><th>gate</th><th>B_fct (paired)</th><th>B_fct (unpaired)</th><th>max FCT B=8' + US + '</th><th>B=1 over B=8</th>'
    + '<th>B=2 over B=8</th><th>B_rand0 (all draws)</th><th>random % B=4 / 5 / 6 / 7</th><th>overwrite % B=8</th><th>random EV % B=8</th><th>max RTOs / run</th></tr></thead><tbody>'
    + DATA.table.map(r => `<tr><td>${r.label}</td><td>${r.gate}</td><td>${r.bfct == null ? '-' : r.bfct}</td><td>${r.bunp ?? '-'}</td>
      <td>${f(r.fct8, 1)} ±${f(r.fct8ci, 1)}</td><td>${f(r.ex1, 0)}</td><td>${f(r.ex2, 0)}</td>
      <td>${r.brand0a ?? '-'}</td><td>${f(r.rand4, 1)} / ${f(r.rand5, 1)} / ${f(r.rand6, 1)} / ${f(r.rand7, 1)}</td><td>${f(r.ow8, 2)}</td><td>${f(r.rand8, 2)}</td><td>${f(r.rtos, 0)}</td></tr>`).join('') + '</tbody>';
  document.getElementById('hosttbl').innerHTML =
    '<thead><tr><th>config</th><th>B</th><th>slowest host (seeds 42, 43, 44)</th><th>max-FCT host random %</th><th>avg ToR0 host random %</th></tr></thead><tbody>'
    + DATA.hosttbl.map(r => `<tr><td>${r.label}</td><td>${r.B}</td><td>${r.hosts.join(', ')}</td><td>${r.maxrand}</td><td>${r.allrand}</td></tr>`).join('') + '</tbody>';
}
let rKey = 'pct_random', cKey = 'extra_degraded', cMin = 1, costCfg = 0, costMin = 1, mKey = 'pct_random', mHost = 'both';
function drawRndT() {
  drawRnd('rnd', 'rnd-fn', DATA.rnd, rKey, RND_META[rKey][0].replace(/^./, c => c.toUpperCase()) + ' vs B - matched 200G, ToR0 hosts 0-7, uplinks r / 1-r (3 seeds, 95% CI)');
}
function drawMhT() {
  const ser = mHost === 'max' ? DATA.mh.max : mHost === 'all' ? DATA.mh.all : DATA.mh.max.concat(DATA.mh.all);
  const what = mHost === 'max' ? 'max-FCT host' : mHost === 'all' ? 'average ToR0 host' : 'max-FCT host and average ToR0 host';
  drawRnd('mh', 'mh-fn', ser, mKey, RND_META[mKey][0].replace(/^./, c => c.toUpperCase()) + ' vs B - ' + what + ' of each run, ToR0 uplinks r / 1-r (3 seeds, 95% CI)', DATA.mhB);
}
function drawCorrT() {
  drawCorr('corr', 'corrtbl', DATA.corr, cKey, cMin, 'Max-FCT excess vs ' + CORR_META[cKey][0] + ' - ToR0 uplinks r / 1-r, B 1 to 64 (3 seeds, 95% CI)');
  fillCorrTable('corrtbl', 'corrtbl2', DATA.corrStats[cKey]);
}
function drawCostT() {
  const c = DATA.cost[costCfg];
  drawCost('cost', c, costMin, 'Max-FCT excess, predicted vs measured - ' + c.label + ', ToR0 uplinks r / 1-r (3 seeds, 95% CI)');
  fillCostTable('costtbl', DATA.cost);
}
PC.select('fct-y', [['full', 'full range'], ['zoom', 'zoom on the B=128 level']], 'full', v => { yzoom = v === 'zoom'; drawFct(); });
PC.select('cost-ctl', DATA.cost.map((c, i) => [i, c.label]), costCfg, v => { costCfg = +v; drawCostT(); });
PC.select('cost-b', [[1, 'B 1 to 64'], [4, 'B 4 to 64 (zoom)']], costMin, v => { costMin = +v; drawCostT(); });
PC.select('rnd-ctl', Object.entries(RND_META).map(([k, v]) => [k, v[0]]), rKey, v => { rKey = v; drawRndT(); });
PC.select('mh-ctl', Object.entries(RND_META).map(([k, v]) => [k, v[0]]), mKey, v => { mKey = v; drawMhT(); });
PC.select('mh-host', [['both', 'max-FCT host and average ToR0 host'], ['max', 'max-FCT host only'], ['all', 'average ToR0 host only']], mHost, v => { mHost = v; drawMhT(); });
PC.select('corr-ctl', Object.entries(CORR_META).map(([k, v]) => [k, v[0]]), cKey, v => { cKey = v; drawCorrT(); });
PC.select('corr-b', [[1, 'B 1 to 64'], [4, 'B 4 to 64 (zoom)']], cMin, v => { cMin = +v; drawCorrT(); });
function drawAll() { drawFct(); drawRndT(); drawMhT(); drawCorrT(); drawCostT(); drawOw(); drawSpray(); }
drawTable(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        OUT,
        title="T1: extreme non-uniform degradation",
        eyebrow="meeting 26/10/26 · T1",
        h1=f"Max FCT stops improving at B={knees[0]} to {knees[-1]} for every gate-clear r, uniform control included",
        lede=f"With half of the ToR0 uplinks at r and half at 1 - r, B_fct is {knees[0]} to {knees[-1]} for r = {rs}, "
             f"and {crow['bfct']} with no degradation at all. B=1 costs +{ex1} us over B=8.",
        cfg="primary metric: max FCT over all 1024 flows · matched 200G constant-rate sender · tornado 16 MiB · "
            "freezing, SRv6 32 paths, trimming on, -disable_tor_ecn · seeds 42-44 · B in {1..128}",
        full_cmd="run_m4.flags('matched', 'healthy', B, seed) with -degrade_links_file data/degrade_r*.txt "
                 "(see T1/README.md, Setup). One pass per cell with -log_reps_events (ToR0 hosts 0-7) and "
                 "-log_queue_stats; max-FCT host view: all 32 ToR0 hosts (T1/scripts/maxhost_stats.py).",
        brief=question(
            "Does the REPS buffer knee move above B=8 when ToR0's degradation gets extreme (r = 0.25 down to 0.05), against a uniform control?",
            "Pairs (r, 1 - r) on ToR0's uplinks keep mean capacity 0.5; sweep B; r = 0.01 is excluded (Freezing Mode).",
            "Max FCT vs B per r, then random-draw counts, the max-FCT host, and overwrites as explanation."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"fct": fct, "ow": ow, "spray": spray, "table": rows, "ymin": ymin, "ymax": ymax, "knee": kneerows,
                 "owZero": ow_zero, "rnd": rnd, "corr": corr, "corrStats": corr_stats, "cost": cost, "mh": mh, "mhB": mh_b,
                 "hosttbl": hosttbl, **PR.META, "bAll": [f"B={int(b)}" for b in sorted(S.B.unique())]},
        footer="Source `experiments/meeting_26_10_26/T1/data/*.csv`. Regenerate: "
               "`python3 experiments/meeting_26_10_26/scripts/build_page_t1.py`.",
    )

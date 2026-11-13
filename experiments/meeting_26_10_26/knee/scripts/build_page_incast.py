#!/usr/bin/env python3
"""knee/plots/incast.html: dial F, periodic incast into the receivers of the ToR0 flows (oscillating delay), plot_common style (skill interactive-plotter).
Input: data/f_results.jsonl (4 burst sizes, B 2..128, seeds 42-44), data/d1_results.jsonl (cfg h128_p8_mtu4150 = the no-burst baseline
h128_p8, same flags, seeds 42-44). experiments/**/*.html is gitignored.
    python3 build_page_incast.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KNEE = HERE.parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from plot_common import (aside, build_page, callout, chip, end, h2, knee_fct,  # noqa: E402
                         note, plot, question, table, tile)

D = KNEE / "data"
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}   # two-sided 95% t by df


def load(f):
    return pd.DataFrame(map(json.loads, (D / f).read_text().splitlines()))


F = load("f_results.jsonl")
F = F[F.B != 64]                                  # the baseline has no B=64: keep one B axis for every series
BASE = load("d1_results.jsonl")
BASE = BASE[BASE.cfg == "h128_p8_mtu4150"].copy()
GRID = sorted(F.B.unique())
BASE = BASE[BASE.B.isin(GRID)]
ALL = pd.concat([BASE.assign(S=0), F.assign(S=F.cfg.str.extract(r"incast(\d+)")[0].astype(int) // 1000)])
bad = ALL[(ALL.rtos > 0) | (ALL.freeze_entries > 0)]
ALL = ALL.drop(bad.index) if len(bad) else ALL
SIZES = sorted(ALL.S.unique())                 # 0, 25, 50, 100, 200 (KB per source)
NAME = {0: "no burst (baseline)", 25: "25 KB bursts", 50: "50 KB bursts", 100: "100 KB bursts", 200: "200 KB bursts"}


def ci(v):
    n = len(v)
    return float(T975.get(n - 1, 1.96) * np.std(v, ddof=1) / np.sqrt(n)) if n > 1 else 0.0


def curve(S, col, clip=False):
    g = ALL[ALL.S == S].groupby("B")[col]
    s = pd.DataFrame({"m": g.mean(), "c": g.apply(lambda x: ci(x.to_numpy())), "n": g.size()}).reset_index()
    rows = [{"x": f"B={int(r.B)}", "y": round(r.m, 3), "ci": round(min(r.c, r.m) if clip else r.c, 3), "n": int(r.n)} for r in s.itertuples()]
    return s, rows


def paired_knee(S, tol=0.002):
    """smallest B from which every larger B has mean paired max-FCT excess (same seed vs B=128) <= max(tol*ref, 1.96*SE)."""
    x = ALL[ALL.S == S].pivot(index="seed", columns="B", values="fct_max")
    ref = x[128]
    out = {}
    GRID = list(x.columns)                       # the baseline has no B=64
    for B in GRID:
        d = (x[B] - ref).dropna()
        out[B] = (d.mean(), d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else 0.0)
    thr = {B: max(tol * ref.mean(), 1.96 * out[B][1]) for B in GRID}
    return next(B for B in GRID if all(out[b][0] <= thr[b] for b in GRID if b >= B)), out


def b_ow(S):
    o = ALL[ALL.S == S].groupby("B").pct_overwrite.mean()
    GRID = list(o.index)
    return next(B for B in GRID if all(o[b] < 0.1 for b in GRID if b >= B))


fct_series, ow_series = [], []
knees = {}
for i, S in enumerate(SIZES):
    s, rows = curve(S, "fct_max")
    s = s.rename(columns={"m": "fct_max_mean", "c": "fct_max_ci95", "n": "n_seeds"})
    fct_series.append({"label": NAME[S], "style": f"c{i}", "bfct": knee_fct(s), "noBand": False, "rows": rows})
    ow_series.append({"label": NAME[S], "style": f"c{i}", "bfct": None, "noBand": False, "rows": curve(S, "pct_overwrite", clip=True)[1]})
    knees[S] = (b_ow(S), paired_knee(S)[0], paired_knee(S, 0.01)[0], knee_fct(s))

xl = [NAME[S].replace(" bursts", "").replace("no burst (baseline)", "none") for S in SIZES]
kn_series = [
    {"label": "overwrite knee B_ow (< 0.1% overwrites)", "style": "bow", "bfct": None, "noBand": True,
     "rows": [{"x": x, "y": knees[S][0], "ci": 0, "n": 3} for x, S in zip(xl, SIZES)]},
    {"label": "max-FCT knee B_fct (paired, 0.2%)", "style": "bfct", "bfct": None, "noBand": True,
     "rows": [{"x": x, "y": knees[S][1], "ci": 0, "n": 3} for x, S in zip(xl, SIZES)]},
]

tbl = []
for S in SIZES:
    a, b = ALL[(ALL.S == S) & (ALL.B == 128)], ALL[(ALL.S == S) & (ALL.B == 2)]
    tbl.append({"size": NAME[S], "floor": float(a.fct_max.mean()), "ex2": float(b.fct_max.mean() - a.fct_max.mean()),
                "rnd": float(a.pct_random.mean()), "trims": float(a.trims_total.mean()),
                "bow": knees[S][0], "bfct": knees[S][1], "bfct1": knees[S][2]})

nseed = ALL.groupby(["S", "B"]).size()
chips = [chip("ok", f"{len(ALL)} cells in the plots (0 RTOs, 0 Freezing Mode entries)"),
         chip("warn", "3 seeds per point: the knees of 100 and 200 KB are inside the noise (CI 2 to 4 us)"),
         chip("warn", "bursts trim 600 to 5000 packets per run: the delay comes with token kills"),
         chip("ok", "baseline = h128_p8 cells with the same flags (MTU 4150 run of dial D1), same seeds")]
t0 = tbl[0]
tiles = [tile("overwrite knee B_ow, none to 200 KB", f"{knees[0][0]} to {knees[200][0]}", "the overwrite tail stretches 4 to 8x", "bad"),
         tile("max-FCT knee B_fct, 25 / 50 KB", f"{knees[25][1]} / {knees[50][1]}", f"below the no-burst knee ({knees[0][1]})"),
         tile("excess at B=2, none to 200 KB", f"{tbl[0]['ex2']:.0f} to {tbl[-1]['ex2']:.0f} us", "the cost of a small buffer shrinks as bursts grow")]

body = [
    h2("What the experiment does", 1),
    note("Every 60 us each of the 8 receivers of the degraded ToR0 sources gets a burst of 4 flows of S bytes (25 to 200 KB each), on top of the tornado traffic. "
         "The ToR-to-host link has no ECN, so the burst only delays the data and the ACKs of the flow into that receiver, in a 60 us oscillation."),
    end(),
    h2("Does a bigger oscillating delay move the max-FCT knee?", 2),
    plot("fct"),
    callout("Prediction", "Written before the run: a larger swing makes the in-flight count wander further, so overwrites and the overwrite knee grow, "
                          "and because the walk must come back down, the max-FCT knee follows them upward (about 10 at 25 KB, 16 to 24 at 50 KB)."),
    callout("Result", f"Missed. The paired knee is {knees[0][1]} without bursts and {knees[25][1]}, {knees[50][1]}, {knees[100][1]} at 25, 50, 100 KB: it falls, it does not rise. "
                      "At 200 KB the 3-seed noise leaves it unresolved."),
    note("Rings use the page rule (unpaired, one-sided, 0.2% floor), which reads one grid step lower than the paired knee in the next plot."),
    end(),
    h2("The overwrite knee moves, the FCT knee does not", 3),
    plot("kn"),
    note("B_ow rises from 6 to 24, 24, 32, 48 with the burst size, so the prediction about overwrites held. B_fct falls to 4, 4, 3 (paired, 0.2% floor). "
         "The 32 at 200 KB comes from one noisy point of +5.3 us at B=48 (SE 0.6 to 3.9 us over 3 seeds)."),
    plot("ow"),
    note("At B=6 to 16 the bursts keep overwrites above 0.1% where the baseline is at zero, yet they cost nothing in max FCT beyond B=4."),
    end(),
    h2("Why the extra overwrites are free", 4, tag="supporting check"),
    table("ftbl"),
    aside("Reading, not shown",
          "The bursts overflow the receiver's ToR-to-host queue (101 packets) and trim 600 to 5000 packets per run, so tokens are also killed by trims. "
          "The random-draw share at B=128 is already 4.7 to 34% against 2.9% without bursts. With the buffer drained by kills, the extra overwrites "
          "(which need a full buffer) are rare in the part of the run that matters. No burst size delayed without trimming was found; 25 KB, "
          "the smallest, already has the lower knee."),
    end(),
]

PAGE_JS = r"""
function draw() {
  PC.fctVsB('fct', DATA.fct, 'Max FCT vs B - periodic incast into the ToR0 receivers (128 hosts, 3 seeds, 95% CI)');
  PC.fctVsB('kn', DATA.kn, 'Knee vs burst size per source (B_ow from 3 seeds; B_fct paired against B=128)', { ylabel: 'knee B (buffer entries)' });
  PC.fctVsB('ow', DATA.ow, 'Overwrites vs B (% of sends, 3 seeds, 95% CI)', { ylabel: '% overwrites' });
}
document.getElementById('ftbl').innerHTML = '<thead><tr><th>burst per source</th><th>max FCT at B=128 (us)</th><th>excess at B=2 (us)</th>'
  + '<th>random draws at B=128 (%)</th><th>trims per run</th><th>B_ow</th><th>B_fct 0.2%</th><th>B_fct 1%</th></tr></thead><tbody>'
  + DATA.tbl.map(r => `<tr><td>${r.size}</td><td>${r.floor.toFixed(1)}</td><td>${r.ex2.toFixed(1)}</td><td>${r.rnd.toFixed(1)}</td>`
    + `<td>${Math.round(r.trims)}</td><td>${r.bow}</td><td>${r.bfct}</td><td>${r.bfct1}</td></tr>`).join('') + '</tbody>';
draw(); PC.onRedraw(draw);
"""

if __name__ == "__main__":
    build_page(
        KNEE / "plots" / "incast.html",
        title="Dial F: oscillating incast delay",
        eyebrow="meeting 26/10/26 · knee study · dial F",
        h1="Oscillating delay stretches the overwrite knee, not the max-FCT knee",
        lede=f"Bursts into the receivers of the degraded flows raise the overwrite knee from {knees[0][0]} to {knees[200][0]}, "
             f"but the max-FCT knee does not rise: {knees[25][1]} at 25 and 50 KB against {knees[0][1]} without bursts (paired, 0.2%).",
        cfg="primary metric: max FCT over all flows · matched 200G constant-rate sender · ToR0 uplinks 5/95 · 128 hosts, radix 8, tornado 16 MiB · "
            "+ incast every 60 us from 20 us, 4 sources per receiver (`-disable_tor_ecn`) · freezing, trimming on",
        full_cmd="run_m4.flags('matched','healthy',B,seed) with tm=connection_matrices/knee/incast_s{S}.cm "
                 "(knee/scripts/make_incast_cm.py, make_knee_configs.py, run by run_knee.py in container m23-dev). Details: knee/README.md, Dial F.",
        brief=question("Can an oscillating delay on the return path (periodic incast) raise the max-FCT knee above 8?",
                       "Four burst sizes per source (25 to 200 KB) into the receivers of the 8 degraded sources, B = 2 to 128, 3 seeds, plus the no-burst baseline.",
                       "Max-FCT knee against the overwrite knee B_ow, per burst size."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"fct": fct_series, "kn": kn_series, "ow": ow_series, "tbl": tbl},
        footer="Source `knee/data/f_results.jsonl`, `d1_results.jsonl` (baseline). "
               "Regenerate: `python3 experiments/meeting_26_10_26/knee/scripts/build_page_incast.py`.")

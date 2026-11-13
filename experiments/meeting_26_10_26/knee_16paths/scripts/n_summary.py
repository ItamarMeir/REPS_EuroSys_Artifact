#!/usr/bin/env python3
"""Headline numbers of the 16-path N sweep (feeds README results and the page Result text). Reads data/*.csv, writes data/n_summary.txt.
Metric = per (latency, B, seed) mean over messages 2-4 of the max FCT of hosts 0-15; paired = per-seed difference against the same seed at the largest B (plateau); mean and 95% CI over 8 seeds."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nsweep_extra as X
D = Path(__file__).resolve().parent.parent / "data"
def met(f):
    d = pd.read_csv(D / f); d["lat"] = d.cfg.str.extract(r"lat(\d+)")[0].astype(int)
    return d[d.msg >= 1].groupby(["lat", "B", "seed"])["max"].mean().reset_index()
R, G = met("n_permessage.csv"), met("n_permessage_god.csv")
M = pd.read_csv(D / "n_mech.csv"); M["lat"] = M.cfg.str.extract(r"lat(\d+)")[0].astype(int)
S = pd.read_csv(D / "n_sol_sim.csv"); S = S[S.variant == "sol1p"].groupby("lat_ns")[["fct2", "analytic"]].mean()
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
def stats(d, L):
    h = d[d.lat == L]; Bs = sorted(h.B.unique()); ref = Bs[-1]
    p = h.pivot(index="seed", columns="B", values="max"); base = p[ref]
    rows = []
    for B in Bs:
        x = (p[B] - base).dropna().values
        rows.append((B, p[B].mean(), x.mean(), X.ci(x), len(x)))
    return pd.DataFrame(rows, columns=["B", "fct", "exc", "ci", "n"]), ref
for name, d in (("REPS", R), ("GOD", G)):
    P("==", name)
    for L in sorted(d.lat.unique()):
        t, ref = stats(d, L); fct_ref = t.fct.iloc[-1]; tol = 0.002 * fct_ref
        best = t.loc[t.fct.idxmin()]
        # knee: smallest B from which every B up to the plateau has paired excess <= tol (one-sided, CI of the tested B included)
        ok = (t.exc - t.ci) <= tol
        knee = next((int(t.B.iloc[i]) for i in range(len(t)) if ok.iloc[i:].all()), None)
        low = t.loc[t.exc.idxmin()]
        e = lambda B: t[t.B == B].exc.values[0] if (t.B == B).any() else float("nan")
        m = M[(M.lat == L) & (M.B == ref)]
        P(f"lat {L:5d} N(page label: median peak inflight over all cells of the latency) {M[M.lat == L].peak_inflight.median():.0f} fresh_m2 {m.fresh_m2.median():.0f} | plateau {fct_ref:.1f} us, best B={int(best.B)} {best.fct:.1f} | sim SOL {S.loc[L].fct2:.1f} best-SOL {best.fct-S.loc[L].fct2:.1f} | knee(0.2%={tol:.2f}) {knee} | excess B=2 {e(2):.1f} B=8 {e(8):.1f} | lowest paired B={int(low.B)} {low.exc:.1f}+-{low.ci:.1f}")
J = pd.read_csv(D / "god_paired.csv")
P("== REPS minus god (positive = god faster): B=2, 8, 32, plateau")
for L, h in J.groupby("lat"):
    g = lambda B: h[h.B == B]
    P(f"lat {L:5d} " + " ".join(f"B={B}: {g(B).d.values[0]:.1f}+-{g(B).ci.values[0]:.1f}" for B in (2, 8, 32) if len(g(B))) + f" plateau {h.d.iloc[-1]:.1f}+-{h.ci.iloc[-1]:.1f}")
import json
h = (D.parent / "plots" / "nsweep.html").read_text(encoding="utf-8"); i = h.index("const DATA =") + 12
DP = json.loads(h[i:h.index(chr(10), i)].rstrip().rstrip(";"))
P("== page rule (plots/nsweep.html, DATA.fct[*].bfct: the largest-B reference, knee at 0.2% or the lowest B when it is a dip by more than 2 SE): N", DP["Ns"], "ring B", [s["bfct"] for s in DP["fct"]], "god", [s["bfct"] for s in DP["gfct"]])
um = {}
for arm, pre in (("REPS", "n_um_"), ("GOD", "n_um_god_")):
    P("== uplink-class numbers of the max-FCT host (all sends of the post-warmup phase; warmup draws on 5% links = even EVs); needs data/n_um_*.csv")
    wt = []
    for L in sorted(R.lat.unique()):
        u = pd.read_csv(D / f"{pre}{L}.csv"); u = u[u.role == "max"]
        w = u[[f"hist_w_{j}" for j in range(16)]].sum(); wt.append((w[[f"hist_w_{j}" for j in range(0, 16, 2)]].sum(), w.sum()))
        for lo, hi in ((2, 8), (32, 128), (256, 100000)):
            s = u[(u.B >= lo) & (u.B <= hi)]
            if not len(s): continue
            tot = sum(s[c].sum() for c in ("pb_r", "pb_f", "pb_o", "pg_r", "pg_f", "pg_o"))
            P(f"{arm} lat {L:5d} B {lo}-{min(hi, 9999)}: random share of all sends {(s.pb_r.sum() + s.pg_r.sum()) / tot:.2f}, ECN-marked share of ACKs of 95% links {s.pg_a1.sum() / (s.pg_a0.sum() + s.pg_a1.sum()):.3f}, of 5% links {s.pb_a1.sum() / (s.pb_a0.sum() + s.pb_a1.sum()):.3f}")
    P(f"{arm} warmup draws on 5% links: per latency", [round(a / b, 3) for a, b in wt], "pooled", round(sum(a for a, _ in wt) / sum(b for _, b in wt), 3), "of", int(sum(b for _, b in wt)), "warmup sends (max-FCT host)")
(D / "n_summary.txt").write_text("\n".join(out) + "\n")

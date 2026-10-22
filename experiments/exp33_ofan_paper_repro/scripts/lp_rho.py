#!/usr/bin/env python3
"""E6 follow-up: LP-optimal rho_max for a Fig 9 instance (max concurrent flow over valid shortest paths).
Usage: lp_rho.py <inst_dir> [--pods 12 --apod 6 --hpt 6]. Reads fail.txt, wl.cm; writes <inst_dir>/inst_lp.json
(same keys as inst.json that run_fig9.sh uses: rho_max, ideal_cct_increase_pct) plus rho_equal for comparison.
Same topology indexing as fig9_instance.py. Maximise rho s.t. sum_path x_fp = rho per flow, link load <= 1."""
import argparse, json, os
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
ap = argparse.ArgumentParser(); ap.add_argument("d"); ap.add_argument("--pods", type=int, default=12)
ap.add_argument("--apod", type=int, default=6); ap.add_argument("--hpt", type=int, default=6); a = ap.parse_args()
A, HPT = a.apod, a.hpt; TPP = A; NCORE = A * A
E, C = set(), set()
for ln in open(os.path.join(a.d, "fail.txt")):
    k, x, y = ln.split()
    (C if k == "C" else E).add((int(x), int(y)))
flows = []
for ln in open(os.path.join(a.d, "wl.cm")):
    if "->" in ln:
        s, r = ln.split("->"); flows.append((int(s), int(r.split()[0])))
lid = {}; rows = []; cols = []; nv = 0; fl_vars = []
for f, (s, d) in enumerate(flows):
    ts, td = s // HPT, d // HPT; ps, pd = ts // TPP, td // TPP; vs = []
    for pos in range(A):
        g, dg = ps * A + pos, pd * A + pos
        if (ts, g) in E or (td, dg) in E: continue
        for c in range(pos, NCORE, A):
            if (g, c) in C or (dg, c) in C: continue
            for k in (("Eu", ts, g), ("Cu", g, c), ("Cd", c, dg), ("Ed", dg, td)):
                rows.append(lid.setdefault(k, len(lid))); cols.append(nv)
            vs.append(nv); nv += 1
    fl_vars.append(vs)
nf = len(flows); nL = len(lid); n = nv + 1   # last var = rho
Aub = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(nL, n)).tocsr()
er, ec, ev = [], [], []
for f, vs in enumerate(fl_vars):
    for v in vs: er.append(f); ec.append(v); ev.append(1.0)
    er.append(f); ec.append(nv); ev.append(-1.0)
Aeq = coo_matrix((ev, (er, ec)), shape=(nf, n)).tocsr()
cost = np.zeros(n); cost[-1] = -1.0
r = linprog(cost, A_ub=Aub, b_ub=np.ones(nL), A_eq=Aeq, b_eq=np.zeros(nf), bounds=[(0, None)] * nv + [(0, 1.0)], method="highs")
assert r.status == 0, r.message
rho = float(r.x[-1]); eq = json.load(open(os.path.join(a.d, "inst.json")))
json.dump({"rho_max": rho, "ideal_cct_increase_pct": (1 / rho - 1) * 100, "rho_equal": eq["rho_max"],
           "ideal_equal_pct": eq["ideal_cct_increase_pct"]}, open(os.path.join(a.d, "inst_lp.json"), "w"))
print(f"{a.d} rho_lp={rho:.4f} rho_equal={eq['rho_max']:.4f}")

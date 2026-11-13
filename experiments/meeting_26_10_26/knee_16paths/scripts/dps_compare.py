#!/usr/bin/env python3
"""DPS (95% / 5%, -dps_dist capacity) against REPS and god mode, from the per-message max FCT of hosts 0-15 (e_permessage.py output).
Metric: for a (cfg, B, seed) cell, the mean over messages 2-4 of the max FCT of hosts 0-15 (the page metric). Seeds 42-44 only (the DPS arm has 3 seeds; REPS and god are restricted to the same seeds and paired by seed).
REPS / god columns: B = 2, B = 8 (the knee) and the best B of that latency, the best B being chosen on the same 3 seeds (a favourable selection among ~13 B values, so "best" understates the arm's cost).
usage: python dps_compare.py   (reads data/*.csv, writes data/dps_compare.csv and data/dps_compare.txt)"""
import csv, json, statistics as st
from collections import defaultdict
from pathlib import Path
import params as Pm
D = Path(__file__).resolve().parent.parent / "data"
SEEDS = (42, 43, 44)
T95 = {2: 4.303}                                              # t(0.975, df = n - 1) for n = 3 seeds


def head(path, pfx):
    d = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(open(path)):
        if r["cfg"].startswith(pfx) and int(r["msg"]) >= 1 and int(r["seed"]) in SEEDS:
            d[(r["cfg"], int(r["B"]))][int(r["seed"])].append(float(r["max"]))
    return {k: {s: st.mean(v) for s, v in sv.items() if len(v) == 3} for k, sv in d.items()}


def ci(x):
    return T95[len(x) - 1] * st.stdev(x) / len(x) ** 0.5 if len(x) == 3 else float("nan")


def sol(lat):
    v = [float(r["fct1"]) for r in csv.DictReader(open(D / "n_sol_sim.csv")) if r["variant"] == "sol1p" and int(r["lat_ns"]) == lat]
    return st.mean(v)


reps, god = head(D / "n_permessage.csv", "h512_p16_msgNh_lat"), head(D / "n_permessage_god.csv", "h512_p16_msgNhG_lat")
dps = head(D / "dps_permessage.csv", "h512_p16_msgNhDcap_lat")
res = {json.loads(l)["cfg"]: [] for l in open(D / "dps_results.jsonl")}
for l in open(D / "dps_results.jsonl"):
    r = json.loads(l)
    if r["seed"] in SEEDS: res[r["cfg"]].append(r)
rows, out = [], []
for L in Pm.LATS:
    dv = dps.get((f"h512_p16_msgNhDcap_lat{L}", 8), {})
    if len(dv) < 3: out.append(f"lat {L}: DPS incomplete {sorted(dv)}"); continue
    arms = {}
    for name, tab, cfg in (("REPS", reps, f"h512_p16_msgNh_lat{L}"), ("god", god, f"h512_p16_msgNhG_lat{L}")):
        byB = {B: v for (c, B), v in tab.items() if c == cfg and all(s in v for s in SEEDS)}
        best = min(byB, key=lambda B: st.mean(byB[B].values()))
        arms[name] = {"B=2": byB[2], "B=8": byB[8], f"best B={best}": byB[best]}
    line = f"lat {L:5d} ns  SOL {sol(L):7.1f} | DPS {st.mean(dv.values()):7.1f} +-{ci(list(dv.values())):4.1f}"
    row = dict(lat=L, sol=sol(L), dps=st.mean(dv.values()), dps_ci=ci(list(dv.values())))
    for name, a in arms.items():
        for lab, v in a.items():
            diff = [dv[s] - v[s] for s in SEEDS]                # positive = DPS slower
            line += f" | {name} {lab}: {st.mean(v.values()):7.1f}, DPS-{name} {st.mean(diff):+6.1f} +-{ci(diff):4.1f}"
            row[f"{name} {lab.split(' ')[0]}"] = st.mean(v.values()); row[f"dps_minus_{name}_{lab.split(' ')[0]}"] = st.mean(diff); row[f"dps_minus_{name}_{lab.split(' ')[0]}_ci"] = ci(diff)
    cells = res[f"h512_p16_msgNhDcap_lat{L}"]
    tr = [sum(c["uplink_trims"][0::2]) for c in cells]; tg = [sum(c["uplink_trims"][1::2]) for c in cells]
    line += f" | trims 5%/95% links per cell {st.mean(tr):.0f}/{st.mean(tg):.0f}, RTOs {sum(c['rtos'] for c in cells)}, freezes {sum(c['freeze_entries'] for c in cells)}"
    out.append(line); rows.append(row)
(D / "dps_compare.txt").write_text("\n".join(out) + "\n")
keys = sorted({k for r in rows for k in r}, key=lambda k: (k != "lat", k))
with open(D / "dps_compare.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
print("\n".join(out))

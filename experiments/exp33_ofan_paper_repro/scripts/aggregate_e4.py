#!/usr/bin/env python3
"""Aggregate E4 runs (data/e4/runs/*.out,*.tsv) -> data/e4/e4_runs.csv (per run) and data/e4/e4_summary.md/csv (mean +- SEM).
Link utilisation definition: for every switch egress link, (data_bytes+hdr_bytes)*8 / (800 Gb/s * CCT) = average utilisation over [0,CCT]
(CCT = last flow finish; includes the ramp-up and tail). 'max link util' = max over links of that value, per layer; 'fabric max' = max over layers
E->A,A->C,C->A,A->E (switch-switch links). No time series is available from the frozen binary."""
import re, csv, glob, os, math, sys, statistics as st
sys.stdout.reconfigure(encoding="utf-8")
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "e4"); R = os.path.join(H, "runs")
LAY = ["E->A", "A->C", "C->A", "A->E", "E->H"]; LINK_BPS = 800e9
def parse(tag):
    txt = open(f"{R}/{tag}.out", errors="replace").read()
    rows = [dict(re.findall(r"(\w+) ([\d.]+)", l.split("finished at")[1])) | {"fin": float(re.search(r"finished at ([\d.]+)", l).group(1))}
            for l in txt.splitlines() if "finished at" in l]
    S = lambda k: sum(int(float(r.get(k, 0))) for r in rows)
    d = dict(tag=tag, fin=len(rows), started=len(re.findall(r"starting at", txt)) or None, cct=max((r["fin"] for r in rows), default=float("nan")),
             rc=(re.search(r"^rc=(\d+)", txt, re.M) or [0, "?"])[1], rtos=S("rtos"), ecn_acks=S("ecn_acks"), rts=S("RTS"), fast_loss=S("fast_loss"),
             pkts=sum(int(x) for x in re.findall(r"total packets (\d+)", txt)),
             abort=bool(re.search(r"abort|Aborted|Assertion|Segmentation|terminate", txt, re.I)),
             tor_dl=(re.search(r"enable on tor downlink (\d)", txt) or [0, "?"])[1])
    q = {l: 0 for l in LAY}; u = {l: 0.0 for l in LAY}; um = {l: [] for l in LAY}; trims = drops = 0
    for r in csv.DictReader(open(f"{R}/{tag}.tsv"), delimiter="\t"):
        l = r["layer"]; q[l] = max(q[l], int(r["max_q_bytes"])); trims += int(r["trims"]); drops += int(r["drops"])
        ut = (int(r["data_bytes"]) + int(r["hdr_bytes"])) * 8 / (LINK_BPS * d["cct"] * 1e-6); u[l] = max(u[l], ut); um[l].append(ut)
    for l in LAY:
        k = l.replace("->", "")
        d["q_" + k] = q[l] / 4150.0; d["umax_" + k] = u[l] * 100; d["umean_" + k] = 100 * sum(um[l]) / max(1, len(um[l]))
    d["trims"] = trims; d["drops"] = drops
    d["umax_fabric"] = max(d["umax_" + l.replace("->", "")] for l in LAY[:4])
    return d
def meta(tag):
    m = re.match(r"(dctcp|nscc|mswift)_(reps|ar|ofanhash|ofan)(_noDTE)?_s(\d+)$", tag)
    return (m.group(1), m.group(2), "noDTE" if m.group(3) else "DTE", int(m.group(4))) if m else None
single = {}
for f in glob.glob(f"{R}/single_*.out"):
    t = os.path.basename(f)[:-4]; single[t.replace("single_", "")] = parse(t)["cct"]
runs = []
for f in sorted(glob.glob(f"{R}/*_s[0-9]*.out")):
    t = os.path.basename(f)[:-4]; m = meta(t)
    if not m or not os.path.exists(f"{R}/{t}.tsv"): continue
    d = parse(t); d.update(cca=m[0], lb=m[1], ecnmode=m[2], seed=m[3])
    sk = m[0] + ("_noDTE" if m[2] == "noDTE" else ""); d["single"] = single[sk]; d["inc"] = (d["cct"] / d["single"] - 1) * 100
    runs.append(d)
keys = ["cca", "lb", "ecnmode", "seed", "tag", "fin", "cct", "single", "inc", "rc", "abort", "trims", "drops", "rtos", "ecn_acks", "rts", "fast_loss", "pkts", "tor_dl"] \
    + ["q_" + l.replace("->", "") for l in LAY] + ["umax_fabric"] + [p + l.replace("->", "") for p in ("umax_", "umean_") for l in LAY]
with open(f"{H}/e4_runs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, keys, extrasaction="ignore"); w.writeheader(); w.writerows(runs)
def ms(v):
    n = len(v); m = sum(v) / n
    return m, (st.stdev(v) / math.sqrt(n) if n > 1 else 0.0)
groups = {}
for r in runs: groups.setdefault((r["ecnmode"], r["cca"], r["lb"]), []).append(r)
order = {"reps": 0, "ar": 1, "ofan": 2, "ofanhash": 3}
cols = [("n", None), ("CCT us", "cct"), ("CCT inc %", "inc"), ("fabric max util %", "umax_fabric"), ("q E>A", "q_EA"), ("q A>C", "q_AC"), ("q C>A", "q_CA"), ("q A>E", "q_AE"), ("q E>H", "q_EH"),
        ("trims", "trims"), ("drops", "drops"), ("RTOs", "rtos"), ("ecn_acks", "ecn_acks")]
lines = []; summ = []
for mode in ("DTE", "noDTE"):
    lines += [f"\n### {'-disable_tor_ecn (default)' if mode == 'DTE' else 'WITHOUT -disable_tor_ecn (ToR-downlink ECN on; sensitivity)'}\n",
              "| CCA | LB | " + " | ".join(c for c, _ in cols) + " | finished (min) | aborts |", "|" + "---|" * (len(cols) + 4)]
    for (m, cca, lb), rs in sorted(groups.items(), key=lambda kv: (kv[0][1], order[kv[0][2]])):
        if m != mode: continue
        cells = [str(len(rs))]; row = {"mode": m, "cca": cca, "lb": lb, "n": len(rs)}
        for c, k in cols[1:]:
            mu, se = ms([r[k] for r in rs]); row[k] = mu; row[k + "_sem"] = se
            fmt = "%.0f ± %.0f" if k in ("trims", "drops", "rtos", "ecn_acks") else ("%.1f ± %.1f" if k.startswith("q_") else "%.2f ± %.2f")
            cells.append(fmt % (mu, se))
        lines.append(f"| {cca} | {lb} | " + " | ".join(cells) + f" | {min(r['fin'] for r in rs)}/432 | {sum(r['abort'] or r['rc'] != '0' for r in rs)} |")
        summ.append(row)
open(f"{H}/e4_summary.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
with open(f"{H}/e4_summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, sorted({k for r in summ for k in r})); w.writeheader(); w.writerows(summ)
print("\n".join(lines)); print("single-flow CCT us:", single)

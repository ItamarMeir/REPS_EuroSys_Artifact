#!/usr/bin/env python3
"""E5 summary. Reads data/trimrto/runs/*.out/.tsv (+ E4 runs from data/e4/runs.tar.gz) -> data/trimrto/e5_*.csv / e5_summary.md.
Usage: summarize_trimrto.py [e4_runs_dir]  (default: extracts e4 tarball to a temp dir)"""
import re, csv, os, sys, glob, tarfile, tempfile, statistics as st, collections
sys.stdout.reconfigure(encoding="utf-8")
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"); T = os.path.join(H, "trimrto"); R = os.path.join(T, "runs")
LAY = ["E->A", "A->C", "C->A", "A->E", "E->H"]
def parse(path):
    txt = open(path + ".out", errors="replace").read()
    fl = [l for l in txt.splitlines() if l.startswith("Flow ") and "finished at" in l]
    def S(k): return sum(int(m.group(1)) for l in fl for m in [re.search(r"\b%s (\d+)" % k, l)] if m)
    fin = [float(re.search(r"finished at ([\d.]+)", l).group(1)) for l in fl]
    d = dict(fin=len(fl), cct=max(fin) if fin else float("nan"), rc=(re.search(r"^rc=(\d+)", txt, re.M) or [0, "?"])[1],
             rtos=S("rtos"), freeze=S("freeze_entries"), freeze_us=S("freeze_us"), explore=S("ev_explore"), rts=S("RTS"), fast_loss=S("fast_loss"),
             min_rto=float((re.search(r"Setting min RTO to ([\d.]+)", txt) or [0, "nan"])[1]),
             abort=bool(re.search(r"Aborted|Assertion|Segmentation|terminate", txt)), flowlines=fl)
    tsv = path + ".tsv"; q = {l: 0 for l in LAY}; trims = drops = 0
    if os.path.exists(tsv):
        for r in csv.DictReader(open(tsv), delimiter="\t"):
            q[r["layer"]] = max(q[r["layer"]], int(r["max_q_bytes"])); trims += int(r["trims"]); drops += int(r["drops"])
    d.update(q=q, trims=trims, drops=drops, maxq_fab=max(q[l] for l in LAY[:4]))
    return d
if not os.path.isdir(R) and os.path.exists(os.path.join(T, "runs.tar.gz")):   # raw runs are archived; extract to a temp dir
    _t = tempfile.mkdtemp(); tarfile.open(os.path.join(T, "runs.tar.gz")).extractall(_t); R = os.path.join(_t, "runs")
def done(f): return re.search(r"^rc=", open(f, errors="replace").read(), re.M) is not None
runs = {os.path.basename(f)[:-4]: parse(f[:-4]) for f in glob.glob(R + "/*.out") if done(f)}
out = []
# ---- A1: bit-for-bit vs E4
e4dir = sys.argv[1] if len(sys.argv) > 1 else None
if not e4dir:
    e4dir = tempfile.mkdtemp(); tarfile.open(os.path.join(H, "e4", "runs.tar.gz")).extractall(e4dir); e4dir = os.path.join(e4dir, "runs")
out.append("## A1. Fig 12 cells with -disable_trim vs E4 (trim on)\n")
out.append("| CCA | LB | seed | CCT trim-on (E4) | CCT trim-off | flow-finish lines identical | .tsv queue stats identical | trims/drops/rtos (new) |\n|---|---|---|---|---|---|---|---|")
nid = ntot = 0; rows = []
for tag in sorted(t for t in runs if t.startswith("a_")):
    _, cc, lb, s = tag.split("_"); old = os.path.join(e4dir, f"{cc}_{lb}_{s}")
    if not os.path.exists(old + ".out"): continue
    o = parse(old); n = runs[tag]; same = o["flowlines"] == n["flowlines"]
    tsv_same = open(old + ".tsv").read() == open(os.path.join(R, tag + ".tsv")).read()
    ntot += 1; nid += same and tsv_same
    rows.append((cc, lb, s, o["cct"], n["cct"], same, tsv_same, n["trims"], n["drops"], n["rtos"]))
    out.append(f"| {cc} | {lb} | {s} | {o['cct']:.4f} | {n['cct']:.4f} | {same} | {tsv_same} | {n['trims']}/{n['drops']}/{n['rtos']} |")
out.append(f"\nIdentical (flow lines and queue-stats TSV): {nid}/{ntot} cells.\n")
# ---- S: stress
out.append("## A2. Small-buffer stress (NSCC, -q 40 -ecn 5 10), 3 seeds, mean (min..max over seeds)\n")
out.append("| LB | trimming | CCT us | CCT inc % vs 48.81 | trims | drops | RTOs | RTS | freeze_entries | max fabric queue (pkts) | flows finished |\n|---|---|---|---|---|---|---|---|---|---|---|")
g = collections.defaultdict(list)
for tag, d in runs.items():
    m = re.match(r"s_nscc_(\w+)_(trim|notrim)_s(\d+)$", tag)
    if m: g[(m[1], m[2])].append(d)
single4 = runs["single_4mb_nscc"]["cct"]
def f(v, fmt="%.2f"): return (fmt % st.mean(v)) + ("" if len(v) < 2 else " (%s..%s)" % (fmt % min(v), fmt % max(v)))
for lb in ("reps", "ar", "ofan"):
    for t in ("trim", "notrim"):
        ds = g.get((lb, t), [])
        if not ds: continue
        out.append(f"| {lb} | {'on' if t=='trim' else 'off'} | {f([d['cct'] for d in ds])} | {f([(d['cct']/single4-1)*100 for d in ds])} | {f([d['trims'] for d in ds],'%.0f')} | {f([d['drops'] for d in ds],'%.0f')} | {f([d['rtos'] for d in ds],'%.0f')} | {f([d['rts'] for d in ds],'%.0f')} | {f([d['freeze'] for d in ds],'%.0f')} | {f([d['maxq_fab']/4150 for d in ds],'%.0f')} | {','.join(str(d['fin']) for d in ds)} |")
# ---- R: rto sweep
out.append("\n## B. Fig 7a RTO sweep (no CCA, cwnd 1000 pkt, q 20000, -disable_trim, 432 hosts, permutation)\n")
out.append("| LB | size MB | seed | min_rto us (effective) | CCT us | CCT inc % | RTOs | freeze_entries | freeze_us | ev_explore | drops | max fabric queue (KB) | max E>H queue (KB) | flows |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
csvrows = []
for tag in sorted(runs, key=lambda t: (t.split("_")[2:3], t)):
    m = re.match(r"r_(\w+)_(\d+)mb_rto(\d+)_s(\d+)$", tag)
    if not m: continue
    lb, mb, r, s = m[1], int(m[2]), int(m[3]), int(m[4]); d = runs[tag]; sg = runs.get(f"single_{mb}mb", {}).get("cct", float("nan"))
    inc = (d["cct"] / sg - 1) * 100
    csvrows.append(dict(lb=lb, mb=mb, rto_flag=r, seed=s, min_rto_us=d["min_rto"], cct=d["cct"], single=sg, inc=inc, rtos=d["rtos"], freeze=d["freeze"], freeze_us=d["freeze_us"], explore=d["explore"], drops=d["drops"], maxq_fab_kb=d["maxq_fab"] / 1000, maxq_EH_kb=d["q"]["E->H"] / 1000, fin=d["fin"], rc=d["rc"]))
for c in sorted(csvrows, key=lambda c: (c["mb"], c["lb"], -c["min_rto_us"], c["seed"])):
    part = c["rc"] != "0"   # killed run (no TSV): CCT = latest finish seen among finished flows, counters from finished flows only
    cc = (">=%.0f (killed)" % c["cct"]) if part else "%.2f" % c["cct"]; ic = (">=%.0f" % c["inc"]) if part else "%.2f" % c["inc"]
    qf = "n/a" if part else "%.0f" % c["maxq_fab_kb"]; qe = "n/a" if part else "%.0f" % c["maxq_EH_kb"]
    out.append(f"| {c['lb']} | {c['mb']} | {c['seed']} | {c['min_rto_us']:.1f} | {cc} | {ic} | {c['rtos']} | {c['freeze']} | {c['freeze_us']} | {c['explore']} | {c['drops']} | {qf} | {qe} | {c['fin']} |")
if csvrows:
    with open(os.path.join(T, "e5_rto_runs.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(csvrows[0])); w.writeheader(); w.writerows(csvrows)
out.append("\nSingle-flow bounds: " + ", ".join(f"{k}={v['cct']:.3f} us" for k, v in sorted(runs.items()) if k.startswith("single_")))
open(os.path.join(T, "e5_summary.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print("\n".join(out))

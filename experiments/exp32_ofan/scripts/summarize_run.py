#!/usr/bin/env python3
"""One-line-per-run summary of an htsim_uec stdout (+ optional -log_queue_stats TSV).
usage: summarize_run.py <label> <run.out> [qs.tsv] [ideal_pkts_per_flow]
Prints TSV row: label n_fin n_expected CCT_us mean_fct p99_fct trims drops extra_pkts rts rtos fast_loss ecn_acks abort"""
import re, sys, csv
label, out = sys.argv[1], sys.argv[2]
qs = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
txt = open(out, errors="replace").read()
fin = re.findall(r"finished at ([\d.]+) flowSize (\d+) total packets (\d+) RTS (\d+).*?rtos (\d+).*?ecn_acks (\d+).*?fast_loss (\d+)", txt)
# flow line order in file: "ecn_acks" precedes "rtos"; parse fields by name instead
rows = []
for l in txt.splitlines():
    if "finished at" not in l: continue
    d = dict(re.findall(r"(\w+) ([\d.]+)", l.split("finished at")[1]))
    rows.append(d)
nstart = len(re.findall(r"starting at", txt))
fct = sorted(float(r["flowSize"] and re.match(r"[\d.]+", l).group(0)) if False else 0 for r in rows)  # placeholder
fcts = []
for l in txt.splitlines():
    m = re.search(r"finished at ([\d.]+)", l)
    if m: fcts.append(float(m.group(1)))
fcts.sort()
n = len(fcts)
p99 = fcts[min(n-1, int(0.99*n))] if n else float("nan")
mean = sum(fcts)/n if n else float("nan")
ideal = int(sys.argv[4]) if len(sys.argv) > 4 else 0
pk = sum(int(r["packets"]) for r in rows) if rows and "packets" in rows[0] else 0
# 'total packets N' parses as ('total',...)? fall back to regex
pk = sum(int(x) for x in re.findall(r"total packets (\d+)", txt))
trims = drops = 0
if qs:
    for r in csv.DictReader(open(qs), delimiter="\t"):
        trims += int(r["trims"]); drops += int(r["drops"])
S = lambda k: sum(int(float(r.get(k, 0))) for r in rows)
abort = "ABORT" if re.search(r"abort|Aborted|Assertion|epsn > expected|Segmentation|terminate", txt, re.I) else "-"
extra = pk - ideal*n if ideal else pk
print("\t".join(str(x) for x in [label, n, nstart, "%.2f" % (fcts[-1] if n else float('nan')),
      "%.2f" % mean, "%.2f" % p99, trims, drops, extra, S("RTS"), S("rtos"), S("fast_loss"), S("ecn_acks"), abort]))

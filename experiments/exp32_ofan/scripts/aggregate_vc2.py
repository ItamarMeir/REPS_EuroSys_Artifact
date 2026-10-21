#!/usr/bin/env python3
"""V-C part 2 (paper Fig 17): max queue over ALL switch queues per run; ratio DRB-variant / Ofan per seed, mean +- SEM; ratio of means too."""
import csv, glob, os, re, statistics as st, collections
D = os.path.join(os.environ.get("VCDIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "vc"), "runs2")
mx = collections.defaultdict(dict); mx_fab = collections.defaultdict(dict)
for p in glob.glob(D + "/*_n*_s*.tsv"):
    m = re.match(r"(.+)_n(\d+)_s(\d+)\.tsv", os.path.basename(p)); s, n, seed = m.group(1), int(m.group(2)), int(m.group(3))
    rows = list(csv.DictReader(open(p), delimiter="\t"))
    mx[(s, n)][seed] = max(int(r["max_q_bytes"]) for r in rows)
    mx_fab[(s, n)][seed] = max(int(r["max_q_bytes"]) for r in rows if r["layer"] != "E->H")
def ms(x): return (st.mean(x), st.stdev(x) / len(x) ** .5 if len(x) > 1 else 0.0)
sizes = sorted({n for (_, n) in mx}); variants = sorted({s for (s, _) in mx if s != "ofan"})
for v in variants:
    print("\n### %s / ofan" % v); print("| hosts | n seeds | max q ofan (pkts) | max q %s (pkts) | ratio per seed (mean +- SEM) | ratio of means |\n|---|---|---|---|---|---|" % v)
    for n in sizes:
        a, b = mx.get(("ofan", n), {}), mx.get((v, n), {}); ks = sorted(set(a) & set(b))
        if not ks: continue
        r = [b[k] / a[k] for k in ks]
        print("| %d | %d | %.1f | %.1f | %.2f +- %.2f | %.2f |" % (n, len(ks), st.mean(a[k] for k in ks) / 4160, st.mean(b[k] for k in ks) / 4160, *ms(r), st.mean(b[k] for k in ks) / st.mean(a[k] for k in ks)))

#!/usr/bin/env python3
"""Predicted per-link load for the 54-host k=6 fat-tree with Agg0<->Core0 of pod 0 dead (both directions).
Compares (a) equal share per live port (current Ofan) and (b) equal share per valid path (weighted).
Topology (verified: pod p agg g uplink l -> core l*3+g; core c -> agg c%3 of every pod).
Usage: predict_link_load.py <workload.cm> [bytes_per_flow]"""
import re, sys, collections
cm = sys.argv[1]; B = float(sys.argv[2]) if len(sys.argv) > 2 else 4260032.0  # healthy mean bytes/link incl headers
flows = [(int(a), int(b)) for a, b in (re.match(r'(\d+)->(\d+)', l).groups() for l in open(cm) if '->' in l)]
P, A, C = 6, 3, 9
pod = lambda h: h // 9
tor = lambda h: h // 3
DEAD = {('up', 0, 0, 0), ('dn', 0, 0, 0)}   # (dir, pod, agg, core)
def up_ok(p, g, c): return ('up', p, g, c) not in DEAD
def dn_ok(p, g, c): return ('dn', p, g, c) not in DEAD
def run(weighted):
    L = collections.defaultdict(float)
    for s, d in flows:
        p, q = pod(s), pod(d)
        assert p != q
        cores = {k: [c for c in range(C) if c % A == k and up_ok(p, k, c) and dn_ok(q, k, c)] for k in range(A)}
        ws = {k: (len(cores[k]) if weighted else (1 if cores[k] else 0)) for k in range(A)}
        W = sum(ws.values())
        for k in range(A):
            if not ws[k]: continue
            f = B * ws[k] / W
            L[('E>A', tor(s), k)] += f
            for c in cores[k]:
                L[('A>C', p, k, c)] += f / len(cores[k])
                L[('C>A', c, q, k)] += f / len(cores[k])
            L[('A>E', q, k, tor(d))] += f
    return L
for name, w in (('equal-per-port (current Ofan)', False), ('equal-per-valid-path (weighted)', True)):
    L = run(w); ac = [v for k, v in L.items() if k[0] in ('A>C', 'C>A')]
    mx = max(ac)
    print('%-34s max core-link %.0f B = %.3fx healthy-mean ; predicted CCT ~ %.1f us (84*ratio + 14.5 overhead)' % (name, mx, mx / B, 84 * mx / B + 14.5))
    top = sorted(((v, k) for k, v in L.items() if k[0] in ('A>C', 'C>A')), reverse=True)[:4]
    print('   hottest:', [(k, round(v / B, 3)) for v, k in top])

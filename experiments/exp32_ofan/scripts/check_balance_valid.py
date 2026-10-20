#!/usr/bin/env python3
"""G4 gate (balance under a static Agg0<->Core0 failure, -routing_convergence_us 0, failure at t=0.01us).
usage: check_balance_valid.py <ofan_counts.tsv> [agg=0 core=0 tors_per_pod=3 aggs_per_pod=3]

Part A (Ofan, -log_ofan_counts): per (switch, destination key d (ToR id at a ToR, POD id at an Agg), type t) packet counts over the ports VALID for that key
must differ by <= 1. Valid ports are determined two ways:
  empirical : ports ever used by ANY packet of key (switch,d) (all types/classes);
  analytic  : uplinks from the fat-tree structure (core of agg g uplink l = l*A + g%A; a core c reaches pod Q only through
              agg Q*A + c%A, so with the dead link (agg,core) core `core` cannot reach agg's pod through other aggs).
Asserts: no packet to the dead port; empirical == analytic valid set for every key; max spread over valid ports <= 1.
(Core/down ports are not Ofan-owned and have no counts; the dead C->A direction is covered by link_overload_valid.py / S7 queue stats.)"""
import csv, sys, re, collections
f = sys.argv[1]
dagg = int(sys.argv[2]) if len(sys.argv) > 2 else 0
dcore = int(sys.argv[3]) if len(sys.argv) > 3 else 0
T = int(sys.argv[4]) if len(sys.argv) > 4 else 3
A = int(sys.argv[5]) if len(sys.argv) > 5 else 3
dead_port = "US%d->CS%d" % (dagg, dcore)
per = collections.defaultdict(lambda: collections.defaultdict(int))   # (sw,d,t) -> port -> count
used = collections.defaultdict(set)                                    # (sw,d) -> ports
dead_hits = 0
for r in csv.DictReader(open(f), delimiter="\t"):
    m = re.search(r"(LS\d+->US\d+|US\d+->CS\d+)", r["port"]); p = m.group(1); c = int(r["count"])
    per[(r["switch"], int(r["d"]), r["t"])][p] += c; used[(r["switch"], int(r["d"]))].add(p)
    if p == dead_port and r["switch"] == "Switch_UpperPod_%d" % dagg: dead_hits += c
def analytic(sw, d):
    g = int(sw.rsplit("_", 1)[1])
    if sw.startswith("Switch_UpperPod"):
        Q = d                                           # AGG key d = destination POD (HOST_POD)
        if g // A == Q: return None                         # same pod: goes down, not an Ofan up decision
        ports = set()
        for l in range(A):
            c = l * A + g % A
            if g == dagg and c == dcore: continue            # own dead uplink
            if c == dcore and Q * A + c % A == dagg: continue  # core cannot reach dest pod (its only dest agg link is dead)
            ports.add("US%d->CS%d" % (g, c))
        return ports
    else:
        Q = d // T                                      # ToR key d = destination ToR (HOST_POD_SWITCH)
        if g // T == Q: return None
        return {"LS%d->US%d" % (g, (g // T) * A + k) for k in range(A)}
bad = 0; bad_set = 0; worst = 0; nkeys = 0; sizes = collections.Counter()
for (sw, d, t), pc in sorted(per.items()):
    emp = used[(sw, d)]; ana = analytic(sw, d)
    if ana is None: continue
    nkeys += 1; sizes[(sw.rsplit("_", 1)[0], len(emp))] += 1
    if emp != ana:
        bad_set += 1; print("VALIDSET-MISMATCH", sw, "d=%d" % d, "empirical", sorted(emp), "analytic", sorted(ana)); continue
    cnt = [pc.get(p, 0) for p in ana]; sp = max(cnt) - min(cnt); worst = max(worst, sp)
    if sp > 1: bad += 1; print("IMBALANCE", sw, "d=%d t=%s" % (d, t), dict(pc))
print("keys checked (switch,d,t) with an up decision:", nkeys, "| valid-set size histogram (switch type, #ports):", dict(sizes))
print("packets to dead port %s: %d" % (dead_port, dead_hits))
print("max spread over valid ports: %d | keys spread>1: %d | valid-set mismatches: %d" % (worst, bad, bad_set))
ok = dead_hits == 0 and bad == 0 and bad_set == 0 and nkeys > 0
print("G4 balance", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)

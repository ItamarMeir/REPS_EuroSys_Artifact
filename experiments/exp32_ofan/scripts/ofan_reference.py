#!/usr/bin/env python3
"""Independent reference model for Ofan (arXiv 2610.07230, Sec. 4 + App. F.1/F.2).

Written from the paper text/equations (16)-(18) only; it does NOT share code
with htsim's ofan_order.h / fat_tree_switch.cpp.  It replays a decision trace
produced by `htsim_uec ... -strat ofan -log_ofan_trace <tsv>` and checks each
decision against the specification.

Trace (TAB separated; node names contain commas):
  P <w> <p0,p1,...,p(w-1)>                       shared permutation for w
  I <switch> <TOR|AGG> <swid> <d> <t> <init_ptr>  initial pointer of (switch,key d,t)
  D <time_ps> <switch> <TOR|AGG> <swid> <pkttype> <size> <dst> <d> <Nd> <t> <w> <ptr> <slot> <queue>
Lines starting with '#' are ignored.

Checks per decision D:
  (a) key: TOR d=dst//hosts_per_tor, Nd=ceil(nodes/hosts_per_tor);
           AGG d=dst//hosts_per_pod, Nd=#pods
  (b) t = 0 for a data packet, else 1 (size-quantization noted informationally)
  (c) id=d+Nd*t; b=ceil(log2 w); id1=id mod 2^b; id2=id>>b;
      slot=(xor_w(P[ptr],id1)+id2) mod w, xor_w(v,x)=v^x if v^x<w else v
      (identity mode: slot = ptr, no xor/add)
  (d) pointer advances by exactly 1 mod w between consecutive decisions of the same (switch,key,t)
      and equals the init pointer at the first decision
  (e) ACK init ptr = (data init ptr + w//2) mod w
  (f) any w consecutive decisions of one (switch,key,t) hit every slot once
  (g) slot->queue is a fixed bijection per switch
In --ack-mode hash the t=1 (ACK) pointer checks (c),(d),(e),(f) are skipped
(ACKs are not pointer driven); (a),(b),(g) still apply.
"""
import sys, math, argparse, copy
from collections import defaultdict


def xor_w(v, x, w):
    r = v ^ x
    return r if r < w else v


def expected_slot(P, ptr, d, Nd, t, w):
    ident = d + Nd * t
    b = math.ceil(math.log2(w)) if w > 1 else 0
    id1 = ident % (1 << b)
    id2 = ident >> b
    return (xor_w(P[ptr], id1, w) + id2) % w


def parse(lines):
    perms, inits, decs = {}, {}, []
    for ln in lines:
        ln = ln.rstrip("\n")
        if not ln or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if f[0] == "P":
            perms[int(f[1])] = [int(x) for x in f[2].split(",")]
        elif f[0] == "I":
            inits[(f[1], int(f[4]), int(f[5]))] = int(f[6])
        elif f[0] == "D":
            decs.append(dict(time=int(f[1]), sw=f[2], typ=f[3], swid=int(f[4]), ptype=f[5],
                             size=int(f[6]), dst=int(f[7]), d=int(f[8]), Nd=int(f[9]),
                             t=int(f[10]), w=int(f[11]), ptr=int(f[12]), slot=int(f[13]),
                             queue=f[14]))
    return perms, inits, decs


INFO = {}


def check(lines, hosts_per_tor, nodes, hosts_per_pod, pods, full_size,
          ack_mode="ptr", identity=False, max_report=10):
    perms, inits, decs = parse(lines)
    viol = []
    info = INFO

    def v(kind, msg):
        viol.append((kind, msg))

    for w, P in perms.items():
        if sorted(P) != list(range(w)):
            v("perm", "P for w=%d is not a permutation" % w)

    nd_tor = -(-nodes // hosts_per_tor)
    last_ptr = {}
    hist = defaultdict(list)
    s2q, q2s = defaultdict(dict), defaultdict(dict)
    n = 0
    info["short_data"] = 0
    for k, r in enumerate(decs):
        n += 1
        tag = "dec#%d t=%d %s" % (k, r["time"], r["sw"])
        # (a) key
        if r["typ"] == "TOR":
            d_e, nd_e = r["dst"] // hosts_per_tor, nd_tor
        else:
            d_e, nd_e = r["dst"] // hosts_per_pod, pods
        if r["d"] != d_e or r["Nd"] != nd_e:
            v("key", "%s: d,Nd=(%d,%d) expected (%d,%d)" % (tag, r["d"], r["Nd"], d_e, nd_e))
        # (b) t
        # paper: t distinguishes data from acknowledgements (+ size quantization, 2 groups)
        t_e = 0 if r["ptype"] == "DATA" else 1
        if r["ptype"] == "DATA" and r["size"] != full_size:
            info["short_data"] += 1
        if r["t"] != t_e:
            v("t", "%s: t=%d expected %d (type %s size %d)" % (tag, r["t"], t_e, r["ptype"], r["size"]))
        w = r["w"]
        key = (r["sw"], d_e, r["t"])
        hash_ack = (ack_mode == "hash" and r["t"] == 1)
        # (g) bijection
        if r["slot"] in s2q[r["sw"]] and s2q[r["sw"]][r["slot"]] != r["queue"]:
            v("map", "%s: slot %d -> %s but earlier %s" % (tag, r["slot"], r["queue"], s2q[r["sw"]][r["slot"]]))
        if r["queue"] in q2s[r["sw"]] and q2s[r["sw"]][r["queue"]] != r["slot"]:
            v("map", "%s: queue %s slot %d but earlier slot %d" % (tag, r["queue"], r["slot"], q2s[r["sw"]][r["queue"]]))
        s2q[r["sw"]].setdefault(r["slot"], r["queue"])
        q2s[r["sw"]].setdefault(r["queue"], r["slot"])
        if hash_ack:
            continue
        # (c)
        P = perms.get(w)
        if P is None:
            v("perm", "%s: no permutation for w=%d" % (tag, w))
            continue
        if not (0 <= r["ptr"] < w):
            v("ptr", "%s: ptr %d out of range" % (tag, r["ptr"]))
            continue
        # use trace's own (d,Nd) as the id inputs only after (a) validated them; use expected ones
        e = r["ptr"] if identity else expected_slot(P, r["ptr"], d_e, nd_e, r["t"], w)
        if r["slot"] != e:
            v("slot", "%s: slot=%d expected %d (ptr=%d d=%d Nd=%d t=%d w=%d)" % (tag, r["slot"], e, r["ptr"], d_e, nd_e, r["t"], w))
        # (d)
        if key in last_ptr:
            if r["ptr"] != (last_ptr[key] + 1) % w:
                v("advance", "%s: key %s ptr %d after %d (expected %d)" % (tag, key, r["ptr"], last_ptr[key], (last_ptr[key] + 1) % w))
        else:
            ini = inits.get(key)
            if ini is None:
                v("init", "%s: no init record for %s" % (tag, key))
            elif ini != r["ptr"]:
                v("init", "%s: first ptr %d != init %d" % (tag, r["ptr"], ini))
        last_ptr[key] = r["ptr"]
        hist[key].append((r["slot"], w))
    # (e) ack init
    if True:
        for (sw, d, t), ini in inits.items():
            if t == 1 and (sw, d, 0) in inits:
                # need w: take from any decision of that switch
                ws = {r["w"] for r in decs if r["sw"] == sw}
                for w in ws:
                    if ini != (inits[(sw, d, 0)] + w // 2) % w:
                        v("ackinit", "%s key %d: ack init %d != (%d + %d//2) mod %d" % (sw, d, ini, inits[(sw, d, 0)], w, w))
    # (f) windows
    for key, h in hist.items():
        w = h[0][1]
        slots = [s for s, _ in h]
        for i in range(0, len(slots) - w + 1):
            if len(set(slots[i:i + w])) != w:
                v("window", "key %s window starting at decision %d is not a permutation: %s" % (key, i, slots[i:i + w]))
                break
    return n, viol


def selftest(lines, args):
    n, base = check(lines, **args)
    assert not base, "self-test needs a clean trace, got %d violations" % len(base)
    perms, inits, decs = parse(lines)
    idxs = [i for i, ln in enumerate(lines) if ln.startswith("D\t")]
    # pick a data decision with w>2 and several later decisions of the same key
    def mutate(fn, expect, name):
        L = list(lines)
        for i in idxs:
            f = L[i].split("\t")
            if fn(f):
                L[i] = "\t".join(f)
                _, vs = check(L, **args)
                kinds = {k for k, _ in vs}
                assert expect & kinds, "self-test '%s' not detected (got %s)" % (name, kinds)
                print("  selftest ok: %-18s -> flagged %s" % (name, sorted(kinds)))
                return
        print("  selftest SKIPPED (no site): %s" % name)

    def wrong_xor(f):  # change slot by 1 (different xor result)
        w = int(f[11]); f[13] = str((int(f[13]) + 1) % w); return w > 1
    def wrong_id2(f):  # pretend a different d (changes id2)
        f[8] = str(int(f[8]) + 1); return True
    def skipped_ptr(f):
        w = int(f[11]); f[12] = str((int(f[12]) + 1) % w); return w > 1
    def swapped_t(f):
        f[10] = str(1 - int(f[10])); return True
    mutate(wrong_xor, {"slot", "window"}, "wrong xor/slot")
    mutate(wrong_id2, {"key", "slot"}, "wrong id/d")
    mutate(skipped_ptr, {"advance", "slot"}, "skipped pointer")
    mutate(swapped_t, {"t", "slot", "advance", "init"}, "swapped t")
    # swapped queue mapping
    L = list(lines)
    seen = {}
    for i in idxs:
        f = L[i].split("\t")
        if f[2] in seen and seen[f[2]][0] != f[13]:
            pass
        seen.setdefault(f[2], (f[13], f[14], i))
    for i in idxs:
        f = L[i].split("\t")
        o = seen[f[2]]
        if f[13] == o[0] and i != o[2]:
            f[14] = f[14] + "_X"
            L[i] = "\t".join(f)
            _, vs = check(L, **args)
            assert any(k == "map" for k, _ in vs), "map corruption not detected"
            print("  selftest ok: %-18s -> flagged map" % "queue-map swap")
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--hosts-per-tor", type=int, required=True)
    ap.add_argument("--nodes", type=int, required=True)
    ap.add_argument("--hosts-per-pod", type=int, required=True)
    ap.add_argument("--pods", type=int, required=True)
    ap.add_argument("--full-size", type=int, required=True, help="full data packet size in bytes (as in trace)")
    ap.add_argument("--ack-mode", default="ptr", choices=["ptr", "hash"])
    ap.add_argument("--identity", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    with open(a.trace) as fh:
        lines = fh.read().split("\n")
    args = dict(hosts_per_tor=a.hosts_per_tor, nodes=a.nodes, hosts_per_pod=a.hosts_per_pod,
                pods=a.pods, full_size=a.full_size, ack_mode=a.ack_mode, identity=a.identity)
    n, viol = check(lines, **args)
    print("decisions checked: %d   violations: %d   (DATA packets with size != --full-size: %d)" % (n, len(viol), INFO.get("short_data", 0)))
    for k, m in viol[:15]:
        print("  VIOLATION[%s] %s" % (k, m))
    if a.selftest:
        selftest(lines, args)
    sys.exit(1 if viol else 0)


if __name__ == "__main__":
    main()

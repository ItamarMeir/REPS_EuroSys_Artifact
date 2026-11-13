#!/usr/bin/env python3
"""Smoke tests with obvious answers for [ADDED: reps-draw-weights] (run in the container).
Cell: ONE connection host 0 -> 256, 4 x 4 MiB (cfg h512_p16_sol_lat1000 with the sweep's 5/95 degrade file), SRv6 over 16 paths, REPS freezing with B = 2 (a minority of the sends are random draws: 188-347 of about 4100 over 3 seeds; the rest recycle), 3 seeds.
The EV of every `random` send of the traced flows is classified: even EV = 5% uplink (20G), odd EV = 95% uplink (380G).
Expected before running (uniform = vanilla): 50% of the random draws on the 5% class; capacity weights 20:380 give 8 x 20 / (8 x 20 + 8 x 380) = 5%; inverted capacity 95%; list 1,0,1,0,... 100%; list 0,1,0,1,... 0%;
uniform list, host not selected, scope explore (no explore draws exist), healthy fabric: byte-identical flow-finish lines to the baseline binary.
usage: python draw_smoke.py <baseline binary> <new binary>"""
import csv, gzip, math, os, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/kneework16")
import run_knee16 as rk
r = rk.r
OLD, NEW = sys.argv[1], sys.argv[2]
DC = r.m4.DC
csv.field_size_limit(10 ** 8)


def cell(seed, healthy=False, nosrv6=False):
    c = dict(rk.CFGS["h512_p16_sol_lat1000"])
    c["degrade"] = "/work/knee16/degrade_h512_p16.txt"          # 5/95 as in the sweep
    f = r.flags(c, 2, seed)
    if healthy:
        i = f.index("-degrade_links_file"); del f[i:i + 2]
    if nosrv6:
        f.remove("-use_srv6")
    return f


def run(binary, extra, seed=42, healthy=False, nosrv6=False, trace=True):
    f = cell(seed, healthy, nosrv6)
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    qs = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    cmd = [binary] + f + extra + ["-log_queue_stats", qs]
    if trace:
        cmd += ["-log_reps_events", tr] + sum([["-log_reps_events_src", str(s)] for s in (0, 512, 1024, 1536)], [])
    p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True, timeout=1800)
    return p, tr, qs


def fin(p):
    return [l for l in p.stdout.splitlines() if "finished at" in l]


def draws(tr):
    cnt = [0] * 16
    with open(tr) as fh:
        for row in csv.DictReader(fh):
            if row["event"] in ("SEND", "RTX") and row["ev_src"] == "random":
                cnt[int(row["ev"]) % 16] += 1
    return cnt


def uplink_data(qs):
    d = {}
    with open(qs) as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["layer"] == "E->A" and row["i"] == "0":
                d[int(row["j"])] = int(row["data_pkts"]) + int(row["trims"])
    return [d[j] for j in range(16)]


def share_test(name, extra, p_exp, exact=False):
    tot = [0] * 16
    up = [0] * 16
    for seed in (42, 43, 44):
        p, tr, qs = run(NEW, extra, seed)
        c = draws(tr)
        tot = [a + b for a, b in zip(tot, c)]
        up = [a + b for a, b in zip(up, uplink_data(qs))]
        os.remove(tr); os.remove(qs)
    n = sum(tot); bad = sum(tot[0::2]); obs = bad / n
    z = (obs - p_exp) / math.sqrt(max(p_exp * (1 - p_exp), 1e-12) / n) if not exact else (0 if obs == p_exp else 99)
    ok = abs(z) < 4
    print(f"{'PASS' if ok else 'FAIL'}  {name:46s} draws {n:6d}  share on 5% class {obs:.4f}  expected {p_exp:.4f}  z {z:+.2f}  per-EV {tot}  uplink sends {up}")
    return ok, tot


def same_as_baseline(name, extra, **kw):
    a, tra, qa = run(OLD, [], trace=False, **kw)
    b, trb, qb = run(NEW, extra, trace=False, **kw)
    ok = fin(a) == fin(b) and len(fin(a)) > 0
    print(f"{'PASS' if ok else 'FAIL'}  {name:46s} {len(fin(a))} flow-finish lines {'identical' if ok else 'DIFFERENT'} to the baseline binary")
    return ok


def must_fail(name, extra, **kw):
    p, tr, qs = run(NEW, extra, trace=False, **kw)
    ok = p.returncode != 0
    print(f"{'PASS' if ok else 'FAIL'}  {name:46s} exit {p.returncode} {(p.stderr or p.stdout).strip().splitlines()[-1][:110] if (p.stderr or p.stdout).strip() else ''}")
    return ok


allok = True
print("--- Tier 1: byte identity")
allok &= same_as_baseline("flags absent", [])
allok &= same_as_baseline("uniform list (16 x 1)", ["-reps_draw_weights", ",".join(["1"] * 16)])
allok &= same_as_baseline("capacity, healthy fabric (all speeds equal)", ["-reps_draw_weights", "capacity"], healthy=True)
allok &= same_as_baseline("capacity, host 5 selected (flow is host 0)", ["-reps_draw_weights", "capacity", "-reps_draw_hosts", "5"])
allok &= same_as_baseline("capacity, scope explore (no explore draws)", ["-reps_draw_weights", "capacity", "-reps_draw_scope", "explore"])
print("--- Tier 2b: draw distribution (random sends of the flow, 3 seeds pooled)")
ok0, _ = share_test("baseline-like: no flag (uniform)", [], 0.5); allok &= ok0
allok &= share_test("capacity (expect 5%)", ["-reps_draw_weights", "capacity"], 0.05)[0]
ok, tot = share_test("capacity, per-EV frequencies", ["-reps_draw_weights", "capacity"], 0.05)
n = sum(tot); pe = [20 / 3200 if e % 2 == 0 else 380 / 3200 for e in range(16)]
chi = sum((tot[e] - n * pe[e] / sum(pe)) ** 2 / (n * pe[e] / sum(pe)) for e in range(16))
print(f"{'PASS' if chi < 37.70 else 'FAIL'}  chi-square of per-EV counts vs capacity weights: {chi:.2f} (15 dof, 0.001 critical 37.70)"); allok &= chi < 37.70
allok &= share_test("capacity inverted (expect 95%)", ["-reps_draw_weights", "capacity", "-reps_draw_invert"], 0.95)[0]
allok &= share_test("list 1,0,1,0.. (expect 100%)", ["-reps_draw_weights", ",".join(["1", "0"] * 8)], 1.0, exact=True)[0]
allok &= share_test("list 0,1,0,1.. (expect 0%)", ["-reps_draw_weights", ",".join(["0", "1"] * 8)], 0.0, exact=True)[0]
allok &= share_test("capacity, hosts 0 selected (expect 5%)", ["-reps_draw_weights", "capacity", "-reps_draw_hosts", "0-15"], 0.05)[0]
allok &= share_test("capacity, scope both (expect 5%)", ["-reps_draw_weights", "capacity", "-reps_draw_scope", "both"], 0.05)[0]
print("--- hard errors at startup")
allok &= must_fail("hosts without weights", ["-reps_draw_hosts", "0"])
allok &= must_fail("invert without weights", ["-reps_draw_invert"])
allok &= must_fail("list of wrong length", ["-reps_draw_weights", "1,2,3"])
allok &= must_fail("list with zero sum", ["-reps_draw_weights", ",".join(["0"] * 16)])
allok &= must_fail("capacity without -use_srv6", ["-reps_draw_weights", "capacity"], nosrv6=True)
allok &= must_fail("bad scope", ["-reps_draw_weights", "capacity", "-reps_draw_scope", "x"])
allok &= must_fail("non-numeric list", ["-reps_draw_weights", "a,b"])
print("ALL PASS" if allok else "SOME FAILED")

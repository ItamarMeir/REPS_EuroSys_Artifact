#!/usr/bin/env python3
"""Verification + validation of [ADDED: dps] (Distribution Packet Spraying), run in the container
(scripts/setup_dps_container.sh lays out /build/htsim_main/sim/datacenter and /kneework16 from a bind-mounted repo).

Cell (small, answers derivable from the definitions): ONE connection host 0 -> 256, 4 x 4 MiB (cfg h512_p16_sol_lat1000 with the sweep's 5/95
degrade file), SRv6 over 16 paths: EV e -> ToR0 uplink e % 16, even = 5% link (20G), odd = 95% link (380G), 200G constant-rate sender.
Expected BEFORE running (written here, compared by the script):
  T1  flag absent / REPS / god cells: flow-finish lines byte-identical to the baseline binary (.baseline/htsim_uec.pre-dps); DPS deterministic.
  T2  DPS with a manual uniform distribution == OPS (-load_balancing_algo oblivious): identical flow-finish lines AND identical EV sequence of the
      traced flows, for `uniform`, `list 1,..,1`, `list 7,..,7`. NEG: `list` with one weight 1 -> 2 must differ (the test can fail).
  T2b share of sends on the 5% class (even EVs): uniform 50%; capacity 8x20 / (8x20 + 8x380) = 5%; list 1,0,1,0.. 100% exactly; list 0,1,0,1.. 0% exactly;
      list with all mass on EV 5: every send on EV 5 and uplink 5 carries every data packet. Per-EV chi-square vs an INDEPENDENT python pmf for
      capacity, zipf, poisson, normal, geometric, binomial. The pmf printed by the simulator equals the python pmf (6 significant digits).
      -dps_perm: printed pmf is a permutation of the unpermuted pmf, differs from it, counts fit the printed pmf.
  T3  identity: sends per ev % 16 == data + trims + drops of ToR0 uplink j (all 16 j), exact. B-invariance: DPS flow-finish lines identical for B = 2, 8, 64.
  T5  memorylessness on the loaded cell (512 hosts, 2048 flows): share of sends on even EVs does not depend on the last feedback seen by the source
      (ECN ACK / clean ACK / NACK) for DPS-uniform; REPS (freezing) is the positive control and must depend on it.
  hard errors at startup for every invalid combination.
usage (container): python3 dps_smoke.py [--quick]"""
import csv, math, os, re, subprocess, sys, tempfile
sys.path.insert(0, "/kneework16")
import run_knee16 as rk
r = rk.r
DC = r.m4.DC
OLD = "/workspace/.baseline/htsim_uec.pre-dps"
NEW = "/workspace/htsim/sim/datacenter/htsim_uec"
csv.field_size_limit(10 ** 8)
QUICK = "--quick" in sys.argv
N = 16


def set_flag(f, key, *vals):
    i = f.index(key)
    f[i + 1:i + 1 + len(vals)] = [str(v) for v in vals]


def cell(seed=42, B=2, healthy=False, nosrv6=False, cfg="h512_p16_sol_lat1000", algo=None, tm=None):
    c = dict(rk.CFGS[cfg])
    c["degrade"] = "/work/knee16/degrade_h512_p16.txt"
    f = r.flags(c, B, seed)
    f += list(c.get("extra", [])) if cfg != "h512_p16_sol_lat1000" else []
    if algo:
        set_flag(f, "-load_balancing_algo", algo)
    if tm:
        set_flag(f, "-tm", tm)
    if healthy:
        i = f.index("-degrade_links_file"); del f[i:i + 2]
    if nosrv6:
        f.remove("-use_srv6")
    return f


def run(binary, extra, algo=None, trace=True, **kw):
    f = cell(algo=algo, **kw)
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    qs = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    cmd = [binary] + f + extra + ["-log_queue_stats", qs]
    if trace:
        cmd += ["-log_reps_events", tr] + sum([["-log_reps_events_src", str(s)] for s in (0, 1, 2, 3, 512, 1024, 1536)], [])
    p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True, timeout=3600)
    return p, tr, qs


def fin(p):
    return [l for l in p.stdout.splitlines() if "finished at" in l]


def sends(tr, only_dps=False):
    """EV sequence of SEND/RTX rows of the traced flows, and ev_src values seen."""
    seq, srcs = [], set()
    with open(tr) as fh:
        for row in csv.DictReader(fh):
            if row["event"] in ("SEND", "RTX"):
                seq.append((row["src_id"], row["event"], int(row["ev"])))
                srcs.add(row["ev_src"])
    return seq, srcs


def uplinks(qs):
    d = {}
    with open(qs) as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["layer"] == "E->A" and row["i"] == "0":
                d[int(row["j"])] = (int(row["data_pkts"]), int(row["trims"]), int(row["drops"]))
    return [d[j] for j in range(N)]


def clean(*fs):
    for x in fs:
        if os.path.exists(x): os.remove(x)


# ----- independent reference pmfs (python, not the C++ header) -----
def norm(w):
    s = sum(w); return [x / s for x in w]
REF = {
    "zipf":      (["1.2"], lambda: norm([(e + 1) ** -1.2 for e in range(N)])),
    "poisson":   (["4"], lambda: norm([math.exp(-4 + e * math.log(4) - math.lgamma(e + 1)) for e in range(N)])),
    "geometric": (["0.3"], lambda: norm([0.3 * 0.7 ** e for e in range(N)])),
    "binomial":  (["10", "0.3"], lambda: norm([math.comb(10, e) * 0.3 ** e * 0.7 ** (10 - e) if e <= 10 else 0.0 for e in range(N)])),
    "normal":    (["5", "2"], lambda: norm([0.5 * (math.erf((e + .5 - 5) / (2 * math.sqrt(2))) - math.erf((e - .5 - 5) / (2 * math.sqrt(2)))) for e in range(N)])),
}
CAP = norm([20.0 if e % 2 == 0 else 380.0 for e in range(N)])


def chi2(counts, pmf):
    n = sum(counts); chi = 0.0; bins = 0; to = te = 0.0
    for c, p in zip(counts, pmf):
        ex = p * n
        if ex < 5: to += c; te += ex; continue
        chi += (c - ex) ** 2 / ex; bins += 1
    if te >= 5: chi += (to - te) ** 2 / te; bins += 1
    df = bins - 1
    return chi, df, chi < df + 6 * math.sqrt(2 * df) + 10


def printed_pmf(stdout):
    for ln in stdout.splitlines():
        if ln.startswith("dps_dist: src") and " pmf " in ln + " ":
            toks = ln.split(" pmf")[1].split()
            if len(toks) == N: return [float(t) for t in toks]
    return None


allok = True
def report(ok, msg):
    global allok
    allok &= bool(ok)
    print(("PASS  " if ok else "FAIL  ") + msg, flush=True)
    return ok


def dps(spec, **kw):
    return run(NEW, ["-dps_dist"] + spec, algo="dps", **kw)


def pooled_counts(spec, seeds=(42, 43, 44), extra=()):
    tot = [0] * N; up = [[0, 0, 0] for _ in range(N)]; last = None
    for s in seeds:
        p, tr, qs = run(NEW, ["-dps_dist"] + spec + list(extra), algo="dps", seed=s)
        assert p.returncode == 0, p.stderr[-300:]
        seq, srcs = sends(tr)
        assert srcs == {"dps"}, srcs
        for _, _, ev in seq: tot[ev % N] += 1
        for j, u in enumerate(uplinks(qs)): up[j] = [a + b for a, b in zip(up[j], u)]
        last = p
        clean(tr, qs)
    return tot, up, last


print("=== Tier 1: byte identity with the baseline binary (flag absent)")
for name, extra, kw in [("REPS cell, no dps flag", [], {}),
                        ("god cell (-reps_draw_weights capacity)", ["-reps_draw_weights", "capacity"], {}),
                        ("REPS cell, healthy fabric", [], {"healthy": True}),
                        ("oblivious (OPS) cell", [], {"algo": "oblivious"})]:
    a, *_ = run(OLD, extra, trace=False, **kw); b, *_ = run(NEW, extra, trace=False, **kw)
    report(fin(a) == fin(b) and len(fin(a)) == 4, f"{name}: {len(fin(a))} flow-finish lines identical to baseline")
a, *_ = dps(["capacity"], trace=False); b, *_ = dps(["capacity"], trace=False)
report(fin(a) == fin(b) and len(fin(a)) == 4, "DPS capacity deterministic (two identical runs)")

print("=== Tier 2: DPS with a manual uniform distribution == OPS (oblivious)")
o, tro, qo = run(NEW, [], algo="oblivious")
seq_o, _ = sends(tro)
for name, spec in [("uniform", ["uniform"]), ("list 1,1,..,1", ["list", ",".join(["1"] * N)]), ("list 7,7,..,7", ["list", ",".join(["7"] * N)])]:
    p, tr, qs = dps(spec)
    seq, _ = sends(tr)
    report(fin(p) == fin(o) and len(fin(o)) == 4 and [e for *_, e in seq] == [e for *_, e in seq_o] and len(seq) > 1000,
           f"DPS {name}: flow-finish lines AND the EV sequence ({len(seq)} sends) identical to oblivious")
    clean(tr, qs)
w = ["1"] * N; w[3] = "2"
p, tr, qs = dps(["list", ",".join(w)]); seq, _ = sends(tr)
report(fin(p) != fin(o) and [e for *_, e in seq] != [e for *_, e in seq_o], "NEG: DPS list with one weight 1 -> 2 differs from oblivious (the identity test can fail)")
clean(tr, qs, tro, qo)

print("=== Tier 2b: draw distributions on the fabric (3 seeds pooled)")
tot, up, p = pooled_counts(["uniform"]); n = sum(tot); sh = sum(tot[0::2]) / n
report(abs(sh - .5) < 4 * math.sqrt(.25 / n), f"uniform: share on 5% class {sh:.4f}, expected 0.5, n={n}")
tot, up, p = pooled_counts(["capacity"]); n = sum(tot); sh = sum(tot[0::2]) / n
z = (sh - .05) / math.sqrt(.05 * .95 / n)
report(abs(z) < 4, f"capacity: share on 5% class {sh:.4f}, expected 0.0500, z {z:+.2f}, n={n}")
c, df, ok = chi2(tot, CAP); report(ok, f"capacity: per-EV chi-square {c:.1f} (df {df}) vs 20:380 weights; per-EV {tot}")
pm = printed_pmf(p.stdout); report(pm is not None and max(abs(a - b) for a, b in zip(pm, CAP)) < 1e-5, "capacity: pmf printed by the simulator == 20:380 normalised")
tot, up, p = pooled_counts(["list", ",".join(["1", "0"] * 8)]); report(sum(tot[1::2]) == 0 and sum(tot) > 0, f"list 1,0,1,0..: all {sum(tot)} sends on the 5% class (expected 100%)")
tot, up, p = pooled_counts(["list", ",".join(["0", "1"] * 8)]); report(sum(tot[0::2]) == 0 and sum(tot) > 0, f"list 0,1,0,1..: 0 of {sum(tot)} sends on the 5% class (expected 0%)")
one = ["0"] * N; one[5] = "1"
tot, up, p = pooled_counts(["list", ",".join(one)])
report(tot[5] == sum(tot) and up[5][0] + up[5][1] == sum(tot), f"all mass on EV 5: {tot[5]} of {sum(tot)} sends on EV 5, uplink 5 carried {up[5][0]} data + {up[5][1]} trims")
for name, (args, ref) in REF.items():
    tot, up, p = pooled_counts([name] + args)
    pm = printed_pmf(p.stdout); rp = ref()
    report(pm is not None and all(abs(a - b) <= 1e-5 * max(b, 1e-3) + 1e-9 for a, b in zip(pm, rp)), f"{name} {' '.join(args)}: simulator pmf == independent python pmf (6 digits)")
    c, df, ok = chi2(tot, rp); report(ok and sum(1 for i in range(N) if rp[i] == 0 and tot[i]) == 0, f"{name} {' '.join(args)}: per-EV chi-square {c:.1f} (df {df}), n={sum(tot)}")
# permutation
tot, up, p = pooled_counts(["zipf", "1.2"], extra=["-dps_perm", "7"])
pm = printed_pmf(p.stdout); rp = REF["zipf"][1]()
report(pm is not None and sorted(round(x, 5) for x in pm) == sorted(round(x, 5) for x in rp) and pm != rp, "-dps_perm 7: printed pmf is a permutation of zipf(1.2) and differs from it")
c, df, ok = chi2(tot, pm); report(ok, f"-dps_perm 7: per-EV counts fit the printed (permuted) pmf, chi-square {c:.1f} (df {df})")
c2, df2, ok2 = chi2(tot, rp); report(not ok2, f"NEG: the same counts do NOT fit the unpermuted pmf (chi-square {c2:.0f}, df {df2})")

print("=== Tier 3: identities")
tot, up, p = pooled_counts(["capacity"], seeds=(42,))
report(all(tot[j] == sum(up[j]) for j in range(N)), f"sends per ev % 16 == data + trims + drops of ToR0 uplink j, all 16 j (sends {tot}, uplinks {[sum(u) for u in up]})")
txt = p.stdout
report("SRv6 source routing enabled" in txt and re.search(r"distinct_paths=\[?16", txt) is not None and "enable on tor downlink 1" not in txt, "configuration from the output: SRv6 line, distinct_paths 16, no `enable on tor downlink 1`")
report(len(fin(p)) == 4 and all(" rtos 0 " in l for l in fin(p)), "4 flow-finish lines, 0 RTOs")
fins = []
for B in (2, 8, 64):
    p, *_ = dps(["capacity"], trace=False, B=B); fins.append(fin(p))
report(fins[0] == fins[1] == fins[2] and len(fins[0]) == 4, "B-invariance: DPS flow-finish lines identical for -reps_buffer_size 2, 8, 64")
fr = [fin(run(NEW, [], trace=False, B=B)[0]) for B in (2, 64)]
report(fr[0] != fr[1], "NEG: the REPS cell DOES depend on B (2 vs 64), so the B-invariance test can fail")

print("=== hard errors at startup")
def must_fail(name, extra, algo="dps", **kw):
    p, tr, qs = run(NEW, extra, algo=algo, trace=False, **kw); clean(tr, qs)
    msg = ((p.stderr or p.stdout).strip().splitlines() or [""])[-1][:110]
    report(p.returncode != 0, f"{name}: exit {p.returncode} {msg}")
must_fail("dps without -dps_dist", [])
must_fail("-dps_dist with freezing", ["-dps_dist", "uniform"], algo="freezing")
must_fail("-dps_perm with freezing", ["-dps_perm", "1"], algo="freezing")
must_fail("unknown distribution", ["-dps_dist", "bogus"])
must_fail("list of wrong length", ["-dps_dist", "list", "1,2,3"])
must_fail("list with zero sum", ["-dps_dist", "list", ",".join(["0"] * N)])
must_fail("list with a negative weight", ["-dps_dist", "list", ",".join(["1"] * 15 + ["-1"])])
must_fail("list non-numeric", ["-dps_dist", "list", "a,b"])
must_fail("capacity without -use_srv6", ["-dps_dist", "capacity"], nosrv6=True)
must_fail("normal sigma 0", ["-dps_dist", "normal", "5", "0"])
must_fail("poisson without lambda", ["-dps_dist", "poisson"])
must_fail("missing file", ["-dps_dist", "file", "/nonexistent"])

print("=== Tier 6: -dps_dist file, -host_lb_overrides, a source with a single route")
wts = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3]
wf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir="/tmp"); wf.write("\n".join(map(str, wts)) + "\n"); wf.close()
pf, trf, qf = dps(["file", wf.name]); pl, trl, ql = dps(["list", ",".join(map(str, wts))])
sf, _ = sends(trf); sl, _ = sends(trl)
report(fin(pf) == fin(pl) and len(fin(pf)) == 4 and sf == sl and len(sf) > 1000, f"-dps_dist file == -dps_dist list with the same weights: flow-finish lines and EV sequence ({len(sf)} sends) identical")
clean(trf, qf, trl, ql, wf.name)
p, tr, qs = run(NEW, ["-host_lb_overrides", "0:dps", "-dps_dist", "capacity"])      # global freezing, host 0 overridden to dps
seq, srcs = sends(tr)
report(p.returncode == 0 and srcs == {"dps"} and len(seq) > 1000, f"-host_lb_overrides 0:dps under global freezing: every traced send of host 0 has ev_src dps ({len(seq)} sends)")
clean(tr, qs)
p, tr, qs = run(NEW, ["-host_lb_overrides", "5:dps", "-dps_dist", "capacity"]); a, *_ = run(NEW, [], trace=False)
seq, srcs = sends(tr)
report(p.returncode == 0 and "dps" not in srcs and fin(p) == fin(a), "-host_lb_overrides 5:dps (host 0 not overridden): no dps sends, flow-finish lines identical to plain freezing")
clean(tr, qs)
cm = tempfile.NamedTemporaryFile("w", suffix=".cm", delete=False, dir="/tmp"); cm.write("Nodes 512\nConnections 1\n0->1 id 1 start 0 size 4194304\n"); cm.close()
p, tr, qs = run(NEW, ["-dps_dist", "capacity"], algo="dps", tm=cm.name); o, tro, qo = run(NEW, [], algo="oblivious", tm=cm.name)
report(p.returncode == 0 and len(fin(p)) == 1 and fin(p) == fin(o), f"same-ToR pair 0->1, capacity: completes ({len(fin(p))} flow), identical to oblivious (no choice to weight); note: {[l for l in p.stdout.splitlines() if 'nothing to weight' in l][:1]}")
clean(tr, qs, tro, qo, cm.name)

if not QUICK:
    print("=== Tier 5: memorylessness on the loaded cell (512 hosts, 2048 flows, lat 250, 5/95 ToR0)")
    def loaded(algo, extra, B=8):
        f = cell(cfg="h512_p16_msgNh_lat250", B=B, algo=algo) + extra
        tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
        p = subprocess.run([NEW] + f + ["-log_reps_events", tr, "-log_reps_events_max", "50000000"], cwd=DC, capture_output=True, text=True, timeout=7200)
        assert p.returncode == 0, p.stderr[-300:]
        grp = {"ecn_ack": [0, 0], "clean_ack": [0, 0], "nack": [0, 0], "none": [0, 0]}   # [sends, sends on even EV]
        last = {}
        with open(tr) as fh:
            for row in csv.DictReader(fh):
                s = row["src_id"]; ev = row["event"]
                if ev == "ACK": last[s] = "ecn_ack" if row["ecn"] == "1" else "clean_ack"
                elif ev == "NACK": last[s] = "nack"
                elif ev in ("SEND", "RTX") and int(s) % 512 < 16:
                    g = grp[last.get(s, "none")]; g[0] += 1; g[1] += int(row["ev"]) % 2 == 0
        clean(tr)
        return p, grp
    for algo, extra, label in [("dps", ["-dps_dist", "uniform"], "DPS uniform"), ("dps", ["-dps_dist", "capacity"], "DPS capacity"), ("freezing", [], "REPS (positive control)")]:
        p, grp = loaded(algo, extra)
        base = sum(g[1] for g in grp.values()) / sum(g[0] for g in grp.values())
        shares = {k: (g[1] / g[0] if g[0] else float("nan"), g[0]) for k, g in grp.items() if g[0] >= 200}
        print(f"      {label}: share on even EVs by last feedback: " + ", ".join(f"{k} {v[0]:.3f} (n={v[1]})" for k, v in shares.items()) + f"; overall {base:.3f}", flush=True)
        if algo == "dps":
            ok = all(abs(v[0] - base) < 4 * math.sqrt(base * (1 - base) / v[1]) for v in shares.values()) and len(shares) >= 2
            report(ok, f"{label}: share on the 5% class independent of the last feedback (ECN / clean / NACK), 4-sigma binomial")
            report(sum(1 for l in fin(p)) == 2048, f"{label}: 2048 flow-finish lines")
        else:
            spread = max(v[0] for v in shares.values()) - min(v[0] for v in shares.values())
            report(spread > 0.02, f"{label}: share depends on the last feedback (spread {spread:.3f} > 0.02), so the test can detect feedback dependence")

print("ALL PASS" if allok else "SOME FAILED")
sys.exit(0 if allok else 1)

#!/usr/bin/env python3
"""(ofan_weighted variant of rc_check.py: also compares per-entry path counts) G2 gate for -routing_convergence_us: run -routing_check on random failed-pipe sets.

Run INSIDE container ofan-dev:
  docker exec ofan-dev python3 /workspace/experiments/exp32_ofan/scripts/rc_check.py [seed] [sets_per_topo]
Every run must print `ROUTING_CHECK mismatches=0` and `ROUTING_CONV decisions_to_known_dead=0`.
3-tier: failures via -fail_link_time/-fail_link_target (Agg<->Core, both directions).
2-tier: failures via -timed_window / -timed_fail_tor_uplinks / -timed_fail_tor_downlinks.
"""
import random, re, subprocess, sys, tempfile, os

R = "/workspace"
DC = R + "/htsim/sim/datacenter"
TOPO = DC + "/topologies/reps/"
WL = R + "/experiments/exp32_ofan/workloads/"
# name: (topo file, workload, tiers, A=aggs/pod (3t) , NAGG, NCORE)  / 2t: (.., ntors, nspines)
CFGS = {
    "16":  ("fat_tree_16_1os_3t_400g.topo", "derange16_1mb_s42.cm", 3, 2, 8, 4),
    "54":  ("fat_tree_54_1os_3t_400g.topo", "derange54_4mb_s42.cm", 3, 3, 18, 9),
    "128": ("fat_tree_128_1os_3t_400g.topo", "derange128_1mb_s42.cm", 3, 4, 32, 16),
    "32_2t": ("fat_tree_32_1os_2t_400g.topo", "perm32_1mb_s42.cm", 2, 0, 4, 0),
}
STRATS = ["-strat ofan_weighted -load_balancing_algo ecmp"]
GS = ["0", "5", "30", "1000000000"]


def pairs3(A, NAGG, NCORE):
    return [(g, c) for g in range(NAGG) for c in range(NCORE) if c % A == g % A]


def random_set(rng, A, NAGG, NCORE):
    allp = pairs3(A, NAGG, NCORE)
    mode = rng.choice(["rand_small", "rand_big", "agg_isolated", "core_isolated", "pod_cut"])
    if mode == "rand_small":
        s = rng.sample(allp, rng.randint(1, 3))
    elif mode == "rand_big":
        s = rng.sample(allp, max(2, len(allp) * rng.randint(2, 5) // 10))
    elif mode == "agg_isolated":
        g = rng.randrange(NAGG); s = [p for p in allp if p[0] == g]
    elif mode == "core_isolated":
        c = rng.randrange(NCORE); s = [p for p in allp if p[1] == c]
    else:  # all uplinks of every agg of one pod at one core column -> one pod cut from half the cores
        pod = rng.randrange(NAGG // A)
        s = [p for p in allp if p[0] // A == pod and rng.random() < 0.7]
        if not s: s = [allp[0]]
    return mode, s


def run(args, wd):
    p = subprocess.run(args, cwd=wd, capture_output=True, text=True, timeout=1200)
    return p.returncode, p.stdout + p.stderr


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    nsets = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    only = sys.argv[3].split(",") if len(sys.argv) > 3 else list(CFGS)
    rng = random.Random(seed)
    bad = 0; total = 0; nreal_tot = 0
    for name in only:
        topo, wl, tiers, A, NAGG, NCORE = CFGS[name]
        for si in range(nsets):
            if tiers == 3:
                mode, tg = random_set(rng, A, NAGG, NCORE)
                fail = ["-fail_link_time", "10", rng.choice(["90", "1000000000"])]
                for g, c in tg: fail += ["-fail_link_target", str(g), str(c)]
                desc = "%s n=%d" % (mode, len(tg))
            else:
                ntors = 8
                t_up = rng.randrange(ntors); c_up = rng.randint(0, NAGG)
                t_dn = rng.randrange(ntors); c_dn = rng.randint(0, NAGG)
                fail = ["-timed_window", "10", rng.choice(["90", "1000000000"]),
                        "-timed_fail_tor_uplinks", str(t_up), str(c_up),
                        "-timed_fail_tor_downlinks", str(t_dn), str(c_dn)]
                desc = "2t up(tor%d,%d) dn(tor%d,%d)" % (t_up, c_up, t_dn, c_dn)
            for G in GS:
                strat = STRATS[(si + GS.index(G)) % len(STRATS)]
                wd = tempfile.mkdtemp()
                cmd = [DC + "/htsim_uec", "-tm", WL + wl, "-topo", TOPO + topo, "-linkspeed", "400000",
                       "-seed", str(42 + si), "-end", "150", "-connections_mapping", "-sender_cc_only",
                       "-disable_tor_ecn", "-sender_cc_algo", "nscc", "-q", "193", "-ecn", "19", "19"] \
                      + strat.split() + fail + ["-routing_convergence_us", G, "-routing_check"]
                rc, out = run(cmd, wd)
                m = re.search(r"ROUTING_CHECK mismatches=(\d+)", out)
                c = re.search(r"ROUTING_CONV decisions_to_known_dead=(\d+) drops_before_known=(\d+) drops_after_known=(\d+)", out)
                i = re.search(r"ROUTING_CHECK_INFO runs=(\d+) synthetic_pairs=(\d+) real_fib_vectors=(\d+)", out)
                ok = bool(m and c and i) and m.group(1) == "0" and c.group(1) == "0" and rc == 0
                total += 1; bad += (not ok)
                if i: nreal_tot += int(i.group(3))
                print("%-6s %-34s G=%-10s %-22s rc=%d mism=%s dkd=%s drops(b/a)=%s/%s runs=%s synth=%s real=%s %s" % (
                    name, desc, G, strat.split()[1], rc, m and m.group(1), c and c.group(1), c and c.group(2),
                    c and c.group(3), i and i.group(1), i and i.group(2), i and i.group(3), "OK" if ok else "FAIL"))
                if not ok:
                    print("   ---- first output lines with CHECK/ERROR ----")
                    for l in out.splitlines():
                        if "ROUTING" in l or "ERROR" in l or "Assert" in l or "assert" in l:
                            print("   " + l)
                    print("   cmd: " + " ".join(cmd))
                subprocess.run(["rm", "-rf", wd])
    print("TOTAL runs=%d failures=%d real_fib_vector_checks=%d" % (total, bad, nreal_tot))
    sys.exit(1 if bad else 0)


main()

#!/usr/bin/env python3
"""Smoke test of the explore and frozen-mode-empty branches of [ADDED: reps-draw-weights] (run in the container).
Cell as draw_smoke.py (one connection host 0 -> 64, 4 x 4 MiB, 5/95 degrade, SRv6 over 8 paths, B = 2) plus `-fail_src_paths 0 4` (paths 0..3 of source 0 are blackholed at emit: an RTO, so freezing mode, and after
-exit_freeze the thaw sets explore_counter = BDP / MTU explore draws). Labels in the trace: `explore` (explore branch), `random` with frozen_mode 1 (frozen-empty branch), `random` with frozen_mode 0 (normal fallback).
Expected before running: with `capacity` the share of draws on the 5% class (even EV) is 5% for the branches in scope and 50% (uniform) for the others:
  scope fallback -> normal+frozen random 5%, explore 50%;  scope explore -> explore 5%, random 50%;  scope both -> all 5%;  flag absent -> all 50%.
usage: python draw_freeze_smoke.py <new binary> [exit_freeze_ps]"""
import csv, math, os, subprocess, sys, tempfile
sys.path.insert(0, "/kneework16")
import run_knee16 as rk
r = rk.r
NEW = sys.argv[1]
EXIT = sys.argv[2] if len(sys.argv) > 2 else "100000000"
FAILCNT = sys.argv[3] if len(sys.argv) > 3 else "8"      # 16 = every path of source 0 blackholed: the buffer stays empty, so the frozen-mode-empty branch fires
END = ["-end", "400"] if FAILCNT == "16" else []
DC = r.m4.DC
csv.field_size_limit(10 ** 8)


def run(extra, seed):
    c = dict(rk.CFGS["h512_p16_sol_lat1000"]); c["degrade"] = "/work/knee16/degrade_h512_p16.txt"
    f = r.flags(c, 2, seed)
    if "-exit_freeze" in f:
        f[f.index("-exit_freeze") + 1] = EXIT
    else:
        f += ["-exit_freeze", EXIT]
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    cmd = [NEW] + f + ["-fail_src_paths", "0", FAILCNT] + END + extra + ["-log_reps_events", tr] + sum([["-log_reps_events_src", str(s)] for s in (0, 512, 1024, 1536)], [])
    p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True, timeout=1800)
    cls = {"explore": [0, 0], "random_frozen": [0, 0], "random_normal": [0, 0]}
    with open(tr) as fh:
        for row in csv.DictReader(fh):
            if row["event"] in ("SEND", "RTX") and row["ev_src"] in ("explore", "random"):
                k = "explore" if row["ev_src"] == "explore" else ("random_frozen" if row["frozen_mode"] != "0" else "random_normal")
                cls[k][int(row["ev"]) % 2 == 0] += 1                    # [odd, even]
    os.remove(tr)
    return cls, p.stdout.count("started freezing"), [l for l in p.stdout.splitlines() if "finished at" in l]


def pooled(extra):
    tot = {"explore": [0, 0], "random_frozen": [0, 0], "random_normal": [0, 0]}
    fr = 0; fl = 0
    for seed in (42, 43, 44):
        c, f, fin = run(extra, seed)
        fr += f; fl += len(fin)
        for k in tot:
            tot[k][0] += c[k][0]; tot[k][1] += c[k][1]
    return tot, fr, fl


def show(name, extra, exp):
    tot, fr, fl = pooled(extra)
    exp = {k: v for k, v in exp.items() if not ((FAILCNT == "16" and k == "explore") or (FAILCNT != "16" and k == "random_frozen"))}
    ok = True
    parts = []
    for k, p_exp in exp.items():
        n = sum(tot[k]); obs = tot[k][1] / n if n else float("nan")
        z = (obs - p_exp) / math.sqrt(p_exp * (1 - p_exp) / n) if n else float("nan")
        good = (n >= 20 and abs(z) < 4) or (n == 0 and p_exp is None)
        ok &= good
        parts.append(f"{k}: n={n} even-share {obs:.3f} (expected {p_exp:.2f}, z {z:+.2f})")
    print(f"{'PASS' if ok else 'FAIL'}  {name:34s} freeze starts {fr}, flows finished {fl}/12 | " + " | ".join(parts))
    return ok


ok = True
ok &= show("flag absent (uniform)", [], {"explore": .5, "random_frozen": .5, "random_normal": .5})
ok &= show("capacity, scope fallback", ["-reps_draw_weights", "capacity"], {"explore": .5, "random_frozen": .05, "random_normal": .05})
ok &= show("capacity, scope explore", ["-reps_draw_weights", "capacity", "-reps_draw_scope", "explore"], {"explore": .05, "random_frozen": .5, "random_normal": .5})
ok &= show("capacity, scope both", ["-reps_draw_weights", "capacity", "-reps_draw_scope", "both"], {"explore": .05, "random_frozen": .05, "random_normal": .05})
print("ALL PASS" if ok else "SOME FAILED")

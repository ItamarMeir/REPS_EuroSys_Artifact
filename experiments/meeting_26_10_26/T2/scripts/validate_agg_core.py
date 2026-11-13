#!/usr/bin/env python3
"""Tier 1 + Tier 2 checks for `per-link-degrade-agg-core` (agg_core lines in -degrade_links_file). Run inside the container:
  python3 validate_agg_core.py [name ...]    (files next to run_t2.py in /t2work; binaries in /build/baseline)
OLD = htsim_uec.pre-agg-core (clean build of HEAD), NEW = htsim_uec.agg-core (clean build with the change).
Checks (all on the 3-tier k=8 cell, B=8, seed 42, flags from run_t2.flags):
  v1  flag absent (healthy): old vs new flow-finish lines identical + new deterministic     (regress.sh)
  v2  ToR->agg-only file (a_r005): old vs new identical + deterministic                     (regress.sh)
  v3  agg_core ratio 1.0 on all 16 links: new flow-finish lines == healthy run's lines
  v4  agg_core 5/95 file: 16 `Failure: US..->CS..` lines, speeds {20, 380} Gbps, mean ratio 0.5, no error
  v5  negative controls: unconnected pair, out-of-range agg, ratio 0, ratio 5 each exit nonzero with the error text, nothing simulated
"""
import subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/t2work")
import run_t2 as r

DC = "/build/htsim_main/sim/datacenter"
OLD, NEW = "/build/baseline/htsim_uec.pre-agg-core", "/build/baseline/htsim_uec.agg-core"
B, SEED = 8, 42


def absflags(cfg, degrade=None):
    f = r.flags(dict(cfg, degrade=degrade if degrade else cfg["degrade"]), B, SEED)
    return [f"{DC}/{a}" if a.startswith(("connection_matrices/", "topologies/")) else a for a in f]


def run(binary, args):
    d = tempfile.mkdtemp()
    p = subprocess.run([binary] + args, cwd=d, capture_output=True, text=True)
    return p


def fin(p):
    return [ln for ln in p.stdout.splitlines() if "finished at" in ln]


def regress(args):
    p = subprocess.run(["/t2work/regress.sh", OLD, NEW, "--"] + args, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip().splitlines()[-1]


def write(name, lines):
    Path(f"/work/t2/{name}").write_text("".join(l + "\n" for l in lines))
    return f"/work/t2/{name}"


if __name__ == "__main__":
    healthy, a5, b5 = r.CFGS["healthy"], r.CFGS["a_r005"], r.CFGS["b_r005"]
    print("v1 healthy old-vs-new:", regress(absflags(healthy)))
    print("v2 a_r005 old-vs-new:", regress(absflags(a5)))
    one = write("degrade_b_one.txt", [f"agg_core {a} {a + 4 * l} 1.0" for a in range(4) for l in range(4)])
    ph, p1 = run(NEW, absflags(healthy)), run(NEW, absflags(healthy, one))
    print("v3 ratio-1.0 lines vs healthy: flow lines", len(fin(ph)), len(fin(p1)), "identical" if fin(ph) == fin(p1) else "DIFFERENT",
          "| Failure lines", sum(ln.startswith("Failure:") for ln in p1.stdout.splitlines()))
    p4 = run(NEW, absflags(b5))
    fl = [ln for ln in p4.stdout.splitlines() if ln.startswith("Failure:")]
    sp = sorted({ln.split("linkspeed set to")[1].strip() for ln in fl}, key=float)
    print("v4 b_r005:", "rc", p4.returncode, "Failure lines", len(fl), "speeds", sp, "flows", len(fin(p4)), "| sample:", fl[:2])
    print("v4 b_r005 old binary (must reject or ignore the unknown key):", end=" ")
    po = run(OLD, absflags(b5)); print("rc", po.returncode, (po.stdout + po.stderr).strip().splitlines()[-1][:120])
    for tag, line in (("unconnected pair (agg 0, core 1)", "agg_core 0 1 0.5"), ("agg out of range", "agg_core 99 0 0.5"),
                      ("core out of range", "agg_core 0 99 0.5"), ("ratio 0", "agg_core 0 0 0"), ("ratio 5", "agg_core 0 0 5"),
                      ("missing field", "agg_core 0 0")):
        f = write("degrade_b_bad.txt", [line]); pn = run(NEW, absflags(healthy, f))
        msg = [ln for ln in (pn.stdout + pn.stderr).splitlines() if "bad -degrade_links_file" in ln]
        print(f"v5 {tag}: rc {pn.returncode}, flows finished {len(fin(pn))}, msg {msg[:1]}")

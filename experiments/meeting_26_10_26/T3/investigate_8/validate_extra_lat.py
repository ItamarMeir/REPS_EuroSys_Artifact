#!/usr/bin/env python3
"""Tier 1/2 checks for `per-link-extra-latency` (latency_tor_agg lines in -degrade_links_file). Run in the container next to run_t3.py:
  v1 flag absent: old (htsim_uec.agg-core) vs new binary, flow-finish lines identical (128-host cell h128_p8, B=8, seed 42)
  v2 latency lines of 0 ns: identical to no latency lines
  v3 known answer: +10000 ns on every ToR->agg uplink of every ToR: every data packet and every ACK crosses exactly one such pipe, so RTT +20 us:
     predicted p50 FCT = old p50 + 20.0 us (+-0.5)
  v4 negative controls: tor/agg out of range, negative ns, missing field: nonzero exit, nothing simulated"""
import re, subprocess, sys, tempfile
import numpy as np
sys.path.insert(0, "/t3work")
import run_t3 as r
OLD, NEW = "/build/baseline/htsim_uec.agg-core", "/build/baseline/htsim_uec.extra-lat"
cfg = r.CFGS["h128_p8"]; U = cfg["U"]; NT = cfg["hosts"] // cfg["H"]
base = open(cfg["degrade"].replace("/work/t3/", "/work/t3/")).read()
def run(binary, extra_lines):
    deg = "/work/t3/_val_deg.txt"; open(deg, "w").write(base + "".join(l + "\n" for l in extra_lines))
    f = r.flags(dict(cfg, degrade=deg), 8, 42)
    return subprocess.run([binary] + f, cwd=r.m4.DC, capture_output=True, text=True)
def fin(p): return [l for l in p.stdout.splitlines() if "finished at" in l]
def p50(p): return float(np.median([float(re.search(r"finished at ([\d.]+)", l).group(1)) for l in fin(p)]))
o = run(OLD, []); n0 = run(NEW, []); nz = run(NEW, [f"latency_tor_agg {t} {a} 0" for t in range(NT) for a in range(U)])
print("v1 flag absent old vs new:", len(fin(o)), len(fin(n0)), "identical" if fin(o) == fin(n0) else "DIFFERENT")
print("v2 0 ns lines vs none:", "identical" if fin(nz) == fin(n0) else "DIFFERENT", "| Failure lines", sum(l.startswith("Failure:") and "extra latency" in l for l in nz.stdout.splitlines()))
n10 = run(NEW, [f"latency_tor_agg {t} {a} 10000" for t in range(NT) for a in range(U)])
print(f"v3 +10000 ns on all {NT*U} uplinks: p50 old {p50(o):.2f} new {p50(n10):.2f} delta {p50(n10)-p50(o):.2f} us (predicted 20.0), Failure lines",
      sum("extra latency" in l for l in n10.stdout.splitlines()))
for tag, line in (("tor out of range", f"latency_tor_agg {NT} 0 100"), ("agg out of range", f"latency_tor_agg 0 {U} 100"), ("negative ns", "latency_tor_agg 0 0 -5"), ("missing field", "latency_tor_agg 0 0")):
    p = run(NEW, [line]); print(f"v4 {tag}: rc {p.returncode}, flows finished {len(fin(p))}, msg", [l for l in (p.stdout + p.stderr).splitlines() if "bad -degrade" in l][:1])

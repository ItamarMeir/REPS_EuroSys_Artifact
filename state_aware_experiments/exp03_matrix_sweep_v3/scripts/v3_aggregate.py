#!/usr/bin/env python3
"""
Aggregate v3 matrix outputs into a tidy long-form CSV.

Reads <exp03>/runs/<workload>/<mode>/sev<N>/seed<S>.out
Emits <exp03>/data/v3_data.csv (one row per flow) + v3_events.csv (one row per run).

Paths are resolved relative to this script's location.
"""
import os, re, csv, glob, sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_EXP_DIR    = os.path.dirname(_SCRIPT_DIR)
OUT_ROOT = os.path.join(_EXP_DIR, "runs")
CSV_OUT  = os.path.join(_EXP_DIR, "data", "v3_data.csv")
EVT_OUT  = os.path.join(_EXP_DIR, "data", "v3_events.csv")
os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)

# Flow class definition by id range, per workload (matches generators).
CLASS_BY_WORKLOAD = {
    "pureperm":  lambda fid: "elephant",
    "mice":      lambda fid: "elephant" if fid <= 16 else "mice",
    "elephant":  lambda fid: "elephant",
    "composite": lambda fid: ("elephant" if fid <= 96
                              else "mice" if fid <= 352
                              else "incast"),
}

FLOW_PAT = re.compile(r"^Flow \S+ flowId (\d+) \S+ \S+ finished at (\S+) flowSize (\d+)")
FAIL_PAT = re.compile(r"\[link_failure\] failed")
REST_PAT = re.compile(r"\[link_failure\] restored")
SA_FREEZE_PAT = re.compile(r"\[state-aware\] .*FREEZING freeze \+ asymmetric=true")
SA_THAW_PAT   = re.compile(r"\[state-aware\] .*FREEZING unfreeze \+ asymmetric=false")
FZ_START_PAT  = re.compile(r"started freezing mode")
FZ_EXIT_PAT   = re.compile(r"exited freezing mode")

def parse_run(path, workload, mode, sev, seed, rows, events):
    classify = CLASS_BY_WORKLOAD[workload]
    pipe_fails = pipe_restores = 0
    fz_starts = fz_exits = 0
    sa_fr = sa_th = 0
    flows = 0
    with open(path) as f:
        for line in f:
            m = FLOW_PAT.match(line)
            if m:
                fid = int(m.group(1)); t = float(m.group(2)); sz = int(m.group(3))
                rows.append({
                    "workload": workload, "mode": mode, "sev": sev, "seed": seed,
                    "flow_id": fid, "fct_us": t, "size": sz,
                    "flow_class": classify(fid),
                })
                flows += 1
                continue
            if FAIL_PAT.search(line):       pipe_fails += 1
            elif REST_PAT.search(line):     pipe_restores += 1
            elif SA_FREEZE_PAT.search(line): sa_fr += 1
            elif SA_THAW_PAT.search(line):   sa_th += 1
            elif FZ_START_PAT.search(line):  fz_starts += 1
            elif FZ_EXIT_PAT.search(line):   fz_exits += 1
    events.append({
        "workload": workload, "mode": mode, "sev": sev, "seed": seed,
        "n_flows_finished": flows,
        "pipe_fails": pipe_fails, "pipe_restores": pipe_restores,
        "fz_starts": fz_starts,   "fz_exits": fz_exits,
        "sa_freezes": sa_fr,      "sa_thaws": sa_th,
    })
    return flows

def main():
    rows = []; events = []; bad = []
    for path in sorted(glob.glob(f"{OUT_ROOT}/*/*/sev*/seed*.out")):
        # path: <exp03>/runs/<w>/<mode>/sev<N>/seed<S>.out
        parts = path[len(OUT_ROOT)+1:].split("/")
        workload = parts[0]; mode = parts[1]
        sev = int(parts[2][3:]); seed = int(parts[3].replace("seed", "").replace(".out", ""))
        if workload not in CLASS_BY_WORKLOAD:
            bad.append((path, "unknown workload"))
            continue
        try:
            n = parse_run(path, workload, mode, sev, seed, rows, events)
            if n == 0:
                bad.append((path, "no flows finished"))
        except Exception as e:
            bad.append((path, f"err: {e}"))

    with open(CSV_OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "workload","mode","sev","seed","flow_id","fct_us","size","flow_class"])
        w.writeheader(); w.writerows(rows)

    with open(EVT_OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "workload","mode","sev","seed","n_flows_finished",
            "pipe_fails","pipe_restores","fz_starts","fz_exits","sa_freezes","sa_thaws"])
        w.writeheader(); w.writerows(events)

    print(f"wrote {CSV_OUT}: rows={len(rows)}")
    print(f"wrote {EVT_OUT}: rows={len(events)}")
    if bad:
        print(f"\n{len(bad)} problematic files:")
        for p, why in bad[:15]:
            print(f"  {p}: {why}")
        if len(bad) > 15: print("  ...")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""C3: bursty-src0 sweep. One sim per cell: (cm config) x B x seed.

cm configs (see gen_c3_cm.py, PLAN.md "Design"):
  n1_drained   -- anchor (b), src0's own N=1 baseline, background sized to
                   C3's full budget (NOT the same file as C1/C2's tornado.cm).
  n4_drained   -- N=4 bursts, 5-RTT drained gap
  n16_drained  -- N=16 bursts, 5-RTT drained gap
  n4_longgap   -- N=4 bursts, 50-RTT gap (gap-length control, folds into
                   panel 2 as a dashed overlay, see PLAN.md)

Anchor (a) (C1-NSCC exact config + -connections_mapping) needs NO new run:
common30.base_flags() already passes -connections_mapping unconditionally on
every arm, so C1's own committed reps_bN_nscc data on 16 MiB tornado already
IS anchor (a). Comparison against that existing data happens in the analysis
script, not here.

-log_reps_events_src gets src0's bursts' node_nums from each cm's
<stem>.schedule.json ("bursts"[].node_num) -- NOT a fixed list, since node_num
shifts with N (0..N-1 for all 4 configs here, since src0's bursts are always
re-inserted first, but read from the sidecar rather than assumed).

Writes:
  ../runs/<cm_stem>/seed<seed>/reps_b<B>_nscc/stdout.txt
  ../traces/<cm_stem>_seed<seed>_B<B>.csv.gz   (gzip -9, like C2)

Resumable (skip a cell whose stdout.txt + trace already exist) and resilient
(one cell's failure doesn't abort the batch) -- same pattern as run_c2.py.

CLI:
  --cells n1_drained:8:42 ...   only these (cm_stem:B:seed) cells (default: all 108)
  --workers N                   parallel cells (default 2, matching C1's finding)
"""
import argparse
import gzip
import json
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP30 = Path("/workspace/experiments/exp30_packet_trimming_en/scripts")
DC_DIR = Path("/workspace/htsim/sim/datacenter")
CM_DIR = DC_DIR / "connection_matrices"
C3 = HERE.parent
RUNS = C3 / "runs"
TRACES = C3 / "traces"

sys.path.insert(0, str(EXP30))
import common30 as C  # noqa: E402

SEEDS = [42, 43, 44]
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
CM_STEMS = ["c3_n1_drained", "c3_n4_drained", "c3_n16_drained", "c3_n4_longgap"]


def arm_name(b):
    return f"reps_b{b}_nscc"


def burst_node_nums(cm_stem):
    sidecar = json.loads((CM_DIR / f"{cm_stem}.schedule.json").read_text())
    return [b["node_num"] for b in sidecar["bursts"]]


def cell_flags(cm_stem, b, seed):
    flags = C.base_flags(arm_name(b), part="b", size=16777216, seed=seed, f_uplinks=0)
    # override -tm (base_flags points at the plain tornado.cm; C3 needs its
    # own bursty-src0 + resized-background file instead)
    i = flags.index("-tm")
    flags[i + 1] = f"connection_matrices/{cm_stem}.cm"
    return flags


def run_cell(cm_stem, b, seed):
    run_dir = RUNS / cm_stem / f"seed{seed}" / arm_name(b)
    stdout_path = run_dir / "stdout.txt"
    trace_gz = TRACES / f"{cm_stem}_seed{seed}_B{b}.csv.gz"
    if stdout_path.exists() and trace_gz.exists():
        return "skip (already done)"

    run_dir.mkdir(parents=True, exist_ok=True)
    TRACES.mkdir(parents=True, exist_ok=True)
    trace_plain = Path(f"/tmp/c3_run/{cm_stem}_seed{seed}_B{b}.csv")
    trace_plain.parent.mkdir(parents=True, exist_ok=True)

    srcs = []
    for n in burst_node_nums(cm_stem):
        srcs += ["-log_reps_events_src", str(n)]
    cmd = ([str(DC_DIR / "htsim_uec")] + cell_flags(cm_stem, b, seed)
           + ["-log_reps_events", str(trace_plain), "-log_reps_events_max", "200000000"] + srcs)
    proc = subprocess.run(cmd, cwd=str(DC_DIR), capture_output=True, text=True, timeout=7200)
    stdout_path.write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"htsim_uec rc={proc.returncode} for {cm_stem} B{b} seed{seed}: {proc.stderr[-400:]}")
    if not trace_plain.exists():
        raise RuntimeError(f"no trace written for {cm_stem} B{b} seed{seed}")

    tmp_gz = trace_gz.with_suffix(trace_gz.suffix + ".tmp")
    with open(trace_plain, "rb") as src, gzip.open(tmp_gz, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    tmp_gz.rename(trace_gz)
    trace_plain.unlink()
    return f"ran ({trace_gz.stat().st_size / 1e6:.1f} MB trace)"


def run_job(cm_stem, b, seed):
    try:
        return (cm_stem, b, seed, True, run_cell(cm_stem, b, seed))
    except Exception as e:
        return (cm_stem, b, seed, False, f"{e}\n{traceback.format_exc()[-500:]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", nargs="*", default=None,
                     help="cm_stem:B:seed triples, e.g. c3_n4_drained:8:42 (default: all 108)")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    if args.cells:
        jobs = []
        for c in args.cells:
            stem, b, seed = c.split(":")
            jobs.append((stem, int(b), int(seed)))
    else:
        jobs = [(stem, b, seed) for stem in CM_STEMS for b in BS for seed in SEEDS]
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_job, stem, b, seed) for stem, b, seed in jobs]
        for fut in futs:
            stem, b, seed, success, msg = fut.result()
            if success:
                ok += 1
                print(f"OK {stem} B{b} seed{seed}: {msg}", flush=True)
            else:
                fail += 1
                print(f"FAILED {stem} B{b} seed{seed}: {msg}", flush=True)
    print(f"done: {ok} ok, {fail} failed, {len(jobs)} total", flush=True)

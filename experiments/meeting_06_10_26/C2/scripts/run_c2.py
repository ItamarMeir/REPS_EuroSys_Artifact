#!/usr/bin/env python3
"""C2: Freezing-Mode drain speed vs B. One sim per cell, -log_reps_events on from the
start (no separate trace-only rerun like C1 needed, since there's no pre-existing
unlogged data to reuse here -- every cell is fresh).

Scenario (see ../PLAN.md): exp30_packet_trimming_en base, trim ON, NSCC, freezing LB,
16 MiB tornado, seed 42. F=0 (healthy, no failure flags) vs F=16 (transient kill of
16 of ToR0's 32 uplinks: -timed_window 10 110 -timed_fail_tor_uplinks 0 16 -- kill at
t=10us, past the ~8.8us warmup end measured from C1; recover at t=110us, 100us down).

common30.py's own Part B branch hardcodes a PERMANENT kill window (start=1,recover=1,
module constants, not parameters) for its own use case. This script avoids that branch
entirely by always calling base_flags(..., f_uplinks=0) and appending the real
transient-kill flags itself for F=16.

Writes:
  ../runs/x<F>_ef200/seed42/reps_b<B>_nscc/stdout.txt
  ../traces/16MiB_x<F>_B<B>.csv.gz   (gzip -9, like C1)

Resumable (skip a cell whose stdout.txt + trace already exist) and resilient (one
cell's failure doesn't abort the batch).

CLI:
  --cells 0:8 16:8 ...   only these (F:B) cells (default: all 18)
  --workers N            parallel cells (default 2, matching C1's CPU-contention finding)
"""
import argparse
import gzip
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP30 = Path("/workspace/experiments/exp30_packet_trimming_en/scripts")
DC_DIR = Path("/workspace/htsim/sim/datacenter")
C2 = HERE.parent
RUNS = C2 / "runs"
TRACES = C2 / "traces"

sys.path.insert(0, str(EXP30))
import common30 as C  # noqa: E402

SIZE = 16777216
SEED = 42
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
TOR0 = 32
FS = [0, 16]

KILL_START_US = 10
KILL_RECOVER_US = 110  # 100us down

# ===== ADDED (sol-avoid-timed-failure): SoL reference arm for F=16 =====
# Oracle floor for the F=16 cell: avoids the 16 dead uplinks (both data,
# pinned via path_static, and ACK, rerouted on the sink port) instead of
# running NSCC+Freezing. kill_cwnd=56 is the sweep-determined argmin (see
# experiments/meeting_06_10_26/C2/PLAN.md); delta=1.0us switch margin was
# swept {1,2,5,9,9.9}us with no measurable effect, so the minimum tested
# value is used. F=0 needs no SoL run -- the healthy cell never fails, so
# it's byte-identical to C1's x=0 `sol` run already committed there.
SOL_KILL_CWND_PKTS = 56
SOL_DELTA_US = 1.0
SOL_CWND_PKTS = 127  # C1's healthy knee -- the value setCwnd/setMaxWnd restore to at recovery
# F=0 floor: byte-identical to C1's x=0 `sol` run (confirmed in C2/PLAN.md), reused directly.
C1_HEALTHY_SOL_STDOUT = Path(
    "/workspace/experiments/exp30_packet_trimming_en/runs/a1/16777216/"
    "x0_ef200/seed42/sol/stdout.txt")


def sol_flags():
    return [
        "-connections_mapping", "-sack_threshold", "4000",
        "-tm", f"connection_matrices/tornado_n1024_s{SIZE}.cm",
        "-end", "90000", "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "constant",
        "-topo", "topologies/reps/fat_tree_1024_1os_2t_400g.topo",
        "-enable_qa_gate", "-linkspeed", "400000",
        "-ecn", "25", "76", "-q", "101", "-cwnd", str(SOL_CWND_PKTS),
        "-exit_freeze", "200000000",
        "-load_balancing_algo", "path_static", "-use_srv6", "-paths", "32",
        "-timed_window", str(KILL_START_US), str(KILL_RECOVER_US),
        "-timed_fail_tor_uplinks", "0", "16",
        "-sol_avoid_timed_failure", str(SOL_KILL_CWND_PKTS), str(SOL_DELTA_US),
    ]


def run_sol_cell():
    """F=16 SoL reference. No -log_reps_events (path_static has no REPS
    buffer to trace); stdout alone carries the per-flow finish lines
    build_c2.py needs."""
    run_dir = RUNS / "x16_ef200" / "seed42" / "sol"
    stdout_path = run_dir / "stdout.txt"
    if stdout_path.exists():
        return "skip (already done)"
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(DC_DIR / "htsim_uec")] + sol_flags()
    proc = subprocess.run(cmd, cwd=str(DC_DIR), capture_output=True, text=True, timeout=7200)
    stdout_path.write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"htsim_uec rc={proc.returncode} for SoL: {proc.stderr[-400:]}")
    return "ran"
# ===== END ADDED (sol-avoid-timed-failure) =====


def arm_name(b):
    return f"reps_b{b}_nscc"


def cell_flags(f, b):
    flags = C.base_flags(arm_name(b), part="b", size=SIZE, seed=SEED, f_uplinks=0)
    if f:
        flags += ["-timed_window", str(KILL_START_US), str(KILL_RECOVER_US),
                  "-timed_fail_tor_uplinks", "0", str(f)]
    return flags


def run_cell(f, b):
    run_dir = RUNS / f"x{f}_ef200" / "seed42" / arm_name(b)
    stdout_path = run_dir / "stdout.txt"
    trace_gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
    if stdout_path.exists() and trace_gz.exists():
        return "skip (already done)"

    run_dir.mkdir(parents=True, exist_ok=True)
    TRACES.mkdir(parents=True, exist_ok=True)
    trace_plain = Path(f"/tmp/c2_run/x{f}_B{b}.csv")
    trace_plain.parent.mkdir(parents=True, exist_ok=True)

    srcs = []
    for s in range(TOR0):
        srcs += ["-log_reps_events_src", str(s)]
    cmd = ([str(DC_DIR / "htsim_uec")] + cell_flags(f, b)
           + ["-log_reps_events", str(trace_plain), "-log_reps_events_max", "200000000"] + srcs)
    proc = subprocess.run(cmd, cwd=str(DC_DIR), capture_output=True, text=True, timeout=7200)
    stdout_path.write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"htsim_uec rc={proc.returncode} for F{f} B{b}: {proc.stderr[-400:]}")
    if not trace_plain.exists():
        raise RuntimeError(f"no trace written for F{f} B{b}")

    # Write to a .tmp path and rename into place atomically -- a partial gz
    # left at the final path (e.g. the battery-death scenario from C1) would
    # otherwise pass the `trace_gz.exists()` skip-check forever with corrupt data.
    tmp_gz = trace_gz.with_suffix(trace_gz.suffix + ".tmp")
    with open(trace_plain, "rb") as src, gzip.open(tmp_gz, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    tmp_gz.rename(trace_gz)
    trace_plain.unlink()
    return f"ran ({trace_gz.stat().st_size / 1e6:.1f} MB trace)"


def run_job(f, b):
    try:
        return (f, b, True, run_cell(f, b))
    except Exception as e:
        return (f, b, False, f"{e}\n{traceback.format_exc()[-500:]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", nargs="*", default=None,
                     help="F:B pairs, e.g. 0:8 16:8 (default: all 18)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--skip-sol", action="store_true",
                     help="skip the F=16 SoL reference arm")
    args = ap.parse_args()
    if args.cells:
        jobs = [tuple(int(v) for v in c.split(":")) for c in args.cells]
    else:
        jobs = [(f, b) for f in FS for b in BS]
    # ===== ADDED (sol-avoid-timed-failure) =====
    if not args.cells and not args.skip_sol:
        try:
            print(f"SOL: {run_sol_cell()}", flush=True)
        except Exception as e:
            print(f"SOL FAILED: {e}", flush=True)
    # ===== END ADDED (sol-avoid-timed-failure) =====
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_job, f, b) for f, b in jobs]
        for fut in futs:
            f, b, success, msg = fut.result()
            if success:
                ok += 1
                print(f"OK F{f} B{b}: {msg}", flush=True)
            else:
                fail += 1
                print(f"FAILED F{f} B{b}: {msg}", flush=True)
    print(f"done: {ok} ok, {fail} failed, {len(jobs)} total", flush=True)

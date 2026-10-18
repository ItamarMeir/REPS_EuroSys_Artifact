#!/usr/bin/env python3
"""Buffer view pages for every C1 cell (16 MiB, seed 42, trim on).

For each (scenario, B): reuse the gzipped trace if already on disk, otherwise run the cell
with -log_reps_events for the ToR0 hosts (trace-only, see occupancy.run_trace) and gzip it.
Render the buffer viewer for ToR0 host 0 (first 5000 events).
Output: ../plots/buffer_view_16MiB_B<B>_<scenario>_src0.html
Traces: ../traces/16MiB_x<x>_B<B>.csv.gz (kept, max gzip, not committed -- like runs.tar.gz)

All local: the sim binary, the viewer and every path here are on disk in the container.
No network call is made by this script or by reps_event_viewer.py.

Run inside the container (needs /workspace paths and the htsim_uec binary).

CLI:
  --cells 0:8 32:16 ...   only these (x:B) cells (default: all 18)
  --workers N             parallel cells (default 2 -- 4 caused CPU contention
                           that timed out the viewer on large B before)
  --timeout S             viewer subprocess timeout in seconds (default 3600)
"""
import argparse
import gzip
import os
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import occupancy as O  # noqa: E402

VIEWER = Path("/workspace/experiments/tools/reps_event_viewer.py")
SCEN = {0: "healthy", 32: "degraded"}


def _dirs():
    c1 = HERE.parent
    return c1 / O.cc_label() / "plots", c1 / O.cc_label() / "traces"


def get_trace(x, b):
    """Return a plain (uncompressed) scratch copy of the trace for this cell.
    Reuses ../<CC>/traces/*.csv.gz if present; otherwise runs the sim and gzips the result."""
    _plots, traces = _dirs()
    gz = traces / f"16MiB_x{x}_B{b}.csv.gz"
    plain = Path(f"/tmp/c1_view_{O.CC}") / f"x{x}_B{b}.csv"
    plain.parent.mkdir(parents=True, exist_ok=True)
    if gz.exists():
        with gzip.open(gz, "rb") as src, open(plain, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return plain, True  # reused
    tp, out_path = O.run_trace(x, b)
    traces.mkdir(parents=True, exist_ok=True)
    # Write to a .tmp path and rename into place atomically -- two overlapping
    # invocations (e.g. a stale job that outlived a TaskStop) writing the same
    # final path directly can interleave, producing a gzip stream that still
    # passes `gzip -t` but decompresses to corrupt (NUL-containing) content.
    # Hit this for real: x0 B16/B32 got corrupted exactly this way.
    tmp_gz = gz.with_suffix(gz.suffix + ".tmp")
    with open(tp, "rb") as src, gzip.open(tmp_gz, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    tmp_gz.rename(gz)
    # Persist this run's own stdout alongside the trace so occupancy.py can
    # reuse both (cross_check + summarise) without re-running the sim --
    # one sim per cell total instead of one for view_traces and another for
    # occupancy.
    shutil.copyfile(out_path, traces / f"16MiB_x{x}_B{b}.stdout.txt")
    shutil.copyfile(tp, plain)
    os.remove(tp)
    return plain, False  # freshly run


def view_one(x, b, timeout):
    plots, _traces = _dirs()
    html = plots / f"buffer_view_16MiB_B{b}_{SCEN[x]}_src0.html"
    plain, reused = get_trace(x, b)
    try:
        proc = subprocess.run(
            [sys.executable, str(VIEWER), str(plain), "--src", "0", "--max-events", "5000",
             "-o", str(html)], capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"viewer rc={proc.returncode}: {proc.stderr[-400:]}")
    finally:
        os.remove(plain)
    return f"{html.name} (trace {'reused' if reused else 'fresh'})"


def traces_only_one(x, b):
    """Run the sim and save the gz trace + stdout sidecar (get_trace's side
    effect), without rendering any buffer-view HTML. Keeps the data available
    for a buffer-view pass later without re-simulating."""
    plain, reused = get_trace(x, b)
    os.remove(plain)  # only the persisted .gz (written by get_trace) is kept
    return f"trace saved ({'reused' if reused else 'fresh'})"


def run_job(x, b, timeout, traces_only):
    try:
        if traces_only:
            return (x, b, True, traces_only_one(x, b))
        return (x, b, True, view_one(x, b, timeout))
    except Exception as e:  # keep going on one cell's failure
        return (x, b, False, f"{e}\n{traceback.format_exc()[-500:]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", choices=["mprdma", "nscc"], default="mprdma")
    ap.add_argument("--cells", nargs="*", default=None,
                     help="x:B pairs, e.g. 0:128 32:8 (default: all 18)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--traces-only", action="store_true",
                     help="save the gz trace + stdout sidecar only, skip rendering HTML")
    args = ap.parse_args()
    O.CC = args.cc
    if args.cells:
        jobs = [tuple(int(v) for v in c.split(":")) for c in args.cells]
    else:
        jobs = [(x, b) for x in (0, 32) for b in O.BS]
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_job, x, b, args.timeout, args.traces_only) for x, b in jobs]
        for fut in futs:
            x, b, success, msg = fut.result()
            if success:
                ok += 1
                print(f"wrote x{x} B{b}: {msg}", flush=True)
            else:
                fail += 1
                print(f"FAILED x{x} B{b}: {msg}", flush=True)
    print(f"done: {ok} ok, {fail} failed, {len(jobs)} total", flush=True)

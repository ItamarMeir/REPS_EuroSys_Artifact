#!/usr/bin/env python3
"""C1 buffer occupancy from the REPS event trace (16 MiB, seed 42, trim on).

Claim under test (after the first ACK, during backlog, the buffer holds <= 2 valid EVs).

For every ToR0 host (flow src id < 32):
  t0          = time of the host's first ACK row
  last_send   = time of the host's last SEND or RTX row
  fresh       = post-event count of valid buffer entries, logged on every row
                (verified equal to the number of valid slots in the snapshot)

Per cell (pooled over the 32 hosts):
  share_le2_after_t0   share of rows with time >= t0 and fresh <= 2     (primary)
  share_le2_backlog    share of rows with t0 <= time < last_send and fresh <= 2
  max_fresh_backlog    max fresh over backlog rows
  n_ge3_backlog        backlog rows with fresh >= 3
  drain_share          share of post-t0 rows at or after last_send (the drain tail)

Modes:
  --cell X B   run one trace-only cell (X = 0 healthy, 32 degraded), summarise, delete trace
  --check      byte-compare the trace run's finish lines with the committed C1 stdout

Trace-only: output goes to /tmp/c1_traces/. Nothing is written under runs/.
"""
import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

EXP30 = Path("/workspace/experiments/exp30_packet_trimming_en/scripts")
RUNS = Path("/workspace/experiments/exp30_packet_trimming_en/runs/a1/16777216")
TRACE_DIR = Path("/tmp/c1_traces")
DC_DIR = Path("/workspace/htsim/sim/datacenter")
C1 = Path("/workspace/experiments/meeting_06_10_26/C1")
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
TOR0 = 32
SIZE = 16777216

# Set from --cc at the bottom; cell_flags/cross_check/OUT all key off this.
CC = "mprdma"


def arm_name(b):
    return f"reps_b{b}" + ("_nscc" if CC == "nscc" else "")


def cc_label():
    return "MPRDMA" if CC == "mprdma" else "NSCC"


def out_path():
    return C1 / cc_label() / "data" / "c1_occupancy.csv"


sys.path.insert(0, str(EXP30))
import common30 as C  # noqa: E402


def cell_flags(x, b):
    kw = dict(n=x, r=(0.5 if x else None))
    return C.base_flags(arm_name(b), part="a1", size=SIZE, seed=42, **kw)


def trace_path(x, b):
    return TRACE_DIR / f"{CC}_x{x}_b{b}.csv"


def finish_lines(text):
    return sorted(l for l in text.splitlines() if "finished at" in l and "uecSrc" in l)


def run_trace(x, b):
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    tp = trace_path(x, b)
    srcs = []
    for s in range(TOR0):
        srcs += ["-log_reps_events_src", str(s)]
    cmd = ([str(DC_DIR / "htsim_uec")] + cell_flags(x, b)
           + ["-log_reps_events", str(tp), "-log_reps_events_max", "200000000"] + srcs)
    proc = subprocess.run(cmd, cwd=str(DC_DIR), capture_output=True, text=True, timeout=7200)
    stdout_path = TRACE_DIR / f"{CC}_x{x}_b{b}.stdout.txt"
    stdout_path.write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"htsim_uec rc={proc.returncode} for x{x} B{b}")
    return tp, stdout_path


def summarise(tp):
    """Stream the trace; keep one compact tuple per row per host."""
    per = {}  # src -> list of (time_ns, event, fresh)
    with open(tp, newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        ci = {k: head.index(k) for k in ("src_id", "time_ns", "event", "fresh")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= TOR0:
                continue
            per.setdefault(src, []).append(
                (float(row[ci["time_ns"]]), row[ci["event"]], int(row[ci["fresh"]])))
    n_after = le2_after = 0
    n_back = le2_back = n_ge3_back = 0
    max_back = 0
    n_post_tail = 0
    for src, rows in per.items():
        rows.sort(key=lambda r: r[0])  # stable: file order within equal times
        t0 = next(t for t, ev, _ in rows if ev == "ACK")
        last_send = max(t for t, ev, _ in rows if ev in ("SEND", "RTX"))
        for t, ev, fr in rows:
            if t < t0:
                continue
            n_after += 1
            if fr <= 2:
                le2_after += 1
            if t < last_send:
                n_back += 1
                if fr <= 2:
                    le2_back += 1
                if fr >= 3:
                    n_ge3_back += 1
                max_back = max(max_back, fr)
            else:
                n_post_tail += 1
    return dict(
        hosts=len(per),
        rows_after_t0=n_after,
        share_le2_after_t0=le2_after / n_after,
        rows_backlog=n_back,
        share_le2_backlog=(le2_back / n_back) if n_back else float("nan"),
        max_fresh_backlog=max_back,
        n_ge3_backlog=n_ge3_back,
        drain_share=n_post_tail / n_after,
    )


def cross_check(x, b, stdout_path):
    """Trace-run finish lines must equal the committed C1 stdout for the same cell."""
    committed = RUNS / f"x{x}_ef200" / "seed42" / arm_name(b) / "stdout.txt"
    got = finish_lines(stdout_path.read_text(errors="replace"))
    want = finish_lines(committed.read_text(errors="replace"))
    return got == want, len(got), len(want)


def cell(x, b):
    """Reuse the gz trace + paired stdout.txt from view_traces.py if both already
    exist under <CC>/traces/ (one sim per cell total, instead of a second sim
    here on top of view_traces.py's). Falls back to running fresh otherwise."""
    traces_dir = C1 / cc_label() / "traces"
    gz = traces_dir / f"16MiB_x{x}_B{b}.csv.gz"
    stdout_sidecar = traces_dir / f"16MiB_x{x}_B{b}.stdout.txt"
    scratch = TRACE_DIR / f"{CC}_x{x}_b{b}_reuse.csv"
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    if gz.exists() and stdout_sidecar.exists():
        import gzip as _gzip
        import shutil as _shutil
        with _gzip.open(gz, "rb") as src, open(scratch, "wb") as dst:
            _shutil.copyfileobj(src, dst)
        same, ng, nw = cross_check(x, b, stdout_sidecar)
        s = summarise(scratch)
        size_b = os.path.getsize(scratch)
        os.remove(scratch)
    else:
        tp, stdout_path = run_trace(x, b)
        same, ng, nw = cross_check(x, b, stdout_path)
        s = summarise(tp)
        size_b = os.path.getsize(tp)
        os.remove(tp)  # explicit path; trace-only scratch file

    row = dict(scenario="healthy" if x == 0 else "32 ToR0 uplinks at 50%", x=x, B=b,
               crosscheck_match=same, finish_lines_trace=ng, finish_lines_committed=nw,
               trace_mb=round(size_b / 1e6, 1), **s)
    return row


def write_rows(rows):
    out = out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0].keys())
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", choices=["mprdma", "nscc"], default="mprdma")
    ap.add_argument("--cell", nargs=2, type=int, metavar=("X", "B"))
    ap.add_argument("--all", action="store_true", help="all 18 cells, 4 at a time")
    args = ap.parse_args()
    CC = args.cc
    if args.cell:
        r = cell(*args.cell)
        print(r)
    elif args.all:
        from concurrent.futures import ThreadPoolExecutor
        jobs = [(x, b) for x in (0, 32) for b in BS]
        with ThreadPoolExecutor(max_workers=4) as ex:
            rows = list(ex.map(lambda j: cell(*j), jobs))
        rows.sort(key=lambda r: (r["x"], r["B"]))
        write_rows(rows)
        for r in rows:
            print(r)

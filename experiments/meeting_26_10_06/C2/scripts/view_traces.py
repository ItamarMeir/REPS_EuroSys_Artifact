#!/usr/bin/env python3
"""Buffer view pages for C2 cells (16 MiB, NSCC, trim on).

Unlike C1 (always src 0, first 5000 events -- never froze, so it never mattered),
C2 picks a src that actually freezes (freeze_entries > 0 in the finish line) and
windows the page around that src's first FREEZE event, not a first-5000-events cut
(which would likely miss the freeze entirely on a 16 MiB trace -- C1's own warmup
measurement put the first ACK at ~8.8us, and FREEZE here can't happen before the
10-110us kill window).

Output: ../plots/buffer_view_16MiB_F<F>_B<B>_src<N>.html

CLI:
  --cells 0:8 16:8 ...   only these (F:B) cells (default: all 18)
  --workers N            parallel cells (default 2, matches C1's CPU-contention finding)
  --timeout S            viewer subprocess timeout in seconds (default 600)
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
from build_c2 import FRZ, arm_name  # noqa: E402

C2 = HERE.parent
PLOTS = C2 / "plots"
TRACES = C2 / "traces"
RUNS = C2 / "runs"
VIEWER = Path("/workspace/experiments/tools/reps_event_viewer.py")

# -exit_freeze is 200us; a freeze entered inside the 10-110us kill window only
# exits at FREEZE_time + 200us. Window generously past that.
KILL_START_NS = 9_000  # just before the t=10us kill, not just before FREEZE --
# FREEZE itself fires later (~50us observed), so a window anchored there alone
# would start mid-outage and miss the healthy-to-fail transition entirely.
WINDOW_AFTER_NS = 260_000


PREFERRED_SRC = 0  # fixed across every B so the pages are a like-for-like comparison


def freezing_src(f, b):
    """PREFERRED_SRC if it froze in this cell (true for every F=16 B checked --
    all 32 ToR0 hosts freeze in every cell here), else the first ToR0 src
    (< 32) with freeze_entries > 0, else None (expected for F=0).

    A plain "first src with freeze_entries>0" picks whichever host's finish
    line happens to appear first in the file -- file order follows finish
    *time*, not src id, and that ordering shifts with B. That produced a
    different host's buffer-view page per B, making the pages impossible to
    compare across the B ladder. Pin one host instead."""
    path = RUNS / f"x{f}_ef200" / "seed42" / arm_name(b) / "stdout.txt"
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    freezing = {int(s): int(fz) for s, fz in FRZ.findall(text) if int(s) < 32}
    if freezing.get(PREFERRED_SRC, 0) > 0:
        return PREFERRED_SRC
    for src, fz in sorted(freezing.items()):
        if fz > 0:
            return src
    return None


def first_freeze_time_ns(gz_path, src):
    with gzip.open(gz_path, "rt", newline="") as f:
        import csv
        rd = csv.reader(f)
        head = next(rd)
        ci = {k: head.index(k) for k in ("src_id", "event", "time_ns")}
        for row in rd:
            if int(row[ci["src_id"]]) == src and row[ci["event"]] == "FREEZE":
                return float(row[ci["time_ns"]])
    return None


def view_one(f, b, timeout):
    gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
    if not gz.exists():
        raise RuntimeError("trace missing")
    src = freezing_src(f, b)
    if src is None:
        return f"no freezing src found (F={f}) -- skipped, not a failure"
    t_freeze = first_freeze_time_ns(gz, src)
    if t_freeze is None:
        raise RuntimeError(f"finish line says src {src} froze, but no FREEZE row found in trace")
    # Full flow, start to finish -- not windowed around the kill/freeze.
    # --src already limits load_events to this one host (the loader filters
    # during parse, per the C1 OOM fix), so the full per-host row count
    # (~8-9k events for this flow size) is cheap; no --from/--to.
    html = PLOTS / f"buffer_view_16MiB_F{f}_B{b}_src{src}.html"
    plain = Path(f"/tmp/c2_view/F{f}_B{b}.csv")
    plain.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz, "rb") as s, open(plain, "wb") as d:
        shutil.copyfileobj(s, d)
    try:
        proc = subprocess.run(
            [sys.executable, str(VIEWER), str(plain), "--src", str(src),
             "--max-events", "20000",
             "-o", str(html)], capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"viewer rc={proc.returncode}: {proc.stderr[-400:]}")
    finally:
        os.remove(plain)
    return f"{html.name} (src {src}, full flow, FREEZE at {t_freeze:.0f} ns)"


def run_job(f, b, timeout):
    try:
        return (f, b, True, view_one(f, b, timeout))
    except Exception as e:
        return (f, b, False, f"{e}\n{traceback.format_exc()[-500:]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", nargs="*", default=None,
                     help="F:B pairs, e.g. 0:8 16:8 (default: all 18)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    if args.cells:
        jobs = [tuple(int(v) for v in c.split(":")) for c in args.cells]
    else:
        from build_c2 import SCEN, BS
        jobs = [(f, b) for f in SCEN for b in BS]
    PLOTS.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_job, f, b, args.timeout) for f, b in jobs]
        for fut in futs:
            f, b, success, msg = fut.result()
            if success:
                ok += 1
                print(f"wrote F{f} B{b}: {msg}", flush=True)
            else:
                fail += 1
                print(f"FAILED F{f} B{b}: {msg}", flush=True)
    print(f"done: {ok} ok, {fail} failed, {len(jobs)} total", flush=True)

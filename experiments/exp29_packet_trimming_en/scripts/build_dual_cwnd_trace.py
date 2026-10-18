#!/usr/bin/env python3
"""
Concatenate the per-cell cwnd traces -- -log_dual_cwnd for the two dual-window
arms (data/dual_cwnd/<arm>_F<F>.csv) and -log_cwnd for the single-window CCs
(data/dual_cwnd/plain_b8/reps_b8_F<F>.{csv,stdout},
data/dual_cwnd/nscc_b8/reps_b8_nscc_F<F>.{csv,stdout}) -- one representative
flow each (seed 42, affected src 0, ef=100) into one tidy
data/dual_cwnd_trace.csv for the dashboard's "Dual-window cwnd through time"
section.

This is a single-flow diagnostic feed (not a seed-averaged statistic like
every other CSV in data/), so it's kept separate from aggregate29.py's
schema/responsibility rather than bolted onto it.

Also emits data/freeze_unfreeze.csv (F, arm, event in {freeze,unfreeze},
time_us) -- per-algorithm freeze-entry/unfreeze timestamps for host 0, used to
draw algorithm-specific vertical markers on the cwnd-through-time chart (each
arm freezes/thaws at a different time, unlike the fixed fail@100/recover@200
lines). Dual-window arms: read straight off the `frozen` column already in
their per-event CSV (exact). Single-window arms (plain MPRDMA, NSCC): no such
column in -log_cwnd's output, so parsed from host 0's own freeze/unfreeze
printf lines in that cell's stdout.

    python3 build_dual_cwnd_trace.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
SRC_DIR = EXP_DIR / "data" / "dual_cwnd"
PLAIN_DIR = SRC_DIR / "plain_b8"
NSCC_DIR = SRC_DIR / "nscc_b8"
OUT = EXP_DIR / "data" / "dual_cwnd_trace.csv"
FREEZE_OUT = EXP_DIR / "data" / "freeze_unfreeze.csv"

NAME_RE = re.compile(r"^(reps_b8_dual(?:_cap)?)_F(\d+)\.csv$")
PLAIN_NAME_RE = re.compile(r"^reps_b8_F(\d+)\.csv$")
NSCC_NAME_RE = re.compile(r"^reps_b8_nscc_F(\d+)\.csv$")
FINISH_RE = re.compile(
    r"uecSrc 0 finished.*total packets (\d+) RTS \d+ total bytes (\d+)")

# Freeze/unfreeze printf lines for host 0 specifically (_name = "Uec_<src>_<dest>",
# see main_uec.cpp's setName call) -- both printed via eventlist().now()/1000,
# the same mislabeled-"us" bug as everywhere else in this logger family (actual
# unit is nanoseconds); divide by 1000 again below for true microseconds.
FREEZE_RE = re.compile(r"^Uec_0_\d+ started freezing mode\d+ at (\d+)")
UNFREEZE_RE = re.compile(r"^Uec_0_\d+ exited freezing mode at (\d+)")

COLS = ["F", "arm", "time_us", "srcaddr", "node_num", "flow_id",
        "safe_cwnd", "random_cwnd", "maxwnd",
        "safe_in_flight", "random_in_flight", "frozen"]
FREEZE_COLS = ["F", "arm", "event", "time_us"]


def load_dual_frames():
    frames = []
    for path in sorted(SRC_DIR.glob("*.csv")):
        m = NAME_RE.match(path.name)
        if not m:
            continue
        arm, f = m.group(1), int(m.group(2))
        df = pd.read_csv(path)
        df["arm"] = arm
        df["F"] = f
        # FIXED: -log_dual_cwnd's "time_us" column is mislabeled -- it holds
        # eventlist().now()/1000, i.e. NANOSECONDS (picoseconds/1000), not
        # microseconds. Convert to true microseconds here so this trace lines
        # up with the rest of the dashboard's µs-based x-axes (fail@100/
        # recover@200). See experiments/tools/README.md's noted units quirk.
        df["time_us"] = df["time_us"] / 1000.0
        frames.append(df[COLS])
    return frames


def load_single_window_frames(subdir: Path, name_re: re.Pattern, arm: str):
    """Shared loader for any single-shared-window CC logged via -log_cwnd
    (plain MPRDMA, NSCC, ...). -log_cwnd gives cwnd in PACKETS
    (cwnd / get_avg_pktsize()), but the dual-window trace is in raw bytes.
    Recover the exact byte value by multiplying back by that same cell's own
    avg packet size, read from its finish line (total bytes / total packets
    for src 0) -- not an assumed MTU constant, so there's no approximation
    error beyond the one division+cast to unsigned already baked into
    -log_cwnd's own logged value. Stored in the `safe_cwnd` column (this arm
    has only one window); `random_cwnd` is left null so the dashboard draws
    a single line for it.
    """
    frames = []
    for path in sorted(subdir.glob("*.csv")):
        m = name_re.match(path.name)
        if not m:
            continue
        f = int(m.group(1))
        stdout_path = path.with_suffix(".stdout")
        text = stdout_path.read_text(errors="ignore")
        fm = FINISH_RE.search(text)
        if not fm:
            print(f"  skip {arm} F={f}: no finish line found in {stdout_path.name}")
            continue
        avg_pkt_size = int(fm.group(2)) / int(fm.group(1))

        df = pd.read_csv(path, names=["time_us", "src_id", "cwnd_pkts"], header=0)
        df["safe_cwnd"] = df["cwnd_pkts"] * avg_pkt_size
        df["random_cwnd"] = pd.NA
        df["maxwnd"] = pd.NA
        df["safe_in_flight"] = pd.NA
        df["random_in_flight"] = pd.NA
        df["frozen"] = pd.NA
        df["srcaddr"] = df["src_id"]
        df["node_num"] = df["src_id"]
        df["flow_id"] = pd.NA
        df["arm"] = arm
        df["F"] = f
        # Same mislabeled-unit fix as the dual-window logger (same fprintf
        # pattern: eventlist().now()/1000 = nanoseconds, not microseconds).
        df["time_us"] = df["time_us"] / 1000.0
        frames.append(df[COLS])
    return frames


def freeze_times_from_frozen_col(dual_frames):
    """Dual-window arms log `frozen` (0/1) at every cwnd mutation event -- the
    exact ground truth, no stdout parsing needed. A transition 0->1 is a freeze
    entry, 1->0 is an unfreeze; both timestamped at the mutation event that
    crossed the boundary (already converted to true microseconds upstream).
    """
    rows = []
    for df in dual_frames:
        for (arm, f), g in df.groupby(["arm", "F"]):
            g = g.sort_values("time_us")
            prev = 0
            for _, r in g.iterrows():
                cur = int(r["frozen"]) if pd.notna(r["frozen"]) else prev
                if cur == 1 and prev == 0:
                    rows.append(dict(F=f, arm=arm, event="freeze", time_us=r["time_us"]))
                elif cur == 0 and prev == 1:
                    rows.append(dict(F=f, arm=arm, event="unfreeze", time_us=r["time_us"]))
                prev = cur
    return rows


def freeze_times_from_stdout(subdir: Path, name_re: re.Pattern, arm: str):
    """Single-window arms (-log_cwnd has no `frozen` column) -- recover freeze/
    unfreeze timestamps straight from host 0's own printf lines in the run's
    stdout (see FREEZE_RE/UNFREEZE_RE above)."""
    rows = []
    for path in sorted(subdir.glob("*.stdout")):
        m = name_re.match(path.name.replace(".stdout", ".csv"))
        if not m:
            continue
        f = int(m.group(1))
        for line in path.read_text(errors="ignore").splitlines():
            fm = FREEZE_RE.match(line)
            if fm:
                rows.append(dict(F=f, arm=arm, event="freeze",
                                  time_us=int(fm.group(1)) / 1000.0))
                continue
            um = UNFREEZE_RE.match(line)
            if um:
                rows.append(dict(F=f, arm=arm, event="unfreeze",
                                  time_us=int(um.group(1)) / 1000.0))
    return rows


def main() -> None:
    dual_frames = load_dual_frames()
    frames = (dual_frames
              + load_single_window_frames(PLAIN_DIR, PLAIN_NAME_RE, "reps_b8")
              + load_single_window_frames(NSCC_DIR, NSCC_NAME_RE, "reps_b8_nscc"))
    if not frames:
        raise SystemExit(f"no dual_cwnd CSVs found in {SRC_DIR}")

    out = pd.concat(frames, ignore_index=True)
    out = out[COLS].sort_values(["arm", "F", "time_us"])
    out.to_csv(OUT, index=False)
    print(f"dual_cwnd_trace.csv : {len(out)} rows, "
          f"{out['arm'].nunique()} arms x {out['F'].nunique()} F values")

    freeze_rows = (freeze_times_from_frozen_col(dual_frames)
                   + freeze_times_from_stdout(PLAIN_DIR, PLAIN_NAME_RE, "reps_b8")
                   + freeze_times_from_stdout(NSCC_DIR, NSCC_NAME_RE, "reps_b8_nscc"))
    fout = pd.DataFrame(freeze_rows, columns=FREEZE_COLS)
    fout["time_us"] = fout["time_us"].round(2)
    fout = fout.sort_values(["arm", "F", "time_us"])
    fout.to_csv(FREEZE_OUT, index=False)
    print(f"freeze_unfreeze.csv : {len(fout)} rows, "
          f"{fout['arm'].nunique()} arms x {fout['F'].nunique()} F values")


if __name__ == "__main__":
    main()

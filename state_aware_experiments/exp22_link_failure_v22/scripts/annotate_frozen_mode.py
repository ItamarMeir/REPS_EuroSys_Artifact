#!/usr/bin/env python3
"""
annotate_frozen_mode.py — Add frozen_mode column to all exp22 buffer CSVs.

For each buf_<runname>.csv in data/, reads the matching <runname>.out from
runs.tar.gz, extracts the freeze-enter and freeze-exit timestamps for
Uec_0_512, and writes a frozen_mode column (0 = normal, 1 = frozen) to the
CSV in place.  Handles multiple freeze episodes per run.
"""
import re
import tarfile
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_DIR   = EXP_DIR / "data"
RUNS_TAR   = EXP_DIR / "runs.tar.gz"

ENTER_RE = re.compile(r"Uec_0_512 started freezing mode\S* at (\d+)")
EXIT_RE  = re.compile(r"Uec_0_512 exited freezing mode at (\d+)")


def parse_freeze_intervals(out_text: str) -> list[tuple[float, float]]:
    """Return list of (enter_us, exit_us) pairs; exit_us = inf if no exit line."""
    enters = [int(m.group(1)) for m in ENTER_RE.finditer(out_text)]
    exits  = [int(m.group(1)) for m in EXIT_RE.finditer(out_text)]
    intervals = []
    for i, enter in enumerate(enters):
        exit_t = exits[i] if i < len(exits) else float("inf")
        intervals.append((float(enter), float(exit_t)))
    return intervals


def in_frozen(time_us: float, intervals: list[tuple[float, float]]) -> int:
    for enter, exit_t in intervals:
        if enter <= time_us <= exit_t:
            return 1
    return 0


def main():
    # Build index: runname -> out file content
    out_cache: dict[str, str] = {}
    with tarfile.open(RUNS_TAR, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith(".out"):
                runname = Path(member.name).stem
                f = tf.extractfile(member)
                if f:
                    out_cache[runname] = f.read().decode("utf-8", errors="replace")

    csv_files = sorted(DATA_DIR.glob("buf_*.csv"))
    for csv_path in csv_files:
        runname = csv_path.stem[4:]  # strip "buf_" prefix
        out_text = out_cache.get(runname, "")
        intervals = parse_freeze_intervals(out_text)

        df = pd.read_csv(csv_path)
        df["frozen_mode"] = df["time_us"].apply(lambda t: in_frozen(t, intervals))

        df.to_csv(csv_path, index=False)
        status = f"{len(intervals)} episode(s): {intervals}" if intervals else "no freeze events"
        print(f"{csv_path.name}: {status}")


if __name__ == "__main__":
    main()

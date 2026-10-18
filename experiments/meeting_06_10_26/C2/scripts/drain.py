#!/usr/bin/env python3
"""C2 drain metric: per freeze epoch (FREEZE to next UNFREEZE, same src), based on
draw classification, not raw slot occupancy.

First version of this script defined "drained" as "stale fraction among occupied
slots reaches 0" -- wrong, caught by advisor review: once a slot has been written
it stays occupied (valid or stale) until UNFREEZE resets the whole buffer, so
occupied is ~buf_size for the rest of the epoch. Reading 0 stale among occupied
slots is not "no further stale draws can happen" -- it is a transient state that
doesn't track what actually matters, which is whether SENDS keep drawing stale
EVs.

This version tracks that directly, per epoch: of the frozen-mode draws (SEND/RTX/
RTS with frozen_mode=1, classified via the same (frozen_head-1)%modulus slot
lookup send_occupancy.py uses), how many are stale, and where the LAST stale draw
falls -- draws after that point in the same epoch got a valid EV, even though the
epoch hadn't unfrozen yet. Stale draws are also split by whether they happened
during the 10-110us kill window (dead paths genuinely exist) or after recovery at
110us (paths are alive again, so a stale draw there is a leftover, not a forced
one).

Output: ../data/c2_drain.csv -- one row per epoch:
  scenario, B, src, freeze_start_n, buf_size_at_freeze,
  n_frozen_draws, n_stale_draws, n_valid_draws,
  sends_to_last_stale, stale_during_kill, stale_after_recovery, outcome
  outcome in {no_stale_draws, cleared_before_unfreeze, stale_until_unfreeze}
"""
import csv
import gzip
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_c2 import SCEN, BS  # noqa: E402
from send_occupancy import frozen_pop_valid  # noqa: E402

C2 = HERE.parent
TRACES = C2 / "traces"
DATA = C2 / "data"
DRAW_EVENTS = {"SEND", "RTX", "RTS"}
KILL_END_NS = 110_000  # recover at t=110us, see ../PLAN.md


def analyse_cell(f, b):
    gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
    host_prev_slots = {}  # src -> raw slots string of the previous row
    epochs = {}  # src -> dict(...)
    rows_out = []

    def close(src, outcome):
        e = epochs.pop(src)
        rows_out.append(dict(
            scenario=SCEN[f], B=b, src=src, freeze_start_n=e["freeze_start_n"],
            buf_size_at_freeze=e["buf_size_at_freeze"],
            n_frozen_draws=e["n_frozen_draws"], n_stale_draws=e["n_stale_draws"],
            n_valid_draws=e["n_frozen_draws"] - e["n_stale_draws"],
            sends_to_last_stale=e["sends_to_last_stale"],
            stale_during_kill=e["stale_during_kill"],
            stale_after_recovery=e["stale_after_recovery"],
            outcome=outcome))

    with gzip.open(gz, "rt", newline="") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        ci = {k: head.index(k) for k in
              ("n", "src_id", "event", "ev_src", "time_ns", "frozen_mode",
               "frozen_head", "buf_size", "slots")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= 32:
                continue
            ev = row[ci["event"]]
            n = int(row[ci["n"]])
            t = float(row[ci["time_ns"]])

            if ev == "FREEZE":
                epochs[src] = dict(
                    freeze_start_n=n, buf_size_at_freeze=int(row[ci["buf_size"]]),
                    n_frozen_draws=0, n_stale_draws=0, sends_to_last_stale=0,
                    stale_during_kill=0, stale_after_recovery=0)
                host_prev_slots[src] = row[ci["slots"]]
                continue

            e = epochs.get(src)
            if e is None:
                host_prev_slots[src] = row[ci["slots"]]
                continue

            if ev == "UNFREEZE":
                close(src, "stale_until_unfreeze" if e["n_stale_draws"]
                           and e["sends_to_last_stale"] == e["n_frozen_draws"]
                           else ("no_stale_draws" if e["n_stale_draws"] == 0
                                 else "cleared_before_unfreeze"))
                host_prev_slots[src] = row[ci["slots"]]
                continue

            if ev in DRAW_EVENTS and int(row[ci["frozen_mode"]]) == 1:
                e["n_frozen_draws"] += 1
                ev_src = row[ci["ev_src"]]
                is_stale = False
                if ev_src == "frozen_pop" and host_prev_slots.get(src) is not None:
                    valid = frozen_pop_valid(host_prev_slots[src],
                                              int(row[ci["frozen_head"]]),
                                              int(row[ci["buf_size"]]))
                    is_stale = (valid is False)
                if is_stale:
                    e["n_stale_draws"] += 1
                    e["sends_to_last_stale"] = e["n_frozen_draws"]
                    if t < KILL_END_NS:
                        e["stale_during_kill"] += 1
                    else:
                        e["stale_after_recovery"] += 1
            host_prev_slots[src] = row[ci["slots"]]

    for src in list(epochs):
        close(src, "ongoing_at_trace_end")
    return rows_out


def write_csv(path, rows):
    if not rows:
        print("no epochs found at all -- nothing to write")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    all_rows = []
    for f in SCEN:
        for b in BS:
            gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
            if not gz.exists():
                print(f"SKIP F{f} B{b}: trace missing")
                continue
            rows = analyse_cell(f, b)
            all_rows += rows
            by_outcome = {}
            for r in rows:
                by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
            avg_sends = (sum(r["sends_to_last_stale"] for r in rows) / len(rows)) if rows else float("nan")
            print(f"F{f:>3} B={b:<4} epochs={len(rows):<4} avg_sends_to_last_stale={avg_sends:.1f} "
                  f"{by_outcome}", flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    write_csv(DATA / "c2_drain.csv", all_rows)
    print(f"\n{len(all_rows)} epochs total")


if __name__ == "__main__":
    main()

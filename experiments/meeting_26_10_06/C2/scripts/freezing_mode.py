#!/usr/bin/env python3
"""C2, F=16 only: the three C1-style diagnostics (send-time k, valid/
random/stale draw split, ACKs-per-SEND-to-SEND), restricted to draws that
happen WHILE frozen (frozen_mode==1 at draw time) -- i.e. during Freezing
Mode itself, not pooled with the surrounding normal-mode traffic.

Reuses C2's own existing classification logic (classify(), frozen_pop_valid())
from send_occupancy.py verbatim -- same frozen_pop valid/stale lookup
((frozen_head-1) % modulus in the PREVIOUS row of the same src), same
random==explore+random bucket. No new sim, no new trace: reads the traces
run_c2.py already wrote (``../traces/16MiB_x16_B<B>.csv.gz``).

k-histogram: a frozen-mode subset of what send_occupancy.py already
computes into c2_send_occupancy.csv (same (scenario,B,k,frozen_mode) key) --
not recomputed here, just re-read and filtered to frozen_mode==1.

a_i (ACKs-per-SEND-to-SEND window): same definition as C1's
acks_per_window.py (every ACK row since the previous draw, ECN-marked or
not), but the resulting count is only kept if the WINDOW'S OWN draw (the one
that closes it) is itself frozen_mode==1.

Writes: ../data/c2_freezing_split.csv, ../data/c2_freezing_acks.csv
(c2_send_occupancy.csv's own frozen_mode==1 rows are reused as-is for k).
"""
import csv
import gzip
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from send_occupancy import classify, frozen_pop_valid  # noqa: E402
from build_c2 import SCEN, BS, TOR0_HOSTS, arm_name  # noqa: E402

C2 = HERE.parent
TRACES = C2 / "traces"
DATA = C2 / "data"
F = 16  # this script only covers the failure cell -- F=0 never freezes
DRAW_EVENTS = {"SEND", "RTX", "RTS"}


def analyze_cell(b):
    gz = TRACES / f"16MiB_x{F}_B{b}.csv.gz"
    if not gz.exists():
        return None
    host = {}  # src -> seen_ack, last_fresh, acks_since_draw, prev_slots_raw
    split_counts = {"valid": 0, "random": 0, "stale": 0, "other": 0}
    a_hist = {}
    n_frozen_draws = 0
    with gzip.open(gz, "rt", newline="") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        ci = {k: head.index(k) for k in
              ("src_id", "event", "ev_src", "fresh", "ecn", "frozen_mode",
               "frozen_head", "buf_size", "slots")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= TOR0_HOSTS:
                continue
            ev = row[ci["event"]]
            st = host.setdefault(src, dict(seen_ack=False, last_fresh=0,
                                            acks_since_draw=0, prev_slots_raw=None))
            if ev == "ACK":
                if not st["seen_ack"]:
                    st["seen_ack"] = True
                else:
                    st["acks_since_draw"] += 1
            elif ev in DRAW_EVENTS and st["seen_ack"]:
                frozen_mode = int(row[ci["frozen_mode"]])
                if frozen_mode:
                    n_frozen_draws += 1
                    ev_src = row[ci["ev_src"]]
                    frozen_valid = None
                    if ev_src == "frozen_pop" and st["prev_slots_raw"] is not None:
                        frozen_valid = frozen_pop_valid(
                            st["prev_slots_raw"], int(row[ci["frozen_head"]]),
                            int(row[ci["buf_size"]]))
                    cls = classify(ev_src, frozen_valid)
                    split_counts[cls] += 1
                    n = st["acks_since_draw"]
                    a_hist[n] = a_hist.get(n, 0) + 1
                st["acks_since_draw"] = 0
            st["last_fresh"] = int(row[ci["fresh"]])
            st["prev_slots_raw"] = row[ci["slots"]]
    if n_frozen_draws == 0:
        return None
    split_row = dict(scenario=SCEN[F], B=b, n_frozen_draws=n_frozen_draws,
                      valid_frac=split_counts["valid"] / n_frozen_draws,
                      random_frac=split_counts["random"] / n_frozen_draws,
                      stale_frac=split_counts["stale"] / n_frozen_draws,
                      other_frac=split_counts["other"] / n_frozen_draws)
    a_rows = [dict(scenario=SCEN[F], B=b, n_acks=n, share=cnt / n_frozen_draws,
                    n_frozen_draws=n_frozen_draws) for n, cnt in sorted(a_hist.items())]
    return split_row, a_rows


def main():
    all_split, all_a = [], []
    for b in BS:
        r = analyze_cell(b)
        if r is None:
            print(f"SKIP B{b}: trace missing or no frozen-mode draws")
            continue
        split_row, a_rows = r
        all_split.append(split_row)
        all_a += a_rows
        print(f"B={b:<4} n_frozen_draws={split_row['n_frozen_draws']:<6} "
              f"valid={split_row['valid_frac']:.3f} random={split_row['random_frac']:.3f} "
              f"stale={split_row['stale_frac']:.3f} other={split_row['other_frac']:.3f}",
              flush=True)
    if not all_split:
        print("no cells with frozen-mode draws found")
        return
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA / "c2_freezing_split.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_split[0].keys()))
        w.writeheader()
        w.writerows(all_split)
    with open(DATA / "c2_freezing_acks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_a[0].keys()))
        w.writeheader()
        w.writerows(all_a)
    print("wrote", DATA / "c2_freezing_split.csv")
    print("wrote", DATA / "c2_freezing_acks.csv")


if __name__ == "__main__":
    main()

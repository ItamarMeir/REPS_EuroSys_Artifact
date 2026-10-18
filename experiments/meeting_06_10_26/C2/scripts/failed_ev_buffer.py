#!/usr/bin/env python3
"""C2 buffer-content metrics in Freezing Mode (F=16 cells only -- F=0 never freezes).

Two questions, both read from the `slots` column already in every C2 trace
(-log_reps_events_src 0..31, all 32 ToR0 hosts, already on):

1. Failed-EV (spine 0-15) buffer content and self-clearing speed: once the 16 ToR0
   uplinks die at t=10us, how much of the buffer still physically holds a dead EV, and
   how fast does that clear via ACK overwrite?
2. Good-EV (16-31) load spread while frozen: how evenly are frozen-mode sends spread
   across the 16 surviving paths, and does uneven spreading correlate with ECN/trim on
   those same paths?

Key correctness points (see ../../../../.claude/plans or PLAN.md for the full writeup;
caught by advisor review before this was written):

- `buf_size` column = CircularBufferREPS::getSize() = `count`, the number of array
  slots EVER WRITTEN so far (saturates at max_size once the buffer has filled once, see
  buffer_reps.cpp). A never-written slot defaults to value=0,isValid=false -- indistin-
  guishable from a real stale EV 0 by value alone. Only slot indices < buf_size are real
  (add() writes sequentially from index 0, so "first buf_size indices" == "written
  indices" exactly, until the first wraparound after which buf_size stays at max_size
  forever). Every slot-content query below restricts to index < buf_size.
- `isValid` means FRESH (not yet drawn), not WRITTEN. A slot drawn once (isValid=false)
  still holds its real cached EV until the next add() overwrites that index --
  remove_frozen() draws these "stale" slots exactly like valid ones. So "does the buffer
  physically hold EV X" counts written slots by `value` regardless of `isValid`.
- Failed EVs = spine indices 0-15 (`-timed_fail_tor_uplinks 0 16` kills fail_pipes'
  s=0..15). Good EVs = 16-31 (-paths 32, 16 survive).
- Metric 1's clock starts at kill onset (t=10us), not at each host's own FREEZE event --
  FREEZE lands tens of us after the kill (only good-path ACKs return in between, each
  one overwriting a slot via the still-unfrozen `head` pointer), so the buffer may
  already be partly/fully clean of failed EVs by the time FREEZE fires. That lag is
  itself reported, not just the time-to-zero.
- Metric 1's "time to zero" clock stops at recovery (t=110us), not at UNFREEZE: after
  110us the failed paths are alive again, so a failed EV reappearing post-recovery is
  healing (a fresh ACK from a now-live path), not leftover dirt.
- Metric 2's primary statistic is send-side load imbalance (paper's own Appendix B
  definition, lambda = max/mean - 1 over the 16 good EVs' frozen-mode send counts), not
  buffer-occupancy distinct-count -- the latter is structurally capped at both ends of
  the B range (B<16 can't reach "all distinct"; B>16 can't exceed 16 distinct out of B
  slots), so it's kept only as a secondary panel.

Outputs:
  ../data/c2_failed_ev_epochs.csv       one row per (src,B,epoch)
  ../data/c2_failed_ev_timeseries.csv   bucketed mean failed_n/buf_size vs time-since-kill, per B
  ../data/c2_good_ev_spread.csv         bucketed lambda, ecn_rate_good, trim_rate_good vs time-since-kill, per B
  ../data/c2_good_ev_buffer_occupancy.csv  bucketed mean n_distinct_good/n_good_slots, per B (secondary)
"""
import csv
import gzip
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_c2 import SCEN, BS  # noqa: E402

C2 = HERE.parent
TRACES = C2 / "traces"
DATA = C2 / "data"

DRAW_EVENTS = {"SEND", "RTX", "RTS"}
FAILED_LO, FAILED_HI = 0, 16   # [0,16)
GOOD_LO, GOOD_HI = 16, 32      # [16,32)
N_GOOD = GOOD_HI - GOOD_LO     # 16

KILL_START_NS = 10_000
KILL_END_NS = 110_000  # recovery, see ../PLAN.md
BUCKET_NS = 5_000      # 5us, per user decision


def parse_slots(raw):
    out = []
    for chunk in raw.split("|"):
        v, valid, life = chunk.split(":")
        out.append((int(v), valid != "0", int(life)))
    return out


def bucket_of(t_ns, t0_ns):
    return int((t_ns - t0_ns) // BUCKET_NS)


def analyse_cell(f, b):
    """Single pass over one cell's trace. Returns:
      epochs: list of per-(src,epoch) dicts (Metric 1)
      failed_buckets: dict[bucket] -> [sum(failed_n/buf_size), n] (Metric 1 series)
      lambda_buckets: dict[bucket] -> dict[ev in GOOD] -> send count (Metric 2 lambda)
      ecn_buckets: dict[bucket] -> dict(ack_good, ack_good_ecn, nack_good) (Metric 2 rates)
      occ_buckets: dict[bucket] -> [sum(n_distinct_good), sum(n_good_slots), n] (secondary)
    """
    gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
    host_prev_slots = {}     # src -> list of (value, isValid, lifetime), current snapshot
    host_buf_size = {}       # src -> current buf_size
    epochs_open = {}         # src -> dict(epoch state)
    epochs_out = []

    failed_buckets = {}      # bucket -> [sum_frac, n]
    lambda_buckets = {}      # bucket -> {ev: count}
    ecn_buckets = {}         # bucket -> dict(ack_good=0, ack_good_ecn=0, nack_good=0)
    occ_buckets = {}         # bucket -> [sum_distinct, sum_good_slots, n]

    def count_failed(src):
        slots = host_prev_slots.get(src)
        bs = host_buf_size.get(src, 0)
        if not slots or bs <= 0:
            return 0
        return sum(1 for v, _val, _life in slots[:bs] if FAILED_LO <= v < FAILED_HI)

    def close_epoch(src, outcome, t_now):
        e = epochs_open.pop(src)
        epochs_out.append(dict(
            scenario=SCEN[f], B=b, src=src,
            freeze_start_ns=e["freeze_t"], kill_to_freeze_lag_ns=e["freeze_t"] - KILL_START_NS,
            failed_n_at_freeze=e["failed_n_at_freeze"], buf_size_at_freeze=e["buf_size_at_freeze"],
            outcome=outcome,
            time_to_zero_ns=e["time_to_zero_ns"], events_to_zero=e["events_to_zero"]))

    with gzip.open(gz, "rt", newline="") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        ci = {k: head.index(k) for k in
              ("n", "src_id", "event", "ev", "ev_src", "ecn", "time_ns",
               "frozen_mode", "buf_size", "slots")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= 32:
                continue
            ev_kind = row[ci["event"]]
            t = float(row[ci["time_ns"]])
            n = int(row[ci["n"]])

            # Metric 1: track failed_n(t) time series from kill onset onward, per src,
            # regardless of frozen/epoch state (the "killed, not yet frozen" phase is
            # part of the point).
            if t >= KILL_START_NS:
                bu = bucket_of(t, KILL_START_NS)
                bs_now = int(row[ci["buf_size"]]) if row[ci["buf_size"]] not in ("", "-1") else host_buf_size.get(src, 0)
                if bs_now > 0:
                    slots_now = parse_slots(row[ci["slots"]])
                    failed_now = sum(1 for v, _val, _life in slots_now[:bs_now]
                                      if FAILED_LO <= v < FAILED_HI)
                    acc = failed_buckets.setdefault(bu, [0.0, 0])
                    acc[0] += failed_now / bs_now
                    acc[1] += 1

            if ev_kind == "FREEZE":
                fn = count_failed(src)
                epochs_open[src] = dict(
                    freeze_t=t, freeze_n=n, failed_n_at_freeze=fn,
                    buf_size_at_freeze=host_buf_size.get(src, 0),
                    time_to_zero_ns=None, events_to_zero=None,
                    reached_zero=(fn == 0), clock_stopped=False)
                if fn == 0:
                    epochs_open[src]["time_to_zero_ns"] = t - KILL_START_NS
                    epochs_open[src]["events_to_zero"] = 0
                host_prev_slots[src] = parse_slots(row[ci["slots"]])
                host_buf_size[src] = int(row[ci["buf_size"]])
                continue

            e = epochs_open.get(src)
            if e is not None and ev_kind != "UNFREEZE":
                if not e["clock_stopped"]:
                    if t >= KILL_END_NS:
                        e["clock_stopped"] = True
                    elif not e["reached_zero"]:
                        fn_now = count_failed(src)
                        if fn_now == 0:
                            e["reached_zero"] = True
                            e["time_to_zero_ns"] = t - KILL_START_NS
                            e["events_to_zero"] = n - e["freeze_n"]

            if ev_kind == "UNFREEZE":
                if e is not None:
                    outcome = ("cleared_before_recovery" if e["reached_zero"]
                                else "not_cleared_before_recovery")
                    close_epoch(src, outcome, t)
                host_prev_slots[src] = parse_slots(row[ci["slots"]])
                host_buf_size[src] = int(row[ci["buf_size"]])
                continue

            # Metric 2: frozen-mode draws -> lambda buckets; ACK/NACK on good EVs -> ecn/trim buckets.
            if t >= KILL_START_NS:
                bu = bucket_of(t, KILL_START_NS)
                if ev_kind in DRAW_EVENTS and int(row[ci["frozen_mode"]]) == 1:
                    ev_id = int(row[ci["ev"]])
                    if GOOD_LO <= ev_id < GOOD_HI:
                        d = lambda_buckets.setdefault(bu, {})
                        d[ev_id] = d.get(ev_id, 0) + 1
                elif ev_kind in ("ACK", "NACK"):
                    ev_id = int(row[ci["ev"]])
                    if GOOD_LO <= ev_id < GOOD_HI:
                        d = ecn_buckets.setdefault(bu, dict(ack_good=0, ack_good_ecn=0, nack_good=0))
                        if ev_kind == "ACK":
                            d["ack_good"] += 1
                            if row[ci["ecn"]] == "1":
                                d["ack_good_ecn"] += 1
                        else:
                            d["nack_good"] += 1

                # secondary occupancy view, only meaningful while frozen
                if int(row[ci["frozen_mode"]]) == 1:
                    bs_now = int(row[ci["buf_size"]])
                    if bs_now > 0:
                        slots_now = parse_slots(row[ci["slots"]])
                        good_vals = [v for v, _val, _life in slots_now[:bs_now] if GOOD_LO <= v < GOOD_HI]
                        if good_vals:
                            acc = occ_buckets.setdefault(bu, [0, 0, 0])
                            acc[0] += len(set(good_vals))
                            acc[1] += len(good_vals)
                            acc[2] += 1

            host_prev_slots[src] = parse_slots(row[ci["slots"]])
            host_buf_size[src] = int(row[ci["buf_size"]])

    for src in list(epochs_open):
        # Trace ended mid-epoch (no UNFREEZE seen) -- distinct from a clean
        # "never cleared before recovery" verdict, since we don't know what
        # would have happened next.
        e = epochs_open[src]
        outcome = "cleared_before_recovery" if e["reached_zero"] else "ongoing_at_trace_end"
        close_epoch(src, outcome, -1)

    return epochs_out, failed_buckets, lambda_buckets, ecn_buckets, occ_buckets


def lambda_of(counts_by_ev):
    vals = [counts_by_ev.get(ev, 0) for ev in range(GOOD_LO, GOOD_HI)]
    mean = sum(vals) / N_GOOD
    if mean <= 0:
        return None
    return max(vals) / mean - 1


def write_csv(path, rows):
    if not rows:
        print(f"no rows for {path.name} -- nothing to write")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    all_epochs, failed_series, spread_series, occ_series = [], [], [], []
    for f, scname in SCEN.items():
        if f == 0:
            continue  # healthy never freezes -- nothing to measure
        for b in BS:
            gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
            if not gz.exists():
                print(f"SKIP F{f} B{b}: trace missing")
                continue
            epochs, failed_buckets, lambda_buckets, ecn_buckets, occ_buckets = analyse_cell(f, b)
            all_epochs += epochs

            for bu, (sum_frac, n) in sorted(failed_buckets.items()):
                failed_series.append(dict(scenario=scname, B=b, bucket_start_ns=bu * BUCKET_NS,
                                           mean_failed_frac=sum_frac / n, n=n))

            all_bu = sorted(set(lambda_buckets) | set(ecn_buckets))
            for bu in all_bu:
                lam = lambda_of(lambda_buckets.get(bu, {})) if bu in lambda_buckets else None
                ec = ecn_buckets.get(bu, dict(ack_good=0, ack_good_ecn=0, nack_good=0))
                ack_g, ack_ge, nack_g = ec["ack_good"], ec["ack_good_ecn"], ec["nack_good"]
                ecn_rate = (ack_ge / ack_g) if ack_g else None
                trim_rate = (nack_g / (ack_g + nack_g)) if (ack_g + nack_g) else None
                spread_series.append(dict(
                    scenario=scname, B=b, bucket_start_ns=bu * BUCKET_NS,
                    lambda_imbalance=lam if lam is not None else "",
                    ecn_rate_good=ecn_rate if ecn_rate is not None else "",
                    trim_rate_good=trim_rate if trim_rate is not None else "",
                    n_sends_good=sum(lambda_buckets.get(bu, {}).values()),
                    n_ack_good=ack_g, n_nack_good=nack_g))

            for bu, (sum_d, sum_g, n) in sorted(occ_buckets.items()):
                occ_series.append(dict(scenario=scname, B=b, bucket_start_ns=bu * BUCKET_NS,
                                        mean_n_distinct_good=sum_d / n, mean_n_good_slots=sum_g / n, n=n))

            by_outcome = {}
            for e in epochs:
                by_outcome[e["outcome"]] = by_outcome.get(e["outcome"], 0) + 1
            print(f"F{f:>3} B={b:<4} epochs={len(epochs):<4} {by_outcome}", flush=True)

    DATA.mkdir(parents=True, exist_ok=True)
    write_csv(DATA / "c2_failed_ev_epochs.csv", all_epochs)
    write_csv(DATA / "c2_failed_ev_timeseries.csv", failed_series)
    write_csv(DATA / "c2_good_ev_spread.csv", spread_series)
    write_csv(DATA / "c2_good_ev_buffer_occupancy.csv", occ_series)
    print(f"\n{len(all_epochs)} epochs, {len(failed_series)} failed-series rows, "
          f"{len(spread_series)} spread rows, {len(occ_series)} occupancy rows")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""C3 analysis: src0-only, srcaddr-keyed (NOT src_id-keyed -- see PLAN.md's
blocking pitfall). Every cell's trace only ever contains srcaddr=0 rows
(C1/C2 style -log_reps_events_src is restricted to src0's burst node_nums by
run_c3.py), but src_id (== node_num) changes once per burst. Any "previous
row for this host" lookup MUST carry state across that src_id change -- this
script never resets per-host state on a src_id change, only on srcaddr change
(which never happens within one file).

Per cell (cm_stem, B, seed), computes:
  - per-burst FCT (from stdout finish/start lines, node_num -> burst_index
    read from the cm's schedule.json)
  - per-boundary (burst k -> k+1) observed-fresh-at-first-draw vs predicted
    min(B, tail), tail = clean ACKs of burst k arriving after its last plain
    SEND, minus any draws in that same window (RTX/RTS competing for the
    same refill)
  - N=16 only: valid-draw decay by send-index within each burst (one row per
    (burst_index, send_index) -> ev_src class)

Outputs:
  ../data/c3_fct.csv        cm_stem,B,seed,N,burst_index,start_us,finish_us,fct_us
  ../data/c3_boundary.csv   cm_stem,B,seed,N,boundary,observed_fresh,tail,predicted,cwnd_pkts_end
  ../data/c3_decay.csv      cm_stem,B,seed,burst_index,send_index,ev_src,fresh   (N=16 cells only)
  ../data/c3_checks.csv     one row per cell: verification (see RUNNING below)
"""
import csv
import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
C3 = HERE.parent
TRACES = C3 / "traces"
DATA = C3 / "data"
CM_DIR = Path("/workspace/htsim/sim/datacenter/connection_matrices") \
    if Path("/workspace").exists() else Path("../../..") / "htsim/sim/datacenter/connection_matrices"

BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
SEEDS = [42, 43, 44]
CM_STEMS = ["c3_n1_drained", "c3_n4_drained", "c3_n16_drained", "c3_n4_longgap"]

DRAW_EVENTS = {"SEND", "RTX", "RTS"}
START_RE = re.compile(r"Flow Uec_\d+_\d+ flowId \d+ uecSrc (\d+) starting at ([\d.]+)")
# "finished at" is the FLOW'S OWN elapsed duration since ITS start line (==
# FCT directly) -- NOT absolute sim time, except trivially when start==0
# (which is why C1/C2, whose one flow always starts at t=0, never hit this).
# "sim time" on the same line IS the absolute end time. For src0's bursts
# after the first (nonzero start), these two differ -- confirmed directly:
# "uecSrc 1 starting at 125.572 ... finished at 97.5507 ... sim time 223.122"
# (125.572 + 97.5507 == 223.122, not 97.5507). Use "finished at" for fct_us,
# "sim time" for the absolute end time needed for overlap/ordering checks.
FIN_RE = re.compile(
    r"Flow Uec_\d+_\d+ flowId \d+ uecSrc (\d+) finished at ([\d.]+).*?sim time ([\d.]+)")


def burst_meta(cm_stem):
    sidecar = json.loads((CM_DIR / f"{cm_stem}.schedule.json").read_text())
    node_to_burst = {b["node_num"]: b["burst_index"] for b in sidecar["bursts"]}
    return sidecar["N"], node_to_burst


def parse_stdout_times(stdout_path, node_nums):
    """node_num -> start_us (absolute), fct_us (own duration), abs_finish_us."""
    text = stdout_path.read_text(errors="replace")
    start = {}
    fct = {}
    abs_finish = {}
    for src, st in START_RE.findall(text):
        src = int(src)
        if src in node_nums:
            start[src] = float(st)
    for src, fin, simtime in FIN_RE.findall(text):
        src = int(src)
        if src in node_nums:
            fct[src] = float(fin)
            abs_finish[src] = float(simtime)
    return start, fct, abs_finish


def analyze_cell(cm_stem, b, seed):
    N, node_to_burst = burst_meta(cm_stem)
    node_nums = sorted(node_to_burst)
    run_dir = C3 / "runs" / cm_stem / f"seed{seed}" / f"reps_b{b}_nscc"
    stdout_path = run_dir / "stdout.txt"
    gz = TRACES / f"{cm_stem}_seed{seed}_B{b}.csv.gz"
    if not stdout_path.exists() or not gz.exists():
        return None

    start_us, fct_us_map, abs_finish_us = parse_stdout_times(stdout_path, set(node_nums))
    fct_rows = []
    for n in node_nums:
        k = node_to_burst[n]
        if n in start_us and n in fct_us_map:
            fct_rows.append(dict(cm_stem=cm_stem, B=b, seed=seed, N=N, burst_index=k,
                                  start_us=start_us[n], finish_us=abs_finish_us[n],
                                  fct_us=fct_us_map[n]))

    # Single streaming pass, rows already in time order (file write order).
    # last_fresh/last_src_id persist across the src_id (burst) boundary --
    # that persistence IS the fix for the blocking pitfall.
    last_fresh = 0
    last_src_id = None
    cur_burst_rows = []          # rows of the burst currently being accumulated
    bursts_rows = {}             # burst_index -> list of rows (time, event, ev_src, ecn, fresh, cwnd_pkts)
    boundary_rows = []
    decay_rows = []
    is_n16 = (N == 16)

    def flush_burst(src_id, rows):
        if src_id is not None and node_to_burst.get(src_id) is not None:
            bursts_rows[node_to_burst[src_id]] = rows

    with gzip.open(gz, "rt", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        ci = {k: head.index(k) for k in
              ("time_ns", "src_id", "event", "ev_src", "ecn", "fresh", "cwnd_pkts")}
        send_idx_in_burst = 0
        for row in rd:
            src_id = int(row[ci["src_id"]])
            if src_id != last_src_id:
                flush_burst(last_src_id, cur_burst_rows)
                cur_burst_rows = []
                send_idx_in_burst = 0
                k = node_to_burst.get(src_id)
                if k is not None and k >= 1:
                    # boundary (k-1 -> k): observed fresh-at-first-draw is
                    # last_fresh carried in from the PREVIOUS burst's last row
                    boundary_rows.append(dict(boundary=k - 1, observed_fresh=last_fresh))
                last_src_id = src_id
            event = row[ci["event"]]
            ev_src = row[ci["ev_src"]]
            ecn = row[ci["ecn"]]
            fresh = int(row[ci["fresh"]])
            t_ns = float(row[ci["time_ns"]])
            cwnd = int(row[ci["cwnd_pkts"]])
            cur_burst_rows.append((t_ns, event, ev_src, ecn, fresh, cwnd))
            if event in DRAW_EVENTS:
                if is_n16:
                    k = node_to_burst.get(src_id)
                    if k is not None:
                        decay_rows.append(dict(cm_stem=cm_stem, B=b, seed=seed,
                                                burst_index=k, send_index=send_idx_in_burst,
                                                ev_src=ev_src, fresh=fresh))
                send_idx_in_burst += 1
            last_fresh = fresh
        flush_burst(last_src_id, cur_burst_rows)

    for brow in boundary_rows:
        k = brow["boundary"]
        prev_rows = bursts_rows.get(k, [])
        last_plain_send_t = max((t for t, ev, _, _, _, _ in prev_rows if ev == "SEND"),
                                 default=None)
        cwnd_end = prev_rows[-1][5] if prev_rows else None
        if last_plain_send_t is None:
            tail = 0
        else:
            clean_acks = sum(1 for t, ev, _, ecn, _, _ in prev_rows
                              if ev == "ACK" and ecn == "0" and t > last_plain_send_t)
            draws_after = sum(1 for t, ev, _, _, _, _ in prev_rows
                               if ev in DRAW_EVENTS and t > last_plain_send_t)
            tail = max(0, clean_acks - draws_after)
        boundary_rows_out = dict(cm_stem=cm_stem, B=b, seed=seed, N=N, boundary=k,
                                  observed_fresh=brow["observed_fresh"], tail=tail,
                                  predicted=min(b, tail), cwnd_pkts_end=cwnd_end)
        brow.clear()
        brow.update(boundary_rows_out)

    checks = dict(
        cm_stem=cm_stem, B=b, seed=seed, N=N,
        n_bursts_with_fct=len(fct_rows), n_bursts_expected=N,
        fct_complete=(len(fct_rows) == N),
        n_boundaries=len(boundary_rows), n_boundaries_expected=max(0, N - 1),
        boundaries_complete=(len(boundary_rows) == max(0, N - 1)),
    )
    return fct_rows, boundary_rows, decay_rows, checks


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    all_fct, all_boundary, all_decay, all_checks = [], [], [], []
    for stem in CM_STEMS:
        for b in BS:
            for seed in SEEDS:
                result = analyze_cell(stem, b, seed)
                if result is None:
                    print(f"SKIP {stem} B{b} seed{seed}: data missing")
                    continue
                fct_rows, boundary_rows, decay_rows, checks = result
                all_fct += fct_rows
                all_boundary += boundary_rows
                all_decay += decay_rows
                all_checks.append(checks)
                print(f"{stem:16s} B{b:<4} seed{seed}: "
                      f"fct_complete={checks['fct_complete']} "
                      f"boundaries_complete={checks['boundaries_complete']}", flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    write_csv(DATA / "c3_fct.csv", all_fct)
    write_csv(DATA / "c3_boundary.csv", all_boundary)
    write_csv(DATA / "c3_decay.csv", all_decay)
    write_csv(DATA / "c3_checks.csv", all_checks)
    bad = [c for c in all_checks if not (c["fct_complete"] and c["boundaries_complete"])]
    print(f"\n{len(all_checks)} cells analyzed, {len(bad)} with a failed check")
    for c in bad:
        print("FAILED CHECK:", c)


if __name__ == "__main__":
    main()

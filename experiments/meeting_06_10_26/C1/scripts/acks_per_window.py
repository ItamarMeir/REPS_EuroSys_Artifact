#!/usr/bin/env python3
"""C1: distribution of ACK count per SEND-to-SEND window, over all 32 ToR0
hosts -- the mechanism behind the k>=4 cases in send_occupancy.py's k
distribution (see RESULTS.md / interactive page conclusion).

Same population as send_occupancy.py's k plot, exactly: all post-warmup
SEND/RTX/RTS draws (after a host's first ACK), no other restriction -- so
the histogram's total ties out 1:1 against n_sends_post in c1_send_checks.csv.
A window's ACK count is the number of ACK rows since the PREVIOUS draw (0 for
a window immediately following a random draw with no intervening ACK yet).

Mean ACKs/window is NOT the right summary here: every packet is ACKed once,
so over a whole flow sum(ACKs) == sum(draws) and the mean is pinned near 1.0
regardless of B -- that is conservation, not evidence against k>=4 occurring.
k is a running sum (each clean ACK is +1, each fresh_pop draw is -1), so
k>=4 comes from several 2-ACK windows CLUSTERING, not from a high mean. This
script reports the full distribution (0,1,2,3,4,5+ ACKs per window) instead.

Also verifies the mechanism directly (not just inferred): for every ACK row,
checks fresh_after - fresh_before == 1 if ecn==0 else == 0 -- i.e. k only
moves via (ACK ecn=0 -> +1) and (fresh_pop draw -> -1), nothing else.

Writes (per CC):
  <CC>/data/c1_acks_per_window.csv       scenario,B,n_acks,share,n_sends_post
  <CC>/data/c1_acks_per_window_gaps.csv  scenario,B,gap_median_ns,gap_p99_ns,
    gap_max_ns,frac_gap_gt_2x_median (same population, SEND-to-SEND gap stats,
    for the "no other pause source" check)
"""
import argparse
import csv
import gzip
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
C1 = HERE.parent
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
SCEN = {0: "healthy", 32: "32 ToR0 uplinks at 50%"}
TOR0 = 32
DRAW_EVENTS = {"SEND", "RTX", "RTS"}


def analyze_cell(cc_label, x, b):
    gz = C1 / cc_label / "traces" / f"16MiB_x{x}_B{b}.csv.gz"
    if not gz.exists():
        return None
    host = {}  # src -> dict(seen_ack, acks_since_draw, last_draw_t, last_fresh)
    hist = {}
    gaps = []
    fresh_mismatches = 0
    n_acks_checked = 0
    with gzip.open(gz, "rt", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        ci = {k: head.index(k) for k in ("src_id", "time_ns", "event", "ecn", "fresh")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= TOR0:
                continue
            st = host.setdefault(src, dict(seen_ack=False, acks_since_draw=0,
                                            last_draw_t=None, last_fresh=0))
            ev = row[ci["event"]]
            fresh = int(row[ci["fresh"]])
            t = float(row[ci["time_ns"]])
            if ev == "ACK":
                if not st["seen_ack"]:
                    st["seen_ack"] = True
                else:
                    ecn = row[ci["ecn"]]
                    expect = 1 if ecn == "0" else 0
                    got = fresh - st["last_fresh"]
                    if got != expect:
                        # Only "explained" mismatch: buffer already at capacity
                        # (fresh==B) when a clean ACK arrives, so it can't add
                        # another valid slot -- not a break in the model.
                        if not (ecn == "0" and got == 0 and st["last_fresh"] >= b):
                            fresh_mismatches += 1
                    n_acks_checked += 1
                st["acks_since_draw"] += 1
            elif ev in DRAW_EVENTS and st["seen_ack"]:
                n = st["acks_since_draw"]
                hist[n] = hist.get(n, 0) + 1
                if st["last_draw_t"] is not None:
                    gaps.append(t - st["last_draw_t"])
                st["last_draw_t"] = t
                st["acks_since_draw"] = 0
            st["last_fresh"] = fresh
    if not hist:
        return None
    n_total = sum(hist.values())
    rows_hist = [dict(scenario=SCEN[x], B=b, n_acks=n, share=cnt / n_total,
                       n_sends_post=n_total) for n, cnt in sorted(hist.items())]
    if gaps:
        gaps_sorted = sorted(gaps)
        n = len(gaps_sorted)
        median = gaps_sorted[n // 2]
        stalls = sum(1 for g in gaps if g > 2 * median)
        gap_row = dict(scenario=SCEN[x], B=b, gap_median_ns=median,
                       gap_p99_ns=gaps_sorted[int(n * 0.99)], gap_max_ns=gaps_sorted[-1],
                       frac_gap_gt_2x_median=stalls / n)
    else:
        gap_row = dict(scenario=SCEN[x], B=b, gap_median_ns=None, gap_p99_ns=None,
                       gap_max_ns=None, frac_gap_gt_2x_median=None)
    return rows_hist, gap_row, dict(n_acks_checked=n_acks_checked, fresh_mismatches=fresh_mismatches)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", choices=["mprdma", "nscc"], default="mprdma")
    args = ap.parse_args()
    cc_label = "MPRDMA" if args.cc == "mprdma" else "NSCC"
    all_hist, all_gaps = [], []
    total_checked = total_mismatch = 0
    for x in SCEN:
        for b in BS:
            r = analyze_cell(cc_label, x, b)
            if r is None:
                print(f"SKIP {cc_label} x{x} B{b}: trace missing or empty")
                continue
            rows_hist, gap_row, check = r
            all_hist += rows_hist
            all_gaps.append(gap_row)
            total_checked += check["n_acks_checked"]
            total_mismatch += check["fresh_mismatches"]
            dist = {r2["n_acks"]: r2["share"] for r2 in rows_hist}
            print(f"{cc_label} {SCEN[x]:30s} B={b:<4} "
                  f"n_sends_post={rows_hist[0]['n_sends_post']:<7} "
                  f"dist={{{', '.join(f'{k}:{v:.4f}' for k,v in sorted(dist.items()))}}} "
                  f"gap_median={gap_row['gap_median_ns']:.2f}ns "
                  f"frac_gap_gt_2x_median={gap_row['frac_gap_gt_2x_median']:.5f} "
                  f"fresh_mismatches={check['fresh_mismatches']}/{check['n_acks_checked']}",
                  flush=True)
    out_hist = C1 / cc_label / "data" / "c1_acks_per_window.csv"
    out_gaps = C1 / cc_label / "data" / "c1_acks_per_window_gaps.csv"
    out_hist.parent.mkdir(parents=True, exist_ok=True)
    with open(out_hist, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_hist[0].keys()))
        w.writeheader()
        w.writerows(all_hist)
    with open(out_gaps, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_gaps[0].keys()))
        w.writeheader()
        w.writerows(all_gaps)
    print("wrote", out_hist)
    print("wrote", out_gaps)
    print(f"\nTotal fresh-delta mismatches (ACK ecn=0 -> +1, ecn=1 -> +0): "
          f"{total_mismatch}/{total_checked}")


if __name__ == "__main__":
    main()

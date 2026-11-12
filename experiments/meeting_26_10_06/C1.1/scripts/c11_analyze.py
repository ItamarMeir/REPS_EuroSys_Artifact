#!/usr/bin/env python3
"""C1.1 analysis: for each (rate, cwnd, fixed_q) cell's events.csv, compute
send-time k (valid EVs just before a draw, same definition as C1's
send_occupancy.py), a_i (clean ACKs per send-to-send window, C1's
acks_per_window.py), per-packet RTT via seqno matching (SEND<->ACK), and the
derived ΔRTT/T_s collapse quantities. See plan: ``C1.1: is REPS buffer
pile-up (k) predictable from serialization time + ACK jitter?``.

Single streaming pass per cell's events.csv (not gzipped here, unlike C1's
archived traces). src_id < 32 only (ToR0, all logged here anyway since every
cell logs -log_reps_events_src 0..31).

Outputs (data/):
  c11_k.csv          cell,k,n_sends,share            (send-time k distribution)
  c11_checks.csv      cell,...                        (per-cell verification)
  c11_acks_window.csv cell,n_acks,share,n_sends        (a_i histogram)
  c11_collapse.csv    cell,rate_mbps,fixed_q,cwnd,T_s_ns,dRTT_std_ns,
                       dRTT_over_Ts,mean_k,p_k_ge2,max_k,recursion_residual
"""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
C11 = HERE.parent
RUNS = C11 / "runs"
DATA = C11 / "data"

DRAW_EVENTS = {"SEND", "RTX", "RTS"}
TOR0 = 32
MTU_BITS = 4096 * 8  # data_packet_size() in main_uec.cpp default, bytes*8


def rate_mbps_of(cell: str) -> int:
    # cell tag: "<rate>g[_fixedq]_cwnd<N>"
    return int(cell.split("g")[0]) * 1000


def cwnd_of(cell: str) -> int:
    return int(cell.rsplit("cwnd", 1)[1])


def is_fixed_q(cell: str) -> bool:
    return "_fixedq_" in cell


def iter_cells():
    for d in sorted(RUNS.iterdir()):
        if (d / "events.csv").exists():
            yield d.name


def load_rows(cell: str):
    path = RUNS / cell / "events.csv"
    with open(path, newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        ci = {k: head.index(k) for k in
              ("n", "time_ns", "src_id", "event", "ecn", "seqno", "fresh")}
        rows = []
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= TOR0:
                continue
            rows.append(dict(
                n=int(row[ci["n"]]), t=float(row[ci["time_ns"]]), src=src,
                event=row[ci["event"]], ecn=row[ci["ecn"]],
                seqno=int(row[ci["seqno"]]), fresh=int(row[ci["fresh"]])))
    # group by src, keep each src's own chronological order (n is global
    # monotonic, so sorting by n within a src group recovers that host's
    # own event order)
    by_src: dict[int, list] = {}
    for r in rows:
        by_src.setdefault(r["src"], []).append(r)
    for src in by_src:
        by_src[src].sort(key=lambda r: r["n"])
    return by_src


def analyze_k_and_acks(by_src: dict[int, list]):
    """Send-time k (pre-draw valid count) and a_i (clean ACKs per window),
    same definitions as C1's send_occupancy.py / acks_per_window.py."""
    k_counts: dict[int, int] = {}
    acks_hist: dict[int, int] = {}
    k_sequence: list[tuple[int, int]] = []  # (src, k) in send order, for the recursion check
    a_sequence: list[tuple[int, int]] = []  # (src, a_i) aligned 1:1 with k_sequence
    for src, rows in by_src.items():
        seen_ack = False
        last_fresh = 0
        acks_since_draw = 0
        for r in rows:
            ev = r["event"]
            if ev == "ACK":
                if not seen_ack:
                    seen_ack = True
                elif r["ecn"] == "0":
                    acks_since_draw += 1
            elif ev in DRAW_EVENTS and seen_ack:
                k = last_fresh
                k_counts[k] = k_counts.get(k, 0) + 1
                acks_hist[acks_since_draw] = acks_hist.get(acks_since_draw, 0) + 1
                k_sequence.append((src, k))
                a_sequence.append((src, acks_since_draw))
                acks_since_draw = 0
            last_fresh = r["fresh"]
    return k_counts, acks_hist, k_sequence, a_sequence


def analyze_send_gaps(by_src: dict[int, list]):
    """Post-warmup SEND-to-SEND (draw-to-draw) gaps, pooled over all ToR0
    hosts -- direct check of the user's own framing: is the gap (1) tight/
    consistent within a cell under backlog, (2) equal to the precomputed
    T_s = MTU_bits/rate?"""
    gaps = []
    for src, rows in by_src.items():
        seen_ack = False
        last_t = None
        for r in rows:
            if r["event"] == "ACK" and not seen_ack:
                seen_ack = True
            elif r["event"] in DRAW_EVENTS and seen_ack:
                if last_t is not None:
                    gaps.append(r["t"] - last_t)
                last_t = r["t"]
    return gaps


def analyze_rtt(by_src: dict[int, list]):
    """Per-packet RTT via seqno match: a SEND/RTX/RTS row's seqno is the PSN
    it puts on the wire; the first later ACK row (same src) with that seqno
    is its ack. Returns the pooled RTT list (ns), across all ToR0 hosts."""
    rtts = []
    for src, rows in by_src.items():
        pending: dict[int, float] = {}
        for r in rows:
            if r["event"] in DRAW_EVENTS:
                pending[r["seqno"]] = r["t"]
            elif r["event"] == "ACK":
                t_send = pending.pop(r["seqno"], None)
                if t_send is not None:
                    rtts.append(r["t"] - t_send)
    return rtts


def serialization_time_ns(rate_mbps: int) -> float:
    # rate_mbps Mbps = rate_mbps*1e-3 bits/ns -> time_ns = bits / (bits/ns)
    return MTU_BITS * 1000.0 / rate_mbps


def recursion_check(k_sequence, a_sequence, b_cap: int):
    """One-step predictor: k_i (pre-draw, measured) should equal
    min(B, post_pop(k_{i-1}) + a_i), where post_pop(k)=max(k-1,0) --
    draw i-1 pops one EV only if it had k_{i-1}>0 (a fresh_pop; k_{i-1}==0
    draws random instead, no pop), then a_i clean ACKs arrive before draw i.
    Uses the MEASURED k_{i-1} each step (not a chained running prediction),
    so this tests the one-step transition rule itself, same spirit as
    send_occupancy.py's own fresh_pop/random reconstruction check.
    Returns (n_checked, n_mismatch)."""
    by_src_k: dict[int, list[int]] = {}
    by_src_a: dict[int, list[int]] = {}
    for (src, k), (src2, a) in zip(k_sequence, a_sequence):
        assert src == src2
        by_src_k.setdefault(src, []).append(k)
        by_src_a.setdefault(src, []).append(a)
    n_checked = n_mismatch = 0
    for src, ks in by_src_k.items():
        ascii_ = by_src_a[src]
        for i in range(1, len(ks)):
            post_pop_prev = ks[i - 1] - 1 if ks[i - 1] > 0 else 0
            predicted = min(b_cap, post_pop_prev + ascii_[i])
            n_checked += 1
            if predicted != ks[i]:
                n_mismatch += 1
    return n_checked, n_mismatch


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b-cap", type=int, default=256)
    args = ap.parse_args()

    k_rows, acks_rows, checks_rows, collapse_rows = [], [], [], []
    for cell in iter_cells():
        print(f"analyzing {cell} ...", flush=True)
        by_src = load_rows(cell)
        k_counts, acks_hist, k_seq, a_seq = analyze_k_and_acks(by_src)
        n_post = sum(k_counts.values())
        for k, n in sorted(k_counts.items()):
            k_rows.append(dict(cell=cell, k=k, n_sends=n, share=n / n_post))
        for n_acks, n in sorted(acks_hist.items()):
            acks_rows.append(dict(cell=cell, n_acks=n_acks, share=n / n_post,
                                   n_sends=n_post))

        rtts = analyze_rtt(by_src)
        rtt_mean = statistics.fmean(rtts) if rtts else float("nan")
        drtt_std = statistics.pstdev(rtts) if len(rtts) > 1 else float("nan")
        rate = rate_mbps_of(cell)
        ts_ns = serialization_time_ns(rate)

        gaps = analyze_send_gaps(by_src)
        gaps_sorted = sorted(gaps)
        ng = len(gaps_sorted)
        gap_median = gaps_sorted[ng // 2] if ng else float("nan")
        gap_mean = statistics.fmean(gaps) if gaps else float("nan")
        gap_std = statistics.pstdev(gaps) if ng > 1 else float("nan")
        gap_p99 = gaps_sorted[int(ng * 0.99)] if ng else float("nan")
        gap_max = gaps_sorted[-1] if ng else float("nan")
        print(f"  SEND-gap: n={ng} median={gap_median:.3f}ns mean={gap_mean:.3f}ns "
              f"std={gap_std:.3f}ns p99={gap_p99:.3f}ns max={gap_max:.3f}ns "
              f"  predicted T_s={ts_ns:.3f}ns  median/T_s={gap_median / ts_ns:.4f}",
              flush=True)
        mean_k = sum(k * n for k, n in k_counts.items()) / n_post if n_post else float("nan")
        p_k_ge2 = sum(n for k, n in k_counts.items() if k >= 2) / n_post if n_post else float("nan")
        max_k = max(k_counts) if k_counts else -1

        n_checked, n_mismatch = recursion_check(k_seq, a_seq, args.b_cap)

        checks_rows.append(dict(
            cell=cell, hosts=len(by_src), n_sends_post=n_post,
            max_k=max_k, capacity_ok=(max_k <= args.b_cap),
            p_k0=k_counts.get(0, 0) / n_post if n_post else float("nan"),
            n_rtt_samples=len(rtts),
            recursion_checked=n_checked, recursion_mismatch=n_mismatch,
            recursion_ok=(n_mismatch == 0)))

        collapse_rows.append(dict(
            cell=cell, rate_mbps=rate, fixed_q=is_fixed_q(cell), cwnd=cwnd_of(cell),
            T_s_ns=ts_ns, dRTT_std_ns=drtt_std,
            dRTT_over_Ts=(drtt_std / ts_ns if ts_ns else float("nan")),
            mean_k=mean_k, p_k_ge2=p_k_ge2, max_k=max_k,
            recursion_mismatch=n_mismatch))

        print(f"  n_post={n_post} mean_k={mean_k:.3f} p_k_ge2={p_k_ge2:.4f} "
              f"max_k={max_k} RTT_mean={rtt_mean:.1f}ns dRTT_std={drtt_std:.1f}ns "
              f"T_s={ts_ns:.2f}ns dRTT/Ts={collapse_rows[-1]['dRTT_over_Ts']:.3f} "
              f"recursion_mismatch={n_mismatch}/{n_checked}", flush=True)

    DATA.mkdir(parents=True, exist_ok=True)
    write_csv(DATA / "c11_k.csv", k_rows)
    write_csv(DATA / "c11_acks_window.csv", acks_rows)
    write_csv(DATA / "c11_checks.csv", checks_rows)
    write_csv(DATA / "c11_collapse.csv", collapse_rows)
    print(f"\n{len(checks_rows)} cells analyzed.")


if __name__ == "__main__":
    main()

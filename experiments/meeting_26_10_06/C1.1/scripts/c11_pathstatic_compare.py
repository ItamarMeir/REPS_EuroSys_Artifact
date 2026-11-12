#!/usr/bin/env python3
"""C1.1: matched-pair comparison at 400G -- freezing (B=256) vs path_static
(no buffer), same cwnd=127/Q=101/ECN=25,76. Builds the data payload for
plots/pathstatic_compare.html.

Key fix vs c11_analyze.py: T_s uses the real on-wire packet size (4150 B,
main_uec.cpp:302 `packet_size` default -- confirmed by the exact gap-value
match 332.00/337.12/342.24 ns at 100G for m=0/1/2 interleaved ACKs), not
4096 B.

Chained k-recursion: seeded k=0 at the FIRST ACK (that ACK coun209Gted, not
skipped), then k_i = min(B, max(0, k_{i-1} + a_i - 1)) chained forward using
its OWN predictions (not measured k each step, unlike c11_analyze.py's
per-step check) -- this is what lets path_static (no real k) get a
reconstructed k series from only its a_i sequence. Validated against
freezing 400G's real measured k first: must give 0 mismatches, or the
reconstruction is not trustworthy for path_static either.
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
C11 = HERE.parent
RUNS = C11 / "runs"
DATA = C11 / "data"
PLOTS = C11 / "plots"

DRAW = {"SEND", "RTX", "RTS"}
TOR0 = 32
PKT_BYTES = 4150  # on-wire data packet size (main_uec.cpp:302), NOT 4096
ACK_BYTES = 64
RATE_MBPS = 400000
T_S_DATA_NS = PKT_BYTES * 8 * 1000.0 / RATE_MBPS   # 83.00 ns
T_S_ACK_NS = ACK_BYTES * 8 * 1000.0 / RATE_MBPS    # 1.28 ns
B_CAP = 256
FREEZING_DIR = RUNS / "400g_cwnd127"
PATHSTATIC_DIR = RUNS / "400g_pathstatic_cwnd127"


def load_by_src(path: Path, src_filter=None):
    rows = []
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            s = int(r["src_id"])
            if s >= TOR0:
                continue
            if src_filter is not None and s != src_filter:
                continue
            rows.append(r)
    by_src: dict[int, list] = {}
    for r in rows:
        by_src.setdefault(int(r["src_id"]), []).append(r)
    for s in by_src:
        by_src[s].sort(key=lambda r: int(r["n"]))
    return by_src


def per_host_sequences(by_src: dict[int, list]):
    """Returns per-src dict of: a_i list, measured k list (None entries
    where no real buffer, e.g. path_static -- fresh column is always 0
    there), gap (ns) list, send times (ns), inflight at each draw."""
    out = {}
    for src, rows in by_src.items():
        seen_ack = False
        acks_since = 0
        last_fresh = 0
        last_t = None
        a_seq, k_seq, gaps, send_t, inflight_seq = [], [], [], [], []
        first_ack_counted = False
        for r in rows:
            ev = r["event"]
            if ev == "ACK":
                if not seen_ack:
                    seen_ack = True
                    first_ack_counted = True
                    acks_since += 1 if r["ecn"] == "0" else 0
                elif r["ecn"] == "0":
                    acks_since += 1
            elif ev in DRAW and seen_ack:
                k_seq.append(last_fresh)
                a_seq.append(acks_since)
                t = float(r["time_ns"])
                if last_t is not None:
                    gaps.append(t - last_t)
                last_t = t
                send_t.append(t)
                inflight_seq.append(int(r["inflight_pkts"]))
                acks_since = 0
            last_fresh = int(r["fresh"])
        out[src] = dict(a=a_seq, k=k_seq, gaps=gaps, t=send_t, inflight=inflight_seq)
    return out


def event_level_k(rows: list, b_cap: int) -> tuple[list[int], list[bool]]:
    """Exact event-order rule (no aggregation, no seed parameter): k=0
    before any event. ACK: +1 if clean (ecn==0), capped at B, else
    unchanged. SEND/RTX/RTS: pre-draw k is recorded, then -1 if k>0 else
    unchanged. Returns (pre_draw_k, post_first_ack) -- the second list
    marks whether each draw happened after this host's first ACK (warmup
    filter), matching every other cell's convention on this page."""
    k = 0
    seen_ack = False
    pre_draw_k, post_warmup = [], []
    for r in rows:
        ev = r["event"]
        if ev == "ACK":
            if not seen_ack:
                seen_ack = True
            if r["ecn"] == "0":
                k = min(b_cap, k + 1)
        elif ev in DRAW:
            pre_draw_k.append(k)
            post_warmup.append(seen_ack)
            if k > 0:
                k -= 1
    return pre_draw_k, post_warmup


def chained_recursion(a_seq: list[int], b_cap: int) -> list[int]:
    """Deprecated: slot-aggregated reconstruction with an explicit k_0
    seed. Superseded by event_level_k, which has no seed parameter (k=0 is
    a hard initial condition, not a free choice) and is gate-validated at
    0 mismatches including pre-warmup rows. Kept only for the raster/
    k-over-time panels that still consume a per-slot a_i-aligned series."""
    k = min(b_cap, a_seq[0]) if a_seq else 0
    out = [k]
    for a in a_seq[1:]:
        k = min(b_cap, max(0, k - 1 + a)) if k > 0 else min(b_cap, a)
        out.append(k)
    return out


def validate_chained_on_freezing(seqs: dict[int, dict]) -> tuple[int, int]:
    n_checked = n_mismatch = 0
    for src, d in seqs.items():
        pred = chained_recursion(d["a"], B_CAP)
        for p, m in zip(pred, d["k"]):
            n_checked += 1
            if p != m:
                n_mismatch += 1
    return n_checked, n_mismatch


def hist(values: list[int]) -> dict[int, float]:
    c: dict[int, int] = {}
    for v in values:
        c[v] = c.get(v, 0) + 1
    n = len(values)
    return {k: v / n for k, v in sorted(c.items())}


def unloaded_bdp_packets() -> float:
    # network_max_unloaded_rtt at 400G, confirmed from stdout: 8.33712 us
    rtt_ns = 8337.12
    return rtt_ns / T_S_DATA_NS


def standing_queue_packets(seqs: dict[int, dict], bdp: float) -> float:
    all_inflight = [v for d in seqs.values() for v in d["inflight"]]
    return statistics.fmean(all_inflight) - bdp


def main() -> None:
    frz_by_src = load_by_src(FREEZING_DIR / "events.csv")
    ps_by_src = load_by_src(PATHSTATIC_DIR / "events.csv")
    frz_seqs = per_host_sequences(frz_by_src)
    ps_seqs = per_host_sequences(ps_by_src)

    n_checked, n_mismatch = validate_chained_on_freezing(frz_seqs)
    print(f"GATE: chained recursion vs measured k (freezing 400G): "
          f"{n_mismatch}/{n_checked} mismatches")
    if n_mismatch:
        print("  WARNING: chained reconstruction does not match measured k "
              "-- path_static's reconstructed k is NOT trustworthy as-is")

    bdp = unloaded_bdp_packets()
    print(f"unloaded BDP (400G) = {bdp:.2f} packets")

    # headline k distributions
    frz_k_all = [k for d in frz_seqs.values() for k in d["k"]]
    ps_k_recon_all = []
    for src, d in ps_seqs.items():
        ps_k_recon_all += chained_recursion(d["a"], B_CAP)

    frz_a_all = [a for d in frz_seqs.values() for a in d["a"]]
    ps_a_all = [a for d in ps_seqs.values() for a in d["a"]]

    standing_q_frz = standing_queue_packets(frz_seqs, bdp)
    standing_q_ps = standing_queue_packets(ps_seqs, bdp)
    print(f"standing queue (mean inflight - BDP): freezing={standing_q_frz:.2f} "
          f"path_static={standing_q_ps:.2f} pkts")

    # slot raster: src 0, 30 consecutive steady-state slots (skip first 50
    # to clear warmup/startup transient), both arms
    def raster(seqs, src=0, start=50, n=30):
        d = seqs[src]
        t0 = d["t"][start]
        rows = []
        for i in range(start, min(start + n, len(d["t"]))):
            rows.append(dict(i=i - start, t_rel_ns=round(d["t"][i] - t0, 3),
                              a=d["a"][i], k=(d["k"][i] if i < len(d["k"]) else None)))
        return rows

    raster_frz = raster(frz_seqs)
    raster_ps_measured_k = raster(ps_seqs)
    # overlay reconstructed k onto the path_static raster rows
    ps0_recon = chained_recursion(ps_seqs[0]["a"], B_CAP)
    for row, kr in zip(raster_ps_measured_k, ps0_recon[50:50 + len(raster_ps_measured_k)]):
        row["k_reconstructed"] = kr

    # k-over-time, src 0, whole flow (downsample to <=2000 points for the page)
    def downsample(vals, cap=2000):
        if len(vals) <= cap:
            return list(enumerate(vals))
        step = len(vals) / cap
        return [(int(i * step), vals[int(i * step)]) for i in range(cap)]

    k_over_time_frz = downsample(frz_seqs[0]["k"])
    k_over_time_ps_recon = downsample(chained_recursion(ps_seqs[0]["a"], B_CAP))

    payload = dict(
        gate_mismatches=n_mismatch, gate_checked=n_checked,
        bdp_400g=round(bdp, 3),
        standing_queue=dict(freezing=round(standing_q_frz, 2),
                             path_static=round(standing_q_ps, 2)),
        k_hist=dict(freezing=hist(frz_k_all),
                    path_static_reconstructed=hist(ps_k_recon_all)),
        a_hist=dict(freezing=hist(frz_a_all), path_static=hist(ps_a_all)),
        raster=dict(freezing=raster_frz, path_static=raster_ps_measured_k),
        k_over_time=dict(freezing=k_over_time_frz,
                          path_static_reconstructed=k_over_time_ps_recon),
        T_s_data_ns=round(T_S_DATA_NS, 3), T_s_ack_ns=round(T_S_ACK_NS, 3),
    )
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "pathstatic_compare.json").write_text(json.dumps(payload), encoding="utf-8")
    print("wrote", DATA / "pathstatic_compare.json")

    print(f"\nk_hist freezing: {hist(frz_k_all)}")
    print(f"k_hist path_static (reconstructed): {hist(ps_k_recon_all)}")
    print(f"a_hist freezing: {hist(frz_a_all)}")
    print(f"a_hist path_static: {hist(ps_a_all)}")


if __name__ == "__main__":
    main()

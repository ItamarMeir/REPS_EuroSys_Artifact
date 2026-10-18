#!/usr/bin/env python3
"""Generate a bursty-src0 connection-matrix for C3, derived from the same
tornado_n1024_s16777216.cm file C1/C2 already use (so the other 992 non-ToR0
hosts stay byte-identical to C1/C2's own background).

What changes vs the base file:
- node 0's single `0->512 ... size 16777216` line is replaced by N separate
  lines (same src->dst pair), each `16 MiB / N` bytes, scheduled with a gap
  between them. `-connections_mapping` (passed on the sim CLI, not written
  here) is what makes these N separate UecSrc objects share one REPS buffer
  across the gaps -- see C3/PLAN.md's "Mechanism" section.
- nodes 1-31 (the rest of ToR0, src0's own background/congestion neighbors)
  get their `size` scaled up so they outlast src0's whole bursty schedule --
  see "Background-flow sizing" below. Nodes 32-1023 (rest of the 1024-node
  fabric) are left untouched, exactly as in C1/C2.
- Connection order is preserved except node 0's single line is replaced
  in-place by its N burst lines; everything before/after keeps its original
  relative order. This matters: `_node_num` (htsim/sim/uec.cpp:1120) is
  assigned by a global counter in connection-list iteration order
  (`main_uec.cpp:1639-1650` creates one UecSrc per connection, in order), so
  each burst's eventual `_node_num` is exactly its 0-based position in this
  file's connection list -- predictable without running the sim. Written to
  the sidecar JSON so the run script can pass the right IDs to
  `-log_reps_events_src` and so analysis can map node_num -> burst_index.

Background-flow sizing (conservative, not exact -- the whole point is margin,
not precision; actual achieved burst/gap timing is always measured from the
trace afterward, never assumed to match the schedule below exactly):
  line_rate_ps(bytes) = bytes * 8 * 1e12 / LINK_BPS            -- time to send
                         `bytes` at full line rate, in picoseconds
  burst_estimate_ps   = line_rate_ps(burst_bytes) * SAFETY     -- conservative
                         per-burst duration budget (SAFETY=8x covers CC
                         ramp-up/congestion slowdown; actual C1/C2 FCTs for
                         16 MiB flows were observed well under this factor
                         over line rate)
  total_span_ps       = N*burst_estimate_ps + (N-1)*gap_ps     -- conservative
                         worst-case span of src0's whole schedule
  background_bytes    = 16MiB * ceil(total_span_ps / line_rate_ps(16MiB)) *
                         BACKGROUND_MARGIN                      -- scale the
                         background flows' byte count by the same ratio
                         (both experience similar congestion scaling under
                         backlog, so a byte-ratio scales roughly to a
                         time-ratio), plus one more explicit margin on top.

Output:
  <out>.cm                  -- the generated connection matrix
  <out>.schedule.json        -- sidecar: per-burst (node_num, start_ps, size_bytes),
                                 gap_ps, background_bytes, total_span_ps estimate
"""
import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DC_DIR = Path("/workspace/htsim/sim/datacenter")
BASE_CM = DC_DIR / "connection_matrices" / "tornado_n1024_s16777216.cm"
OUT_DIR = DC_DIR / "connection_matrices"

LINK_BPS = 400_000 * 1_000_000  # -linkspeed 400000 (Mbps) -> bps
SIXTEEN_MIB = 16 * 1024 * 1024
TOR0_HOSTS = 32
# SAFETY=1.0 (raw line-rate time, no inflation) matches the plan's own worked
# figures exactly: N=16 bursts at a 5-RTT gap -> ~1ms total span, ~50 MiB
# background -- that number assumed NO per-burst safety multiplier, just line
# rate + gap. An earlier draft of this script used SAFETY=8, which inflated
# background to ~200 MiB/host (~2.8ms span) for N=4 alone -- far beyond the
# plan's own "~3x a C1 cell" cost estimate. BACKGROUND_MARGIN alone (not a
# per-burst multiplier) carries the safety buffer instead.
SAFETY = 1.0
BACKGROUND_MARGIN = 1.5  # extra margin on top of the byte-ratio scaling


def line_rate_ps(num_bytes):
    return num_bytes * 8 * 1_000_000_000_000 / LINK_BPS  # ps


def parse_base_cm(path):
    """Returns (header_lines, connections) where each connection is a dict
    with src, dst, size (int), and the original line's other tokens ignored
    (the base file only ever has src->dst id N start T size S for this
    workload)."""
    header_lines = []
    conns = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if "->" in line.split()[0]:
                toks = line.split()
                src, dst = toks[0].split("->")
                d = {"src": int(src), "dst": int(dst)}
                i = 1
                while i < len(toks):
                    if toks[i] == "size":
                        d["size"] = int(toks[i + 1]); i += 2
                    elif toks[i] == "start":
                        d["start"] = toks[i + 1]; i += 2
                    elif toks[i] == "id":
                        i += 2
                    else:
                        i += 1
                conns.append(d)
            else:
                header_lines.append(line)
    return header_lines, conns


def build(N, gap_ps, out_stem):
    header, conns = parse_base_cm(BASE_CM)
    assert len(conns) == 1024, f"expected 1024 base connections, got {len(conns)}"
    assert conns[0]["src"] == 0, "node 0 must be the first connection in the base file"

    src0 = conns[0]
    burst_bytes_each = SIXTEEN_MIB // N
    remainder = SIXTEEN_MIB - burst_bytes_each * N  # goes to the last burst

    burst_estimate_ps = line_rate_ps(burst_bytes_each) * SAFETY
    total_span_ps = N * burst_estimate_ps + (N - 1) * gap_ps

    background_bytes = math.ceil(
        SIXTEEN_MIB * (total_span_ps / line_rate_ps(SIXTEEN_MIB)) * BACKGROUND_MARGIN
    )

    bursts = []
    t = 0
    for k in range(N):
        size_k = burst_bytes_each + (remainder if k == N - 1 else 0)
        bursts.append({"src": src0["src"], "dst": src0["dst"],
                        "start_ps": int(t), "size": size_k, "burst_index": k})
        t += burst_estimate_ps + gap_ps

    new_conns = []
    for c in conns[1:]:
        if 1 <= c["src"] < TOR0_HOSTS:
            c = dict(c)
            c["size"] = background_bytes
        new_conns.append(c)
    # Re-insert src0's bursts at the front (node 0's original position), so
    # every OTHER host's relative order (and hence its _node_num, since node
    # 0 was first before) only shifts by a constant (N-1), staying internally
    # consistent and easy to reason about.
    final_conns = [{"src": b["src"], "dst": b["dst"], "start": b["start_ps"],
                     "size": b["size"]} for b in bursts] + new_conns

    out_cm = OUT_DIR / f"{out_stem}.cm"
    with open(out_cm, "w") as f:
        f.write(f"Nodes 1024\n")
        f.write(f"Connections {len(final_conns)}\n")
        for i, c in enumerate(final_conns, start=1):
            f.write(f"{c['src']}->{c['dst']} id {i} start {c['start']} size {c['size']}\n")

    sidecar = dict(
        N=N, gap_ps=gap_ps, burst_bytes_each=burst_bytes_each,
        burst_estimate_ps=burst_estimate_ps, total_span_ps=total_span_ps,
        background_bytes=background_bytes,
        # node_num == 0-based position in final_conns (iteration order == UecSrc
        # creation order, see module docstring) -- src0's bursts are first, so
        # their node_nums are simply 0..N-1.
        bursts=[dict(b, node_num=b["burst_index"]) for b in bursts],
    )
    out_json = OUT_DIR / f"{out_stem}.schedule.json"
    out_json.write_text(json.dumps(sidecar, indent=2))
    return out_cm, out_json, sidecar


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="bursts for src0")
    ap.add_argument("--gap-ps", type=int, required=True, help="nominal gap between bursts, picoseconds")
    ap.add_argument("--out", required=True, help="output stem (written under connection_matrices/)")
    args = ap.parse_args()
    out_cm, out_json, sidecar = build(args.n, args.gap_ps, args.out)
    print(f"wrote {out_cm}")
    print(f"wrote {out_json}")
    print(f"burst_bytes_each={sidecar['burst_bytes_each']} "
          f"background_bytes={sidecar['background_bytes']} "
          f"total_span_ps={sidecar['total_span_ps']:.0f} "
          f"(~{sidecar['total_span_ps']/1e6:.1f} us)")

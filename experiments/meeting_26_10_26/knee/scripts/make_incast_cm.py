#!/usr/bin/env python3
"""Tornado matrix plus periodic incast bursts into the receivers of the ToR0 flows (hosts N/2 .. N/2+7 on 128 hosts).
Every period P us, each receiver gets one burst of `n_src` flows of S bytes each, from sources that never repeat a (src, dst) pair
(a second flow on the same pair stalls with the constant-rate sender + -connections_mapping). Sources are hosts outside the traced ToR0 hosts and the receivers.
The ToR->host link has no ECN under -disable_tor_ecn, so the burst only DELAYS data and ACKs of the tornado flows into that receiver (an oscillating delay).
usage: python make_incast_cm.py N S_bytes P_us n_src t_first_us out.cm   (S_bytes = 0 writes the plain tornado, the control)"""
import sys
n, s_bytes, period, n_src, t0, out = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
half = n // 2
recv = list(range(half, half + 8))                                  # destinations of hosts 0..7 (tornado i -> i + n/2)
pool = [h for h in range(8, n) if h not in recv]
flows = [(i, (i + half) % n, 0, 16777216) for i in range(n)]
if s_bytes > 0:
    j = 0
    while t0 + j * period < 1400 and (j + 1) * n_src <= len(pool):   # until the tornado flows are over; pairs stay unique
        for r in recv:
            for i in range(n_src):
                flows.append((pool[(j * n_src + i) % len(pool)], r, int((t0 + j * period) * 1e6), s_bytes))
        j += 1
lines = [f"Nodes {n}", f"Connections {len(flows)}"] + [f"{a}->{b} id {k + 1} start {t} size {sz}" for k, (a, b, t, sz) in enumerate(flows)]
assert len({(a, b) for a, b, _, _ in flows}) == len(flows), "duplicate src-dst pair"
open(out, "w", newline="\n").write("\n".join(lines) + "\n")
print(f"{len(flows)} flows, {len(flows) - n} burst flows")

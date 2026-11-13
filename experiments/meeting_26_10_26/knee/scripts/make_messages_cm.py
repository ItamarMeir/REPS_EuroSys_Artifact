#!/usr/bin/env python3
"""Repeated-message tornado matrix: every host i sends K messages of S bytes to host (i + N/2) % N, one every P microseconds (same src-dst pair, so -connections_mapping hands the
REPS buffer of a finished message to the next one). Format = the tokenised one of connection_matrices/t3/tornado_*.cm (start in picoseconds).
usage: python make_messages_cm.py N K S_bytes P_us out.cm"""
import sys
n, k, size, period_us, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
lines = [f"Nodes {n}", f"Connections {n * k}"]
fid = 1
for m in range(k):
    for i in range(n):
        lines.append(f"{i}->{(i + n // 2) % n} id {fid} start {int(m * period_us * 1e6)} size {size}")
        fid += 1
open(out, "w", newline="\n").write("\n".join(lines) + "\n")

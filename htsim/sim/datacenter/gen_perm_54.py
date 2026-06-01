#!/usr/bin/env python3
"""Generate a random permutation traffic matrix for 54 hosts."""
import random, sys

N = 54
size_bytes = int(sys.argv[1]) if len(sys.argv) > 1 else 8388608  # 8 MB default
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42

random.seed(seed)
hosts = list(range(N))
random.shuffle(hosts)
pairs = [(hosts[i], hosts[(i + 1) % N]) for i in range(N)]

print(f"Nodes {N}")
print(f"Connections {N}")
for idx, (src, dst) in enumerate(pairs, start=1):
    print(f"{src}->{dst} id {idx} start 0 size {size_bytes}")

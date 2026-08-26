#!/usr/bin/env python3
"""Composite TM regen.

Writes composite.cm in the same directory as this script. Class ids:
  1..96    = elephants (8 MB)
  97..352  = mice (32 KB, 16 waves)
  353..416 = incast (4 victims x 16 senders, 2 MB)
"""
import os, random
HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "composite.cm")

N = 128
US = 1_000_000
rng = random.Random(20)

lines = []
fid = 0

# elephants 1..96 (8 MB each)
hosts = list(range(N))
e_src = rng.sample(hosts, 96); e_dst = rng.sample(hosts, 96)
for i in range(96):
    if e_src[i] == e_dst[i]: e_dst[i] = (e_dst[i] + 1) % N
for s, d in zip(e_src, e_dst):
    fid += 1
    lines.append(f"{s}->{d} id {fid} start 0 size 8388608")

# mice 97..352 (32 KB, 16 waves of 16 every 25us)
for k in range(256):
    s = rng.randrange(N); d = rng.randrange(N)
    while d == s: d = rng.randrange(N)
    start_us = 10 + (k % 16) * 25
    fid += 1
    lines.append(f"{s}->{d} id {fid} start {start_us * US} size 32768")

# incast 353..416: 4 victims, 16:1, 2 MB each, all start at t=80us
victims = [3, 41, 77, 119]
incast_start_us = 80
for v in victims:
    senders = [(v + 1 + o) % N for o in range(16)]
    for s in senders:
        if s == v: s = (s + 17) % N
        fid += 1
        lines.append(f"{s}->{v} id {fid} start {incast_start_us * US} size 2097152")

with open(OUT, "w") as f:
    f.write(f"Nodes {N}\nConnections {len(lines)}\n")
    for ln in lines: f.write(ln + "\n")
print(f"wrote {OUT}: connections={len(lines)}")

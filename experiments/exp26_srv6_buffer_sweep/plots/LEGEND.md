# exp26 plot legend

Every arm runs with `-use_srv6` and `-paths <n_paths>` (distinct physical
paths for the panel topology: fat_tree_32=4, fat_tree_128_2t=8,
fat_tree_128_3t=16, fat_tree_1024_2t=32).

| arm | flags added vs the paper command | colour | marker |
|-----|----------------------------------|--------|--------|
| `ops` | `-load_balancing_algo oblivious -use_srv6 -paths N` | #d95f02 (orange) | square, dashed |
| `reps_b1` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size 1` | #440154 | X, solid |
| `reps_b2` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size 2` | #404387 | X, solid |
| `reps_b4` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size 4` | #29788e | X, solid |
| `reps_b8` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size 8` | #22a784 | X, solid |
| `reps_b16` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size 16` | #79d151 | X, solid |
| `reps_b32` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size 32` | #fde724 | X, solid |

A given `B` keeps the same colour in every figure. Not every figure runs
every `B` -- the ladder stops at the topology's path count.

The paper's fig_2 / fig_4 micro panels plot **Speedup vs ECMP**; exp26 has
no ECMP arm, so the baseline is the `ops` arm and the axis reads
**Speedup vs OPS**. fig_7 already uses OPS as its baseline in the paper.
dc panels show absolute Average FCT; ai panels show absolute collective
runtime -- no baseline.

A red `OPS finished x/y flows` note marks rows where the OPS arm stalled on
flows every REPS arm completed; its FCT is then measured over the finished
subset only, so the speedup drawn on that row is a lower bound.

fig8 keeps the paper's analytic `ideal` line
(`33 MiB / 400 Gbps + 20 us`, scaled `10/(10-fail%)`) and the per-point
% slowdown-vs-ideal annotations (shown for B=8, the paper's default).

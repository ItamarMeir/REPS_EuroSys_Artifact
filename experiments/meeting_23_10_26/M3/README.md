# M3: non-uniform degradation

Flag `-degrade_links_file` (see `experiments/MODIFICATIONS.md`, `per-link-degrade`). Specs here: `degrade_uniform50.txt` (all 32 ToR0 uplinks at 0.5) and `degrade_nonuniform_25_75.txt` (even agg 0.25 = degraded 75%, odd agg 0.75 = degraded 25%; total 50%).

Checks (NSCC, freezing B8, tornado 16 MiB, seed 42, 400G):
- uniform spec == `-failed 32 -down_ratio 0.5`: flow-finish lines identical (md5), max FCT 730.77 us.
- non-uniform: 32 `Failure:` lines summing to 16.0 of 32 uplink-equivalents (50%). NSCC+REPS max FCT 715.3 us.
- OPS (`path_random`) on the non-uniform fabric: max FCT 1080.1 us, i.e. uniform spraying loses ~51% against REPS here, as expected when a quarter-speed link caps an equal split.

# C1 results: per-packet EV source split (exp30 trim-on, seed 42)

Config: `exp30_packet_trimming_en`, MPRDMA, freezing LB, tornado 4 MiB, trim ON, one seed (42).
Healthy = n=0. Degraded = all 32 ToR0 uplinks at 50% speed (`-failed 32 -down_ratio 0.5`).
Fractions are over all EV draws of the ToR0 hosts (new packets + retransmissions), so valid + random + stale = 1.

| Scenario | B | valid | random | stale |
|---|---|---|---|---|
| healthy | 1 | 0.6789 | 0.3211 | 0 |
| healthy | 2 | 0.8535 | 0.1465 | 0 |
| healthy | 4..256 | 0.8816 | 0.1184 | 0 |
| degraded n=32 | 1 | 0.6997 | 0.3003 | 0 |
| degraded n=32 | 2 | 0.7064 | 0.2936 | 0 |
| degraded n=32 | 4..256 | 0.7075 | 0.2925 | 0 |

Reading: B=1 is the only size that changes the valid/random split; from B=4 up the split is identical,
including B=64..256 (duplicate EVs, see the -paths 32 caveat). Stale is 0 in all runs (trim on, no RTO, no freeze).

Checks:
- Conservation: in the degraded B=8 run, the trace has 32864 SEND rows (= 32 x 1027 packets) and 1568 RTX rows.
  The EV draws are SEND + RTX; the per-flow excess of 1568 over unique packets is exactly the RTX count.
- Seeds: only seed 42 carries the new counters. Seeds 43/44 were run before them, so every fraction above is seed 42 only.
  The `n_seed` column in `data/diagnostics.csv` counts all seeds and is misleading for these fractions.
- B>32 cells are excluded from the exp30 plots (shared helpers only know B 1..32). The data is in `data/`.

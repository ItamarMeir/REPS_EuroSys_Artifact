# C1 results: per-packet EV source split (exp30 trim-on, seed 42)

Config: `exp30_packet_trimming_en`, MPRDMA, freezing LB, tornado, trim ON, seed 42.
Sizes: 4 MiB (1027 packets/flow) and 16 MiB (4107 packets/flow).
Healthy = n=0. Degraded = all 32 ToR0 uplinks at 50% speed (`-failed 32 -down_ratio 0.5`).
Fractions are over all EV draws of the 32 ToR0 hosts: draws = new packets + retransmissions.
valid + random + stale = 1. Interactive page: `plots/interactive.html`. Data: `data/c1_split.csv`, `data/c1_split_hosts.csv`.

| Size | Scenario | B | valid | random | stale | RTX |
|---|---|---|---|---|---|---|
| 4 MiB | healthy | 1 | 0.6789 | 0.3211 | 0 | 0 |
| 4 MiB | healthy | 2 | 0.8535 | 0.1465 | 0 | 0 |
| 4 MiB | healthy | 4..256 | 0.8816 | 0.1184 | 0 | 0 |
| 4 MiB | degraded | 1 | 0.6997 | 0.3003 | 0 | 1567 |
| 4 MiB | degraded | 2..256 | 0.706..0.708 | 0.292..0.294 | 0 | 1568..1574 |
| 16 MiB | healthy | 1 | 0.7579 | 0.2421 | 0 | 0 |
| 16 MiB | healthy | 2 | 0.9398 | 0.0602 | 0 | 0 |
| 16 MiB | healthy | 4..256 | 0.9681..0.9691 | 0.031..0.032 | 0 | 0 |
| 16 MiB | degraded | 1 | 0.8744 | 0.1256 | 0 | 1567 |
| 16 MiB | degraded | 2..256 | 0.8817..0.8829 | 0.117..0.118 | 0 | 1568..1574 |

Reading:
- Buffer size changes the split only at B=1 and B=2. From B=4 up it is flat, at both sizes.
- The valid share is much higher at 16 MiB (about 0.97 healthy, 0.88 degraded) than at 4 MiB (0.88 / 0.71). Longer flows spend more of their life in steady state.
- Stale is 0 in every run (trim on, no RTO, no freeze).

Checks:
- Conservation: SEND rows = 32 x packets/flow, and RTX rows = NACK rows = draws - packets. Checked by trace at 4 MiB (degraded, B=8: 32864 SEND, 1568 RTX) and at 16 MiB (degraded, B=8: 131424 SEND, 1568 RTX).
- RTX count is 1568 at both sizes for every B from 8 up. It does not scale with flow size, so it probably comes from a fixed early event (trimming before the congestion window settles). Not yet explained.
- Seeds: only seed 42 has the new counters. Seeds 43/44 predate them. Fractions are seed 42 only.
- B>32 cells are excluded from the exp30 plots, and shown only in this page.

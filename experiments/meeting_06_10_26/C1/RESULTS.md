# C1 results: 16 MiB

Config: `exp30_packet_trimming_en` (trim ON), MPRDMA, freezing LB, tornado 16 MiB (4107 packets/flow),
ToR0 hosts (32), seed 42 only. Healthy = n=0. Degraded = all 32 ToR0 uplinks at 50% speed.
Page: `plots/interactive.html`. Data: `data/c1_split.csv`, `data/c1_split_hosts.csv`, `data/c1_occupancy.csv`.
(4 MiB runs are kept on disk but not presented here.)

## Claim

After each host's first ACK, during backlog (before its last send), the buffer holds at most 2 valid EVs.
B=1 and 2 hold this trivially (the buffer cannot hold more than 2), so only B>=4 tests it.

## Occupancy (event trace, pooled over 32 ToR0 hosts)

Metric: share of trace rows with fresh <= 2, where fresh = valid buffer entries after each event.
"After t0" = rows with time >= the host's first ACK. "Backlog" = after t0 and before the host's last send.

| Scenario | B | after t0 | backlog | max fresh (backlog) | backlog rows fresh>=3 |
|---|---|---|---|---|---|
| healthy | 1 | 1.0000 | 1.0000 | 1 | 0 |
| healthy | 2 | 1.0000 | 1.0000 | 2 | 0 |
| healthy | 4 | 0.8110 | 0.8234 | 4 | 45121 |
| healthy | 8..256 | 0.8309 | 0.8439 | 5 | 39885 |
| degraded | 1 | 1.0000 | 1.0000 | 1 | 0 |
| degraded | 2 | 1.0000 | 1.0000 | 2 | 0 |
| degraded | 4 | 0.9920 | 0.9999 | 3 | 36 |
| degraded | 8..256 | 0.9918 | 0.9998 | 3 | 51 |

Healthy B=8..256 are identical: the valid count never reaches 8, so the buffer size never limits it.
Degraded B=8..256 are identical for the same reason (max valid count is 3).

Drain share (rows after the last send, out of rows after t0): about 1.6% healthy, 0.8% degraded.

## Reading

- **Healthy: the claim does not hold.** During backlog the buffer holds 3–5 valid EVs for about 16% of rows.
  The excess is not a drain tail (drain is 1.6%). This contradicts the earlier conclusion, which came from the
  degraded trace alone.
- **Degraded (all ToR0 uplinks at 50%): the claim holds.** During backlog 99.98% of rows have at most 2 valid
  EVs, and the maximum is 3 (51 rows). The 0.8% drain tail contains the full-buffer states (8 valid).
- Only B>=4 counts as a test. Degraded B=4 already equals B=8..256 at these tolerances.

## Per-packet split (C1, seed 42)

| Scenario | B | valid | random | stale | RTX |
|---|---|---|---|---|---|
| healthy | 1 | 0.7579 | 0.2421 | 0 | 0 |
| healthy | 2 | 0.9398 | 0.0602 | 0 | 0 |
| healthy | 4..256 | 0.9681..0.9691 | 0.031..0.032 | 0 | 0 |
| degraded | 1 | 0.8744 | 0.1256 | 0 | 1567 |
| degraded | 2..256 | 0.8817..0.8829 | 0.117..0.118 | 0 | 1568..1574 |

Reading: the split is flat from B=4 up. Stale is 0 everywhere (trim on, no RTO, no freeze).
The split includes the warmup: before a host's first ACK every draw is random (about 105 sends per host).

## Checks

- **Trace matches C1:** for every occupancy cell, the trace run's finish lines (1024) match the committed C1
  stdout exactly (`crosscheck_match` = True).
- **Conservation:** SEND rows = 32 x packets per flow, and RTX = NACK = draws - packets (degraded B=8, both sizes).
- **Retransmissions:** 1568 at every B from 8 up, at 16 MiB. Not explained yet.
- **Seed:** every value here is seed 42 only.
- **Binary:** the trace runs use `htsim_uec` rebuilt from HEAD (5d84e80). The C1 split values come from the earlier
  build, which has the same counters.

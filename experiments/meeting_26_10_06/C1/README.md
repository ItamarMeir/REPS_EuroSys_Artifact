# C1 - how many valid EVs does the REPS buffer hold when not frozen?

## Claim under test
From the 2026-10-06 meeting (Gabriel Skalosub): outside Freezing Mode, while a sender is backlogged, the number of valid EVs in the REPS buffer (k) stays at one small, stable value most of the time. If so, a big buffer is never filled and buffer sizes above that value should behave identically. The claim is *not* about Freezing Mode, where the buffer is replayed instead of refilled (that is [C2](../C2/README.md)).

`PLAN.md` operationalised this strictly: "at most 2 valid EVs in more than 95% of samples, independent of B". That strict threshold is a test of the claim, not the claim itself; the results below report both.

## Setup
- Fabric `fat_tree_1024_1os_2t_400g` (1024 hosts, 32 ToRs, 32 spines), tornado, 16 MiB per flow (`tornado_n1024_s16777216.cm`), seed 42, packet trimming ON (the `exp30_packet_trimming_en` base config), `-load_balancing_algo freezing -use_srv6 -paths 32`, `-q 101 -ecn 25 76 -cwnd 151`.
- Two scenarios: **healthy** (x0) and **degraded** (x32: all 32 ToR0 uplinks at 50% speed, `-failed 32 -down_ratio 0.5`). Only the 32 ToR0 senders are analysed.
- Buffer size B in {1, 2, 4, 8, 16, 32, 64, 128, 256}. Only B >= 4 can test the claim (B = 1, 2 cannot hold more than 2).
- Two congestion controllers, each with its own folder: [`MPRDMA/`](MPRDMA/) (original) and [`NSCC/`](NSCC/). The NSCC arm was **rerun on 2026-10-18 with `-target_q_delay 4.17`** (the paper's rule, 0.5 x base RTT, instead of the 6 us default); the original 6 us results are in `NSCC/_prev_target6us/` (local, not committed). The healthy NSCC cells were not rerun (they never mark ECN, so the target does not matter).
- `-disable_tor_ecn` is not passed (inherited from the exp30 trim-on base). Stdout therefore shows `enable on tor downlink 1`. Both scenarios share this, so it does not bias the healthy-vs-degraded comparison.
- Every cell logs the full per-event trace (`-log_reps_events`, sources 0 to 31), which is the input to all the metrics.

## What is measured
- **Occupancy** (`occupancy.py`): `fresh` = valid buffer entries after every event, per host, between the host's first ACK and its last send ("backlog").
- **Send-time k** (`send_occupancy.py`): valid EVs in the buffer just before each SEND/RTX/RTS draw, from the host's first ACK on.
- **Per-packet split** (`build_c1.py`, from the finish-line counters): share of draws that took a valid EV, a random EV, or a stale EV.
- **ACKs per send-to-send window, a_i** (`acks_per_window.py`): how many ACKs arrive between consecutive sends; k is a running sum of a_i - 1.
- **FCT vs speed of light** (SoL): `path_static` + constant CC, cwnd 127 (healthy) / 56 (degraded, set per host with `-host_cwnd_overrides`). SoL max FCT is 354.25 us healthy and 700.37 us degraded.
- Internal checks (all 18 cells pass per CC): send count conserved against the finish lines, P(k = 0) equals the random-draw share, 0 reconstruction mismatches, stale = 0, max k <= B.

## Results (seed 42)
k at send time, B = 8 (identical for every B >= 8 in healthy; see `data/c1_send_occupancy.csv`):

| Scenario / CC | k = 0 | k = 1 | k = 2 | k = 3 | k >= 4 | max k |
|---|---|---|---|---|---|---|
| healthy (both CCs) | 0.7% | 11.7% | **57.2%** | **29.7%** | 0.7% | 5 |
| degraded, MPRDMA | 9.4% | **86.5%** | 4.1% | 0.0% | 0 | 3 |
| degraded, NSCC (4.17 us) | 58.4% | 38.3% | 1.8% | 0.6% | 0.9% | 8 at B = 8 (17 at B = 256) |
| degraded, NSCC (old 6 us) | 79.2% | 20.5% | 0.2% | 0 | 0 | 8 |

- **The claim holds in the sense that matters.** k sits at a small, stable value: 2 to 3 when healthy (87% of draws), 1 under MPRDMA degradation, 0 to 1 under NSCC degradation (97%). It never uses a large buffer: healthy results are identical for every B >= 8 (max k 5), and degraded MPRDMA saturates at B = 8 (max k 3). Stale draws are 0 everywhere (trim on, no RTO, so Freezing Mode never starts).
- **The strict "<= 2 valid EVs" threshold fails when healthy**: k = 3 occurs for 30% of draws and 16% of backlog rows have 3 to 5 valid EVs (`RESULTS.md`). It holds when degraded with MPRDMA (99.98% of backlog rows) and mostly with NSCC (98.2 to 98.7%, rare tail up to 17).
- **Why k is not larger when degraded:** with persistent ECN marking there are few clean ACKs to refill the buffer (NSCC leaves 55 to 80% of ACKs marked at 4.17 / 6 us targets; MPRDMA about 6%). Moving the target from 6 to 4.17 us raises k a little (k >= 3 from 0% to 1.5% of draws) but does not restore the healthy distribution.
- **FCT:** healthy REPS is 1.006x SoL for every B and CC. Degraded, REPS max FCT is 1.094x SoL with MPRDMA (766.6 us) and 1.03 to 1.04x with NSCC (719 to 729 us at 4.17 us; 1.043x at 6 us). B does not change p50 FCT (healthy 356.2 us, degraded 688 us MPRDMA / 693 us NSCC at B = 8 and 256).

## Caveats
- One seed (42); no confidence intervals.
- When degraded (MPRDMA, 16 MiB) there are 1,568 retransmissions at every B >= 8; the cause is not explained (`RESULTS.md`).
- `RESULTS.md` was written for the MPRDMA run and still states its numbers; the NSCC numbers above come from `NSCC/data/*.csv`.
- The committed NSCC data and page were generated in a temporary mirror so the new stdout could be used. `exp30_packet_trimming_en/runs/` (which `build_c1.py` reads for FCT and the split) still holds the old 6 us stdout for the NSCC degraded cells, so re-running `build_c1.py --cc nscc` against the real tree would rebuild the old FCT/split numbers.

## Reproduce
Inside the `reps-artifact` container (needs `/workspace` paths and `htsim_uec`):
```bash
cd /workspace/experiments/meeting_06_10_26/C1/scripts
python3 view_traces.py --cc nscc --traces-only     # run the 18 cells, write ../NSCC/traces/*.csv.gz
python3 occupancy.py --cc nscc --all               # -> ../NSCC/data/c1_occupancy.csv
python3 send_occupancy.py --cc nscc                # -> c1_send_occupancy.csv, c1_send_checks.csv
python3 acks_per_window.py --cc nscc               # -> c1_acks_per_window*.csv
python3 build_c1.py --cc nscc                      # -> ../NSCC/plots/interactive.html
```
Use `--cc mprdma` for the MPRDMA arm. The committed scripts do not take the target delay as an option: the 2026-10-18 NSCC rerun added `-target_q_delay 4.17` to the degraded cells' simulator flags in a temporary copy of this pipeline, so reproducing it means adding that flag to the NSCC degraded cells in `occupancy.py`'s `cell_flags` (via `common30.base_flags`).

## Files
- `PLAN.md` (original plan), `RESULTS.md` (MPRDMA write-up with the SoL sweep details).
- `MPRDMA/`, `NSCC/`: each has `data/` (occupancy, send-time k, split, a_i, FCT, SoL), `plots/interactive.html`, `traces/` (gzipped event traces; local only).
- `NSCC/data/freezing_mode.json`, `NSCC/plots/freezing_mode.html`: a C2-style view of Freezing Mode on the C1 cells (`build_freezing_mode.py`).
- `scripts/`: runners and analysers listed above.

# M4 - Does REPS buffer size B matter at known constant send rates?

## Setup
- Sender: `-sender_cc_algo constant` with `-rate_const_gbps R`, which is the **NIC egress rate of all packet types** (data, retransmissions, ACKs/control; see `../../RATE_CONST_ARCHITECTURE.md`, "NIC egress shaper"). R = 100 / 200 / 400 Gbps per host = 0.25 / 0.5 / 1.0 of the 400G NIC ("under" / "matched" / "over"). No congestion control.
- Fabric: `fat_tree_1024_1os_2t_400g` (all links 400G), tornado 16 MiB, 1024 flows (every host sends and receives), SRv6 32 paths, trimming on, `-disable_tor_ecn`, `-load_balancing_algo freezing`.
- Failure models (ToR0 uplinks only): `healthy`; `uniform50` (all 32 uplinks at 50%); `nonuniform` (even agg 25% / odd agg 75%, mean 50%; see `../M3`).
- B in {1,2,4,8,16,32,64}, **seeds 42-44 (189 runs)**; table values are means of 3 seeds, 95% CIs use t(2)=4.30 (wide, see `data/m4_summary.csv`).
- A degraded ToR0 uplink carries 200 Gbps, so under/matched/over = below / at / above the bottleneck. On the healthy fabric 400 Gbps is the matched case, so healthy "over" is really "matched to healthy capacity".
- Per-run results `data/results.jsonl`, raw event traces `traces/` (gzip, kept, gitignored), aggregation/plots `scripts/plot_m4.py`, runner `scripts/run_m4.py`.

## Why the first M4 was wrong
The first M4 used a pacer that charged only DATA packets to R. In tornado each host also returns one 64 B ACK per 4150 B data packet over the same uplinks, so "matched" 200G data plus ~3.1G of ACKs put ~203G on a 200G degraded uplink (rho ~ 1.015). The queue sat in the ECN ramp: ~56% of ACKs marked, ~49% of draws random, ~400 retransmits, independent of B. On a healthy/over fabric the 400G NIC itself capped data+ACK at 400G, so the same effect did not appear, which is why matched/uniform50 did not look like over/healthy. A data-only sweep confirmed it (R=200: 49% random; 197: 1.1%; 195: 0.45%; 190: 0.24%; `data/sweep_data_only_197_195_190.jsonl`). A fixed sending rate must cap whatever the NIC puts on the wire, so the flag now shapes the whole NIC egress (old behaviour: `-rate_const_data_only`; old results kept in `data/results_data_only_rate.jsonl`). Side effect: data goodput is ~1.5% below R (under: 1392 us instead of 1371 us). R is per host NIC, not per flow.

## Metric definitions
- **k** = valid EVs in the buffer immediately before a draw (previous row's post-event `fresh` of the same source). Draws = SEND / RTX / RTS, counted only after the source's first ACK (before it the buffer is necessarily empty).
- **Overwrite** = a clean (non-ECN) ACK arriving when the buffer is already full, so `add()` replaces a still-valid EV. Only clean ACKs **before the source's last draw** count (`ev_overwrites`, `pct_overwrite` = share of those ACKs): after the last send no EV is popped any more, the buffer just fills during the flow tail and every later clean ACK would overwrite harmlessly (this tail effect made an earlier version of the metric read 10-60% at B=64 and over-degraded; the all-ACK variant is kept as `*_all`). `add_mismatch == 0` and `recon_mismatch == 0` (both keys present) in all 189 runs. Overwrite fields are recomputed from the kept traces by `scripts/reaggregate_overwrites.py`.
- Traces cover ToR0 sources 0-7 (8 of 32 ToR0 hosts). Retransmit and ECN counts are whole-run (1024 flows).
- No RTOs and no freezing in any run.

## Results: percent of post-warmup draws using a random EV (mean of 3 seeds)

| rate | fail | B=1 | B=2 | B=4 | B=8 | B>=16 |
|---|---|---|---|---|---|---|
| under (100G) | healthy | 33.6 | 6.5 | 0.05 | 0.05 | 0.05 |
| under | uniform50 | 29.3 | 3.2 | 0.06 | 0.06 | 0.06 |
| under | nonuniform | 37.7 | 13.5 | 0.72 | 0.14 | 0.14 |
| matched (200G) | healthy | 32.7 | 9.2 | 0.07 | 0.05 | 0.05 |
| matched | uniform50 | 48.5 | 38.6 | 26.3 | 1.10 | 0.66 |
| matched | nonuniform | 44.3 | 23.9 | 9.1 | 2.03 | 1.93 |
| over (400G) | healthy | 25.5 | 3.9 | 0.71 | 0.83 | 0.83 |
| over | uniform50 | 99.7 | 99.7 | 99.7 | 99.7 | 99.7 |
| over | nonuniform | 99.4 | 99.3 | 99.3 | 99.3 | 99.3 |

Share of clean ACKs (before the source's last draw) that overwrite a valid EV, mean of 3 seeds (%):

| rate / fail | B=1 | B=2 | B=4 | B=8 | B>=16 |
|---|---|---|---|---|---|
| under / healthy, uniform50 | 33.6 / 29.3 | 6.5 / 3.1 | 0 | 0 | 0 |
| under / nonuniform | 37.4 | 13.4 | 0.64 | 0 | 0 |
| matched / healthy | 32.7 | 9.2 | 0.04 | 0 | 0 |
| matched / uniform50 | 28.9 | 10.4 | 2.7 | 0.01 | 0 |
| matched / nonuniform | 29.1 | 14.7 | 5.0 | 0.13 | 0 |
| over / healthy | 19.8 | 2.6 | 0 | 0 | 0 |
| over / nonuniform | 16.1 | 7.8 | 3.3 | 3.7 | 1.2 (B=16), 0.06 (B=32), 0 |
| over / uniform50 | 11.4 | 0.8 | 0 | 0 | 0 |

(over/degraded has only ~200-400 clean ACKs per run in the traced hosts, so those percentages rest on very few events: 0-75 overwrites per run.)

ToR0 mean FCT (us), B=1 / 8 / 64: under 1392.2-1392.9 flat; matched healthy 700.3 flat; matched uniform50 706.0 / 702.1 / 702.0; matched nonuniform 713.6 / 702.3 / 702.3; over healthy 357.5 / 356.3 / 356.3; over uniform50 710.7 / 711.0 / 711.0; over nonuniform 700.7 / 700.7 / 700.7.

## Findings
1. **With a correct matched rate, B matters up to ~8 on a degraded fabric.** Matched/uniform50: 48.5 / 38.6 / 26.3 / 1.1 % random at B=1/2/4/8, then 0.66 flat from B=16 (retransmits 5 / 41 / 32 at B=1/2/4, 0 at B>=8; ECN-marked ACKs 36k / 41k / 32k at B=1/2/4, 1.0k at B=8, 0.5k at B>=16). Matched/nonuniform: 44.3 / 23.9 / 9.1 / 2.0 % random at B=1/2/4/8 and 1.9% from B=16, ~54 retransmits per run remain at B>=8; ToR0 FCT 713.6 us (B=1) to 702.3 us (B=8), -1.6%. Matched/healthy needs only B=4 (0.07%). Beyond B=16 nothing changes: peak k (mean over seeds) is 9 at matched/uniform50 and 13.7 at matched/nonuniform, so B>16 is never filled. B=8 is the knee on degraded fabrics (it was ~4 in the data-only first version, which was an overloaded operating point).
2. **Matched/uniform50 now behaves like over/healthy** (both ~1% random at B=8 and flat beyond, 0 retransmits, FCT flat for B>=8), as expected: both sit at the bottleneck capacity on a clean fabric. Matched/nonuniform is a little worse (2%, 54 retransmits) because the 25% links are overloaded.
3. **B=1 and B=2 are bad everywhere except over/degraded**: 25-48% random at B=1, 3-39% at B=2. Under capacity from B=4 on <=0.7% random, FCT rate-bound (1392 us), 0 retransmits, and ECN only on non-uniform (621 / 157 / 50 / 53 marked ACKs per run at B=1 / 2 / 4 / >=8; none on healthy and uniform50).
4. **Over capacity on a degraded fabric (400G into 200G):** 99.4-99.7% random draws and ~32k retransmits per run for every B; k ~0, FCT 701-711 us independent of B. The sender, not the load balancer, is the problem.
5. **Overwrites:** once the flow-tail artefact is removed, a valid EV is lost only when B is too small: at B=1 17-37% of clean ACKs, B=2 up to 15%, B=4 up to 5%, and at B>=8 ~0 (matched/nonuniform B=8: 0.13%; over/nonuniform keeps 3.7% at B=8 and 1.2% at B=16 from a few hundred clean ACKs). This tracks the random-draw drop: a buffer that never fills never overwrites. Overwrites of an identical EV value were not separated.
6. **Reconciling with NSCC (M1):** NSCC settles at the target-delay standing queue, mid-ECN-ramp. With the corrected rate a constant sender at the matched knee has ~1% random draws, so the 55-60% random draws under NSCC come from the standing queue of the delay target, not from operating at capacity per se.

## Caveats
- 3 seeds; CIs wide, ~1 us FCT differences are not significant. Single workload and topology, trimming on.
- Rate is per host NIC (data + ACK), data goodput ~1.5% below R; "matched 200G" therefore leaves ~3G headroom for data, which is what removes the standing queue.
- Random/k/overwrite statistics come from 8 of 32 ToR0 hosts; retransmit/ECN counts are whole-run.
- M1's `pct_random` includes pre-first-ACK warmup; M4's excludes it.

## Plots
`plots/m4_pct_random.png`, `m4_k_mean.png`, `m4_k_ge3.png`, `m4_fct_tor0.png`, `m4_fct_p99.png`, `m4_spray_width.png`; `python ../scripts/build_interactive.py` writes `plots/interactive.html` (gitignored; publish via thesis repo on request) with split, k distribution, overwrites, FCT and loss panels per rate and failure model.

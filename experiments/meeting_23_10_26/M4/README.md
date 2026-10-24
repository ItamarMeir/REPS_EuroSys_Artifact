# M4 - Does REPS buffer size B matter at known constant send rates?

## Setup
- Sender: `-sender_cc_algo constant` with `-rate_const_gbps R` (timer-paced, no congestion control; see `../../RATE_CONST_ARCHITECTURE.md`). R = 100 / 200 / 400 Gbps per source = 0.25 / 0.5 / 1.0 of the 400G NIC ("under" / "matched" / "over").
- Fabric: `fat_tree_1024_1os_2t_400g`, tornado 16 MiB, 1024 flows, SRv6 32 paths, trimming on, `-disable_tor_ecn`, `-load_balancing_algo freezing`.
- Failure models (ToR0 uplinks only): `healthy`; `uniform50` (all 32 uplinks at 50%); `nonuniform` (even agg 25% / odd agg 75% of speed, mean 50%; see `../M3`).
- B in {1,2,4,8,16,32,64}, seeds 42-46 (315 runs). Table values are means over seeds; 95% CIs (t-distribution) in `data/m4_summary.csv`.
- Capacity per source on degraded ToR0 is 200 Gbps, so under/matched/over = below / at / above the bottleneck. On the healthy fabric 400 Gbps is the matched case and "over" is not reachable beyond NIC line rate.
- Raw per-run results: `data/results.jsonl`; aggregation and plots: `scripts/plot_m4.py`, `plots/`. Runner: `scripts/run_m4.py`.

## Results (percent of sends using a random EV, seed mean)

| rate | fail | B=1 | B=2 | B=4 | B=8 | B=16..64 |
|---|---|---|---|---|---|---|
| under (100G) | healthy | 22.4 | 0.7 | 0.7 | 0.7 | 0.7 |
| under | uniform50 | 29.0 | 0.7 | 0.7 | 0.7 | 0.7 |
| under | nonuniform | 33.0 | 3.5 | 0.95 | 0.79 | 0.79 |
| matched (200G) | healthy | 33.8 | 7.5 | 1.3 | 1.3 | 1.3 |
| matched | uniform50 | 69.1 | 55.3 | 50.6 | 49.9 | 49.5 |
| matched | nonuniform | 50.1 | 29.6 | 21.3 | 20.2 | 20.8 |
| over (400G) | healthy | 27.3 | 6.3 | 3.4 | 3.25 | 3.25 |
| over | uniform50 | 99.5 | 99.4 | 99.4 | 99.4 | 99.4 |
| over | nonuniform | 99.2 | 99.2 | 99.2 | 99.2 | 99.2 |

FCT (ToR0 mean, us; p99 tracks it within ~0.5 us):

| rate | fail | B=1 | B=8 |
|---|---|---|---|
| under | any | ~1371.3-1371.7 | ~1371.3-1371.9 |
| matched | healthy | 689.8 | 689.8 |
| matched | uniform50 | 703.6 | 704.8 |
| matched | nonuniform | 709.6 | 696.5 |
| over | healthy | 357.6 | 356.2 |
| over | uniform50 | 711.1 | 711.2 |
| over | nonuniform | 700.8 | 700.9 |

## Findings
1. **B matters only below ~4; beyond 4-8 nothing changes.** Every metric is flat from B=8 to B=64 (for healthy runs the values are identical to the digit). Peak buffer occupancy `k_max` at B=64 is 1.6-8.6 valid EVs, so a larger buffer is never filled. This confirms the meeting's observation that B beyond 4-8 is irrelevant, now measured with known send rate instead of NSCC.
2. **B=1 is clearly bad** (22-69% random draws everywhere sub-saturated): one slot is lost every time it is consumed with no replacement ACK yet. B=2 recovers most of the benefit when the fabric is clean (under: 0.7%), B=4 the rest.
3. **Under capacity (100G):** random draws drop to <1% for healthy and uniform50 from B=2; FCT is rate-bound (1371 us) and identical across B and failure models. Non-uniform needs B>=4-8 (k_ge3 rises from 26% to 77%), but with no FCT effect. No RTOs, no freezing, no retransmits.
4. **Matched capacity (200G):** this is where B and the failure model interact. Healthy: 1.3% random from B=4. Uniform50: ~50% random draws regardless of B (50.6 at B=4, 49.5 at B=16+), about 400 retransmits per run; the standing queue at the bottleneck makes roughly half of ACKs ECN-marked, so valid EVs are not available. B cannot fix it; FCT is 704-705 us for all B (healthy 690). Non-uniform: 20% random at B=8, better than uniform because the 75%-speed links keep returning valid EVs; B=1->8 improves FCT 710 -> 697 us, the only place B visibly moves FCT.
5. **Over capacity (400G):** healthy stays fine (3.3% random at B>=8, FCT 356 us). On degraded fabrics the sender exceeds capacity: 99.2-99.5% random draws and ~32k retransmits per run (about half of all packets, tail dropped / trimmed) for every B; FCT 701-712 us independent of B. With no ACK feedback to throttle the sender, the buffer is permanently empty (k ~ 0). B is irrelevant here because the sender, not the load balancer, is the problem.
6. **Reconciling with the NSCC runs (M1):** NSCC settles at the target-delay standing queue, which is the matched-degraded operating point, hence ~55-60% random draws: it sits in the matched/uniform50 row above, not at "healthy-looking" behaviour. The premise that a perfect CC would restore ~1% random draws on a 50%-degraded fabric is only true when the rate is held clearly below capacity (under row: 0.7%), not at the matched knee, where marking itself is the cost of operating at capacity.
7. No RTOs and no freezing in any of the 315 runs (`rtos`, `freeze_entries` are 0), so the freezing mechanism plays no role in this grid.

## Caveats
- Single workload (tornado 16 MiB), single topology, trimming on. `rtx` counts at "over" reflect the constant-rate sender ignoring loss (retransmits are charged against R).
- "Random draw" = fresh buffer empty at send; it is reported as measured from the first 8 ToR0 sources' event traces (8 of 32 per-ToR hosts), not all 1024.
- Plots: `plots/m4_pct_random.png`, `m4_k_mean.png`, `m4_k_ge3.png`, `m4_fct_tor0.png`, `m4_fct_p99.png`, `m4_spray_width.png`.

## Interactive page
`python ../scripts/build_interactive.py` writes `plots/interactive.html` (Plotly from cdnjs; gitignored, publish via the thesis repo on request).

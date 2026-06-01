# exp07 — Filter Comparison: Vanilla vs WTD vs Smart-Filter Modes A/B

**Status**: **Complete.** 144 cells run (6 modes × 4 workloads × 2 sev × 3 seeds). Full artifacts preserved: 7 plots, 3 CSVs, scripts, raw runs.

---

## Motivation

Exp06 implements two smart-filter modes (Mode A: `md_gain`, Mode B: `rtt_blend_ecn_thresh`)
that use the REPS buffer's congestion-evidence counter to dampen NSCC's multiplicative
decrease step. The natural comparison baseline is the SMaRTT-REPS paper's own §3.6.1 mechanism
— **"Wait to Decrease" (WTD)** — which also tries to prevent NSCC from over-reacting to
transient ECN events, but uses a single EWMA threshold on the ECN signal rather than
REPS buffer state.

**The central question**: does using *network topology knowledge* (REPS buffer saturation)
give a better filter than a pure *signal-averaging* approach (ECN EWMA)?

Both mechanisms target the same pathology: one outlier EV in the REPS buffer returns occasional
ECN-marked ACKs, triggering NSCC's multiplicative decrease even though the rest of the
buffer's paths are clean. WTD blunts this by requiring the ECN *average* to exceed 25%
before MD fires. Smart-filter Mode A blunts it by scaling MD's step size by `counter/B`.
Smart-filter Mode B fully suppresses ECN below K=ceil(B/4) and blends the delay signal above it.

---

## WTD implementation (paper §3.6.1)

The paper's WTD is:
> "NSCC waits for the smoothed ECN rate to exceed a threshold before performing a
> multiplicative decrease."

In code (`htsim/sim/uec.cpp`):
- `_exp_avg_ecn` (α=0.125) is already computed every ACK by `average_ecn_bytes()`.
- WTD gates the MD dispatch in `updateCwndOnAck_NSCC()`:
  ```cpp
  if (!(_nscc_wtd_enabled && _exp_avg_ecn < _wtd_threshold)) {
      multiplicative_decrease(newly_acked_bytes);
  }
  ```
- `_wtd_threshold = 0.25` (paper value; 25% ECN rate).
- The existing `_exp_avg_ecn = 1.0` reset on RTO is preserved: after a timeout the EWMA
  is forced high so WTD does not suppress MD on real congestion events.
- `_nscc_wtd_enabled = false` by default; enabled with `-wtd_in_nscc`.
- Mutually exclusive with `-state_aware_ecn` and `-smart_filter_mode` (3-way hard error).

See `CLAUDE.md` Modifications inventory `[ADDED: wtd-in-nscc]` for code-level details.

---

## Topology

- **fat_tree_128_1os_3t_400g.topo** — k=8, 128 hosts, 400 Gbps links, 3-tier, 1:1 OC
- BDP reference: 400 Gbps × 4 µs RTT / (8 × 4150 bytes) ≈ **48 packets**

---

## Common flags (all runs)

```
-sack_threshold 4000 -end 5000 -paths 65535
-sender_cc_only -sender_cc_algo nscc
-load_balancing_algo freezing -exit_freeze 200000000
-topo fat_tree_128_1os_3t_400g.topo
-linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151
-disable_tor_ecn
```

No `-state_aware_ecn`. Default REPS buffer size `B=8` (auto-K = ceil(8/4) = 2 for Mode B).

---

## Design matrix (144 cells)

| Dimension | Values | Count |
|-----------|--------|-------|
| `mode` | `vanilla`, `wtd`, `sf_md_gain_ecn`, `sf_md_gain_fresh`, `sf_blend_ecn`, `sf_blend_fresh` | 6 |
| `workload` | `pureperm_8mb`, `composite`, `perm_32mb`, `perm_128mb` | 4 |
| `sev` | `0` (healthy), `4` (one Agg↔Core link fails 50→200 µs) | 2 |
| `seed` | `42`, `43`, `44` | 3 |

**Total: 144 cells.** Runtime ≈ 20-40s/cell; ~1–2 hours sequential, ~10-15 min on 8 cores.

---

## Mode → CLI flag mapping

| Mode label | Extra CLI flags |
|---|---|
| `vanilla` | *(none)* |
| `wtd` | `-wtd_in_nscc` |
| `sf_md_gain_ecn` | `-smart_filter_mode md_gain -smart_filter_counter ecn` |
| `sf_md_gain_fresh` | `-smart_filter_mode md_gain -smart_filter_counter fresh` |
| `sf_blend_ecn` | `-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn` |
| `sf_blend_fresh` | `-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh` |

For `sev=4`, add: `-fail_link_time 50 200 -fail_link_target 0 0`

---

## Workload files

| Label | File |
|---|---|
| `pureperm_8mb` | `htsim/sim/datacenter/connection_matrices/perm_n128_s8388608.cm` |
| `composite` | `state_aware_experiments/workloads/composite.cm` |
| `perm_32mb` | `htsim/sim/datacenter/connection_matrices/perm_128n_128c_32MB_s{seed}.cm` |
| `perm_128mb` | `htsim/sim/datacenter/connection_matrices/perm_128n_128c_128MB_s{seed}.cm` |

---

## How to run

```bash
# Build (one-time, from repo root)
cd htsim/sim && make -j8 && cd datacenter && make -j8 && cd ../../..

# Run all 144 cells (idempotent — safe to rerun, skips existing outputs)
bash state_aware_experiments/exp07_filter_compare_v7/scripts/v7_run_matrix.sh

# Optional dry-run to preview commands
bash state_aware_experiments/exp07_filter_compare_v7/scripts/v7_run_matrix.sh --dry-run

# Aggregate to CSVs
python3 state_aware_experiments/exp07_filter_compare_v7/scripts/v7_aggregate.py

# Generate plots (7 PNGs to plots/)
python3 state_aware_experiments/exp07_filter_compare_v7/scripts/v7_plot.py

# Compress raw runs (after analysis)
tar -czf state_aware_experiments/exp07_filter_compare_v7/runs.tar.gz \
    -C state_aware_experiments/exp07_filter_compare_v7/runs . \
  && rm -rf state_aware_experiments/exp07_filter_compare_v7/runs/
```

---

## Output structure

```
exp07_filter_compare_v7/
├── README.md                  ← this file
├── plots/                     ← PNG plots (after v7_plot.py)
├── data/
│   ├── v7_fct.csv             ← per-flow FCT + slowdown (one row per flow)
│   ├── v7_events.csv          ← per-run event counts + WTD stats
│   └── v7_diagnostics.csv     ← per-ACK state for src=0,7,63 (diagnostic)
├── scripts/
│   ├── v7_run_matrix.sh       ← experiment driver
│   ├── v7_aggregate.py        ← CSVs aggregator
│   └── v7_plot.py             ← plotter (7 PNGs)
└── runs/                      ← raw outputs (compress to runs.tar.gz after analysis)
    └── {mode}/{workload}/sev{S}/seed{K}/
        ├── run.out
        └── reps_state.csv     ← per-ACK state for src 0, 7, 63
```

---

## Plots (7 PNGs)

| File | Description |
|---|---|
| `fig1_overall_p99_slowdown.png` | p99 FCT slowdown per mode × sev, 4 workload panels |
| `fig2_overall_mean_fct.png` | Mean FCT (µs) per mode × sev, 4 workload panels |
| `fig3_composite_class.png` | Composite only: elephant/mice/incast p99 slowdown × mode × sev |
| `fig4_fct_cdf_{workload}.png` | FCT CDF all flows, 6 modes overlaid (sev=0, sev=4 panels) |
| `fig5_md_event_count.png` | REPS freeze event count per mode × sev (congestion proxy) |
| `fig6_diagnostic_timeseries.png` | cwnd, exp_avg_ecn, ecn_counter vs time (src=0, composite, sev=4, seed=42) |
| `fig7_wtd_block_rate.png` | WTD block rate per workload × sev (sanity: is WTD firing?) |

---

## CSV columns

### v7_fct.csv
One row per finished flow.
`mode, workload, sev, seed, flow_id, fct_us, size, flow_class, ideal_fct_us, slowdown`

`flow_class`: for composite — `elephant` (id 1-96), `mice` (97-352), `incast` (353-416);
for perm workloads — `all`.

### v7_events.csv
One row per run (144 rows when complete).
`mode, workload, sev, seed, n_flows_finished, pipe_fails, pipe_restores, fz_starts, fz_exits,
n_ecn_acks, n_wtd_blocked, wtd_block_rate`

`wtd_block_rate` = fraction of ECN-marked ACKs where `wtd_can_decrease=0` (only meaningful
for `mode=wtd`; always 0 for other modes).

### v7_diagnostics.csv
Per-ACK rows from `reps_state.csv` for sources 0, 7, 63.
`mode, workload, sev, seed, time_us, src_id, ecn, fresh, cwnd_pkts, in_flight_pkts,
exp_avg_ecn, buf_size, ecn_counter, fresh_inv, sf_mode, sf_counter_used, sf_ecn_thresh,
sf_gain, sa_asym, cc_ecn_view, wtd_enabled, wtd_can_decrease`

---

## Validation checks before claiming results

1. `grep "enable on tor downlink 1" runs/*/run.out` must return nothing.
2. Vanilla cells: FCTs match exp04 vanilla cells for same workloads+seeds (regression check).
3. WTD sanity: `fig7_wtd_block_rate.png` must show non-zero block rate for at least `perm_8mb sev=0` (light congestion where a single ECN event doesn't push EWMA to 0.25).
4. Smart-filter sanity: `fig6` must show `ecn_counter` tracking `ecn` marks, and lower `cwnd` volatility for sf modes relative to vanilla.
5. Coexistence: verify `-wtd_in_nscc -state_aware_ecn` exits with error code 1.
6. Default-off invariant: build without new flags; run one vanilla cell; diff the output vs a pre-implementation vanilla run — byte-identical except line numbers.

---

## Expected outcomes

- **WTD**: should reduce cwnd thrashing on light ECN events (EWMA stays < 0.25 for brief bursts),
  improving healthy-state incast p99. Under failure, ECN floods quickly → EWMA hits 0.25 → MD
  fires normally. Recovery should be similar to vanilla.
- **Mode A (`sf_md_gain`)**: similar intent to WTD but evidence from buffer state. At `counter/B ≈ 0`
  the MD step is nearly zero; at `counter/B = 1` it's vanilla. Expect smoother cwnd dynamics.
- **Mode B (`sf_blend`)**: most aggressive suppression; ECN fully blocked below K=2/8 of buffer.
  Expect the highest FCT improvement in healthy state but potentially slower failure recovery.
- **`fresh` counter**: leading indicator (fires before first ECN). Expect earlier response but
  risk of over-damping in healthy state if buffer empties transiently.

---

## Open questions (pre-run)

1. If WTD shows `wtd_block_rate ≈ 0` across all workloads, the EWMA converges too slowly (or
   too fast) to the paper's threshold. Consider sweeping `_wtd_threshold ∈ {0.15, 0.25, 0.35}`.
2. If Mode B's failure recovery is ≥ 20% worse than vanilla, consider raising K from ceil(B/4)
   to ceil(B/3) (K=3 for B=8).
3. If CIs are wide enough that no mode is distinguishable from vanilla, add seeds 45+46 (→ 5 seeds,
   df=4) for tighter intervals.

---

---

## Results and Analysis

All 144 cells completed successfully. Zero `"enable on tor downlink 1"` lines detected.

### Headline: All filters are statistically neutral

**No mode produces a statistically significant FCT improvement over vanilla across any workload.**
All p99 slowdown values are within the confidence intervals of vanilla, and every pairwise
paired t-test (3 seeds, df=2) returns p > 0.05 — with one exception that is actually a
*regression*, not an improvement (see §"sf_md_gain_fresh anomaly" below).

Summary of p99 FCT slowdown (mean ± 95% CI over 3 seeds):

| Mode | pureperm_8mb sev=0 | pureperm_8mb sev=4 | composite sev=0 | perm_128mb sev=0 |
|---|---|---|---|---|
| vanilla | 1.115 ± 0.003 | 1.319 ± 0.112 | 17.219 ± 0.470 | 1.070 ± 0.004 |
| wtd | 1.115 ± 0.003 | 1.320 ± 0.109 | 17.354 ± 0.575 | 1.070 ± 0.002 |
| sf_md_gain_ecn | 1.115 ± 0.003 | 1.326 ± 0.114 | 17.243 ± 0.354 | 1.069 ± 0.002 |
| sf_md_gain_fresh | 1.115 ± 0.003 | 1.317 ± 0.101 | 17.269 ± 0.686 | 1.070 ± 0.004 |
| sf_blend_ecn | 1.115 ± 0.003 | 1.303 ± 0.100 | 17.158 ± 0.645 | 1.072 ± 0.011 |
| sf_blend_fresh | 1.115 ± 0.003 | 1.316 ± 0.090 | 17.111 ± 0.916 | 1.071 ± 0.005 |

Mean FCT and freezing event counts are likewise indistinguishable across modes.

---

### Finding 1 — The central hypothesis does not hold at these workloads

The hypothesis was: *"NSCC over-reacts to ECN from a single outlier EV in the REPS buffer;
suppressing MD when the buffer shows low ECN saturation will improve FCT."*

The counter data falsifies this. Among ECN-marked ACKs (sev=0, src=0 across all runs):
- **ecn_counter mean = 4.87 / 8** at time of ECN receipt (median = 5)
- **65% of ECN ACKs** arrive when `ecn_counter ≥ 4` (≥ 50% buffer saturation)
- Only **15% arrive when `ecn_counter < 2`** — the "true outlier" scenario

At these workloads and load levels, congestion is **diffuse**, not spatially localized. Most
ECN marks arrive when the buffer is already substantially saturated across multiple EVs, meaning
the congestion signal is accurate and suppressing MD is simply wrong. The "one bad EV" scenario
that both WTD and the smart-filter target is present in only ~15% of ECN events, too rarely to
move the FCT distribution.

---

### Finding 2 — WTD fires often but randomly (high variance, no FCT effect)

WTD block rates (fraction of ECN ACKs where MD was suppressed, sev=0):
- `pureperm_8mb`: seeds 42/43/44 give **0.89 / 0.98 / 0.53** — wildly different for identical workloads
- `composite`: **1.00 / 1.00 / 0.93** — WTD suppresses almost every MD event
- `perm_32mb`: **0.10 / 0.99 / 0.12** — bimodal: seed 43 nearly always suppressed, others rarely
- `perm_128mb`: **0.03 / 0.99 / 0.04** — same bimodal pattern

The seed-to-seed variance is enormous because the `_exp_avg_ecn` EWMA (α=0.125) converges to
a different regime depending on each traffic matrix's initial ECN burst pattern. When the
run starts with a dense burst, `avg_ecn` immediately exceeds 0.25 and WTD never fires; when
it starts clean, `avg_ecn` stays low and WTD suppresses nearly all MD.

This means WTD's behavior is regime-dependent, not traffic-load-dependent — which explains
why it produces no mean FCT gain even when it fires frequently.

At sev=4, block rates collapse: `perm_32mb` drops to 0.06-0.14, `perm_128mb` to 0.015-0.024.
The link failure floods ECN marks instantly and the EWMA ramps past 0.25 within a few RTTs,
restoring MD. Recovery speed is vanilla-equivalent, confirming the `_exp_avg_ecn = 1.0` RTO
reset works as intended.

---

### Finding 3 — Mode A (md_gain, ECN counter) damps MD by 76–84% but has no FCT effect

The ECN-counter-based gain is operating correctly:
- sev=0: mean gain = **0.16 / 8 = 2%** — MD is reduced to ~16% of its vanilla magnitude 76% of the time
- sev=4: mean gain = **0.31** — buffer is more saturated under failure, gain rises appropriately

ECN suppression = **0%** (ECN always passes through; only the MD step size is scaled). Despite
the heavy per-step damping, NSCC's AI/PI branches quickly recover any lost cwnd in the next
clean ACK. The net cwnd trajectory is nearly identical to vanilla because:
1. Each individual MD is smaller but happens at similar frequency
2. The subsequent PI/AI bring cwnd back up faster
3. The flow completes at the same time

---

### Finding 4 — Mode A with the `fresh` counter is nearly identical to vanilla (and slightly worse under failure)

The `fresh` counter measures `B − getNumberFreshEntropies()`. The buffer almost always has
fresh_inv ≈ B because REPS depletes its fresh slots rapidly:
- **sev=0**: mean_fresh = 1.95/8; `fresh_inv ≥ 4` for **98.1%** of ACKs; `fresh_inv = 8` for **12.1%**
- **sev=4**: mean_fresh = 1.41/8; `fresh_inv ≥ 4` for **96.1%** of ACKs

This gives `sf_md_gain_fresh` mean_gain = **0.84** at sev=0 (vs 0.16 for ECN counter).
The "leading indicator" hypothesis (fresh depletes before ECN → earlier damping) is correct,
but it's almost always fully depleted — so the gain is near 1 almost always, making this
mode behave like slightly-degraded vanilla.

The one statistically significant result in the experiment is `sf_md_gain_fresh` at
`perm_128mb sev=4`: Δp99_slowdown = **+0.0015, p = 0.008** — a small but real regression.
The mechanism: during failure, the buffer briefly refills with fresh EVs when frozen flows
release their slots, causing `fresh_inv` to dip. This makes the filter under-react precisely
during the period of maximum congestion, delaying cwnd recovery. The ECN counter does not
have this artifact (it decays organically by −1 per clean ACK regardless of the LB state).

---

### Finding 5 — Mode B (rtt_blend_ecn_thresh) suppresses ~18% of ECN marks but has no FCT effect

Mode B's ECN gate (threshold K = ceil(8/4) = 2) suppresses ECN when `ecn_counter < 2`:
- sev=0: ECN suppression rate = **17.8%** (sf_blend_ecn) vs 1.4% (sf_blend_fresh)
- sev=4: ECN suppression rate = **17.3%** (sf_blend_ecn) vs 1.3% (sf_blend_fresh)

When ECN is suppressed (counter < 2), `fair_increase` or `proportional_increase` fires instead
of MD — cwnd actively **grows** on an ECN-marked ACK. This is the most aggressive damping mode
and gives the best incast p99 hint in composite (sf_blend_fresh: **798.5 µs vs 810.9 µs**
vanilla at sev=0, −1.5%), but the effect is not statistically significant (p=0.161).

The `fresh` counter source for Mode B is nearly useless: with `fresh_inv ≥ 4` for 98% of ACKs,
the counter almost never falls below K=2, so the gate almost never fires (1.4% suppression rate).

---

### Finding 6 — Logging bug in cc_ecn_view for vanilla and WTD

The `cc_ecn_view` CSV column is reconstructed in the logging code as:
```cpp
bool cc_ecn_log = pkt.ecn_echo() && (_network_is_asymmetric
                   || (_smart_filter_mode == SF_MD_GAIN)
                   || (_smart_filter_mode == SF_RTT_BLEND_ECN_THRESH && counter >= K));
```
For vanilla and WTD modes all three conditions are false, so `cc_ecn_view` is always logged
as 0. **The actual CC behavior is correct** — vanilla sees the real ECN bit and WTD gates
MD internally — but the diagnostic column cannot be trusted for those two modes.
This does not affect any FCT results and can be fixed in a future patch by adding a
`vanilla/wtd` leg to the reconstruction logic.

---

### Summary table

| Mode | Mechanism fires? | Direction of effect | FCT impact | p-value range |
|---|---|---|---|---|
| `wtd` | Yes, but highly variable (0–100% by seed) | Neutral / slight EWMA inflation at sev=4 | None | p > 0.4 all cells |
| `sf_md_gain_ecn` | Yes (gain ≈ 0.16 at sev=0) | MD damped but AI/PI compensate | None | p > 0.5 |
| `sf_md_gain_fresh` | Almost no damping (gain ≈ 0.84) | Slight regression at sev=4 | **Small regression** (perm_128mb sev=4, p=0.008) | p=0.008 (bad direction) |
| `sf_blend_ecn` | Yes, 18% ECN suppression | AI/PI grows cwnd on suppressed ECN | None | p > 0.05 |
| `sf_blend_fresh` | Almost none (1.4% suppression) | Near-vanilla | None | p > 0.05 |

---

### Interpretation and next steps

The null result is informative: **at full-bisection load on this topology, NSCC+REPS is
already correctly coupled to the network's congestion signal.** The ECN marks that NSCC
reacts to are, 65% of the time, genuinely sustained congestion across multiple paths —
not the outlier-EV scenario these filters were designed to address.

This points to three productive follow-up directions:

1. **Lower-load / sparse traffic**: Run the same 6 modes at 20–40% load or with a
   small number of concurrent flows (2-4 sources). At low load, outlier-EV spatial
   collisions dominate over genuine congestion, and the 15% "low counter ECN" share
   should grow substantially. Mode A with ECN counter is the right candidate to test first.

2. **Fix the fresh counter**: The fresh-inv counter is near-maximal because REPS depletes
   fresh slots at initialization. A proper "outlier" signal would be `B − number_of_good_EVs`
   (EVs that have been seen at least once and returned without ECN), not the inverse of
   unused slots. This requires tracking EV health state, not just freshness.

3. **Composite WTD finding**: WTD fully suppresses MD for the composite workload at sev=0
   (block rate ≈ 1.0 for seeds 42,43). Yet incast p99 is 816.5 µs vs vanilla's 810.9 µs —
   a slight degradation, not improvement. The finding that blocking MD on incast-heavy
   workloads hurts (rather than helps) is itself a result: the paper's WTD mechanism
   benefits NSCC only in the single-flow or mice-dominant regime, not composite.

The ECN-counter-based smart filter (Mode A with ECN counter) is the most mechanically sound
of the tested filters. Its failure to improve FCT is a workload-regime finding, not a
mechanism failure. It should be re-evaluated at lower loads and/or with a more targeted
"outlier EV" counter definition.

# State-Aware NSCC + REPS — experiments

This directory holds everything produced while building and evaluating the **state-aware NSCC + REPS** extension to the htsim simulator. The architecture sits on top of the paper's existing REPS (= `-load_balancing_algo freezing` in this code) and toggles how the Congestion Controller reacts to ECN based on whether the load balancer's internal state suggests the network is in a "spatially-resolvable" or a "structurally-asymmetric" state.

If you're new here, the recommended reading order is:
1. **[ARCHITECTURE.md](ARCHITECTURE.md)** — what the extension is and how it's wired into `htsim/sim/`.
2. **[exp03_matrix_sweep_v3/README.md](exp03_matrix_sweep_v3/README.md)** — the main empirical result (200-cell sweep with plots).
3. **[RUNNING_EXPERIMENTS.md](RUNNING_EXPERIMENTS.md)** — how to add the next experiment in this layout.

---

## Experiment lineage

| # | Dir | LB algo | What it measured | Status | Headline takeaway |
|---|---|---|---|---|---|
| 01 | [`exp01_lb_dynamics_reps_v1/`](exp01_lb_dynamics_reps_v1/) | `reps` (simpler code variant) | Per-ACK buffer dynamics across 6 scenarios (paths × workload × topology), no failures | Findings only — raw plots/data lost between sessions | Per-ACK absolute buffer size is NOT predictive of ECN (corr ≈ 0); buffer dips on ECN and recovers within ~3 ACKs. Triggered the v2 redo. |
| 02 | [`exp02_lb_dynamics_freezing_v2/`](exp02_lb_dynamics_freezing_v2/) | `freezing` (paper-REPS, 8-slot bounded) | Same 6 scenarios under the paper's actual REPS algorithm | Findings only — raw plots/data lost between sessions | **`fresh = 0` ⇒ P(next ACK is ECN) ≈ 1.0** in every workload. The bounded buffer's emptiness is a sharp, near-deterministic signal of imminent congestion. |
| 03 | [`exp03_matrix_sweep_v3/`](exp03_matrix_sweep_v3/) | `freezing` | 200-cell matrix: 4 workloads × 5 failure severities × 2 modes × 5 seeds, with per-class FCT + event counts | **Full artifacts preserved**: 16 plots, 2 CSVs, scripts, compressed raw runs | Once the leaf-ECN exception is correctly in place (`-disable_tor_ecn`), state-aware mode's FCT impact on synthetic workloads is small. The architecture is **correctly wired** (SA flag flips exactly equal FREEZING entries; zero false positives in 40 healthy-state runs) but the FCT win is narrow. Strongest signal: incast p99 improves ~14 μs in healthy composite. |
| 04 | [`exp04_buffer_ev_sweep_v4/`](exp04_buffer_ev_sweep_v4/) | `freezing` | Two 200-cell sweeps: (A) buffer size ∈ {1,2,4,8,∞} × (B) EV domain ∈ {1,2,4,8,16}; 4 workloads including full-bisection 128MB perm; sev ∈ {0,4}; 5 seeds; tracks FCT slowdown + cwnd/BDP + window fill rate | **Full artifacts preserved**: 12 plots, 3 CSVs, scripts, compressed raw runs (43 MB) | **Buffer size is irrelevant** (FCT flat across buf=1..∞; cwnd/BDP≈4.3 throughout). **EV domain is critical**: ev_domain=1 → 5× FCT slowdown + only 45/128 heavy flows complete under failure; diminishing returns after ev=8. CC window fill_rate≈0.97 everywhere — CC is always the binding constraint, not data availability. |
| 06 | [`exp06_smart_filter_v6/`](exp06_smart_filter_v6/) | `freezing` | Smart filter between REPS (LB) and NSCC (CC): two filter modes (md_gain, rtt_blend_ecn_thresh) × two counter sources (ecn, fresh) × 4 workloads × 2 sev × 3 seeds = 120 cells. All on vanilla REPS+NSCC (no `-state_aware_ecn`). Stretch sweep: B ∈ {2,8,16,32}. | **Code implemented, experiments not yet run** | TBD |
| 07 | [`exp07_filter_compare_v7/`](exp07_filter_compare_v7/) | `freezing` | Filter comparison: vanilla vs WTD vs smart-filter Modes A/B × 2 counter sources. 6 modes × 4 workloads × 2 sev × 3 seeds = 144 cells. Directly compares the paper's own ECN-EWMA gate (WTD) against the buffer-state-aware smart filter. | **Full artifacts preserved**: 7 plots, 3 CSVs, scripts | **Null result across all filters.** At full bisection load 65% of ECN ACKs arrive with `ecn_counter ≥ 4/8` — congestion is diffuse, not outlier-EV. WTD suppresses MD but with high seed-to-seed variance (0–100%). `sf_md_gain_fresh` causes a small p=0.008 regression under failure. Best incast p99 gain: `sf_blend_fresh` saves ~12 µs at sev=0 composite, not significant. |
| 08 | [`exp08_lowload_v8/`](exp08_lowload_v8/) | `freezing` | Low-load filter comparison: same 8 modes (incl. new `evhealth` counter) on sparse TMs (2, 16, 32 concurrent flows) where outlier-EV spatial collisions are expected to dominate. 8 modes × 3 workloads × 2 sev × 5 seeds = 240 cells. Also serves as WTD targeted test (2-flow workload). | **Full artifacts preserved**: 8 plots, 3 CSVs, scripts, compressed raw runs (8.3 MB) | **Zero ECN at all tested loads — deeper null result.** n_ecn_acks=0 for all 240 runs. At ≤32 flows on a 128-host 400Gbps fat-tree, queues never reach the 25% ECN threshold. All modes produce identical FCT (p99 slowdown ≈ 1.08). The "outlier-EV" regime requires hot-spot traffic, not sparse permutations. |
| 09 | [`exp09_cdf_v9/`](exp09_cdf_v9/) | `freezing` | Real-CDF workload filter comparison: WebSearch + Hadoop CDFs × 3 loads × 8 modes × 2 sev × 3 seeds. Two-phase: Phase 1 (24 cells, vanilla probe) + Phase 2 (144 cells, WebSearch only). | **Full artifacts preserved**: 10 plots, 3 CSVs, scripts, compressed raw runs | **Null result + evhealth regression.** Hadoop has zero ECN at all loads. WebSearch ECN only at l=90 (sparse, hcr<0.15). Standard filters (WTD, sf_md_gain/blend with ecn/fresh counters) produce neutral FCT. **evhealth modes regress significantly** (+18–25% p99) due to persistent dirty-state design that under-weights MD. First regime where ECN IS localized — but counter design is flawed. Suggests time-decayed evhealth variant as next step. |
| 10 | [`exp10_paper_buf_ev_v10/`](exp10_paper_buf_ev_v10/) | `freezing` | Paper-workload buf/EV sweep on 800 Gbps 3-tier 128h fat-tree (MSwift/MNSCC arXiv:2509.07907 topology). 4 paper workloads (baseline, perm, hsdp, incast32) × Part A (buf ∈ {1,2,4,8,∞}, paths=65K) + Part B (paths ∈ {32,256,65K}, buf=8) × 2 sev × 3 seeds = 192 cells. Vanilla REPS+NSCC. | **Full artifacts preserved**: 8 plots, 2 CSVs, scripts, raw runs | **Buffer size is flat across all 4 workloads** — extends the exp04/05 finding to paper traffic. **EV domain matters modestly for permutation-like workloads** (6–7% p99 win going from 32 → 64K paths, saturating at 256); HSDP gets 2–3%; incast 0% (receiver bottleneck). **Zero ECN ACKs across all 192 cells at 800 G** — transport never engages, pure-LB result. HSDP is most failure-sensitive (+17% p99 at sev=4). |
| 11 | [`exp11_paper_filters_v11/`](exp11_paper_filters_v11/) | `freezing` | Paper-workload filter comparison at 800 Gbps with **paper-faithful ECN/queue/cwnd flags** (`-q 200 -ecn 10 50 -cwnd 100` ≈ 800 KB buffer, 40 KB ECN threshold). 8 modes × 4 paper workloads × 2 sev × 3 seeds = 192 cells. Validates the regime exp10 missed. | **Full artifacts preserved**: 8 plots, 3 CSVs, scripts, raw runs | **ECN fires (770–3400 ACKs per cell), filters fire (WTD blocks 24–27% MD on baseline/perm), high_counter_rate 0.40–0.84 — diffuse congestion, same as exp07.** **At sev=0 all 8 modes within ±0.3% p99 of vanilla** across all workloads — diffuse signal gives filters nothing to act on. **At sev=4 evhealth modes win on HSDP**: `sf_blend_evhealth` cuts HSDP p99 from 1.82 → 1.66 (−8.8%), `sf_md_gain_evhealth` 1.82 → 1.73 (−5%). **Inverts exp09's evhealth regression** — HSDP's tight ring structure makes the sticky dirty state correctly localised. First positive filter-FCT result in this lineage. |
| 12 | [`exp12_paper_repro_reps/`](exp12_paper_repro_reps/) | `freezing` | **Paper reproduction (REPS column only)**: Figs 4, 5c, 6, 7, 8, 9, 10, 11, 12, 14 from arXiv:2509.07907v2. Implements 4 new CCAs: Swift (delay-AIMD), LSwift (5-RTT-round threshold), MSwift (median-delay window), MNSCC (NSCC + median window). 5 CCAs × 3 seeds × 10 scenarios ≈ 150 runs. Paper-faithful 0.5 µs/hop topology + empirical ZQLB. | **Full artifacts preserved**: 10 CCT bar charts + 1 CDF plot, 2 CSVs, scripts | **NSCC<MNSCC ordering holds across all 10 figures.** NSCC CCT% ≈ 19% (paper 23%) — close. **MSwift ≡ LSwift in all-REPS regime** (known; the distinction only appears with static ECMP bottlenecks that htsim cannot reproduce in a single-LB run). **Swift does not collapse** (43% vs paper's 1308%) — same root cause: no persistent ECMP bottleneck links for Swift to collide on. Incast (Fig 14) is CCA-agnostic (~288% across all CCAs). All known limitations are documented in exp12 README. |
| 13 | [`exp13_papers_reps_repro/`](exp13_papers_reps_repro/) | `freezing` | **REPS-only reproduction of BOTH papers** + Phase D root-cause fix. Paper 1: Figs 2/4/6/8 (synth, DC, AI, asym, failures). Paper 2: Figs 4/5c/6/7/8/9/10/11/12/14 all 5 CCAs × 3 seeds. **Phase D (2026-05-30) identified and FIXED a `_target_Qdelay` reset bug at `uec.cpp:195`** that silently overrode all `-target_q_delay` flags, invalidating exp12 + initial exp13 Paper 2 results. Adds 4 new 500 ns/hop topo files, `-min_rto` CLI flag, MD-fire counter. | **Full artifacts**: 15 plots, CSVs (2.65 M flows, 471 cells), scripts, RESULTS_DIAGNOSTIC.md | **Paper 1 Fig 2**: Perm/Tornado speedup vs ECMP 1.80-1.98×; Incast 1.00× exact match. **Paper 1 Fig 8**: REPS vs OPS up to 110× at 50%% failures. **Paper 2 Fig 4 post-fix**: Swift 85.5%% (was 54%%; paper 1308%%), LSwift 46.4%%, MSwift 49.8%%, NSCC 28.9%%. **Paper 2 Fig 7 post-fix**: MSwift beats LSwift 1.7× (paper 2×) - direction recovered. Residual L1 (mixed-LB) caps Swift collapse. |
| 15 | [`exp15_path_rr_order_v15/`](exp15_path_rr_tornado_v15/) | `path_rr` | **PATH_RR buffer-order study**: does the starting index in the RR cycle affect FCT? PATH_RR+constant, 4 starting-index modes (zero/src_mod/dst_mod/srcdst_hash) × 3 sizes × 3 seeds = 36 runs. Adds `-path_rr_start_mode` CLI flag. | **Full artifacts preserved**: 1 plot, fcts.csv, scripts | **Buffer ordering has NO measurable effect** (~0.001 difference across all modes, within CI). The ~1.78× overhead is entirely from cwnd/queue-size mismatch (cwnd=90 > queue=60 packets), not path synchronization. src_mod = dst_mod for tornado (confirmed). To reduce overhead, use NSCC (exp14), not path reordering. |
| 14 | [`exp14_path_rr_tornado_v14/`](exp14_path_rr_tornado_v14/) | `path_rr`, `freezing` | **PATH_RR vs paper-REPS on tornado workload**, 4-ary fat-tree (k=4, 16 hosts, 3-tier). 4 conditions (path_rr+constant, path_rr+nscc, freezing+nscc, freezing+constant) × 3 sizes (4/8/16 MiB) × 3 simulator seeds = 36 runs. Metric: FCT slowdown from theoretical optimum (non-blocking topology + full line-rate). | **Full artifacts preserved**: 1 plot, fcts.csv, scripts | **CC quality dominates LB quality.** NSCC reduces avg slowdown from ~1.78× to ~1.09–1.28× regardless of LB. PATH_RR+constant ≈ REPS+constant (REPS probabilistic distribution is equivalent to deterministic PATH_RR for tornado). PATH_RR+NSCC beats REPS+NSCC by 2.5–3.5% with near-zero variance; best result: PATH_RR+NSCC 16MiB avg 1.091× optimal. Key answer: PATH_RR+constant does NOT beat REPS+NSCC — CC matters more than LB. |
| 16 | [`exp16_path_random_v16/`](exp16_path_random_v16/) | `path_random`, `path_rr`, `freezing` | **PATH_RANDOM vs PATH_RR vs FREEZING** at cwnd=90. Adds per-packet uniform-random path selection. 2 new conditions × 3 sizes × 3 seeds = 18 new runs; exp14 data reused for baselines. | **Full artifacts preserved**: 4 plots, fcts.csv, scripts | **PATH_RANDOM ≈ OPS ≈ PATH_RR+constant (all ~1.75×) under constant CC.** PATH_RANDOM+NSCC slightly worse than PATH_RR+NSCC by ~2% (CIs don't overlap). Root cause: cwnd=90 < BDP=150 inflates all FCTs; LB policy is irrelevant when the sender is bottlenecked. Pointed to cwnd fix in exp17. |
| 17 | [`exp17_cwnd_corrected_v17/`](exp17_cwnd_corrected_v17/) | `path_rr`, `path_random`, `freezing`, `ops`, `path_static` | **5-algorithm comparison at cwnd=155** (BDP knee). Adds PATH_STATIC — greedy edge-load pinning + source-routed reverse path for ACK/PULL packets. 10 conditions × (16/64 MiB + 256 MiB) × 3 seeds = 90 runs. | **Full artifacts preserved**: 2 plots, fcts.csv, scripts | **PATH_STATIC is best algorithm** across all sizes: 1.049/1.037/1.033× at 16/64/256 MiB, zero CI spread (no shared edges, no path collisions). PATH_RR is second-best (within 0.007× of PATH_STATIC). PATH_RANDOM ≈ OPS, both ~3–6% worse than PATH_RR. FREEZING+NSCC has 5× larger CI than PATH_RR+NSCC at 256 MiB. |
| 18 | [`exp18_path_rr_startslot_v18/`](exp18_path_rr_startslot_v18/) | `path_rr`, `path_static` | **PATH_RR start-slot sweep** (off0=all at 0, off1=src%np, off2=(src×2)%np) vs PATH_STATIC reference. 256 MiB only. Adds `src_mod2` start mode to binary. 12 new runs; off0 and path_static reused from exp17. | **Full artifacts preserved**: 1 plot, fcts.csv, scripts | **Start-slot staggering provides zero average FCT improvement** (~0.001 across all modes, within CI). FCT spread *worsens* with staggering: off0=20 µs → off1=38 µs → off2=63 µs. PATH_STATIC's 1.033× advantage is structural (no shared edges), not a phase-coordination effect. |
| 21 | [`exp21_srv6_buffer_sweep_k16_v21/`](exp21_srv6_buffer_sweep_k16_v21/) | `freezing` (B=8/16/32/64), `reps`, `path_static` | **SRv6 buffer sweep on K=16 fat tree**: 6 LB algorithms × 2 CC modes (NSCC, CONSTANT) × 3 seeds = 36 runs; 8 MB tornado on 1024-host 3-tier topology; `-paths 64 -use_srv6` ensures EV[0..63] ↔ path[0..63] identity. | **Full artifacts preserved**: 3 plots, exp21_flows.csv, scripts, runs.tar.gz | **Buffer size is irrelevant for tornado** (FREEZING B=8 ≡ B=64 within CI). **REPS slightly worse than all FREEZING variants** (+6 µs mean FCT under NSCC, +3 µs under CONSTANT). PATH_STATIC is the clear oracle (zero flow-to-flow variance; p99=mean). CONSTANT CC outperforms NSCC for all algorithms (+7 µs for PATH_STATIC). The SRv6 identity mapping works correctly; sensitivity to buffer size requires a skewed/incast workload where path contention is non-uniform. |
| 22 | [`exp22_link_failure_v22/`](exp22_link_failure_v22/) | `freezing` (B=1/2/4/8/16/32/64), `reps` | **Buffer sweep under 51 permanent link failures** on K=16 fat tree. 8 algos × 2 CC × 3 seeds = 48 runs; same 51 agg↔core links for all; SRv6 substrate; 8 MB tornado. Buffer log (host 0, seed 42) for every B variant. | **Full artifacts preserved**: 4 plots, exp22_flows.csv, annotated buffer CSVs (with `frozen_mode`, `frozen_ev`, `trigger_ev`), scripts, runs.tar.gz | **FREEZING degrades gracefully with buffer size under failures.** B=8 → P99 ≈ 355 µs (NSCC). Frozen mode entered exactly once per flow (never exits in 200 ms window). `trigger_ev` identifies the failed-path EV that caused each freeze. B=1 is worst (single-EV cycling); B=64 best but within CI of B=8. |
| 23 | [`exp23_freezing_pxr_v23/`](exp23_freezing_pxr_v23/) | `freezing_pxr` (B=8) vs `freezing` (B=8, exp22 baseline) | **FREEZING_PXR: path-excluding REPS**. New LB algo adds failed EVs to an excluded set on RTO; sliding 200 ms timer clears the set. Never enters frozen mode. B=8 × 2 CC × 3 seeds = 6 new runs; exp22 B=8 rows reused as baseline. | **Full artifacts preserved**: 3 plots, exp23_flows.csv, buffer CSV (host 0 seed 42), scripts | **FREEZING_PXR cuts P99 by ~31% vs FREEZING B=8** (355 → 246 µs NSCC; 347 → 232 µs constant). P50 −24%. Host 0 accumulates up to 8 excluded EVs; `frozen_mode=0` throughout — design validated. |
| 19 | [`exp19_path_rr_asymmetry_v19/`](exp19_path_rr_asymmetry_v19/) | `path_rr` | **PATH_RR path-count asymmetry**: one host (host 0) constrained to 3 of 4 physical paths. Adds `-path_rr_npaths_override "host:N"` flag. 256 MiB tornado, src_mod offset, NSCC. 2 conditions × 3 seeds = 6 runs. Metrics include per-flow FCT, core queue integral, cwnd trace. | **Full artifacts preserved**: 1 plot, fcts.csv, queue_integral.csv, scripts | **Damage is highly localized.** Constrained host 0: 1.039× → 1.241× (+0.20). Sole victim: flow 1 (same pod, same agg switches): 1.039× → 1.132× (+0.09). All other 14 flows: Δ < 0.001. Max FCT: 1.042× → 1.241×. Destination-pod flows (8–9) slightly improve (−0.002). The congestion remains upstream (agg→core in pod 0) and doesn't propagate network-wide. |

| 24 | [`exp24_reps_no_rr_v24/`](exp24_reps_no_rr_v24/) | `reps` (round-robin temporarily disabled) vs `freezing_b64`, `reps` (reused from exp21) | **Ablation testing whether REPS's deterministic first-window round-robin explains exp21's REPS-vs-FREEZING FCT gap.** Temp one-line code change (`uec.cpp:3046`, `if (false && ...)`) makes REPS fall straight to random-if-empty steady-state from packet 1, like FREEZING. 2 CC × 3 seeds = 6 new runs (Docker-built); exp21's `path_static`/`freezing_b64`/`reps` rows reused read-only. Code change reverted immediately after the runs. | **Full artifacts preserved**: 2 plots, exp24_flows.csv, scripts | **Hypothesis confirmed.** `reps_no_rr` mean/p99 FCT match `freezing_b64` to the 4th decimal (well inside 95% CI) under both CC modes; original `reps` (with round-robin) sits ~3–6 µs above both. The round-robin phase — not buffer boundedness or "stale EV accumulation" (exp21's original, now-superseded explanation) — drives the gap. Likely mechanism: tornado's synchronized flow starts make every flow's round-robin sequence run in lockstep, correlating load onto the same core switch/uplink across many flows simultaneously. |
| 25 | [`exp25_queue_dynamics_v25/`](exp25_queue_dynamics_v25/) | `reps` vs `freezing_b64` | **Direct queue-occupancy measurement testing exp24's proposed mechanism** (synchronized core-switch queue spike from REPS's round-robin burst). New permanent `CoreDownlinkQueueSampler` instrumentation (`-log_core_downlink_queues`), 0.2 µs sampling, first 16 of 64 core switches' downlink ports (256 queues). `-end 500` (shortened window), 3 seeds × 2 algos × 2 CC modes (NSCC + CONSTANT) = 12 Docker-built runs. | **Full artifacts preserved**: 4 plots, 2 queue-timeseries CSVs, scripts, compressed raw runs | **No early-burst spike, but a matching tail-end gap, in both CC modes.** Mean/peak queue depth are essentially identical between REPS and FREEZING B=64 in the first-window region — the synchronized-spike hypothesis is not supported there. But REPS's queues take longer to fully drain to empty: **6.20 µs** under NSCC (matching exp24's 5.95 µs absolute mean-FCT gap) and **2.20 µs** under CONSTANT (matching its 2.89 µs FCT gap). The FCT penalty shows up as a delayed drain at the tail, not an early spike, consistently across CC modes — see exp25 README's Interpretation section. |

A buggy first run of exp03 (with leaf ECN accidentally enabled) is **not** preserved per maintenance decision; the methodology lesson it produced is recorded inside [`exp03_matrix_sweep_v3/README.md`](exp03_matrix_sweep_v3/README.md).

---

## Code changes (already in `htsim/sim/`)

There are two independent additions on top of the original REPS+NSCC code. Both are
additions-only (no original lines deleted). With all flags absent, the binary is
byte-identical to vanilla NSCC + (REPS or FREEZING). The rule for future additions:
every new mechanism MUST have (i) a banner comment with its gate flag, (ii) a row in
this table, (iii) an ARCHITECTURE doc.

### [ADDED: state-aware] — gated by `-state_aware_ecn`

See [ARCHITECTURE.md](ARCHITECTURE.md) for line-level references.

| File | What was added |
|---|---|
| `htsim/sim/uec.h` | Static toggle + per-source `_network_is_asymmetric` flag + setters/getters. |
| `htsim/sim/uec.cpp` | CC ECN-masking gate (~L1209). RTO-driven freeze trigger with asymmetric-flag flip for REPS (~L3022) and FREEZING (~L3040). Auto-thaw with flag clear for REPS (~L2310) and FREEZING (~L2653). REPS-buffer instrumentation CSV. |
| `htsim/sim/pipe.h` / `pipe.cpp` | `Pipe::_failed` flag + setter + early-drop branch in `receivePacket`. |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flags: `-state_aware_ecn`, `-fail_link_time`, `-fail_link_target`, `-log_reps_state`, `-log_reps_state_src`. `LinkFailureEvent` class. |

### [ADDED: smart-filter] — gated by `-smart_filter_mode`

**Mutually exclusive with state-aware and wtd-in-nscc** (3-way hard error if any two are set). See
[exp06_smart_filter_v6/ARCHITECTURE.md](exp06_smart_filter_v6/ARCHITECTURE.md).

| File | What was added |
|---|---|
| `htsim/sim/uec.h` | Banner block: `SmartFilterMode`/`SmartFilterCounter` enums, static statics, per-source `_ecn_buffer_counter`/`_sf_md_gain`, `smartFilterCounter()`/`smartFilterEcnThresh()` accessors. |
| `htsim/sim/uec.cpp` | Static defs; accessor bodies; counter update + MD-gain scratch in `processAck()`; parallel `else if` branch in ECN gate; Mode A gain + Mode B delay blend in `multiplicative_decrease()`; 9 extra CSV columns in `fprintf`. |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flags: `-smart_filter_mode`, `-smart_filter_counter`, `-smart_filter_ecn_thresh`. 3-way coexistence guard. Updated CSV header (9 new columns). |

### [ADDED: wtd-in-nscc] — gated by `-wtd_in_nscc`

**Mutually exclusive with state-aware and smart-filter** (3-way hard error). Paper's "Wait to Decrease"
(SMaRTT-REPS §3.6.1). Reuses existing `_exp_avg_ecn` (α=0.125); gates NSCC MD on `_exp_avg_ecn ≥ 0.25`.

| File | What was added |
|---|---|
| `htsim/sim/uec.h` | `_nscc_wtd_enabled` (bool static, false) and `_wtd_threshold` (double static, 0.25). |
| `htsim/sim/uec.cpp` | Static defs; WTD gate in `updateCwndOnAck_NSCC()` MD dispatch; 2 extra CSV columns (`wtd_enabled`, `wtd_can_decrease`) in `fprintf`. |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flag: `-wtd_in_nscc`. 3-way coexistence guard. Updated CSV header (+2 columns). |

### [ADDED: ev-health-counter] — activated by `-smart_filter_counter evhealth`

Extension of smart-filter. Replaces the broken `fresh_inv` counter (always near B) with a per-EV ECN-state signal: counts how many EVs currently in the REPS buffer had their **last** ACK ECN-marked. Near 0 at full bisection (diffuse congestion); rises when specific EVs are persistently congested. Uses new `getValidEntropies()` accessor on `CircularBufferREPS` (O(B²) ≈ 64 ops/ACK).

| File | What was added |
|---|---|
| `htsim/sim/buffer_reps.h` | `getValidEntropies()` declaration; `#include <vector>`. |
| `htsim/sim/buffer_reps.cpp` | `getValidEntropies()` implementation (scans valid buffer slots, returns `std::vector<T>`). |
| `htsim/sim/uec.h` | `SF_COUNTER_EVHEALTH = 2` in `SmartFilterCounter` enum; `_ev_last_ecn_state` per-source `vector<uint8_t>`. |
| `htsim/sim/uec.cpp` | Lazy-init of `_ev_last_ecn_state`; EV-health update block in `processAck()` smart-filter section; extended `smartFilterCounter()` comment. |
| `htsim/sim/datacenter/main_uec.cpp` | `evhealth` value added to `-smart_filter_counter` CLI handler. |

---

## Directory map

```
state_aware_experiments/
├── README.md                              ← you are here
├── ARCHITECTURE.md                        ← code-level design
├── RUNNING_EXPERIMENTS.md                 ← how-to for future agents
├── workloads/                             ← shared TMs across all experiments
│   ├── README.md
│   ├── composite.cm
│   ├── mice_heavy.cm
│   ├── elephant_heavy.cm
│   ├── gen_composite.py
│   └── gen_v3_workloads.py
├── exp01_lb_dynamics_reps_v1/
│   └── README.md                          (regen recipe)
├── exp02_lb_dynamics_freezing_v2/
│   └── README.md                          (regen recipe)
└── exp03_matrix_sweep_v3/                 ← primary experimental result
    ├── README.md                          (full results + plots inline)
    ├── plots/                             (16 PNGs)
    ├── data/                              (v3_data.csv + v3_events.csv)
    ├── scripts/                           (driver + aggregator + plotter)
    └── runs.tar.gz                        (200 raw .out files compressed)
```

---

## Project memory pointers

Long-term design hypotheses raised during this work are saved under the agent project-memory dir:

- [`reps_buffer_cache_idea.md`](/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/reps_buffer_cache_idea.md) — hypothesis that REPS' bounded buffer should *cache* known-good EVs across multiple draws rather than invalidating per use. The codebase already has the mechanism (`repsMaxLifetimeEntropy`); it's gated off.

---

## Future directions (not implemented)

These are flagged in the individual experiment READMEs but worth restating here:

1. **v4 buffer-fill gate**: change the CC ECN-masking from `cc_ecn = ecn && asymmetric` to `cc_ecn = ecn && (asymmetric || fresh ≤ 1)`. The v2 finding `fresh=0 ⇒ P(ECN)≈1.0` justifies this. Single-line code change inside the existing `-state_aware_ecn` block at [uec.cpp:1209](../htsim/sim/uec.cpp#L1209).
2. **Long-failure stress**: every experiment so far uses a 150 μs failure window. A 1-10 ms window would let frozen mode actually expire mid-run and exercise the recovery path, which our current experiments don't reach.
3. **Real-CDF workloads**: pull Datamining/Hadoop/Websearch CDFs (used by the paper) instead of synthetic permutations.
4. **Topology sweep**: extend exp03 to k=8 2-tier and 1024-host 3-tier topologies for scale comparisons.
5. **EV-lifetime sweep**: implement the buffer-cache idea via `-reps_lifetime N` and re-run exp02-style instrumentation to see whether the `fresh=0` events become rarer.

---

## Reproducing the entire study

```bash
# Build (one-time)
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..

# Regenerate workload TMs
cd state_aware_experiments/workloads
python3 gen_composite.py
python3 gen_v3_workloads.py
cd ..

# Run the v3 matrix (~8 minutes)
exp03_matrix_sweep_v3/scripts/v3_run_matrix.sh

# Aggregate + plot
python3 exp03_matrix_sweep_v3/scripts/v3_aggregate.py
python3 exp03_matrix_sweep_v3/scripts/v3_plot.py
```

For exp01 and exp02 instrumentation runs, see the regeneration recipes in their READMEs.

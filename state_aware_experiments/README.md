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

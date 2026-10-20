# Experiments

Simulation studies and tooling built on top of the REPS EuroSys artifact (`htsim_uec`): the paper's REPS load balancer (`-load_balancing_algo freezing`, an 8-slot bounded buffer of recently-good entropy values) with the NSCC congestion controller, plus our own extensions (state-aware ECN gating, smart filters, PATH_* load balancers, SRv6 source routing, failure/degradation machinery). Each `expNN_*` directory is one study with its own README; `meeting_06_10_26/` holds the items from the 2026-10-06 supervisor meeting.

**Where to start**
1. [`ARCHITECTURE.md`](ARCHITECTURE.md) - the state-aware NSCC+REPS extension and how it is wired into `htsim/sim/`.
2. [`exp03_matrix_sweep_v3/`](exp03_matrix_sweep_v3/README.md) - the first full result (200-cell sweep).
3. [`RUNNING_EXPERIMENTS.md`](RUNNING_EXPERIMENTS.md) - how to add an experiment (layout, flags, what to commit).
4. [`MODIFICATIONS.md`](MODIFICATIONS.md) - every change we made to `htsim/sim/`, with gate flags (source of truth for code changes).

Other design docs: [`PATH_RR_ARCHITECTURE.md`](PATH_RR_ARCHITECTURE.md), [`SWIFT_CC_ARCHITECTURE.md`](SWIFT_CC_ARCHITECTURE.md), [`SRV6_VALIDATION_REPORT.md`](SRV6_VALIDATION_REPORT.md).

**Conventions.** Always use `freezing` (= paper REPS), not `reps`, for paper-comparable work. Any run with `-sender_cc_only` also needs `-disable_tor_ecn` unless the experiment states otherwise (exp26-exp31 do not pass it, matching the paper; exp28 documents this as deliberate). "B" is the REPS buffer size; "F" or "n" is the number of failed or degraded links; "sev" is a failure severity level. Interactive pages from exp28 onward are published in the separate thesis repo ([Thesis_Itamar_BGU_Networking](https://github.com/ItamarMeir/Thesis_Itamar_BGU_Networking), `REPS Buffer/`); `*.html` here is gitignored. Raw runs, traces and data CSVs are also not committed (see `RUNNING_EXPERIMENTS.md` section 9b).

**Superseded results.** Several earlier conclusions were later overturned; follow the pointers below rather than quoting an old row: exp06 is superseded by exp07, exp12 by exp13 (a `_target_Qdelay` bug invalidated its Paper 2 results), and the "stale deque" explanation of REPS's gap in exp21 by exp24/exp25.

---

## 1. State-aware NSCC + REPS (the original extension)

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp01](exp01_lb_dynamics_reps_v1/) | Per-ACK dynamics of the unbounded `reps` deque, 6 scenarios (paths x workload x topology), vanilla vs state-aware, no failures. | `corr(recycle, ECN)` is -0.09 to +0.04: deque size does not predict ECN. This motivated switching to `freezing`. | Findings only; raw data lost |
| [exp02](exp02_lb_dynamics_freezing_v2/) | Same 6 scenarios with `freezing` (8-slot buffer). | `fresh = 0` implies the next ACK is ECN-marked with probability ~1.0 in every scenario: an empty bounded buffer is a near-deterministic congestion signal. | Findings only; raw data lost |
| [exp03](exp03_matrix_sweep_v3/) | State-aware vs vanilla, `-disable_tor_ecn`, 128-host 3-tier. 4 workloads x 5 failure severities x 2 modes x 5 seeds = 200 cells. | State-aware gives almost no FCT change on synthetic workloads (best: incast p99 -14 us at sev 0). Wiring is correct: flag flips equal freeze entries; 0 false positives in 40 healthy runs. | Complete: 16 plots, 2 CSVs, `runs.tar.gz` |

A first run of exp03 with leaf ECN accidentally enabled was not preserved; the lesson is recorded in exp03's README.

## 2. Buffer size and entropy-value (EV) domain

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp04](exp04_buffer_ev_sweep_v4/) | Vanilla `freezing`, 128-host 3-tier. (A) buffer {1,2,4,8,inf} and (B) EV domain {1,2,4,8,16}; 4 workloads, sev {0,4}, 5 seeds = 400 runs. | Buffer size is irrelevant for B=1..8 (inf is worse under failure: 2.08x vs 1.80-1.85x slowdown). EV domain is critical: 1 EV gives 5x slowdown and only 45/128 heavy flows finish under failure. | Complete: 14 plots, 3 CSVs, `runs.tar.gz` (44 MB) |
| [exp05](exp05_paper_wl_buf_ev_v5/) | Same sweeps on paper workloads (perm 128x8 MB, symm16), 2-tier 128 hosts, plus an analytic balls-in-bins part. | Buffer size irrelevant (max FCT 186.4 us at B=1 vs 184.7 us unbounded). EV=32 costs +2.7% / +7.1% vs 64K; 256 is already saturated. CC never engaged (cwnd flat at 153). | Complete, but the failure arm is void (`-fail_link_target 0 0` hits no link on 2-tier) |
| [exp10](exp10_paper_buf_ev_v10/) | Buffer and path sweeps on the 4 paper workloads, 800G 3-tier, `-q 100 -ecn 25 76` (not paper-faithful). 192 cells. | Zero ECN ACKs in all cells, so a pure-LB result: buffer flat; 32 to 64K paths gives 6-7% p99 on perm-like workloads, 2-3% on HSDP, 0% on incast. | Complete: 8 plots |
| [exp21](exp21_srv6_buffer_sweep_k16_v21/) | Buffer sweep with SRv6 on K=16 (1024 hosts), tornado 8 MB, `-paths 64`. 10 algorithms (FREEZING B=1..64, `reps`, `path_static`, `oblivious64`) x NSCC/CONSTANT x 3 seeds = 60 runs. | Buffer size irrelevant for tornado (B=8 equals B=64). `path_static` is the oracle (zero variance). `reps` is ~6 us slower than FREEZING; the cause is the first-window round-robin, not stale history (exp24, exp25). | Complete: 7 plots; 59 of 60 cells in the CSV |
| [exp26](exp26_srv6_buffer_sweep/) | The five paper "network health" figures (2, 4, 6, 7, 8) re-run with original topologies and seeds, `-use_srv6`, restricted-EV OPS (`oblivious`) vs FREEZING B=1..#paths. 342 cells. | REPS wins on tail Max FCT: 1.06-1.40x healthy, 1.34-1.76x under 2% asymmetry, 2-71x under hard failure; incast gains nothing. B is flat except in fig 4 where B<=2 loses to OPS and B=4 recovers the win. | Complete: plots, `summary.csv`, `flows.csv.gz` |
| [exp27](exp27_buffer_sweep_views/) | Re-plots exp26 plus new runs: K=16 3-tier (120), radix, BDP-threshold and flow-size sweeps, and `-failed 32` asymmetric twins. | The healthy REPS-over-OPS gain (~1.4x) is a double resonance in BDP provisioning (peak at B=101) and flow size (~10 BDP), ~1.05x elsewhere. The asymmetric gain (1.2-1.8x) is robust and needs B>=4. | Complete. The BDP-sweep PNG was never produced (CSV data only); plots are in `plots/fig2/`, `plots/fig4/` |

## 3. Congestion-signal filters (smart filter, WTD, EV-health)

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp06](exp06_smart_filter_v6/) | Smart filter between REPS and NSCC (modes `md_gain`, `rtt_blend_ecn_thresh` x counters ecn/fresh), design and code. | None: experiments were never run. | Code only; superseded by exp07 |
| [exp07](exp07_filter_compare_v7/) | Vanilla vs WTD (paper's Wait-to-Decrease) vs smart-filter Modes A/B, 128-host 3-tier. 6 modes x 4 workloads x sev x 3 seeds = 144 cells. | Null: 65% of ECN ACKs arrive with `ecn_counter >= 4/8`, i.e. congestion is diffuse. Best incast p99 gain ~12 us, not significant; `sf_md_gain_fresh` shows a significant but tiny regression (+0.0015 slowdown). | Complete: 10 plots, `runs.tar.gz` |
| [exp08](exp08_lowload_v8/) | Low-load sparse permutations (2, 16, 32 flows), 8 modes incl. EV-health. 240 cells. | `n_ecn_acks = 0` in every run: queues never reach the ECN threshold at <=32 flows, so all modes are identical. | Complete: 8 plots |
| [exp09](exp09_cdf_v9/) | WebSearch and Hadoop CDF workloads at 3 loads, 8 modes. Phase 1 (24 cells) + Phase 2 (144, WebSearch). | Hadoop has no ECN at any load; WebSearch only at 90% load. Standard filters are neutral; EV-health modes regress p99 by 19-26% (persistent dirty state under-weights MD). | Complete: 10 plots |
| [exp11](exp11_paper_filters_v11/) | Filters on paper workloads at 800G with paper-faithful flags (`-q 200 -ecn 10 50 -cwnd 100`). 192 cells. | At sev 0 all modes are within +-0.3% of vanilla. At sev 4 EV-health helps on HSDP (p99 1.82 to 1.66 and 1.73), directionally only (3 seeds, no significance test). | Complete: 8 plots |

## 4. Paper reproductions

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp12](exp12_paper_repro_reps/) | REPS column of arXiv:2509.07907v2 (Gerstein et al.) figs 4-14, with new Swift, LSwift, MSwift, MNSCC. 100 cells. | Superseded by exp13: a `_target_Qdelay` reset bug (`uec.cpp:195`) silently ignored `-target_q_delay`, invalidating its Paper 2 numbers. | Superseded |
| [exp13](exp13_papers_reps_repro/) | REPS-only reproduction of both papers after fixing the target-delay bug, plus a corrected metric (sprayed-only max FCT over theoretical ZQLB). | Paper 1: max-FCT speedup over ECMP 3.6-3.9x on perm/tornado (2-tier), incast 1.00x, REPS beats OPS 18-110x at 10-50% failed cables. Paper 2 fig 4 (CCT %): Swift 1516 (paper 1308), LSwift 113, MSwift 105 (paper 23), NSCC 80 (49). MSwift beats LSwift 1.84x on fig 7 (paper 2x). | Complete: 17 plots, `RESULTS_DIAGNOSTIC.md`; MSwift stays 3-5x above the paper |

## 5. PATH_* load balancers (deterministic and random source routing)

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp14](exp14_path_rr_tornado_v14/) | `path_rr` vs `freezing`, constant vs NSCC, tornado on k=4 (16 hosts), 4/8/16 MiB. 36 runs. | CC dominates LB: NSCC cuts slowdown from ~1.78x to 1.09-1.28x for any LB. PATH_RR+NSCC beats REPS+NSCC by 2.5-3.5%. | Complete |
| [exp15](exp15_path_rr_order_v15/) | Does the PATH_RR start index (zero, src_mod, dst_mod, hash) matter? 6 sizes (4 MiB-1 GiB) x 4 modes x 3 seeds = 72 runs. | No effect (all modes within 0.002). The ~1.75x slowdown plateau comes from cwnd=90 vs the path's BDP, not from synchronization. | Complete |
| [exp16](exp16_path_random_v16/) | Adds `path_random` (per-packet random path); also OPS, queue logs, a cwnd sweep. | Under constant CC, `path_random` = OPS = `path_rr` (~1.77x). Under NSCC `path_random` is ~2% worse than `path_rr`. The cwnd=90 explanation here conflicts with exp17's (it calls cwnd=90 above vs below BDP). | Complete: 4 plots |
| [exp17](exp17_cwnd_corrected_v17/) | Five LBs (`path_rr`, `path_random`, `freezing`, `ops`, `path_static`) at cwnd=155 (BDP knee). 90 runs. | `path_static` is best (1.049/1.037/1.033x at 16/64/256 MiB, zero CI); `path_rr` within 0.007x; `path_random` and OPS 3-6% worse. | Complete: 3 plots |
| [exp18](exp18_path_rr_startslot_v18/) | PATH_RR start-slot staggering vs `path_static`, 256 MiB. 12 new runs. | No average benefit; finish-time spread worsens (20 to 38 to 63 us). `path_static`'s edge is structural. | Complete |
| [exp19](exp19_path_rr_asymmetry_v19/) | One host limited to 3 of 4 paths, k=4, 256 MiB. 20 runs (10 seeds). | Damage is local: host 0 1.039x to 1.240x, its pod neighbour +0.09, all others unchanged. | Complete: 3 plots |
| [exp20](exp20_path_rr_asymmetry_k8_v20/) | Same on k=8 (128 hosts): host 0 limited to 15 of 16 paths. 10 runs. | Much smaller: host 0 +0.027, mean slowdown unchanged. | Complete: 3 plots |

## 6. Failure, degradation and packet trimming

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp22](exp22_link_failure_v22/) | exp21's design with 51 permanent agg-core link failures (5%). 60 runs. | Buffer size barely matters for the mean; `reps` is the best non-oracle (p99 282 us vs 355 us for FREEZING B=8, NSCC). `path_static` finishes only 926 of 1024 flows. | Complete: 6 plots |
| [exp23](exp23_freezing_pxr_v23/) | `freezing_pxr` (exclude the EV that timed out instead of freezing) vs FREEZING under exp22's failures. 42 runs (B=1..64). | PXR cuts p99 by ~31% (355 to 246 us NSCC) and p50 by ~24%; flat across B. | Complete: 10 plots |
| [exp28](exp28_link_degradation_sweep/) | REPS B in {1..32} on a 1024-host 2-tier fabric; Part 1 varies the number of 50%-degraded ToR uplinks (186 runs), Part 2 the degradation level on 4 links (90). MPRDMA, no OPS arm. | B=1 is clearly worst, B=2 slightly worse than B>=4, B>=4 indistinguishable. Max FCT is not resolvable. | Complete; 3-seed CIs on 7 of 17 K and 3 of 9 severity values |
| [exp29](exp29_failure_response/) | Transient (100 us) full kill of F of ToR0's spine uplinks, B in {1,2,4,8,32}; 135 runs. | B does not move FCT at any F. Severity is ~linear in F (affected p99 371 to 880 us). The freeze timeout is the only recovery knob: padding it to 250 us adds +62 us (F=16) and +134 us (F=31) p99. | Complete |
| [exp29_packet_trimming_en](exp29_packet_trimming_en/) | exp29 rerun with packet trimming ON; 8 arms (adds dual-window and NSCC B=8), 216 runs. | No change: freeze entries stay at 1.0 per host at every F, p99 within 1-2%, because a hard kill causes RTOs with or without trimming. | Complete; tarball holds 189 runs |
| [exp29_packet_trimming_en_allhosts](exp29_packet_trimming_en_allhosts/) | Dashboard-only variant of the previous directory: adds an all-hosts FCT group. | Same data; no new simulations. | Variant |
| [exp30_concentrated_path_loss](exp30_concentrated_path_loss/) | Loss concentrated on ToR0: Part A static degradation (n uplinks, ratio), Part B permanent kill of F uplinks; 4 and 16 MiB. | B is almost never resolvable on median FCT. One exception: at F=24 (16 MiB) B=1 is ~15% worse and is the only arm that leaves flows unfinished. | Complete: 894 runs in the tarball |
| [exp30_packet_trimming_en](exp30_packet_trimming_en/) | exp30 rerun with trimming ON (1,008 MPRDMA/dual runs) plus an NSCC buffer ladder (756 runs). | Trimming turns degradation into ECN instead of RTOs, so freeze never engages in Part A; under a hard kill freeze fires from F=1. B is still unresolvable on FCT. | Complete; NSCC ladder data present, no written summary yet |
| [exp31](exp31_ring_collective/) | Ring all-reduce completion time (16 ranks, 496 chained flows), 4-path fabric, B in {1,2,4}, 12 failure scenarios x 3 seeds = 108 runs. | The single-seed b1-to-b2 knee does not survive 3 seeds: B is not resolvable on CCT. Failure raises CCT 5-45x with very wide CIs. | Complete; 2 cells excluded (htsim SIGFPE) |
| [exp32](exp32_ofan/) | Ofan switch-side per-destination round-robin LB (`-strat ofan`) vs switch AR and host REPS: 16-host balance checks, 432-host no-CCA queue sweep (1-64 MB), NSCC/MSwift, one failed link. Single seed. | Ofan edge-uplink queue stays at the proven bound (6 packets, w+1=7) for all m and downlinks are balanced; AR/REPS queues grow with m and overflow at m>=16. Failures not on the local first hop are not handled (v1). | Complete; single seed |

## 7. Mechanism ablations (why REPS differs from FREEZING)

| Dir | Question and setup | Result | Status |
|---|---|---|---|
| [exp24](exp24_reps_no_rr_v24/) | Disable REPS's deterministic first-window round-robin (temporary one-line change, reverted) and rerun exp21's tornado. 6 runs. | `reps_no_rr` matches FREEZING B=64 to four decimals; original REPS is ~3-6 us slower. The round-robin phase drives the gap. | Complete |
| [exp25](exp25_queue_dynamics_v25/) | Sample 256 core-downlink queues every 0.2 us to test exp24's "synchronized spike" mechanism. 12 runs. | No early spike (same mean and peak queue). REPS drains slower at the tail (6.2 us NSCC, 2.2 us constant), matching the FCT gap. Only 16 of 64 cores sampled; the causal path is still open. | Complete |

## 8. Meeting items and tools

| Dir | What it is | Status |
|---|---|---|
| [meeting_06_10_26](meeting_06_10_26/) | Items from the 2026-10-06 supervisor meeting: C1 (valid EVs under backlog; k is small and stable), C1.1 (send-time k vs link rate), C2 (dead-EV clearing in Freezing Mode; slower for larger B), C3 (bursty sender), T1 (FCT vs lost bandwidth; model holds). | All five items run and written up in their own READMEs (single-seed except T1, C3). |
| [meetings](meetings/) | Written plans derived from meetings. | Plan for 2026-10-06 |
| [workloads](workloads/) | Shared traffic matrices and their generators (composite, mice-heavy, elephant-heavy, and the paper workloads). | Reference |
| [tools](tools/) | `reps_event_viewer.py`: interactive viewer for the `-log_reps_events` trace, with CSV schema and tests. | Reference |
| [test_srv6](test_srv6/) | SRv6 routing verification suite (tests T0-T12). | Run once; see its README for two weak spots (T5, T6) |

---

## Code changes

All changes to `htsim/sim/` are gated behind CLI flags and are additions or wraps; with no new flag the binary behaves like vanilla NSCC + REPS/FREEZING. The gate flags and exact locations are listed in [`MODIFICATIONS.md`](MODIFICATIONS.md); the project guide in the repo root `CLAUDE.original.md` has a one-line summary of each mechanism (`state-aware`, `smart-filter`, `wtd-in-nscc`, `ev-health-counter`, `swift-cc`, `path-rr`, `srv6`, `freezing-pxr`, `timed-failure`, and others). Rule for new mechanisms: a `// ===== ADDED (<name>) =====` banner at each modification site, a row in `MODIFICATIONS.md`, and an architecture doc here.

## Directory map

```
experiments/
|-- README.md  ARCHITECTURE.md  RUNNING_EXPERIMENTS.md  MODIFICATIONS.md   (this index and the shared docs)
|-- PATH_RR_ARCHITECTURE.md  SWIFT_CC_ARCHITECTURE.md  SRV6_VALIDATION_REPORT.md
|-- exp01 ... exp32                       one directory per study (see tables above)
|-- meeting_06_10_26/  meetings/          meeting items and plans
|-- workloads/  tools/  test_srv6/        shared inputs, viewer, SRv6 tests
```

A typical finished experiment contains `README.md`, `scripts/` (driver, aggregator, plotter), `data/` (tidy CSVs), `plots/`, and `runs.tar.gz`. By policy only the README and scripts are committed (a few older data files and pages are tracked from before the policy).

## Future directions (not implemented)

1. **Buffer-fill gate (v4):** change the CC ECN gate to `cc_ecn = ecn && (asymmetric || fresh <= 1)`, motivated by exp02's `fresh = 0` finding.
2. **Topology sweep:** extend exp03 to k=8 2-tier and 1024-host 3-tier fabrics.
3. **EV-lifetime sweep:** implement the buffer-cache idea (`-reps_lifetime N`; the `repsMaxLifetimeEntropy` mechanism exists but is gated off) and re-run exp02-style instrumentation.
4. **NSCC target-delay study:** meeting item C1 found NSCC leaves ~80% of ACKs marked under degradation at the default 6 us target, and 55-60% at 4.17 us (0.5 x base RTT). A sweep of `-target_q_delay` against the ECN thresholds would settle how much of that is a tuning effect.

Already covered, no longer open: real-CDF workloads (exp09), long failures and freeze expiry (exp29, exp30).

## Reproducing

```bash
# Build htsim_uec (use the Docker image: see the repo-root README / CLAUDE.original.md)
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..

# Regenerate shared workloads
cd experiments/workloads && python3 gen_composite.py && python3 gen_v3_workloads.py && cd ..

# Run one experiment: driver, then aggregate, then plot (names differ per experiment)
exp03_matrix_sweep_v3/scripts/v3_run_matrix.sh      # ~8 minutes
python3 exp03_matrix_sweep_v3/scripts/v3_aggregate.py
python3 exp03_matrix_sweep_v3/scripts/v3_plot.py
```

Experiments that did not keep raw data (exp01, exp02) describe a regeneration recipe in their READMEs.

# W1: static-failure imbalance and `-strat ofan_weighted`

Branch `ofan-weighted` (sub-branch of `ofan-lb`). Date: 2026-10-21.

## Question
In exp32 P1, plain Ofan on the 54-host k=6 fat-tree with Agg0<->Core0 failed from t~0 and converged (G=0) had CCT 165.8 us versus 98.5 us on the healthy fabric. Is that a defect of Ofan under failures, or just lost capacity?

## Setup facts
- Topology `fat_tree_54_1os_3t_400g.topo` (k=6): 6 pods, 3 ToR + 3 Agg per pod, 9 cores; Agg g of every pod uplinks to cores g, g+3, g+6.
- Workload `derange54_4mb_s42.cm`: 54 flows of 4 MB, every flow inter-pod; pod 0 sends 9 flows and receives 9.
- Failure: the Agg0<->Core0 link of pod 0, both directions. Pod 0's Agg0 keeps 2 core uplinks; every other Agg keeps 3.

## Step 0: the hypothesis gate (existing data, no new code)
`scripts/predict_link_load.py` computes the byte load per directed link under two splits, using the real flow list:

| split | hottest core-layer link | predicted CCT (84 us x ratio + 14.5 us overhead) |
|-------|-------------------------|---------------------------------------------------|
| equal share per live port (what Ofan does) | 1.500x healthy mean (Agg0-pod0 <-> cores 3, 6) | ~140 us |
| equal share per valid path | 1.125x healthy mean | ~109 us |

Measured on the P1 run `ofan_G0_f0.01` (`scripts/link_overload.py`): the hot links are exactly the predicted ones (`A->C` pod-0 Agg0 to cores 3 and 6: 5.79 MB; `C->A` cores 3 and 6 to that Agg: 6.08 MB, versus 4.26 MB healthy mean; 430 trims, max queue 800950 B = full buffer). The measured ratio (1.36-1.43x) is a little below 1.5x because NSCC backs off. The observed CCT, 165.8 us, is above the 140 us estimate because of the queue build-up and trimming. The comparison with healthy (98.5 us) was never a fair bound: after the failure, pod 0 has 8 of 9 core links.

## Paper check
Ofan paper (arXiv 2610.07230) §6.2 defines the failure-run pacing rate rho_max as "the highest rate at which all flows could send if traffic were balanced perfectly across all valid shortest paths". §4.1 / App. F.2 describe Ofan under failures as skipping invalid ports ("keep incrementing until yielding a valid port"; "each remaining valid port still receives exactly one packet per round"), i.e. equal share per live port, and App. I only says routing protocols such as BGP W-ECMP propagate failure information. The text does not describe weighting the schedule. So **`ofan_weighted` is an extension, not the paper's algorithm**; it is meant to test whether weighting closes the gap that the equal-per-port rule leaves in asymmetric fabrics.

## Step 1: discriminating experiment (paced, no CCA)
`scripts/run_w1.sh` (constant CC, `-q 20000 -disable_trim`, `-linkspeed 400000*rho`, failure as above, G=0). Max queue on the core layers, in 4160 B packets, 4 MB flows:

| rho | plain Ofan, fail | ofan_weighted, fail | either, healthy |
|-----|------------------|---------------------|-----------------|
| 0.50-0.65 | 4-5 | 4 | 4-5 |
| 0.70 | 77.8 | 4 | 5 |
| 0.80 | 261.4 | 4 | 4 |
| 0.85 | 336.2 | 5 | 5 |
| 0.90 | 402.1 | 18 | 5 |

Plain Ofan's queue is flat up to rho 0.65 and rises from 0.70, as predicted for an overload threshold of 2/3. Its 4 MB CCT under failure also flattens at about 141 us from rho 0.70 up (140.98, 141.03, 141.04, 141.70), against the 140.5 us predicted for a 1.5x bottleneck: the strongest single confirmation in the data. Weighted Ofan stays flat through 0.85 and starts to queue only at 0.90, just above the predicted rho_max = 8/9 = 0.889. Full numbers (1 MB runs included) are in `data/w1/` (not committed; regenerate with `scripts/run_w1.sh` then `scripts/summarize_w1.py data/w1`).

## Step 2: the implementation (`-strat ofan_weighted`)
- Strategy value `OFAN` plus the static flag `FatTreeSwitch::_ofan_weighted`, so every existing OFAN branch (full-vector use, no `permute_paths`, dispatch, guards) applies unchanged.
- Requires `-routing_convergence_us` (weights come from the known-down set; no cheating) and is incompatible with `-log_ofan_trace`.
- Weight of a ToR up-entry = number of live shortest paths through that Agg (`rc_agg_paths`); an Agg up-entry has weight 1; a bundle of parallel pipes counts as one leg. Weights are computed per (FIB vector, dst ToR, epoch) next to the validity mask.
- Schedule: interleaved weighted round robin over the same permuted port order pi. Weights are divided by their gcd; one schedule has L = sum(weights) slots; sub-round r visits, in pi order, ports with weight > r. Own pointer map, initial data pointer random mod L, ACK pointer offset by floor(L/2); the pointer is reduced mod L if L changes at an epoch.
- If the valid entries have equal weights (healthy fabric, symmetric failures) the plain Ofan code path is used, so output is byte-identical to `-strat ofan`.

## Gates (all passed)
| Gate | Result |
|------|--------|
| G1: `baseline.sh` hashes (5 configs) | identical |
| G2: `-strat ofan` failure run (`G0_f0.01`), pre-change binary vs new binary | byte-identical |
| G3: healthy fabric, `-strat ofan_weighted` vs `-strat ofan` | byte-identical |
| G3b: `ofan_weighted` without `-routing_convergence_us` | exits with an error (rc=1) |
| Path counts vs an independent brute-force reference (`-routing_check`, switch-sequence counting, bundles counted once): random known-down sets, p = 0.1 and 0.4, 6 topologies including the bundle-2 one | 0 mismatches |
| Real failure runs with `ofan_weighted` over G in {0, 5, 30, never}, 3-tier and 2-tier (`rc_check_w.py`) | 32 runs, 0 mismatches, `decisions_to_known_dead=0` |
| Mutation: path count off by 2x in `rc_agg_paths` | detected, 7936 mismatches |
| G4: `-strat ecmp_ar` failure run (filtered-vector path), pre vs new binary | byte-identical |
| G5: `-strat ofan -routing_check -routing_check_random`, pre vs new binary | byte-identical |
| Balance (`-log_ofan_counts`, NSCC run): pod-0 ToR data share via Agg0 / Agg1 / Agg2 | 0.25 / 0.375 / 0.375 = 2:3:3, as designed |

## Step 3: NSCC run (the original P1 configuration)
| LB | CCT (us) | core-layer max link overload vs layer mean | max queue (B) | trims |
|----|----------|---------------------------------------------|---------------|-------|
| healthy Ofan | 98.5 | 0.15% | 20750 | 0 |
| Ofan, failed link | 165.8 | 35.5% (A->C), 42.8% (C->A) | 800950 | 654 |
| ofan_weighted, failed link | 116.5 | 12.6% | 427450 | 0 |

The residual 12.6% is the intended 9/8 = 12.5% of the healthy per-link load. It is the minimum any split can reach, because pod 0 has 8 core links for 9 hosts' traffic; the load moves to the pod-0 ToR uplinks (3/8 share each), which is also why the weighted NSCC run still shows a 427 KB E->A queue. The predicted lower bound for this workload on the failed topology is ~109 us.

## Verdict
The 165.8 us was mostly the equal-share-per-port rule on an asymmetric fabric, not lost capacity and not a bug in the failure model. Weighting by valid-path count removes it (116.5 us, within ~7% of the estimated 109 us bound). This does **not** change any reproduced paper figure (1, 4, 5, 7, 8, 12 are healthy-fabric runs); it concerns the paper's failure setup (Fig 9), which we have not reproduced. If the paper's Fig 9 numbers use plain Ofan at rho_max as defined above, our result suggests plain Ofan cannot hold rho_max in asymmetric cases, so it is worth checking whether the paper's switches weight their schedules (the authors' predecessor fork uses weighted IWRR schedules).

## Caveats
- One topology, one failed link, one workload, one seed, G=0 only; the paced test has no CCA.
- The 84 us / 14.5 us calibration is approximate, so the ~109 us bound is an estimate.
- Bundled links with partial failure are counted as one leg (documented limitation).
- A multi-hop weight (the Agg-level choice) is not weighted by downstream capacity; only ToR entries can differ in this topology family.

## Revert
Everything is one commit on branch `ofan-weighted`. To remove it: `git revert <commit>` or delete the branch. By hand: delete every block between `// ===== ADDED (ofan-weighted) =====` and `// ===== END ADDED (ofan-weighted) =====` in `fat_tree_switch.{h,cpp}`, `main_uec.cpp` and `ofan_order.h`. The pre-change binary is `/tmp/frozen/htsim_uec_pre_weighted` in container `ofan-dev` (lost if the container is recreated; the real revert path is git). A stale incremental build after the header change caused an abort; after `make clean` in `htsim/sim` and `htsim/sim/datacenter` the gates pass.

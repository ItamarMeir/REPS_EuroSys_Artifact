# E6: Ofan paper Fig 9 (random link failures) - did the paper use weighted or plain Ofan?

Date: 2026-10-21. Branch `ofan-weighted`. Plot: `plots/e6_fig9/fig9.png`. Raw data: `data/e6/` (not committed; `e6_runs.csv`, `e6_summary.md` regenerate with `scripts/run_fig9.sh` and `scripts/aggregate_e6.py`).

## Question
Paper §6.2: every edge-aggregation and aggregation-core link is dropped with probability p; every host paces at rho_max ("highest rate at which all flows could send if traffic were balanced perfectly across all valid shortest paths"); the figure shows the CCT increase over the fully-connected baseline. Ofan beats REPS and AR. Does the paper's Ofan skip invalid ports with equal shares (our `-strat ofan`) or does it weight by valid paths (our `-strat ofan_weighted`, an extension)?

## Setup (what we know and what we guessed)
- 432 hosts (k=12, 800 Gbps, 3-tier), inter-pod permutation, 1 MB flows, no CCA (constant cwnd 400), `-q 20000 -disable_trim` (E3 setup). The paper's Fig 9 topology and message size are not stated; 432 hosts is our assumption.
- Failure instance = (p, seed), p in {0, 0.5, 1, 1.5, 2}%, 10 seeds each; each cable (both directions) fails independently; instances with a flow without any valid shortest path are redrawn (none were needed). Failures present from t=0 and known to all switches (`-routing_convergence_us 0`) for ALL strategies, including REPS and AR (filtered ECMP sets).
- rho_max = min(1, 1 / max link load) for the fluid split with equal share per valid shortest path (our reading of "balanced perfectly"; `scripts/fig9_instance.py`). The model was validated against the simulator on one instance: with weighted Ofan at rho_max the measured per-link loads match the prediction (mean abs error 0.004, max 0.018); plain Ofan deviates by up to 0.2.
- New sim flag `-fail_pipes_file` (static failure sets; `experiments/MODIFICATIONS.md`, row `fail-pipes-file`).
- CCT increase = max flow finish / LB1 - 1, LB1 = healthy single flow at line rate (16.86 us). "Ideal" = healthy single flow paced at the instance's rho_max, i.e. the capacity lost to the failures alone.
- Paper values below are read by eye from the figure (+-1 point).

## Results (CCT increase %, mean +- SEM over 10 instances)
| p (%) | REPS | AR (q=193) | JSQ | Ofan plain | Ofan weighted | ideal |
|---|---|---|---|---|---|---|
| 0 | 15.4 +- 0.2 | 14.0 +- 0.3 | 17.4 +- 0.4 | 2.9 | (same as plain) | 0 |
| 0.5 | 24.7 +- 1.1 | 24.5 +- 1.7 | 23.9 +- 1.9 | 17.6 +- 2.0 | 14.5 +- 0.9 | 12.7 +- 0.9 |
| 1 | 28.1 +- 2.5 | 28.6 +- 2.1 | 29.5 +- 2.8 | 21.5 +- 2.6 | 19.2 +- 2.3 | 17.3 +- 2.3 |
| 1.5 | 34.7 +- 2.3 | 33.8 +- 2.2 | 33.1 +- 2.5 | 29.3 +- 2.7 | 27.5 +- 2.9 | 25.8 +- 2.9 |
| 2 | 36.2 +- 2.3 | 38.5 +- 2.5 | 36.8 +- 2.5 | 33.1 +- 3.2 | 29.9 +- 2.5 | 28.2 +- 2.6 |
| paper REPS / AR / Ofan | 13 / 12.5 / 3.5 at p=0; 21 / 21 / 15 at 0.5; 24.5 / 24.5 / 19.5 at 1; 28 / 27.5 / 23 at 1.5; 30.5 / 31 / 28 at 2 | | | | | |

Excess over each instance's own ideal: plain Ofan 2.9-4.4%, weighted Ofan 1.3-1.6%, REPS 6.4-10.7%, AR 6.5-10.5%. Max queue (packets): plain 15-20, weighted 7-8, REPS/AR 35-52. No drops, all flows finished in all 240 runs.

### The discriminating quantity: Ofan's lead over REPS (paired per instance, points of CCT increase)
| p (%) | paper (REPS - Ofan) | ours: REPS - plain Ofan | ours: REPS - weighted Ofan |
|---|---|---|---|
| 0.5 | ~6 | 7.1 +- 1.1 | 10.2 +- 1.3 |
| 1 | ~5 | 6.6 +- 0.4 | 8.9 +- 0.9 |
| 1.5 | ~5 | 5.3 +- 0.7 | 7.1 +- 1.1 |
| 2 | ~2.5 | 3.1 +- 1.1 | 6.4 +- 1.0 |

## Verdict
**The shape of the paper's Fig 9 is consistent with the unweighted (plain) Ofan and less consistent with the weighted one.** The paper's gap between Ofan and REPS/AR shrinks from ~6 to ~2.5 points as p grows. Plain Ofan reproduces that trend within error (7.1, 6.6, 5.3, 3.1 against ~6, 5, 5, 2.5). Weighted Ofan leads by 10, 9, 7, 6, about 3-4 standard errors above the paper at 0.5% and 2%. The ordering claim (Ofan below REPS and AR at all p) holds for both. This is the answer to the question as far as these data go, but it is suggestive, not proof:
- The absolute levels do not settle it. Our Ofan at 0.5-1% is closest to the paper with the weighted variant (14.5 / 19.2 vs 15 / 19.5), but our REPS and AR curves run 3-6 points above the paper's at every p > 0, and above 1% all our curves are higher than the paper's. Topology size, message size, seeds, and the exact rho_max definition (we use equal share per valid path; an LP-optimal split would raise rho_max and lower every curve) are unknown and move absolute levels by several points.
- The paper's values are read by eye; the failure instances are random draws with SEMs of 1-3 points per curve.
- The paper may implement weighting differently (for example only at one tier), which we did not test.

What is established independently of the paper: plain Ofan under asymmetric failures leaves a 3-4% excess over the capacity-limited ideal and 15-20-packet queues; the path-weighted variant cuts that to ~1.5% and 7-8 packets (W1, `experiments/exp32_ofan/W1_weighted_ofan.md`, and here). The plain variant still beats REPS and AR by a clear margin in every case, so the paper's qualitative Fig 9 claim does not require weighting.

## Possible follow-ups (not done)
Other topology sizes (the paper's Fig 9 size is unknown), an LP-optimal rho_max, a variant that weights only the ToR tier versus both tiers, and a larger seed count at 0.5% and 2%.

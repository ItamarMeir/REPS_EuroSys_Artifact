# Weighted random EV draw for REPS ("god mode", `-reps_draw_weights`)

Purpose (meeting 2026-10-26, knee study, N sweep follow-up): test causally whether the cost of REPS random draws explains the small-B excess, the knee and the dip of max FCT against the buffer size B. REPS draws a random EV whenever its buffer has nothing valid to recycle. Under SRv6 every EV is a path, so on a fabric with 5% / 95% uplinks a uniform draw lands on a 5% link half of the time. "God mode" gives the sender knowledge of the link speeds and draws EVs with probability proportional to the capacity of their path. Nothing else in REPS changes.

## What it changes, and what it does not
- The uniform draw `rand() % _no_of_paths` becomes one weighted draw, still exactly one `rand()` call. It is applied at up to three sites of `UecSrc::nextEntropy_freezing` (`htsim/sim/uec.cpp`):
  - the normal empty-buffer / no-fresh-EV fallback (label `random`);
  - the frozen-mode-empty branch (label `random`);
  - the `explore_counter` branch (label `explore`).
  Which sites use the weights is set by `-reps_draw_scope fallback|explore|both` (default `fallback` = the first two). In the sweeps the explore branch never fires (`explore_counter` stays 0, no freeze entries), so `fallback` and `both` are identical there.
- Unchanged: buffer recycling, deposits, buffer size, trimming, freezing logic, congestion control, ECN, the trace labels (a weighted draw is still `random` / `explore`, so all analysis scripts work unchanged).
- Only `-load_balancing_algo freezing` is wired. The `freezing_pxr` and dual-window predictors are not.

## Flags (`htsim/sim/datacenter/main_uec.cpp`)
| Flag | Meaning |
|---|---|
| `-reps_draw_weights capacity` | weight of EV e = bottleneck speed (Mbit/s) of the route `_paths[e % _paths.size()]`: the minimum `BaseQueue::_bitrate` over the queues of the route. Needs `-use_srv6`. |
| `-reps_draw_weights w0,w1,..,w(P-1)` | explicit integer weights, one per EV; length must equal `-paths`, sum > 0. |
| `-reps_draw_hosts all\|a,b-c` | source hosts (`_srcaddr`) that use the weights; default all. Hosts not listed keep the uniform draw. |
| `-reps_draw_scope fallback\|explore\|both` | which draw sites are weighted (above). |
| `-reps_draw_invert` | maps each weight w to max + min - w. Negative control (a capacity-weighted draw becomes 95% on the 5% links). |

The auxiliary flags without `-reps_draw_weights`, any other load-balancing algorithm, `capacity` without `-use_srv6`, a wrong list length or zero sum, a non-numeric list and a bad scope all exit 1 at startup, before any flow runs.

## Mechanism
- `UecSrc::initDrawWeights()` runs lazily at the first draw of a source: builds the weight vector, exits early (source stays uniform) when the host is not selected, when there are no routes, or when all weights are equal (for example a healthy ToR), so those sources reproduce the baseline byte for byte. Otherwise it stores integer prefix sums `_draw_cum` and prints one line `reps_draw_weights: src <host> weights ...`. It uses no RNG and does not touch the REPS buffer.
- `UecSrc::drawRandomEv()`: `x = rand() % _draw_cum.back()`, returns the index found by `upper_bound`. Inactive sources return `rand() % _no_of_paths`.
- `drawBiasApplies(bool explore)` guards each of the three call sites with the scope.
- Weights are fixed at the first draw of a flow. Link swaps (`update_bit_rate`) and failures are not tracked.
- Every modified site carries `// ===== ADDED (reps-draw-weights) =====`; no original line is deleted (each site is a guarded `return` placed before the original `return rand() % _no_of_paths;`). Details and the verification record: `MODIFICATIONS.md`, section `[ADDED: reps-draw-weights]`.

## Capacity weights in the knee setup
ToR0 uplinks are 20 / 380 Gbit/s alternating (even EV = 5% link), so under SRv6 with `-paths 8` the weights are 20, 380, 20, 380, ..., a draw lands on a 5% link with probability 4 x 20 / (4 x 20 + 4 x 380) = 5% instead of 50%. Hosts behind healthy ToRs see equal weights and keep the uniform draw.

## Verification (summary; full record in `MODIFICATIONS.md`)
- Baseline binary `htsim_uec.pre-reps-draw-weights` copied before the first edit.
- Identity: flag absent, uniform list, `capacity` on a healthy fabric, host filter excluding the flow, scope `explore` with no explore draws all give byte-identical output to the baseline; rerun is deterministic.
- Distribution, one flow host 0 -> 64, B = 2, 3 seeds, expected value written before the run: uniform 52.7% of draws on the 5% class (expected 50%), capacity 5.3% (5%) with per-EV chi-square 3.49 (7 dof), inverted 95.4% (95%), list `1,0,1,0..` exactly 100%, list `0,1,0,1..` exactly 0%. Scope and branch coverage (explore, frozen-empty) in `knee/scripts/draw_freeze_smoke.py`.
- Negative control: the same checks against the wrong expectation fail (z about +40).
- Smokes: `meeting_26_10_26/knee/scripts/draw_smoke.py`, `draw_freeze_smoke.py` (logs in `knee/data/`).

## Using it
Always add it to a normal REPS command; derive the rest of the flags from the experiment driver, not by retyping:
```
... -load_balancing_algo freezing -use_srv6 -paths 8 -reps_draw_weights capacity [-reps_draw_hosts 0-7] [-reps_draw_scope both]
```
Check from the output, not the command line: one `reps_draw_weights: src <h> weights ...` line per affected source, and in the trace the share of `random` sends with even `ev % 8` (about 5% with capacity weights).

## Results and the lesson (knee study, N sweep, 728 cells)
Details in `meeting_26_10_26/knee/README.md` ("God-mode ladder, result"). With capacity weights the small-B excess and the knee shrink strongly and the REPS dip at B = 256/320 disappears, and the best FCT at N = 400 / 789 is 1.15 / 1.29 times the speed of light (REPS: 1.26 / 1.43). It is not a better REPS everywhere: at N = 111 and large B the 95% links are ECN-marked on 40-48% of ACKs (REPS: about 0), the buffer starves and 40-50% of the sends become random draws, so god is 17 us slower there. The cause of the first marks is not established (hypothesis: no slack on the good links, 1600 Gbit/s offered vs 1520 + 80 Gbit/s).

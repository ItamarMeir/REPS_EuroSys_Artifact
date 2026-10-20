# exp32 - Ofan switch-side load balancer

Validation of the Ofan implementation (`-strat ofan`, [`../OFAN_ARCHITECTURE.md`](../OFAN_ARCHITECTURE.md)) against the claims of arXiv 2610.07230: bounded queues independent of message size, near-perfect link balance on every fat-tree layer, and better completion time than switch AR and host REPS. Single seed (42) throughout; see Limitations.

## Method note

- Build and run inside Docker container `ofan-dev` (see `CLAUDE.original.md`, "Docker environment"). `scripts/build.sh`, `scripts/baseline.sh`.
- Always `-load_balancing_algo ecmp` for ofan and AR (constant entropy); REPS uses `-load_balancing_algo freezing -paths 65535` with default switch ECMP.
- `-sender_cc_only` runs all pass `-disable_tor_ecn` (project rule). `reps_dl` in S5 is a sensitivity run that omits it.
- Buffers: `-q 193` (800,950 B per port), `-ecn 19 19` (about 80 KB). **Deviation from the paper:** its footnote 6 uses 800 KB buffers only in the CCA experiments and "practically infinite" buffers in the no-CCA ones, so the S5 drops/RTOs of AR and REPS at m >= 16 are an artifact of this setup and not paper-comparable (the Ofan bound and the queue-vs-m trend are unaffected). S5 uses `-disable_trim` so trim counts are 0 by construction.
- No-CCA emulation (S5): `-sender_cc_algo constant -cwnd 400` (packets; 1.66 MB vs BDP about 0.75 MB). The 64 MB single-flow CCT is 1375 us vs 1360 us ideal, so sources are not window-limited.
- CCT = last flow finish; "CCT increase" is relative to a single-flow lower bound with the same config (paper App. A, empirical variant).

## Topologies and workloads

- S3/S4: `fat_tree_16_1os_3t_400g` (k=4, 4 pods of 4 hosts), 1 MiB flows.
- S5: `topologies/fat_tree_432_1os_3t_400g.topo` (k=12, 36 hosts/pod, 36 cores), m in {1,4,16,64} MB.
- S6/S7: `fat_tree_54_1os_3t_400g` (k=6), 4 MiB flows.
- Workloads from `scripts/gen_derangement.py` (every flow inter-pod; swap-repair fallback for large sizes; `perm` mode = plain random permutation). Generated `.cm` files are in `workloads/` (S5 ones are inside `data/s5/runs.tar.gz`).

## Steps and results

| Step | What | Result |
|---|---|---|
| S0 | Regression baseline (default, `ecmp_host`, `ecmp_ar`, `ecmp_rr`; 16 hosts, determinism checked by running twice) | `baseline/SHA256SUMS`; after the change all four hashes are identical |
| S1 | `ofan_order.h` unit test `tests/test_ofan_order.cpp` | pi bijective for w=1..128, ids < 4096, 4 seeds; one visit per port per w packets; ACK offset; validity-mask round robin. With shuffled P, w=6 gives 30 distinct cyclic orders (as in the paper) |
| S3 | `-log_ofan_counts` on a 16-host permutation, `scripts/check_balance.py` | 58 (switch, key, type) pointers, all balanced within 1 packet across physical ports; 1705 ACKs traverse the type-1 pointer; all 16 flows finish |
| S4 | Inter-pod derangement, 16 hosts, per-layer worst-link overload | see below |
| S5 | No-CCA sweep on 432 hosts (`scripts/run_s5.sh`, summary in `data/s5/summary.md`) | see below |
| S6 | NSCC / MSwift on 54 hosts, paper buffers and a small-buffer stress | see below |
| S7 | One failed Agg->Core link | see below |

### S4 - worst-link overload (%), 16 hosts, 1 MiB, inter-pod derangement

| layer | ofan | ecmp_ar | ecmp_host |
|---|---|---|---|
| E->A | 0.25 | 1.03 | 114 |
| A->C | 0.49 | 0.64 | 180 |
| C->A | 0.39 | 8.96 | 104 |
| A->E | 0.25 | 1.03 | 100 |

AR balances the uplinks but not the downlink it cannot influence (C->A 9%, 103 KB peak queue); Ofan balances all four. With 16 links per layer and one seed, the sub-1% residuals are packet granularity.

### S5 - 432 hosts, no CCA, inter-pod derangement

Max data-queue occupancy per layer in 4150 B packets (E->A / A->C / C->A / A->E / E->H) and CCT increase over the single-flow bound:

| m (MB) | ofan | ar | reps |
|---|---|---|---|
| 1 | 6/7/8/7/7, +2.9% | 15/14/39/34/13, +12.0% | 48/38/38/29/16, +14.2% |
| 4 | 6/8/9/8/8, +1.3% | 18/15/100/70/19, +10.4% | 82/80/75/55/20, +9.8% |
| 16 | 6/8/9/8/9, +0.6% | 18/16/193/151/32, +22.6% (136 drops) | 193/177/145/99/33, +18.6% (134 drops) |
| 64 | 6/8/9/8/9, +0.5% | 18/17/193/193/46, +7.4% (26207 drops) | 193/193/193/193/57, +8.2% (9148 drops) |

- **Exact edge-uplink bound (App. F): PASS in all 8 cells** (derangement and permutation x 4 sizes): max E->A queue is 24,900 B = 6.00 packets, below the w+1 = 7 bound.
- Ofan queues are flat in m; AR and REPS grow with m until the 193-packet buffer overflows.
- Ofan's other layers sit at 7-9 packets, flat from 4 to 64 MB; only E->A has the proven bound.
- **Zero-drop gate fails for AR and REPS at m >= 16** (buffers were deliberately not enlarged; see the footnote-6 deviation above). Their 16/64 MB CCTs include RTO recovery after drops, so the 16/64 MB CCT gaps mix queueing and loss. Only m <= 4 is drop-free for all three. `reps_dl` (ToR-downlink ECN on) has 0 drops at 16 MB (+6.4%).
- REPS `freeze_entries` is about 0 despite thousands of RTOs: with `-disable_trim` the freeze trigger is not reached, so the paper's Fig 7a conjecture (REPS degrading at large m through freezing) was not tested.
- Worst-link overload for Ofan on the derangement is at most 2%; on a plain permutation 1.7-9.8% (intra-pod flows load some links more, so the ideal is not uniform).

### S6 - congestion control (54 hosts, 4 MiB, derangement)

| config | CCT us (paper buffers, NSCC) | CCT us (`-q 40 -ecn 5 10`, NSCC / MSwift) | trims (small buf, NSCC) |
|---|---|---|---|
| ofan | 98.5 | 98.5 / 98.5 | 0 |
| ecmp_ar | 103.7 | 111.1 / 120.1 | 115 |
| REPS | 105.0 | 114.3 / 125.1 | 293 |

- This S6 is at 54 hosts only, not the paper's 432-host Fig 12 setup, so the "CCA-independent" conclusion rests mainly on the small-buffer stress run; a 432-host NSCC/MSwift run is still open.
- MSwift and NSCC are bit-identical at paper buffers (the windows never shrink) for every strategy; the CCA only matters in the stress run, where Ofan is unaffected.
- `-ofan_ack_mode hash`: no spurious retransmits or RTOs, +0.9 us CCT, 1552 ECN-marked ACKs at small buffers (spray: none).
- `-ofan_identity_order`: identical to the default order (paper fn. 4 reports about 0.2%); at this scale and load the order has no effect.
- No `uecMaxInFlightPkts` abort in any run. Retransmit and receiver out-of-order counts are not exposed by the simulator, so trims, RTS and RTOs were used as proxies.

### S7 - one failed Agg0<->Core0 link (54 hosts, failed from 10 ns for the whole run)

| config | finished | CCT us | RTOs |
|---|---|---|---|
| ofan healthy | 54/54 | 98.5 | 0 |
| ofan, link failed | 54/54 | 324.4 | 1276 |
| ecmp_ar | 50/54 | 358.7 (of finished) | 1894 |
| REPS | 54/54 | 167.1 | 1690 |
| ecmp_host | 52/54 | 328.0 (of finished) | 0 |

The local-skip works as designed: zero packets go to the failed port of the owning Agg switch and the two live ports balance within 1. But Ofan v1 cannot see the dead Core0->Agg0 downlink, so other pods' Agg switches keep sending to Core0 for pod-0 destinations (1161 packets lost, 1276 RTOs, 3.3x CCT). REPS recovers fastest here. Lost-packet counts are inferred from queue statistics.

**S7 used the legacy failure model** (instant skip of a locally failed first hop, no other knowledge; no `-routing_convergence_us`). It is kept as the "local skip only" reference. For failure experiments use the convergence model and the P1 results below.

### P1 results - routing-convergence model (`-routing_convergence_us G`)

Model: [`../OFAN_ARCHITECTURE.md`](../OFAN_ARCHITECTURE.md) section "Failure convergence model". Setup: 54-host k=6 3-tier 400G, derangement 4 MiB x54 (seed 42), nscc, `-q 193 -ecn 19 19`, Agg0<->Core0 failed in both directions and never recovered; single-flow minRTT (4096 B inter-pod) 12.506 us. Full tables: `data/p1/summary.md` (drivers `scripts/run_p1.sh`, `scripts/summarize_p1.py`). Healthy CCT (us): ofan 98.5, ecmp_ar 103.7, reps 105.0, ecmp_rr 137.5, ecmp_host 340.8.

- **G3 (no cheating / timing): pass.** `decisions_to_known_dead = 0` in every run (all strategies, G in {0, 20, 50, never}). Packets are dropped by the dead pipe before `t_known` and almost never after: G=50 us, failure at 20 us, drops before/after t_known = ofan 1466/22, ecmp_ar 1223/11, ecmp_host 452/0, ecmp_rr 1676/77, reps 1504/37. The post-known drops are packets already queued or in flight at `t_known`, 3-20% of the 386-packet queue-drain bound. G=0 static: 0/0 (nothing is ever sent into the dead link).
- **G4 (balance over valid ports): pass.** Static failure (G=0, failure at 0.01 us): 244 (switch, key) pointers with an up decision, valid-set mismatches 0, 0 packets to the dead port, max spread over the valid ports 1, no key with spread > 1.
- **G5 (CCT in us over G; failure at 20 us except the first column)**:

| strategy | 0 (static, f=0.01) | 0 (mid-run, f=20) | 1xRTT | 2xRTT | 5xRTT | 10xRTT | never |
|---|---|---|---|---|---|---|---|
| ofan | 165.8 | 126.5 | 125.6 | 131.9 | 169.4 | 231.9 | 399.9 |
| ecmp_ar | 144.1 | 126.4 | 124.8 | 185.5 | 184.2 | 256.2 | 381.0 (51/54 finished) |
| ecmp_host | 331.4 | 344.9 | 332.1 | 339.6 | 340.4 | 361.8 | 340.3 (52/54 finished) |
| reps | 142.1 | 124.3 | 122.9 | 131.7 | 169.2 | 181.0 | 181.0 |

  Ofan tracks REPS up to 5xRTT and is clearly worse for 10xRTT and never (399.9 vs 181.0 us): REPS also reacts on the host (RTO + freezing), while Ofan under this model only has the switch view.

Honest findings and caveats (single seed, no confidence intervals):

1. **Static G=0 Ofan is not healthy.** With the failed link known from t=0, Ofan takes 165.8 us versus 98.5 us healthy, with 654 trims, and the live links of the affected layers are overloaded by 33% (A->C) and 40% (C->A) over the layer mean (`data/p1/summary.md`, G4 block). ecmp_ar (37%/37%) and reps (27%/34%) show the same kind of overload. Hypothesis (not verified): with Agg0<->Core0 down, Agg0 keeps only 2 of its 3 uplinks, but each ToR still hands it 1/3 of its inter-pod traffic (valid-port pruning at the ToR is unweighted: it only removes ports that cannot reach the destination), so Agg0's 2 live uplinks carry 1.5x the per-uplink load of the other aggs. The predecessor paper (arXiv 2507.21372) handles this with W-ECMP weights (each port weighted by the number of valid distinct paths through it, with an interleaved weighted round robin), which our unweighted skip does not implement. This is the next possible extension; it is deliberately not implemented.
2. **Static G=0 (failure at 0.01 us) is slower than mid-run G=1xRTT (failure at 20 us)** for ofan (165.8 vs 125.6 us). This is the different failure time (the failure is present for the whole run, versus appearing after the first window is in flight and being known 12.5 us later), not a bug. The like-for-like cheating reference is the "0 (mid-run, f=20)" column (126.5 us).
3. **ecmp_ar is non-monotonic in G** (124.8 us at 1xRTT, 185.5 at 2xRTT, 184.2 at 5xRTT; RTOs 333 -> 1193 -> 1964). This looks RTO-driven; the cause was not investigated.
4. S7's 324.4 us / 1276 RTOs for Ofan came from the legacy local-skip model; do not compare it with the table above (same failure, different knowledge model).

## Mutation test of the port-order fix

Removing the two `if (_strategy != OFAN)` guards (so `permute_paths` shuffles the up-route vectors again) makes the S3 per-port balance check FAIL (8 of 58 keys imbalanced, e.g. `[32, 249]` packets over two ports) and, on 432 hosts, 1 MB derangement, raises worst-link overload from A->C 1.7% / C->A 1.95% to 18% / 24%, with 1946 + 295 trims. So the fix is load-bearing and the per-physical-port counter catches its absence. The guards were restored and the regression hashes re-verified; `baseline.sh` now also checks that `-strat ofan` is deterministic (two identical runs).

## Limitations

- Single seed; S4 has only 16 links per layer. No confidence intervals.
- Without `-routing_convergence_us`, Ofan failure handling is the legacy local-first-hop skip only (S7). The reachability + convergence-time model exists behind that flag (P1); it prunes ports unweighted (no W-ECMP weights, see P1 finding 1).
- POfan/4Ofan (pipe-local pointers) are not implemented: `getNextHop` receives `ingress_port == NULL`, so identifying the ingress pipe needs extra plumbing.
- The paper's own 800 Gbps / 4096 B settings were approximated with the repo's 400G topologies.

## Reproduce

```bash
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/build.sh            # incremental build
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/baseline.sh /workspace/experiments/exp32_ofan/after   # regression
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_s3.sh && python experiments/exp32_ofan/scripts/check_balance.py experiments/exp32_ofan/data/s3_counts.tsv
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_overload.sh ofan <tm.cm> <topo> # S4
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_s5.sh           # S5 (64 MB cells take 8-12 min each)
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_s6.sh           # S6
docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_s7.sh           # S7
```

## Files

`scripts/` drivers and analysis; `tests/test_ofan_order.cpp`; `topologies/`; `workloads/`; `baseline/` regression hashes; `data/` small summaries (`s5/runs.tar.gz` holds the raw S5 runs).

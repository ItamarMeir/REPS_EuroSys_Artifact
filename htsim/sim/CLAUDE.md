# htsim/sim — simulator-code guide

Loaded only when working on files under `htsim/sim/`. Repo-wide rules (Docker-only builds, `-disable_tor_ecn`, validation checklist) are in the root `CLAUDE.md`.

## Rule for every new mechanism

Every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====` banner at every modification site, (ii) a row in `experiments/MODIFICATIONS.md` and in the inventory below, (iii) an ARCHITECTURE doc under `experiments/`.

What has NOT been changed:
- No original lines deleted from `htsim/sim/`. Every modification is an addition or a wrap.
- With all new flags absent, the binary produces byte-identical behavior to vanilla NSCC + REPS/FREEZING.

## The state-aware NSCC + REPS extension

### What it does

Every incoming ACK carries an ECN bit. The architecture splits how that bit is consumed:

- **Load Balancer (REPS or FREEZING)** — always sees the real ECN bit. ECN-marked ACKs rotate out the EV naturally.
- **Congestion Controller (NSCC)** — sees a *gated* ECN bit. The CC honors ECN only when the sender's internal flag `_network_is_asymmetric` is set. Otherwise the CC sees ECN=0, holds rate, and lets the LB handle spatial collisions.

The `_network_is_asymmetric` flag is set organically when the LB enters frozen mode (triggered by RTO, which fires when a link failure kills ACKs), and cleared when the LB exits frozen mode. No control-plane broadcast required.

### CLI flags added

| Flag | Effect |
|---|---|
| `-state_aware_ecn` | Master toggle (off by default). Enables CC gate + asymmetric-flag wiring. Forces `repsUseFreezing = true`. |
| `-disable_tor_ecn` | Enables leaf exception (`force_disable_tor_ecn = true`). **Required whenever `-sender_cc_only` is also passed.** |
| `-fail_link_time <fail_us> <recover_us>` | Schedules dynamic Agg↔Core pipe failure and recovery. |
| `-fail_link_target <agg> <core>` | Repeatable. Selects which Agg↔Core link(s) to fail. |
| `-log_reps_state <file>` + `-log_reps_state_src <id>` | Per-ACK CSV diagnostic log. |
| `-log_reps_events <file>` + `-log_reps_events_src <id>` | Unified send+ACK+freeze event trace (SEND/RTX/RTS/ACK/NACK/FREEZE/UNFREEZE, slot-indexed buffer snapshot per row). Independent file and schema from `-log_reps_state`. See `experiments/tools/README.md` for the CSV schema and the `reps_event_viewer.py` interactive HTML viewer. |

`-exit_freeze <picoseconds>` already existed; our experiments use `200000000` (= 200 ms) to suppress mid-run thaws.

### Key code locations

<!-- Line numbers drift with every edit to uec.cpp — grep the function/anchor name
     in the right column rather than trusting the number alone. -->

| What | File | Line(s) |
|---|---|---|
| CC ECN-masking gate | `htsim/sim/uec.cpp` | `bool cc_ecn_view = pkt.ecn_echo();` in `processAck()`, ~1855 |
| FREEZING freeze entry + asymmetric-flag set | `htsim/sim/uec.cpp` | `rtxTimerExpired()`, ~4590-4620 |
| FREEZING unfreeze + asymmetric-flag clear | `htsim/sim/uec.cpp` | `processEv_freezing()`, ~3954 |
| REPS freeze entry + flag set | `htsim/sim/uec.cpp` | state-aware `_load_balancing_algo == REPS` branch inside `rtxTimerExpired()`, ~4666-4677 |
| REPS unfreeze + flag clear | `htsim/sim/uec.cpp` | `processEv_REPS()`, ~3443 |
| `_network_is_asymmetric` flag declaration | `htsim/sim/uec.h` | ~static toggle + per-source flag |
| `Pipe::_failed` flag + early-drop | `htsim/sim/pipe.h` ~42-48, `pipe.cpp` ~65 |
| Leaf-ECN re-enable gotcha | `htsim/sim/datacenter/main_uec.cpp` | ~739 |
| `LinkFailureEvent` class | `htsim/sim/datacenter/main_uec.cpp` |
| `_enable_ecn_on_tor_downlink` guards | `htsim/sim/datacenter/fat_tree_topology.cpp` | ~737, 754, 783 |

### REPS vs FREEZING — which to use

**Always use `-load_balancing_algo freezing` (= paper-REPS, 8-slot bounded buffer)** for any paper-comparable or state-aware work.

`-load_balancing_algo reps` is a code-only simpler variant (unbounded `_next_pathid` list). It's retained for archaeology. The buffer instrumentation column to track is `fresh` (FREEZING) vs `recycle` (REPS).

### Future directions (not implemented)

1. **v4 buffer-fill gate**: change CC ECN-masking from `cc_ecn = ecn && asymmetric` to `cc_ecn = ecn && (asymmetric || fresh ≤ 1)`. One-line change at the `cc_ecn_view` assignment in `processAck()`. Justified by exp02's `fresh=0 ⇒ P(ECN)≈1.0` finding (see `experiments/CLAUDE.md`).
2. **Long-failure stress**: early experiments used a 150 μs failure window (50→200 μs). A 1-10 ms window would exercise the freeze-expiry / auto-thaw path, which was never reached.
3. **Real-CDF workloads**: Datamining/Hadoop/Websearch CDFs (used in the paper) instead of synthetic permutations.
4. **Topology sweep**: extend exp03 to k=8 2-tier and 1024-host 3-tier topologies.
5. **EV-lifetime sweep**: implement the buffer-cache idea via `-reps_lifetime N` and re-run exp02-style instrumentation. The mechanism already exists (`repsMaxLifetimeEntropy`) but is gated off. Hypothesis: REPS' bounded buffer should cache known-good EVs (lifetime > 1) across draws instead of invalidating per use.

---

## Modifications inventory

**Repo-wide original-vs-ours map**: [`PROVENANCE.md`](../../PROVENANCE.md) — which top-level
directories/files are the paper's original artifact vs our additions, verified against the
first commit (`e19b8d0`). Use that file for anything outside `htsim/sim/`.

Full detail for `htsim/sim/` itself moved to [`experiments/MODIFICATIONS.md`](../../experiments/MODIFICATIONS.md)
— source of truth for original-vs-added boundary in `htsim/sim/`. Index below; consult that
file for exact lines, rationale, and per-entry results.
**Rule for future additions:** every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====`
banner at every modification site, (ii) a row in MODIFICATIONS.md, (iii) an ARCHITECTURE doc under
`experiments/`.

`[ORIGINAL]` — all of `htsim/sim/` except rows below; `artifact_scripts/`/`artifact_results/` untouched.

| Name | Gate | One-line |
|---|---|---|
| `state-aware` | `-state_aware_ecn` | CC ECN-mask gate + link-failure machinery |
| `smart-filter` | `-smart_filter_mode` | Continuous NSCC MD dampening from REPS buffer saturation |
| `wtd-in-nscc` | `-wtd_in_nscc` | Gate MD on `_exp_avg_ecn < 0.25` (SMaRTT-REPS §3.6.1) |
| `ev-health-counter` | `-smart_filter_counter evhealth` | Per-EV ECN-state tracker, replaces broken `fresh_inv` |
| `swift-cc` | `-sender_cc_algo swift\|lswift\|mswift\|mnscc` | New CCA implementations (arXiv:2509.07907v2 repro) |
| `min-rto-flag` | `-min_rto <us>` | CLI override for RTO floor |
| `swift-md-counter` | always compiled | Diagnostic `_swift_md_fires` counter, no behavior change |
| `per-host-lb` | `-host_lb_overrides` | Per-host LB algorithm override |
| `target-qdelay-respect-cli` (FIX) | n/a, applied 2026-05-30 | Removed post-CLI reset that silently discarded `-target_q_delay` |
| `median-buf-paper-faithful` (FIX) | n/a, applied 2026-06-01 | `DelayMedianBuffer` H-cap 32→128 + no-flush-on-shrink, paper Eq (8-9) fidelity |
| `reps-metrics-per-host-key` (FIX) | n/a, applied during dual-window review | `g_reps_metrics`/`RM()` was keyed by `_node_num` (assigned once per `UecSrc` object, i.e. per flow) despite the "per-host" framing everywhere else (`-log_reps_window`, exp29 docs, the `node` CSV column). Rekeyed to `_srcaddr` (the physical host id) so multi-flow-per-host workloads (this repo's standard permutation/incast matrices) collapse into one row per host instead of one per flow, and the map is bounded by host count instead of growing unboundedly with flow count. |
| `timed-failure-guards` (FIX) | n/a, applied during dual-window review | `-timed_window`/`-timed_fail_tor_uplinks`/`-timed_fail_tor_downlinks` had no mutual-exclusion check against the older `-fail_link_time`/`-fail_link_target` (both could fire simultaneously with indistinguishable log output) and no topology-tier check (the mechanism is documented/designed for the 2-tier fabric only, but ran silently on 3-tier, failing ToR<->Agg links while logging them as "uplink tor", implying spine/core). Both now hard-error at startup instead of silently misbehaving. |
| `swift-sack-hole-md` | `_sender_cc_algo==SWIFT`, always compiled | Swift MDs on SACK holes from OOO (paper 2 §IV.B correction) |
| `path-rr` | `-load_balancing_algo path_rr` | True RR over distinct physical paths via full source routing |
| `path-rr-npaths` | `-path_rr_npaths_override` | Per-host cap on number of PATH_RR paths |
| `path-rr-startslot` | `-path_rr_start_mode src_mod2` | 5th RR start-slot mode |
| `path-random` | `-load_balancing_algo path_random` | Per-packet uniform-random path selection |
| `path-static` | `-load_balancing_algo path_static` | Flow pinned to 1 path (greedy edge-load) + reverse-path routing fix |
| `srv6` | `-use_srv6` | SRv6 source-routing substrate, orthogonal to LB algo |
| `freezing-pxr` | `-load_balancing_algo freezing_pxr` | Path-eXcluding REPS: exclude RTO-triggering EV instead of full freeze |
| `reps-event-trace` | `-log_reps_events` | Unified send+ACK+freeze event trace plus an interactive HTML buffer viewer (`experiments/tools/`) |
| `metrics-counters` | always compiled | Per-source diagnostic counters appended to the flow-finish line (`rtos`, `freeze_entries`, `freeze_us`, `ev_explore`, `ev_random`); file-static side table, no `UecSrc` layout change, no behavior change. exp28. |
| `timed-failure` | `-timed_window` + `-timed_fail_tor_uplinks`/`-timed_fail_tor_downlinks` + `-log_reps_window` | Schedule a transient failure of the first F spine uplinks (or downlinks) of one ToR on the 2-tier fabric (reuses the `LinkFailureEvent` class, new 2-tier pipe resolution); periodic per-host CSV of `g_reps_metrics` deltas (`UecWindowLogger`). Adds `ecn_acks` + `fast_loss_entries` to the side table (`fast_loss` also on the finish line). No behavior change when flags absent. exp29. |
| `fail-src-paths` | `-fail_src_paths <src> <count>` | For one source host only, physical SRv6 path indices `[0,count)` are dead: a packet drawn onto them is `free()`d at emit (== first-hop failed Pipe), sender still arms the RTO. Scoped to one src by construction (no shared fabric pipe is per-path AND per-source). Static, whole-sim. No behavior change when flag absent. exp30 Part B. |
| `dual-window-reps-mprdma` | `-sender_cc_algo dual_mprdma_reps` (requires `-load_balancing_algo freezing`) | Two independent MPRDMA-AIMD windows per flow: `_win_safe` gates/updates from REPS-buffer EVs verified valid at pop time, `_win_random` from unverified EVs (random draws, explore bursts, stale frozen pops). EV selection unchanged (still `nextEntropy_freezing`); only cwnd admission/update is split and re-attributed by trust tier. Each window gets its own independent `_maxwnd` ceiling (combined in-flight can run up to ~2x a single-window MPRDMA ceiling — see the `-cap` v2 row below). See `experiments/MODIFICATIONS.md` for full design notes. |
| `dual-window-cwnd-cap` | `-sender_cc_algo dual_mprdma_reps_cap` (requires `-load_balancing_algo freezing`) | v2 of `dual-window-reps-mprdma`: same window/EV plumbing (reused via widened dispatch conditions, not duplicated), but enforces `_win_safe.cwnd + _win_random.cwnd <= _maxwnd` (a combined budget) instead of each window getting its own full ceiling — fixes that mechanism's confirmed cause of running far higher ECN/RTO than plain MPRDMA at the same B. Implemented as new, parallel functions by explicit user request; every original `dual-window-reps-mprdma` function is untouched (verified byte-identical output). See `experiments/MODIFICATIONS.md` for full design notes. |
| `dual-cwnd-log` | `-log_dual_cwnd <file> [-log_dual_cwnd_src <id>]` | Per-window cwnd time series for `dual-window-reps-mprdma`/`-cwnd-cap` — no prior logger captured `_win_safe`/`_win_random` separately (`-log_cwnd` only logs the combined `_cwnd`). Hooked into `syncDualCwnd()`, the single choke point every cwnd mutation (AI, NACK/MD, RTO decrease, idle reset, unfreeze reset, init) already calls through, so it captures all of them, not just per-ACK state. Raw bytes (not packets, to avoid truncating sub-packet AI increments), filtered on `_srcaddr` (physical src id, not `_node_num`). Schema in `experiments/tools/README.md`. |
| `reps-soft-replay` | `-reps_soft_replay` | Continuous randomize<->safety knob for `nextEntropy_freezing()`'s non-frozen fallback (buffer empty / no fresh entropies). With probability `_exp_avg_ecn` (original per-flow ECN EWMA), replays a recently-seen EV from the ring (`containsEntropy()`, matches stale slots too) instead of a pure random draw, skipping candidates this feature's own new per-EV ECN scoreboard (`_soft_replay_ev_ecn`) last saw marked. Depends only on original `UecSrc`/`CircularBufferREPS` members — no other addition's flag required. Frozen mode untouched (v1 scope). No behavior change when flag absent. |
| `per-host-cwnd` | `-host_cwnd_overrides` | Per-host cwnd override (mirrors `per-host-lb`'s map pattern), for isolating a CONSTANT-CC cwnd sweep to a host subset without perturbing the rest of the run. meeting 2026-10-06 C1 SoL. |
| `upstream-sync-2026-03` | none (always compiled, inert) | Ports Broadcom/csg-htsim commits `0639f63`, `20b2297`, `841d9e7`: `EthPausePacket` paused class, `.cm` `addon` token (`connection::addOnTriggerSignal`), `BarrierTrigger::activate(bool re_arm)`; one upstream assert disabled. No consumer in this repo; output byte-identical. |
| `rate-const-sender` | `-sender_cc_algo constant` + `-rate_const_gbps <R>` | Constant-rate sender, no CC (cwnd forced 1e6). R caps total NIC egress (data + rtx + ACK/control) via `UecNIC` egress shaper; requires 1 port. `-rate_const_data_only` = old per-source data-only pacer. Fixed-rate sweeps meeting 2026-10-23 M2/M4. See `experiments/RATE_CONST_ARCHITECTURE.md`. |
| `per-link-degrade` | `-degrade_links_file <file>` | Per-ToR-uplink degradation (`tor agg ratio` lines); queue size and ECN thresholds scale with ratio. Non-uniform failure model, meeting 2026-10-23 M3. Ratio up to 4; `all_adown`/`all_hdown <r>` lines scale all agg->ToR / ToR->host links (M4 investigate_k). |
| `ofan` | `-strat ofan` (+ `-ofan_ack_mode`, `-ofan_identity_order`, `-log_ofan_counts`) | Switch-side per-destination round-robin LB (arXiv 2610.07230); use with `-load_balancing_algo ecmp`; exp32. Docs: `experiments/OFAN_ARCHITECTURE.md` |
| `queue-stats` | `-log_queue_stats <file>` | Per-queue max occupancy/bytes/trims/drops per fat-tree layer (counters in `CompositeQueue`, no behaviour change) |
| `routing-convergence` | `-routing_convergence_us G` (+ `-routing_check`, `-routing_check_random`) | Failure-knowledge model: all switches learn of a pipe failure G us after it happens, then prune unreachable ports (Ofan, ECMP, AR, RR alike). Nothing is known before t_fail+G. G=0 only means 'converged' for failures present at t=0. Docs: `experiments/OFAN_ARCHITECTURE.md` |
| `ofan-weighted` | `-strat ofan_weighted` (needs `-routing_convergence_us`) | Extension (not in the paper): Ofan with the schedule weighted by live-path count per ToR uplink; falls back to plain Ofan when weights are equal. Branch `ofan-weighted`; `experiments/exp32_ofan/W1_weighted_ofan.md` |
| `ofan-trace` | `-log_ofan_trace <tsv>` (needs `-strat ofan`) | Per-decision Ofan trace; `experiments/exp32_ofan/scripts/ofan_reference.py` replays it against the paper's equations |
| `switch-baselines` | `-strat ecmp_rr_fixed\|ecmp_random\|ecmp_p2c`, `-ar_method exact` | Simple RR (no reshuffle), RSQ, P2C and exact-queue JSQ switch baselines for the Ofan paper comparison |
| `drb` | `-path_rr_start_mode random`, `-path_rr_order agg_fast` | Faithful DRB stand-in on top of `path_rr` (random per-flow phase, Agg-fastest path order); reproduces paper Figs 3/17 |
| `dctcp-debug-gate` | none | UEC DCTCP per-ACK debug print now behind `_debug` (no behaviour change) |

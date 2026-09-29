# State-Aware NSCC + REPS — architecture

> This document describes the as-built behavior of the state-aware extension after the v1 + v2 code changes are both in `htsim/sim/`. Everything is gated behind a single CLI flag `-state_aware_ecn`; with the flag off, the binary is byte-identical to vanilla NSCC + (REPS or FREEZING).

---

## The architectural premise

Every incoming ACK carries one ECN bit. The architecture splits its consumers:

- **Load Balancer (REPS or FREEZING)** — always sees the real ECN bit. Soft eviction is automatic in both algorithms: ECN-marked ACKs don't push their EV back into the active good-paths data structure, so the EV naturally rotates out.
- **Congestion Controller (NSCC)** — sees a *gated* ECN bit. The CC honors ECN only when the sender believes the network is asymmetric. Otherwise the CC sees ECN=0, holds rate, and lets the LB handle the spatial collision.

The gate is one boolean per source: `_network_is_asymmetric`. Driven organically by the LB's own frozen-mode state — no control-plane broadcast required.

## The four pieces of machinery

### 1. Leaf exception (already in baseline)

[`FatTreeTopology::_enable_ecn_on_tor_downlink`](../htsim/sim/datacenter/fat_tree_topology.h#L259) defaults to `false`, and guards at [`fat_tree_topology.cpp:737/754/783`](../htsim/sim/datacenter/fat_tree_topology.cpp#L737) skip ECN-marking on ToR→server downlinks. Destination incast surfaces as RTT/trim, never as ECN — so REPS doesn't bounce paths during incast.

**⚠ Critical gotcha**: at [`main_uec.cpp:739`](../htsim/sim/datacenter/main_uec.cpp#L739),
```cpp
bool ecn_on_tor_dl = !receiver_driven && !force_disable_tor_ecn;
```
Passing `-sender_cc_only` (which most experiments do) sets `receiver_driven=false`, which *re-enables* ECN on ToR downlinks unless you also pass `-disable_tor_ecn`. **Always include `-disable_tor_ecn` in state-aware experiments.** This is the v3-discovered prerequisite.

### 2. CC ECN-masking gate

At [`uec.cpp:1209`](../htsim/sim/uec.cpp#L1209), algorithm-agnostic (works for both REPS and FREEZING):

```cpp
if (_state_aware_ecn_enabled) {
    bool cc_ecn_view = pkt.ecn_echo() && _network_is_asymmetric;
    (this->*updateCwndOnAck)(cc_ecn_view, delay, newly_recvd_bytes);
} else {
    (this->*updateCwndOnAck)(pkt.ecn_echo(), delay, newly_recvd_bytes);   // original
}
```

When `-state_aware_ecn` is off, the original line at uec.cpp:1209 runs unchanged.

### 3. Organic asymmetric-mode detection

We hook into the existing frozen-mode entry/exit paths of *both* LB algorithms. All additions are gated; no original lines removed.

| LB algo | Set flag = true | Clear flag = false |
|---|---|---|
| `REPS` (v1) | New block in `rtxTimerExpired` ([uec.cpp:3022](../htsim/sim/uec.cpp#L3022)) — on RTO, set frozen mode + `_network_is_asymmetric = true`. | New check at top of `processEv_REPS` ([uec.cpp:2310](../htsim/sim/uec.cpp#L2310)) — when `can_exit_frozen_mode` elapses, unfreeze + clear flag. |
| `FREEZING` = paper-REPS (v2) | Existing freeze trigger in `rtxTimerExpired` ([uec.cpp:3040](../htsim/sim/uec.cpp#L3040)) — gated lines added alongside `setFrozenMode(true)` in both inner branches. | Existing unfreeze block in `processEv_freezing` ([uec.cpp:2653](../htsim/sim/uec.cpp#L2653)) — gated line added alongside `setFrozenMode(false)`. |

### 4. Dynamic link-failure mechanism

`Pipe` gains a `_failed` flag ([pipe.h:42-48](../htsim/sim/pipe.h#L42-L48)) and an early-drop branch in `receivePacket` ([pipe.cpp:65](../htsim/sim/pipe.cpp#L65)) — when set, every packet through the pipe is dropped.

A new `LinkFailureEvent` class in [`main_uec.cpp`](../htsim/sim/datacenter/main_uec.cpp) is an `EventSource` that, at simulation time `t_fail`, sets `_failed = true` on a chosen Agg↔Core pipe pair (both directions). At `t_recover`, clears it. Repeatable via multiple `-fail_link_target <agg> <core>` flags to fail several Agg↔Core links simultaneously.

---

## End-to-end behavior, phase by phase

Consider a single sender doing FREEZING + NSCC traffic with `-state_aware_ecn` on, while a core link fails mid-flow:

1. **Healthy, pre-failure** (`_network_is_asymmetric == false`).
   ACKs arrive with a mix of clean and ECN-marked bits. The LB sees the real bits — PATH_GOOD ACKs push to `circular_buffer_reps` (`add()`), PATH_ECN ACKs don't. The CC, gated, sees ECN=0 on every ACK. NSCC holds cwnd at its delay-controlled equilibrium.

2. **Link cut at t = t_fail**. The targeted Pipe drops every packet (both directions). Senders whose EVs route through that pipe stop receiving ACKs entirely.

3. **RTO fires (~1-2 RTT after the cut)** on affected senders. `rtxTimerExpired` runs. The FREEZING freeze trigger executes: `setFrozenMode(true)` + (gated by `-state_aware_ecn`) `_network_is_asymmetric = true`. From this moment, the CC sees real ECN.

4. **Stabilization**. With `_network_is_asymmetric == true` and frozen mode active, the LB stops drawing new EVs and cycles known-good ones only. The CC honors ECN from surviving cores → `multiplicative_decrease` ([uec.cpp:1394](../htsim/sim/uec.cpp#L1394)) shrinks cwnd to match reduced capacity.

5. **Link restored at t = t_recover**. The Pipe accepts packets again. Senders are still frozen + asymmetric but recycle known-good EVs that may now re-traverse the healthy core. No explicit recovery signaling needed.

6. **Auto-thaw**. After `exit_freeze_after` (configurable via `-exit_freeze`; default 10 ms, our experiments used 200 ms) elapses since freeze entry, the next call into `processEv_freezing` detects `eventlist().now() > can_exit_frozen_mode` and runs the unfreeze block: `setFrozenMode(false)` + `resetBuffer()` + `explore_counter = _bdp/_mtu`, AND (gated) `_network_is_asymmetric = false`. CC gate closes again.

---

## What's NOT changed

- **No new transport algorithm**. NSCC's `updateCwndOnAck_NSCC` is unchanged. REPS' `processEv_REPS` is unchanged in its buffer logic (only an added thaw check). FREEZING's `processEv_freezing` is unchanged in its buffer logic (only added gated `_network_is_asymmetric` writes inside existing entry/exit blocks).
- **No removed lines**. Every modification is an addition or a wrap. Vanilla behavior is preserved verbatim when `-state_aware_ecn` is off.
- **No new packet header**. The architecture lives entirely on the sender; the ECN bit is the standard one that already existed.

---

## CLI surface added

| Flag | Effect |
|---|---|
| `-state_aware_ecn` | Master toggle (off by default). Enables the CC gate + asymmetric-flag wiring in both REPS and FREEZING paths; forces `repsUseFreezing = true`. |
| `-disable_tor_ecn` | Enables the leaf exception (`force_disable_tor_ecn = true`). **Required when also passing `-sender_cc_only`.** |
| `-fail_link_time <fail_us> <recover_us>` | Schedules a dynamic pipe failure at `fail_us` and restoration at `recover_us`. Microseconds. Independent of `-state_aware_ecn`. |
| `-fail_link_target <agg> <core>` | Repeatable; selects which Agg↔Core link(s) to fail. Defaults to (0, 0). |
| `-log_reps_state <file>` + `-log_reps_state_src <id>` | Per-ACK CSV log of buffer state for diagnostics. Columns: `time_us, src_id, ecn, fresh, recycle, cwnd_pkts, exp_avg_ecn`. |

`-exit_freeze <picoseconds>` already existed; we typically pass `200000000` (= 200 ms) to suppress mid-run thaws so we observe the steady failure response.

---

## REPS vs FREEZING — which to use

| | `-load_balancing_algo reps` | `-load_balancing_algo freezing` |
|---|---|---|
| Active EV set | unbounded `_next_pathid` list ([uec.h:653](../htsim/sim/uec.h#L653)) | bounded 8-slot `circular_buffer_reps` ([buffer_reps.cpp:5](../htsim/sim/buffer_reps.cpp#L5)) |
| Paper alignment | NO — code-only simpler variant | YES — this is the paper's REPS (19/25 paper experiments) |
| Per-connection state | unbounded (grew to ~200 entries in measurements) | ≤ 25 bytes (matches paper's claim) |
| Instrumentation column to track | `recycle` | `fresh` |
| State-aware wiring | v1 (own RTO trigger + thaw in `processEv_REPS`) | v2 (hooks into existing FREEZING entry/exit) |

**Recommend `-load_balancing_algo freezing` for all paper-comparable work.** REPS is retained for code-archaeology purposes only.

---

## Why FREEZING is the recommended setting

The v2 study found a strong observable in this bounded buffer:

- **`fresh = 0` ⇒ P(next ACK is ECN-marked) ≈ 1.0** in every workload/topology tested.
- `corr(fresh, ECN) ≈ −0.21 to −0.24` across most scenarios.

That's the foundation for a future v4: replace the all-or-nothing asymmetric flag with a buffer-fill threshold (`cc_ecn = pkt.ecn_echo() && (asymmetric || fresh ≤ 1)`), so the CC reacts not only on RTO-confirmed failure but also when the LB's working memory has demonstrably drained. **v4 is NOT implemented yet.**

See also the project memory [`reps_buffer_cache_idea.md`](/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/reps_buffer_cache_idea.md) for a related design hypothesis (cache good EVs instead of invalidating per draw).

---

## Per-switch queue-occupancy sampling (`CoreDownlinkQueueSampler`)

Built for exp25 to test whether REPS's first-window round-robin (exp24 finding) produces a
synchronized queue spike on core switches. Samples `queues_nc_nup[core][agg][0]->queuesize()`
(core→agg **downlink**, bytes) for the first N core switches × all their connected aggs, at a
configurable interval — class in `htsim/sim/datacenter/main_uec.cpp`
(`// ===== ADDED (core-downlink-queue-log) =====`), gated by `-log_core_downlink_queues
<file>`. This is the downlink counterpart to the pre-existing `CoreQueueSampler`/
`TorQueueSampler` (agg→core and ToR→agg uplinks respectively, used by exp20/exp21's
`-log_core_queues`/`-log_tor_queues`). Result: exp25 did **not** find evidence of a REPS-side
queue spike on the sampled subset — see
[`exp25_queue_dynamics_v25/README.md`](exp25_queue_dynamics_v25/README.md).

---

## Per-source diagnostic counters (`metrics-counters`)

Built for exp28 (targeted ToR→spine-0 link-degradation sweep). Five per-source
quantities appended to the flow-finish `cout` line in `uec.cpp` `checkFinished`,
after the pre-existing `ecn_acks`: `rtos`, `freeze_entries`, `freeze_us`
(cumulative time frozen, with any interval still open at flow finish folded in),
`ev_explore`, `ev_random` (forced-exploration vs buffer-empty/no-fresh random EV
draws, both `nextEntropy_freezing` branches). Always compiled; no behaviour
change.

The counters are held in a **file-static side table** in `uec.cpp`
(`std::unordered_map<int, RepsMetrics>` keyed by `_node_num`, banner
`// ===== ADDED (metrics-counters) =====`), not in new `UecSrc` members: adding
any member to `UecSrc` on this codebase deterministically triggers a heap-
corruption abort during construction (a latent OOB write elsewhere is sensitive
to the struct's size/layout). `accrueFreeze()` is called from
`nextEntropy_freezing` (every send) and the end of `rtxTimerExpired`, so every
freeze entry/exit transition is caught within one send; `freeze_entries` was
verified equal to the `"started freezing"` printf count. Consumed by
[`exp28_link_degradation_sweep/README.md`](exp28_link_degradation_sweep/README.md).

## Timed link failure + per-host metric window log (`timed-failure`)

Built for exp29 (fastLossRecovery ↔ freeze crossover). Two independent pieces,
both always compiled, both inert when their flags are absent
(regression-checked byte-identical).

**Timed failure.** `-timed_window <start_us> <recover_us>` +
`-timed_fail_tor_uplinks <tor> <F>` (or `..._downlinks`) fail the first `F`
spine uplinks of one ToR for `t ∈ (start, recover)`, then restore. The
`LinkFailureEvent` class (State-Aware lineage, `main_uec.cpp`) is **reused
unmodified** — it already takes plain `Pipe*` and self-reschedules for recovery;
only its instantiation was 3-tier-bound (`pipes_nup_nc`, resized only when
`_tiers==3`). The new instantiation block resolves the 2-tier ToR↔spine pipe
arrays (`pipes_nlp_nup` / `pipes_nup_nlp`, resized unconditionally) and creates
one `LinkFailureEvent` per pipe (unused up/down slot = `nullptr`, which the
class skips). This is the clean, parametrized form of the paper's hardcoded
`scenario_micro_failures` (`-failed 42`, which string-matches a `-q 100`-encoded
queue name and so is inert under exp29's `-q 101`).

**Window log.** `-log_reps_window <file> <interval_us>` writes, every
`interval_us`, one CSV row per active node with the **deltas** of the
`g_reps_metrics` side table since the previous tick
(`d_rto, d_freeze_entries, d_fast_loss, frozen_frac, d_ev_random, d_ev_explore,
d_ecn_acks, frozen_now`). `UecWindowLogger` is a `Clock`-pattern `EventSource`
in `uec.cpp` (re-arm first, stop past `t_end`) — it lives in `uec.cpp` so it can
read the file-static side table directly, and is started from `main_uec.cpp` via
the `static` method `UecSrc::startRepsWindowLog`. The side table gains two
fields — `ecn_acks` (per-host mirror of `_ecn_ack_count`) and `fast_loss_entries`
(bumped at `fastLossRecovery`'s `_loss_recovery_mode = true` transition) — the
latter making the two-layer loss response (fast retransmit vs freeze/rotate)
directly visible per host per time window. Growing `RepsMetrics` (a plain local
struct) and adding `static` `UecSrc` members are both layout-safe; the heap bug
that forced the side table is specific to non-static `UecSrc` members. Consumed
by [`exp29_failure_response/README.md`](exp29_failure_response/README.md).

## Targeted single-source path loss (`fail-src-paths`)

Built for exp30 Part B. `-fail_src_paths <src> <count>` marks physical SRv6 path
indices `[0, count)` dead **for one source host only**. The check lives at the
two packet-emit sites in `uec.cpp` (`sendNewPacket`, `sendRtxPacket`): right
after the SRv6 pre-draw computes `route_path_idx = ev % _paths.size()`, an inline
`pathDeadForThisSrc(route_path_idx)` guard (`_fail_src_paths.empty()` fast-path →
`find(_node_num)` → `idx < count`) replaces `p->sendOn()` with `p->free()`. The
sender's own bookkeeping (`_highest_sent`/`_rtx_packets_sent`, `createSendRecord`,
`startRTO`) is untouched, so from the sender it is indistinguishable from a
first-hop failed `Pipe` (`pipe.cpp:67-70` does the same `pkt.free(); return`) —
no ACK → RTO → freeze → EV rotation.

Why a source-side guard and not a failed `Pipe`: the fabric has no pipe that is
both *per-path* (diverges by SRv6 index) and *private to one source* — a ToR
uplink carries all 32 hosts on the ToR, the access link carries all 32 of the
source's paths. So `-failed` / `-timed_fail_tor_uplinks` can only express
"1/32 of *every* ToR0 flow's paths" (exp30 Part A) or "F/32 of every ToR0 flow's
paths"; "1/4 of *one* pair's paths" (the meeting's regime) needs the source-side
mechanism. The static `UecSrc` map is layout-safe (same reasoning as
`timed-failure`). Consumed by
[`exp30_concentrated_path_loss/README.md`](exp30_concentrated_path_loss/README.md).

## Dual-window REPS+MPRDMA (`dual-window-reps-mprdma`)

New `-sender_cc_algo dual_mprdma_reps`, composes only with `-load_balancing_algo
freezing` (paper-REPS) — never with the separate, sticky-single-path
`-load_balancing_algo mprdma`, which shares the MPRDMA name but is otherwise
unrelated (CLI hard-errors on the wrong combination).

**Why**: REPS's circular EV buffer already tells you, per draw, whether an EV is
"known-good" (a fresh or valid-frozen buffer pop, backed by a prior `PATH_GOOD`
ACK) or unverified (a random draw, a post-unfreeze forced-explore packet, or a
stale frozen-mode pop). Under a single shared cwnd, losses/ECN marks on
unverified traffic throttle *everything*, including paths already proven clean.
Splitting into two independent MPRDMA-AIMD windows — `_win_safe` for verified
EVs, `_win_random` for everything else — lets clean traffic keep making
progress while REPS is actively exploring or recovering from a freeze. EV/path
selection itself is untouched (still `nextEntropy_freezing`); only cwnd
admission and the MPRDMA update are split and re-attributed by trust tier.

**The hard part isn't the AIMD math** (both windows run literally the same
MPRDMA formula — see `updateCwndOnAck_DualMPRDMA`/`updateCwndOnNack_DualMPRDMA`)
— **it's that admission has to happen before the EV is known.** The cwnd gate
(`sendIfPermitted`/`timeToSend`) fires before `nextEntropy_freezing()` draws an
EV, but the draw is destructive (pops/invalidates a buffer slot), so you can't
draw-and-discard on a gate failure without leaking EVs out of the bounded
8-slot buffer. The fix is a read-only predictor
(`predictWindowForNextEntropy_freezing()`, mirroring `nextEntropy_freezing`'s
branch order exactly against a non-destructive `peek_earliest_fresh()` +
the already-non-mutating `is_valid_frozen()`) that tells the gate which window
the *next* draw will land in, without touching buffer state. The real,
destructive draw happens moments later in the same event with nothing able to
mutate the buffer in between (single-threaded, event-driven sim) — a runtime
mismatch counter, not just that argument, is what actually proves it holds
(`_dual_predict_mismatch_count`, printed at flow finish; must be 0). One real
gap the counter caught during verification: `startFlow()`'s own initial send
loop calls `sendNewPacket()` directly, bypassing the `_sender_based_cc`
admission gate for *every* CC algo, so no prediction happens before those
particular sends — the counter only fires a false positive there once, and
the fix was to only count a round where a prediction was actually made.

The window tag is decided once, at send time (from the resolved `EvSource`),
stored on `sendRecord.win_tag`, and never re-derived later — by ACK/NACK/RTO
time the buffer slot may already be popped, invalidated, or wiped by
`resetBuffer()` on unfreeze, so the EV alone no longer says which window it
belonged to. A retransmission carries the *original* tag forward even though
it draws a fresh EV that may land in the other tier — a small side map
(`_rtx_win_tag`) threads it through, since `_rtx_queue`'s value type has no
room for it.

Per-window in-flight bytes live only on `MprdmaWindow.in_flight` (no separate
mirrored counter — an earlier draft had one and it was removed specifically to
avoid two counters that could silently diverge). The correctness net is a
single runtime-asserted invariant, gated to this algo so it costs nothing for
any other run: `_win_safe.in_flight + _win_random.in_flight == _in_flight`,
checked at the end of `processAck`, `processNack`, and `rtxTimerExpired`.
`mark_packet_for_retransmission()` (RTO path) is a third site besides ACK/NACK
that touches `_in_flight`/`_cwnd` together and needed its own window-aware
version.

Full design-decision rationale (window ceilings, asymmetric init values, the
1-MTU MD floor kept deliberately unraised, the FROZEN_POP validity split) and
the complete touched-file list are in
[`MODIFICATIONS.md`](MODIFICATIONS.md#dual-window-reps-mprdma--two-independent-mprdma-aimd-windows-for-repsfreezing).

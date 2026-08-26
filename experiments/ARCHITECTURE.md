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

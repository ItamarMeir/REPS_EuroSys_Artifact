# exp06 — Smart Filter between REPS (LB) and NSCC (CC)

**Status**: Code implemented. Experiments not yet run.

---

## Motivation

exp02 found `fresh = 0 ⇒ P(next ACK is ECN) ≈ 1.0`: when the bounded REPS buffer runs
out of unused EVs, congestion is imminent. exp03 showed that the state-aware binary gate
gives correct wiring but a narrow FCT win. The question here is: can we do better with a
**continuous, evidence-based filter** — one that uses REPS buffer state to dampen (not just
suppress) NSCC's multiplicative decrease step, without requiring the binary freeze/unfreeze
machinery of state-aware?

This experiment evaluates the smart filter on vanilla REPS+NSCC (no `-state_aware_ecn`),
across two filter modes and two counter sources, with both healthy and failure workloads.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full code-level design.

---

## Topology

- **fat_tree_128_1os_3t_400g.topo** — k=8, 128 hosts, 400 Gbps links, 3-tier, 1:1 OC
- BDP reference: 400 Gbps × 4 µs RTT / (8 × 4150 bytes) ≈ **48 packets**

---

## Common flags (all runs)

```
-sack_threshold 4000 -end 5000 -paths 65535
-sender_cc_only -sender_cc_algo nscc -load_balancing_algo freezing
-linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151
-disable_tor_ecn
```

No `-state_aware_ecn`. No `-fail_link_*` for `sev=0` runs.

---

## Design matrix

### Primary sweep (120 cells)

| Dimension | Values |
|-----------|--------|
| `mode` | `vanilla`, `sf_md_gain_ecn`, `sf_md_gain_fresh`, `sf_blend_ecn`, `sf_blend_fresh` |
| `workload` | composite, perm_8mb, perm_32mb, perm_128mb |
| `sev` | 0 (healthy), 4 (one Agg↔Core link fails at t=50µs, restores at t=200µs) |
| `seed` | 42, 43, 44 |

All cells use default buffer size `B=8` and default auto-threshold `K=ceil(8/4)=2`.

### Stretch sweep (validates B-independence, optional)

Repeat 5 modes × 2 sev × 3 seeds at `B ∈ {2, 8, 16, 32}` with `-reps_buffer_size B`.
The auto-K = ceil(B/4) gives K=1/2/4/8 automatically — no manual threshold tuning.

---

## Mode-to-flag mapping

| `mode` label | CLI flags |
|---|---|
| `vanilla` | *(no smart-filter flags)* |
| `sf_md_gain_ecn` | `-smart_filter_mode md_gain -smart_filter_counter ecn` |
| `sf_md_gain_fresh` | `-smart_filter_mode md_gain -smart_filter_counter fresh` |
| `sf_blend_ecn` | `-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn` |
| `sf_blend_fresh` | `-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh` |

For failure runs (`sev > 0`) add:
```
-fail_link_time 50 200 -fail_link_target 0 0
```

---

---

## How NSCC works (background needed to understand the filter)

NSCC is a sender-driven congestion controller that runs on every ACK. It maintains a single
congestion window `cwnd` and adjusts it based on two signals:

**1. Queuing delay** — the raw RTT minus the measured minimum RTT gives the queuing component
(how much of the RTT is attributable to buffering rather than propagation):
```
avg_delay = get_avg_delay()   # EWMA of (rtt - base_rtt), α=0.0125
target_Qdelay = 6 µs          # target queue depth
```

**2. ECN** — the Congestion Experienced bit carried by ACKs. A second EWMA
(`exp_avg_ecn`, α=0.125) tracks the fraction of ECN-marked ACKs. The raw bit is
also used directly for the immediate per-ACK decision.

**The four CC actions**, dispatched in `updateCwndOnAck_NSCC()` based on `(ecn_bit, avg_delay)`:

| ECN bit | avg_delay vs target | Action |
|---------|---------------------|--------|
| 0 (clean) | ≥ target | `fair_increase` — moderate additive increase |
| 0 (clean) | < target | `proportional_increase` — increase proportional to headroom |
| 1 (ECN) | ≥ target | **`multiplicative_decrease`** — reduce cwnd |
| 1 (ECN) | < target | no action (commented out: was `fair_decrease`) |

The **multiplicative decrease formula** is the key target of the smart filter:
```cpp
_cwnd *= max(1 - γ · (avg_delay - target_Qdelay) / avg_delay, 0.5)
```
where γ = 0.8. This fires *only* when both ECN=1 AND avg_delay ≥ target_Qdelay.
The `0.5` floor prevents reducing cwnd by more than 50% in one step.

**The problem with vanilla NSCC + REPS**: REPS picks EVs (paths) from a small buffer of
8 slots. If one slot holds a congested EV that returns ECN-marked ACKs, NSCC sees the
ECN bit and applies full MD — even though 7/8 EVs in the buffer may be perfectly clean.
The filter inserts a "how saturated is the buffer with congestion evidence?" check to
proportionally dampen the MD response.

---

## Filter Mode A — `md_gain` (scale the MD step)

**Core idea:** keep the ECN gate untouched (CC still sees the real ECN bit), but *scale the
magnitude of the MD step* by how much congestion evidence is in the REPS buffer. The gain
is `counter / B ∈ [0, 1]`.

**Modified MD formula:**
```cpp
double gain = smartFilterCounter() / B;
_cwnd *= max(1.0 - γ · gain · (avg_delay - target_Qdelay) / avg_delay, 0.5)
```

**Behavior at the extremes:**
- `counter = 0` → `gain = 0` → formula becomes `max(1.0, 0.5) = 1.0` → cwnd unchanged (no decrease at all)
- `counter = B` → `gain = 1` → formula is the vanilla NSCC MD formula (full decrease)
- Intermediate values → proportional damping between zero and full decrease

**When does this help?** When a single outlier EV in the buffer triggers occasional ECN
marks (counter stays near 1-2/8 = 12-25%), the MD step is severely dampened. The CC
holds its rate while REPS naturally rotates the bad EV out. This is exactly the "spatial
collision" case where the original paper intended REPS to handle the problem at the LB
layer, not the CC layer.

**When does this hurt?** If the network is broadly congested (many paths bad), the counter
will climb to B quickly and MD will gradually increase to vanilla strength. But the
transition takes `B` clean-vs-ECN ACKs, which is a lag of ~B × RTT in the worst case.
Under a sudden failure where many flows lose their EVs simultaneously, this lag may delay
rate reduction. The `+1/−1` asymmetry means it takes B ECN ACKs in a row to hit full
gain, which is typically reached within 1-2 RTTs of a real failure.

**What Mode A touches and does not touch — precise accounting:**

Mode A only modifies the gain coefficient `γ` inside `multiplicative_decrease()`. Every
other NSCC path runs unchanged:

| Branch | Fires when | RTT signal used | Mode A effect |
|--------|-----------|-----------------|---------------|
| `fair_increase` | `!ecn, delay ≥ target` | None — pure `+= fi·mtu·bytes` | **None** |
| `proportional_increase` | `!ecn, delay < target` | Raw current queuing delay (`target − delay`) | **None** |
| `quick_adapt` | `avgqdelay > qa_threshold` | EWMA avg_delay | **None** |
| MD **gate** (`avg_delay > target`) | always checked in MD | EWMA avg_delay | **None** — gate uses real avg_delay |
| MD **formula** | `ecn, delay ≥ target` (after gate) | EWMA avg_delay in formula | **`γ` scaled by gain** |

Important subtlety: the MD **gate** (`avg_delay > target_Qdelay`) is *not* modified — if
real queuing delay is above target, MD still fires regardless of the counter. Mode A only
controls *how much* cwnd shrinks once MD does fire. At `counter = 1, B = 8`, MD is
triggered by the usual RTT+ECN conditions but reduces cwnd by only 1/8th of the vanilla
amount.

This also means AI and PI continue running at full strength during an MD event. If the
*next* ACK is ECN=0 with delay < target, `proportional_increase` will add to cwnd
normally — unconstrained by the filter. The net effect is that low-counter MD events
barely dent the cwnd, and normal AI/PI quickly undo them, keeping throughput up while
REPS rotates the outlier EV out of the buffer.

**Mode B handles this differently**: it blends `avg_delay` itself to zero at low counter,
which can prevent the MD gate (`avg_delay > target`) from even triggering — stopping MD
entirely rather than merely dampening it.

---

## Filter Mode B — `rtt_blend_ecn_thresh` (blend queuing delay + threshold the ECN gate)

**Core idea:** apply two simultaneous modifications — gate ECN via a threshold so isolated
ECN events are fully suppressed, AND scale the queuing-delay contribution to MD so that
even if ECN passes the gate, the MD magnitude is proportional to buffer saturation.

Before explaining the two parts, note a critical fact about NSCC's delay signals:
there are **two different delay values** in play, and Mode B affects them differently:

- **`delay`** (raw per-ACK): `_raw_rtt − _base_rtt`, computed fresh every ACK.  
  Used for the **branch dispatch** in `updateCwndOnAck_NSCC` and by `proportional_increase`.
- **`avg_delay`** = EWMA of queuing delay (α=0.0125): read independently by `quick_adapt`
  and again inside `multiplicative_decrease()`. Mode B only touches the second one, and
  only as a local copy — the EWMA state is never written.

### Part 1 — ECN threshold gate

In `processAck()`, the CC's view of ECN is replaced:
```cpp
cc_ecn_view = pkt.ecn_echo() && (smartFilterCounter() >= K)
```
`cc_ecn_view` becomes the `skip` argument in `updateCwndOnAck_NSCC`. This is not just
"suppress MD" — it re-routes the entire dispatch:

- **`counter < K`**: `skip = false`. NSCC treats the ACK as clean. If raw `delay ≥ target` → `fair_increase` fires. If raw `delay < target` → `proportional_increase` fires. **Cwnd can grow on an ECN-marked ACK.**
- **`counter ≥ K`**: `skip = true`. ECN passes. If raw `delay ≥ target` → `multiplicative_decrease` (Part 2 applies). If raw `delay < target` → NOOP.

The LB always sees the real ECN bit regardless (`processEv` is called with the unfiltered value).

**Why K=ceil(B/4) as default?** The network ECN-marking threshold is `-ecn 25 76` (25% of queue). K/B = 1/4 = 25% mirrors this: the filter activates when the buffer shows 25% ECN saturation, matching the fabric's own congestion-signaling point.

### Part 2 — Convex-blend on EWMA queuing delay (inside MD only)

Only reached when ECN passed the gate above. Inside `multiplicative_decrease()`:
```cpp
double x = smartFilterCounter() / B;
local_avg_delay = x * get_avg_delay()   // local variable; EWMA state untouched
```

- `counter = K` (minimum to enter): `x = K/B ≈ 0.25` → avg_delay reduced to 25% → inner MD gate `avg_delay > target` likely fails at low congestion → **no MD even after entering this branch**
- `counter = B`: `x = 1` → vanilla MD

There is a subtle two-gate structure: the **outer dispatch** uses raw per-ACK `delay`, while the **inner MD gate** uses blended EWMA `avg_delay`. A single RTT spike can pass the outer gate while the EWMA hasn't caught up, and Mode B's blend makes the inner gate even more likely to fail.

### Full branch effect summary

| ECN mark | `counter` vs K | raw `delay` vs target | Branch fired | Mode B effect |
|---|---|---|---|---|
| ECN=1 | `counter < K` | `≥ target` | **`fair_increase`** | **AI fires on ECN-marked ACK** |
| ECN=1 | `counter < K` | `< target` | **`proportional_increase`** | **PI fires on ECN-marked ACK** |
| ECN=1 | `counter ≥ K` | `≥ target` | **`multiplicative_decrease`** | Blend applied; inner gate and formula magnitude both scaled |
| ECN=1 | `counter ≥ K` | `< target` | NOOP | No change |
| ECN=0 | either | any | AI or PI | None |
| `quick_adapt` | either | any | Pre-dispatch | **None** — reads real EWMA |

### Mode A vs Mode B — comparison

| Aspect | Mode A (`md_gain`) | Mode B (`rtt_blend_ecn_thresh`) |
|--------|--------------------|---------------------------------|
| ECN gate | **Real ECN always passes** | Blocked until `counter ≥ K` |
| What fires on ECN-marked ACK when counter is low | MD with damped gain | **`fair_increase` or `proportional_increase`** (cwnd grows!) |
| What fires on ECN-marked ACK when counter is high | MD with full gain (vanilla) | MD with blended avg_delay |
| Branches affected | Only MD formula | All four dispatch branches (depending on counter) |
| EWMA delay state | Never touched | Never touched (blend is on a local copy) |
| `quick_adapt` | Untouched | Untouched |
| Conservatism at low counter | Moderate (MD barely fires, no growth) | Aggressive damping (MD suppressed, AI/PI grows cwnd) |
| Failure recovery | MD ramps up as counter rises | ECN gate opens at K, then MD fires with blend |
| Tuning knobs | None (only B) | K threshold (default auto=ceil(B/4)) |

Mode A is the simpler mechanism and a better first choice for understanding the filter's
baseline effect. Mode B provides more headroom for suppressing transient ECN events at the
cost of potentially slower recovery under sustained congestion.

---

## Expected outcomes

- **`sf_md_gain` (Mode A)**: in healthy state, `counter/B ≈ 0` most of the time, so MD is
  almost fully suppressed. This should reduce cwnd thrashing on outlier-EV ECN bursts,
  potentially improving incast p99. Under failure, the LB freezes and ECN saturates the
  buffer → `counter` rises → `gain` rises → CC reacts more. Without the `_network_is_asymmetric`
  OR-leg, recovery may be slower than state-aware.

- **`sf_blend` (Mode B)**: the ECN threshold K=2 means the CC reacts only when the counter
  reaches 25% of B. Under light incast this keeps the CC quiet. Under failure/sustained
  congestion the counter climbs and the blend ratio rises, letting MD engage.

- **`ecn` vs `fresh` counter**: `fresh` fires BEFORE the first ECN (leading indicator);
  `ecn` fires AFTER. Expect `sf_*_fresh` modes to react sooner and potentially over-dampen
  in healthy state (the buffer empties transiently even without broad congestion).

---

## How to run

Create `scripts/v6_run_matrix.sh` modeled on `exp04_buffer_ev_sweep_v4/scripts/v4_run_matrix.sh`.
Driver must be idempotent (skip existing `runs/` outputs) and always pass `-disable_tor_ecn`.

After runs complete, compress:
```bash
tar -czf exp06_smart_filter_v6/runs.tar.gz -C exp06_smart_filter_v6/runs . \
  && rm -rf exp06_smart_filter_v6/runs/
```

Aggregate to tidy CSV with columns: `workload, mode, sev, seed, flow_id, fct_us, size, flow_class`.
Plot with 95% CI error bars (t-distribution).

---

## Validation checks before claiming results

1. `grep "enable on tor downlink" <run.out>` must always show `0`.
2. Per-ACK CSV: `corr(ecn, ecn_counter) > 0.5` and `P(cc_ecn_view=1|ecn=1)` is clearly
   below 1.0 for Mode B healthy runs.
3. Vanilla cell FCTs match exp04 numbers for same seeds/workloads (default-off invariant).
4. In B-sweep stretch: sf_gain distributions shift correctly as B changes.

---

## Open questions (see ARCHITECTURE.md §Risks)

1. Counter saturation: if `P(counter/B ≥ 0.5) > 30%` in healthy state, try `+1/−2` increments.
2. K choice: sweep `K ∈ {1, 2, 3}` if Mode B shows lockout artifacts.
3. Counter reset on RTO: if failure-case recovery is poor, seed counter to `B/2` at RTO sites.

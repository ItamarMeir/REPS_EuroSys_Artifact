# Smart Filter between REPS (LB) and NSCC (CC) — Architecture

> **This is a SEPARATE addition from the state-aware NSCC+REPS extension.**
> The two are independent and mutually exclusive at runtime (the binary exits with
> an error if both `-smart_filter_mode` and `-state_aware_ecn` are passed together).

---

## What problem this solves

In the **original** REPS+NSCC implementation, every incoming ACK feeds the real ECN bit
and the raw RTT into NSCC unconditionally. When only a small subset of EVs (entropy
vectors = path choices) experience congestion (e.g. one outlier path saturated while
the rest are fine), the CC still drives a full multiplicative decrease. It has no way to
distinguish local-spatial congestion from broad fabric congestion.

Exp02 found that the REPS buffer's occupancy is a near-deterministic signal:
**`fresh = 0 ⇒ P(next ACK is ECN) ≈ 1.0`** — when the 8-slot buffer runs out of
fresh (never-drawn) EVs, the next ACK is almost certainly ECN-marked. That means REPS
buffer state can be repurposed as a *continuous evidence channel* that NSCC can consult
to dampen its reaction to likely-outlier congestion signals.

---

## Default-off invariant

With `-smart_filter_mode` absent (the default), the binary is **byte-for-byte identical**
to vanilla NSCC + REPS/FREEZING. All new code is inside banner-marked blocks:
```cpp
// ===== ADDED (smart-filter) ========
// ...
// ===== END ADDED (smart-filter) ====
```

---

## The congestion-evidence counter

A per-source integer `_ecn_buffer_counter ∈ [0..B]` is maintained on every ACK, where
`B = CircularBufferREPS<int>::repsBufferSize` (the live REPS buffer size, set by
`-reps_buffer_size`, default 8):

```
+1 on ECN-marked ACK    (capped at B)
-1 on clean ACK         (floored at 0)
```

The counter is NOT reset on RTO/freeze events — it decays organically via +1/−1.

Two counter sources are plumbed side-by-side for A/B comparison via `-smart_filter_counter ecn|fresh`:

| Source | How computed | Indicator type |
|--------|--------------|----------------|
| `ecn` (default) | `_ecn_buffer_counter` (+1/−1 per ACK) | Trailing — fires after first ECN |
| `fresh` | `B − getNumberFreshEntropies()` | Leading — fires when buffer runs low |

The fresh-derived counter saturates BEFORE the first ECN of a burst (because the buffer
depletes first). The ECN counter saturates only after seeing ECN. Expect different FCT
profiles between the two; the A/B is the point.

**All formulas use `counter / B` as the scaling ratio**, so repeating exp04-style
buffer-size sweeps with the smart filter on gives automatic, correct scaling without
any manual K tuning.

---

## Filter modes

### Mode A — `md_gain`

The multiplicative decrease (MD) step is scaled by `gain = counter / B`:

```cpp
double gain = (_smart_filter_mode == SF_MD_GAIN) ? _sf_md_gain : 1.0;
_cwnd *= max(1.0 - _gamma * gain * (avg_delay - _target_Qdelay) / avg_delay, 0.5);
```

- `counter = 0` → `gain = 0` → MD factor = `max(1.0, 0.5) = 1.0` → **no decrease**
- `counter = B` → `gain = 1` → **original vanilla MD**
- In between → proportional damping

The CC still sees real ECN (ECN is not gated). Damping happens purely in MD.
AI/PI/quick_adapt branches are untouched.

**Exactly what Mode A does and does not touch:**

| NSCC branch | Condition | Uses RTT? | Mode A effect |
|---|---|---|---|
| `fair_increase` | `!ecn && delay ≥ target` | No — pure `+= fi·mtu·bytes` | **None** |
| `proportional_increase` | `!ecn && delay < target` | Yes — `α·(target_Qdelay − delay)·bytes` uses raw current queuing delay | **None** |
| `quick_adapt` | `avgqdelay > qa_threshold` | Yes — sets `_cwnd = _achieved_bytes` | **None** |
| `multiplicative_decrease` — gate | `avg_delay > target_Qdelay` check | Yes — EWMA queuing delay | **None** — gate uses real avg_delay |
| `multiplicative_decrease` — formula | `_cwnd *= max(1 − γ·gain·(avg_delay−target)/avg_delay, 0.5)` | Yes — EWMA avg_delay in formula | **Only the gain coefficient γ is scaled** |

Concretely: if `counter = 1` (B=8, gain = 1/8), MD still fires (the `avg_delay > target` check is unchanged), but the cwnd reduction is 1/8th of vanilla. The RTT queuing depth still determines whether MD triggers and how large the raw formula would be — Mode A only scales the final step size. Meanwhile `proportional_increase` in the same ACK stream is completely unaware; if the next ACK is clean and delay is low, PI will increase cwnd normally.

**Implementation site:** `multiplicative_decrease()` in `htsim/sim/uec.cpp:1528` (line may shift with additions).

### Mode B — `rtt_blend_ecn_thresh`

Two simultaneous modifications. Before reading them, note a critical distinction in NSCC's delay signals:

- **`delay`** (raw per-ACK): `_raw_rtt − _base_rtt`, computed in `processAck()` and passed as an argument to `updateCwndOnAck_NSCC`. Used for the **branch dispatch** (`delay >= target_Qdelay?`) and directly by `proportional_increase`.
- **`avg_delay`** = `get_avg_delay()` (EWMA of queuing delay, α=0.0125): read independently inside `updateCwndOnAck_NSCC` (for `quick_adapt`) and again inside `multiplicative_decrease()` (for the inner gate and formula). These are two separate `get_avg_delay()` calls.

**Modification 1 — Threshold ECN gate** (in `processAck()`):
```cpp
cc_ecn_view = pkt.ecn_echo() && (smartFilterCounter() >= K);
```
`cc_ecn_view` becomes the `skip` argument in `updateCwndOnAck_NSCC`. This re-routes entire branches.

**Modification 2 — Convex-blend on EWMA queuing delay** (inside `multiplicative_decrease()` only):
```cpp
double x = (double)smartFilterCounter() / (double)B;
avg_delay = (simtime_picosec)(x * (double)avg_delay);   // local copy only
```
Only reached when ECN passed the gate (Modification 1). The shared EWMA state `_avg_delay` is never written.

### Full branch accounting for Mode B

| ECN mark | `counter` vs K | raw `delay` vs target | Branch fired | Mode B effect |
|---|---|---|---|---|
| ECN=1 | `counter < K` | `delay ≥ target` | **`fair_increase`** | ECN suppressed → ACK looks clean → **AI fires on an ECN-marked ACK** |
| ECN=1 | `counter < K` | `delay < target` | **`proportional_increase`** | ECN suppressed → **PI fires on an ECN-marked ACK** |
| ECN=1 | `counter ≥ K` | `delay ≥ target` | **`multiplicative_decrease`** | Blend: `avg_delay = x·avg_delay`. Inner gate `avg_delay > target` may now fail even though outer dispatch passed. Formula magnitude scales with x. |
| ECN=1 | `counter ≥ K` | `delay < target` | **NOOP** | No change (same as vanilla) |
| ECN=0 | either | `delay ≥ target` | **`fair_increase`** | None |
| ECN=0 | either | `delay < target` | **`proportional_increase`** | None |
| Any | either | any | **`quick_adapt`** (pre-dispatch) | **None** — reads real EWMA avg_delay, unaffected |

**The most significant effect is rows 1–2:** when `counter < K`, ECN-marked ACKs are re-classified as clean by the gate, and `fair_increase` or `proportional_increase` fires instead of (or in place of) MD. Cwnd can actively **grow** on an ECN-marked ACK. This is not just "suppress MD" — it is the same mechanism as the state-aware binary gate when `_network_is_asymmetric = false`.

**The inner-gate subtlety (row 3):** when `counter ≥ K` and the outer dispatch enters MD via raw `delay ≥ target`, the inner gate inside `multiplicative_decrease()` re-checks `x · avg_delay > target_Qdelay` using the blended EWMA. Because raw `delay` and EWMA `avg_delay` are different signals, the outer dispatch can enter MD while the inner gate fails (e.g., a single RTT spike on this ACK with low EWMA), suppressing the decrease. Mode B's blend makes this more likely at low counter.

**Comparison with Mode A:**
- Mode A: ECN always passes the gate. Only the MD formula's gain coefficient is scaled. AI/PI are completely untouched, even on ECN-marked ACKs. Only one formula line is modified.
- Mode B: ECN-marked ACKs at `counter < K` are re-routed to AI/PI. ECN-marked ACKs at `counter ≥ K` enter MD with a blended avg_delay. More branches affected; can grow cwnd on ECN-marked ACKs.

**Implementation sites:**
- ECN gate: `processAck()` in `htsim/sim/uec.cpp` (the `else if (_smart_filter_mode == SF_RTT_BLEND_ECN_THRESH)` branch)
- Delay blend: `multiplicative_decrease()` in `htsim/sim/uec.cpp` (the `if (_smart_filter_mode == SF_RTT_BLEND_ECN_THRESH)` block)

---

## CLI flags summary

| Flag | Values | Default | Effect |
|------|--------|---------|--------|
| `-smart_filter_mode` | `none`, `md_gain`, `rtt_blend_ecn_thresh` | `none` (off) | Select filter mode |
| `-smart_filter_counter` | `ecn`, `fresh` | `ecn` | Counter source for A/B comparison |
| `-smart_filter_ecn_thresh` | integer or -1 | -1 (auto) | Mode B ECN threshold K; auto = ceil(B/4) |

**Coexistence rule:** `-smart_filter_mode` and `-state_aware_ecn` must not be combined.
The binary exits with an error if both are set. They target the same gate site but with
different philosophies (smart-filter = continuous/evidence-based; state-aware = binary/event-based).

**Pre-existing gotcha:** any command with `-sender_cc_only` MUST also include `-disable_tor_ecn`
(see CLAUDE.md gotcha section).

---

## Code changes (all in `htsim/sim/`)

Every modification is additions-only with clear banners. Original lines are preserved.

| File | What was added |
|------|----------------|
| `uec.h` | Banner block: enums `SmartFilterMode`/`SmartFilterCounter`, statics `_smart_filter_mode/_counter/_ecn_thresh`, per-source `_ecn_buffer_counter`/`_sf_md_gain`, accessors `smartFilterCounter()`/`smartFilterEcnThresh()`. |
| `uec.cpp` | Static storage defs; `smartFilterCounter()` / `smartFilterEcnThresh()` bodies; counter update + MD-gain pre-compute in `processAck()` (~L1185); parallel else-if branch in ECN gate (~L1225); Mode A gain + Mode B blend in `multiplicative_decrease()` (~L1428); 8 extra columns in CSV `fprintf` (~L1238). |
| `datacenter/main_uec.cpp` | Three flag parsers (`-smart_filter_mode/-counter/-ecn_thresh`) in a banner block; coexistence guard after parse loop; updated CSV header. |

**No changes** to `buffer_reps.h/.cpp`, `pipe.h/.cpp`, `fat_tree_topology.*`, or any
state-aware code paths.

---

## CSV log columns

When `-log_reps_state <file>` is used, each per-ACK row now contains 17 columns
(8 original + 9 new; old columns unchanged so existing plotters keep working):

```
time_us, src_id, ecn, fresh, recycle, cwnd_pkts, in_flight_pkts, exp_avg_ecn,
buf_size, ecn_counter, fresh_inv, sf_mode, sf_counter_used, sf_ecn_thresh, sf_gain, sa_asym, cc_ecn_view
```

New columns:
- `buf_size` — `CircularBufferREPS<int>::repsBufferSize` at row time (for normalization)
- `ecn_counter` — the explicit `_ecn_buffer_counter` value
- `fresh_inv` — `buf_size − fresh` (leading counter, no ECN lag)
- `sf_mode` — active mode (0=none, 1=md_gain, 2=rtt_blend_ecn_thresh)
- `sf_counter_used` — `smartFilterCounter()` return value (dispatched on source)
- `sf_ecn_thresh` — resolved K (so `-1` auto is visible as its actual value)
- `sf_gain` — the `_sf_md_gain` scratch (0.0..1.0 in Mode A; 1.0 always in Mode B)
- `sa_asym` — `_network_is_asymmetric` (logged for cross-experiment comparison, not composition)
- `cc_ecn_view` — final CC-facing ECN bit after the gate (post-filter)

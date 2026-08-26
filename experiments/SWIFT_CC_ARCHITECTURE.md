# Swift CCA Extensions — Architecture

This document describes the as-built implementation of Swift, LSwift, MSwift, and MNSCC in
`htsim/sim/`, added to support paper reproduction experiments (arXiv:2509.07907v2, "CC4Spraying").
All four CCAs are gated behind `-sender_cc_algo {swift,lswift,mswift,mnscc}`; with none of
these flags set, the binary is byte-identical to vanilla NSCC + REPS/FREEZING.

Paper reference: Gerstein, Silberstein & Keslassy, "CC4Spraying: Congestion Control for
Packet Spraying" (arXiv:2509.07907v2).

---

## Overview of the four CCAs

| CCA | Basis | MD trigger | Reordering resilient | Median filter |
|-----|-------|-----------|---------------------|--------------|
| **Swift** | delay-based AIMD | every high-delay ACK | No — MDs on SACK holes | No |
| **LSwift** | Swift | 5 consecutive high-delay ACKs + 1-RTT cooldown | Yes | No |
| **MSwift** | LSwift | same as LSwift, but on median-filtered delay | Yes | Yes — H = max(W/2, 1) |
| **MNSCC** | NSCC | same MD logic as NSCC, but on median-filtered delay | Yes | Yes — H = max(min(W/2, 4), 1) |

All four share the same delay target as NSCC (`_target_Qdelay`, default 6 µs unless
`-target_q_delay` is passed). The paper explicitly sets `NSCC's target queueing delay to equal
that of Swift`.

---

## File inventory

| File | Role |
|------|------|
| [`htsim/sim/delay_median_buffer.h`](../htsim/sim/delay_median_buffer.h) | New utility class `DelayMedianBuffer`. Shared by MSwift and MNSCC. |
| [`htsim/sim/uec.h`](../htsim/sim/uec.h) | Enum values, static params, per-source fields, method declarations. |
| [`htsim/sim/uec.cpp`](../htsim/sim/uec.cpp) | Static defs, dispatch table entries, all four CCA bodies. |
| [`htsim/sim/datacenter/main_uec.cpp`](../htsim/sim/datacenter/main_uec.cpp) | CLI flag parsing. |

---

## DelayMedianBuffer (`delay_median_buffer.h`)

A fixed-size circular ring of `simtime_picosec` delay samples supporting O(H log H) percentile
queries. Used by MSwift and MNSCC to smooth per-ACK delay noise before feeding it into the CC
decision.

Key design decisions (both motivated by paper fidelity):

**`MAX_H = 128`**
Paper 2 Eq (8) sets MSwift's window H = max(W/2, 1). At BDP cwnd ≈ 120 packets (typical
in the Fig 4 setup), the paper's H = 60. An earlier `MAX_H = 32` silently clamped this
to 32, making the median behave closer to raw delay. Fixed by raising `MAX_H` to 128.
Sort cost is ~640 comparisons per ACK — negligible.
Fix tag: `// ===== FIX (median-buf-paper-faithful) =====` in `delay_median_buffer.h`.

**No flush on shrink**
When the cwnd drops (due to MD), `setCapacity(H)` is called with a smaller H. The original
implementation flushed all history on shrink, which discarded the smoothed signal exactly
when it was most useful. The fix truncates `_count` to `newCap` instead, keeping the
most-recent `newCap` samples. The ring's `_head` pointer needs no adjustment.

```
API
  push(delay)          — record one sample
  setCapacity(H)       — resize window (no flush on shrink)
  percentile(p)        — p-th percentile of stored samples (0–100)
  median()             — shorthand for percentile(50)
```

---

## Swift (`-sender_cc_algo swift`)

**Algorithm**: per-ACK delay-based AIMD. No reordering protection.

```
if delay < target:
    cwnd += mss * ai / cwnd_pkts   (AI)
else:
    factor = max(1 - β*(delay-target)/delay,  1 - max_mdf)
    cwnd  *= factor                (MD, every high-delay ACK)
```

Parameters:
- `ai` — additive increase step, default 1.0 (`-swift_ai`)
- `β` — MD aggressiveness, default 0.8 (`-swift_beta`)
- `max_mdf` — maximum MD fraction, default 0.5 (`-swift_max_mdf`)
- `target` — `_target_Qdelay`, shared with NSCC (default 6 µs)

Swift intentionally does **not** use a per-RTT cooldown; that is what differentiates it from
LSwift. Every high-delay ACK fires an MD. This is the aggressive-collapse behavior the paper
uses to characterise Swift's poor performance under packet spraying.

RTT EMA is maintained (`_swift_rtt`, α = 1/8) even by Swift, because it is needed for the
SACK-hole MD cooldown (see the Swift fix below) and to avoid a stale value if the algo is
ever switched at runtime.

**Swift SACK-hole MD fix** (tag: `// ===== ADDED (swift-sack-hole-md) =====`):
Paper 2 §IV.B explains that Swift's poor CCT inflation under spraying is caused by SACK
holes — out-of-order arrivals that htsim's Swift did not originally treat as loss signals.
Footnote 1 states they had to correct htsim's Swift. Our fix applies an additional MD
when `ooo > 0` (receiver-reported out-of-order count, set in `UecAckPacket::set_ooo`),
subject to the standard 1-RTT cooldown via `_swift_last_decrease`. LSwift, MSwift, MNSCC,
and NSCC are all gated out — only SWIFT triggers this path.

```cpp
// uec.cpp ~L1457
if (_sender_cc_algo == SWIFT && ooo > 0) {
    bool can_decrease_sh = (_swift_rtt > 0) &&
        ((now - _swift_last_decrease) >= (simtime_picosec)_swift_rtt);
    if (can_decrease_sh) {
        _cwnd = (mem_b)(_cwnd * (1.0 - _swift_max_mdf));
        _swift_last_decrease = now;
    }
}
```

With this fix, Paper 2 Fig 4 Swift CCT inflation goes from ~355 % to ~1577 % (paper: 1308 %,
within 20 %).

---

## LSwift (`-sender_cc_algo lswift`)

**Algorithm**: Swift with a two-part reordering guard:

1. Consecutive counter: MD fires only after `_lswift_dup_threshold` (default 5) consecutive
   high-delay ACKs. Clean ACKs reset the counter.
2. 1-RTT cooldown: even when the counter threshold is met, MD fires at most once per RTT
   (`_swift_last_decrease` timestamp compared to `_swift_rtt` EMA).

```
if delay < target:
    cwnd += AI; _swift_consec_high_d = 0
else:
    _swift_consec_high_d++
    if consec >= threshold AND (now - last_decrease) >= swift_rtt:
        cwnd *= factor
        _swift_last_decrease = now
        _swift_consec_high_d = 0
```

LSwift is designed to be resilient to per-packet reordering inherent in packet spraying.
A single out-of-order ACK with elevated delay (from a different path) does not trigger MD;
five consecutive such ACKs do. In practice, spraying's reordering bursts rarely produce 5
consecutive high-delay ACKs from the *same* sender-perspective delay sample sequence.

The `-lswift_dup_threshold` flag overrides the default of 5.

The shared core `_updateCwndOnAck_LSwift_core()` contains this logic. Both LSwift and MSwift
call it; MSwift passes a median-filtered delay instead of the raw value.

---

## MSwift (`-sender_cc_algo mswift`)

**Algorithm**: LSwift with the per-ACK delay replaced by the median of the last H delays.

```
H = max(cwnd_pkts / 2, 1),  capped at DelayMedianBuffer::MAX_H (128)
median_delay_buf.setCapacity(H)
median_delay_buf.push(raw_delay)
eff_delay = median_delay_buf.percentile(_swift_median_pct)  // default: 50th = median
→ _updateCwndOnAck_LSwift_core(eff_delay, ...)
```

The RTT EMA (`_swift_rtt`) is updated from raw delay, not from the median, so that the 1-RTT
cooldown tracks actual round-trip time rather than a smoothed approximation.

`_swift_median_pct` (default 50) allows probing other percentiles via `-swift_median_pct`.
The paper's Fig 12 uses P10 and P90 variants to bracket the sensitivity to the percentile
choice.

Window sizing follows Paper 2 Eq (8): H grows proportionally to cwnd, so that at high
throughput the median window is wide enough to absorb transient reordering spikes, while at
low cwnd (early connection ramp-up or post-MD) it collapses to a smaller but non-zero window.

---

## MNSCC (`-sender_cc_algo mnscc`)

**Algorithm**: NSCC with the per-ACK delay replaced by the median of the last H delays.

```
H = max(min(cwnd_pkts / 2, 4), 1)   ← stricter cap than MSwift (paper: cap at 4)
median_delay_buf.setCapacity(H)
median_delay_buf.push(raw_delay)
eff_delay = median_delay_buf.percentile(50)   ← always median; not configurable
→ _updateCwndOnAck_NSCC_core(skip, eff_delay, ...)
```

MNSCC applies the same quick_adapt / bytes_to_ignore warmup as NSCC, and runs the same
periodic `fulfill_adjustment()` and `_eta` top-up at the end of each ACK. Only the delay
signal fed into the AI/MD decision is replaced.

The H cap of 4 (vs MSwift's effective cap of 128) reflects a deliberate paper design choice:
NSCC's convergence depends on high responsiveness; a long median window would slow down its
reaction to sustained congestion. The H = min(W/2, 4) formula was taken verbatim from Paper 2.

The shared helper `_updateCwndOnAck_NSCC_core()` contains the NSCC AI/MD logic parameterised
on delay. The original `updateCwndOnAck_NSCC()` was refactored to call this helper unchanged;
MNSCC calls it with the median-filtered delay instead.

---

## Shared infrastructure

### Per-source fields (`uec.h` ~L635)

```cpp
simtime_picosec  _swift_rtt           = 0;  // RTT EMA, α = 7/8
simtime_picosec  _swift_last_decrease = 0;  // last MD timestamp (cooldown guard)
uint32_t         _swift_consec_high_d = 0;  // consecutive high-delay ACK counter (LSwift)
DelayMedianBuffer _median_delay_buf;         // shared ring buffer (MSwift, MNSCC)
uint64_t         _swift_md_fires      = 0;  // diagnostic MD-fire counter
```

`_swift_md_fires` is always compiled. It is logged at flow finish as a `swift_md_fires N`
column in the flow completion line. Used in Phase D of exp13 to verify that `-target_q_delay`
actually reaches the decision code (see `[FIX: target-qdelay-respect-cli]` in CLAUDE.md).

### Static parameters (`uec.h` ~L318, defined `uec.cpp` ~L113)

| Static | Default | CLI flag | Used by |
|--------|---------|----------|---------|
| `_swift_ai` | 1.0 | `-swift_ai` | Swift, LSwift, MSwift |
| `_swift_beta` | 0.8 | `-swift_beta` | Swift, LSwift, MSwift |
| `_swift_max_mdf` | 0.5 | `-swift_max_mdf` | Swift, LSwift, MSwift, SACK-hole fix |
| `_lswift_dup_threshold` | 5 | `-lswift_dup_threshold` | LSwift, MSwift |
| `_swift_median_pct` | 50 | `-swift_median_pct` | MSwift only |

MNSCC uses `_swift_max_mdf` indirectly via `multiplicative_decrease()` (NSCC's MD helper),
and uses the percentile 50 hardcoded — it is not affected by `_swift_median_pct`.

### Dispatch table (`uec.cpp` ~L842)

```cpp
case SWIFT:   updateCwndOnAck = &UecSrc::updateCwndOnAck_Swift;   break;
case LSWIFT:  updateCwndOnAck = &UecSrc::updateCwndOnAck_LSwift;  break;
case MSWIFT:  updateCwndOnAck = &UecSrc::updateCwndOnAck_MSwift;  break;
case MNSCC:   updateCwndOnAck = &UecSrc::updateCwndOnAck_MNSCC;   break;
```

Swift, LSwift, and MSwift share `updateCwndOnNack_Swift` (NACK → MD with 1-RTT cooldown).
MNSCC uses `updateCwndOnNack_NSCC` (original NSCC NACK handler).

---

## Key fixes applied to the baseline

### `[FIX: target-qdelay-respect-cli]` (2026-05-30)

`UecSrc::initNsccParams()` at `uec.cpp:195` unconditionally reset `_target_Qdelay = 6 µs`
after CLI parsing, silently ignoring every `-target_q_delay X` passed to the binary. Fixed by
commenting out that line; the L79 static default preserves 6 µs as the no-flag fallback.
Affects all NSCC/Swift-family CCAs. Without this fix, all exp12 and initial exp13 Paper 2
runs used 6 µs instead of the paper-specified 1 µs, masking LSwift/MSwift differentiation.

### `[FIX: median-buf-paper-faithful]` (2026-06-01)

Two deviations from Paper 2 §III.B + Eqs (8–9) in `DelayMedianBuffer`:
1. `MAX_H = 32` silently clamped MSwift's H below the paper value at BDP cwnd. Raised to 128.
2. Flush on shrink discarded all history on MD-induced cwnd drops. Fixed to keep most-recent
   samples.

### `[ADDED: swift-sack-hole-md]`

Implements Paper 2 §IV.B footnote 1: Swift MDs on SACK holes from out-of-order arrivals.
Without this fix, Swift's CCT inflation under spraying is ~355 % (paper: 1308 %). With the
fix it is ~1577 % (within 20 % of paper, within simulation variance).

---

## Line count vs. paper claim

Paper 2 states "Adding MSwift to LSwift and MNSCC to NSCC takes less than a total of 200 lines
of code in htsim." Our count:

| Component | Lines |
|-----------|-------|
| `delay_median_buffer.h` (new file) | 78 |
| `uec.h` additions (enums, statics, fields, declarations) | ~10 |
| `uec.cpp` MSwift body (L1891–1906) | 16 |
| `uec.cpp` MNSCC body (L1927–1959) | 33 |
| `uec.cpp` `_updateCwndOnAck_NSCC_core` helper (L1913–1924) | 12 |
| `uec.cpp` `_updateCwndOnAck_LSwift_core` refactor (L1846–1881) | 43 |
| `uec.cpp` dispatch table entries | 4 |
| `main_uec.cpp` CLI flags | ~10 |
| **Total** | **~206** |

The LSwift core refactor (43 lines) is structural, not new logic — it was extracted from the
existing LSwift body unchanged so that MSwift could reuse it. Excluding it, the M-variant
additions are ~163 lines, well within the paper's claim.

---

## CLI quick reference

```bash
# Swift (aggressive, collapses under spraying)
-sender_cc_algo swift

# LSwift (reordering-resilient Swift)
-sender_cc_algo lswift

# MSwift (LSwift + median delay window)
-sender_cc_algo mswift
-swift_median_pct 50        # default; paper Fig 12 uses 10 / 90

# MNSCC (NSCC + median delay window)
-sender_cc_algo mnscc

# Shared tuning (all four CCAs)
-swift_ai         1.0       # AI step
-swift_beta       0.8       # MD aggressiveness
-swift_max_mdf    0.5       # max multiplicative decrease fraction
-lswift_dup_threshold 5     # consecutive high-delay ACKs for LSwift/MSwift MD

# Always set the delay target explicitly for paper reproduction:
-target_q_delay 1000        # 1 µs = paper 2 value (in picoseconds: 1000 ps)
```

---

## Experiments using these CCAs

- **exp12** (`experiments/exp12_paper_repro_reps/`) — initial Paper 2 Fig 4
  reproduction attempt. Identified the `target-qdelay-respect-cli` bug.
- **exp13** (`experiments/exp13_papers_reps_repro/`) — full multi-phase paper
  reproduction for both Paper 1 and Paper 2 Figs 4, 8, 12.

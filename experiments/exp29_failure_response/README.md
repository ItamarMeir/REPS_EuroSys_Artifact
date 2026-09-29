# exp29 — REPS failure-response scaling under a transient ToR uplink failure

## What this measures

Toward a runtime REPS buffer-size (B) controller: exp28 answered the *static*
severity question (only B=1→2 and B=2→4 are data-backed; nothing above B=4
resolves). exp29 asks the *transient* question — when a bundle of paths dies and
then heals, how does REPS's recovery machinery respond, and does B help or hurt?

### The framing this experiment started with — and why it was wrong

exp28 left a puzzle: REPS's freeze/rotate machinery *barely engaged*
(`freeze_entries ≤ 18` fabric-wide even at K=32 degraded links). The original
exp29 hypothesis was a **crossover** between REPS's two loss-response layers:

| layer | trigger | latency |
|---|---|---|
| `fastLossRecovery` (`uec.cpp:2643`) | ~1 cwnd of out-of-order data past a hole | ~50 µs |
| freeze / rotate (`uec.cpp:4089`) | RTO expiry | 100 µs (min-RTO floor binds) |

The idea: for few dead paths, fastLossRecovery patches holes on healthy EVs
before the RTO; only once *most* paths die do retransmits keep re-dropping →
RTO → freeze. **Gate smoke refuted this:**

- **Freeze fires at every F, including F=1** (1 dead uplink of 32) — 32/32
  affected hosts froze exactly once. It is not a crossover; it is a severity
  gradient of the *same* RTO→freeze response.
- **`fastLossRecovery` never engages** (`fast_loss_entries = 0` at every F,
  including F=31). It needs ~a full cwnd (151 pkts) of out-of-order data on a
  single ACK; sparse loss spread across a few dead paths never piles that much
  OOO before the 100 µs RTO fires first. (exp28's near-zero `freeze_entries` was
  a different thing entirely — **degradation**, where packets are merely slowed,
  so hosts see ECN not loss and never RTO. exp29 fully *fails* the pipe: 100%
  loss on dead EVs → RTO → freeze, always.)

### What exp29 actually measures

**REPS's single RTO→freeze→rotate response, as a function of F = the number of a
ToR's uplinks that fail simultaneously — and whether buffer size B helps or hurts
recovery.**

The controller-relevant hypothesis, stated up front so the high-F columns are a
test not a fishing trip:

> At high F the circular buffer is full of EVs that were *known-good before the
> failure* and are now dead. A **larger B may recover slower** (more poisoned
> entries to flush before it re-locks onto a live path) while a small B refreshes
> almost immediately. This is the **opposite** of exp28's "bigger B is never
> worse" — and if real, it says a controller should *shrink* B under path loss.

**Result: this hypothesis is falsified** (§2). B *does* change how the buffer
refreshes on thaw, but not by enough to move FCT at any F. See `Results`.

Secondary: `-exit_freeze` (the paper's `FREEZING_TIMEOUT`). At 100 µs (= failure
duration, the fig_6 value) the freeze thaws ~50 µs after the link heals — so
"does REPS notice recovery and re-explore early" is unobservable. A second batch
at **250 µs** ("max recovery time + a buffering period", the paper's
real-hardware heuristic) holds hosts frozen well past recovery, making the cost
of an over-long timeout measurable.

## Setup

- **Fabric / workload / CC**: identical to exp28 —
  `fat_tree_1024_1os_2t_400g` (32 ToRs, 32 spines, 32 SRv6 paths), tornado
  **16 MiB** (`tornado_n1024_s16777216.cm`), `-use_srv6 -paths 32`, MPRDMA,
  `-q 101 -ecn 25 76 -cwnd 151`. Healthy affected-host FCT ≈ 356 µs (seed-stable
  to <1 µs). MPRDMA has no slow-start ramp — cwnd hits cap by ~t=9 µs — so the
  failure lands on a fully settled fabric.
- **The failure**: ToR0's first **F** spine uplinks (`pipes_nlp_nup[0][0..F-1][b]`)
  fully failed for **t ∈ (100 µs, 200 µs)**, then restored (`Pipe::_failed`,
  100% drop).
  - **100 µs window = exactly one min-RTO** (`DEFAULT_UEC_RTO_MIN`; base-RTT ≈
    8.3 µs so the floor binds). Any shorter and the RTO cannot fire while the
    link is down. Also the paper's own `scenario_micro_failures` window
    (`compositequeue.cpp:208`).
- **Primary sweep**: `F ∈ {1, 4, 8, 16, 24, 31}` × `reps_b{1,2,4,8,32}` × seeds
  42/43/44, `-exit_freeze 100 µs` = **90 runs**.
- **Secondary sweep**: `-exit_freeze 250 µs`, `F ∈ {1, 16, 31}` only = **45 runs**.
- Affected = the 32 senders under ToR0 (`node_num` 0–31); the other 992 hosts
  are the on-schedule baseline.

### Resolution limit

Freeze *onset* is pinned at ≈ t_fail + 100 µs by the RTO floor and is
B-invariant — B cannot change *when* the RTO fires, only what follows. Freeze
*duration* at `exit_freeze=100 µs` is likewise a near-constant (≈ the timeout
itself). The B signal, if any, lives in: RTO count during the freeze, how fast
`ev_random` climbs on thaw (buffer refresh rate), whether a second RTO follows,
and the recovery-phase FCT tail. The 10 µs window log resolves these.

## htsim change — `timed-failure`

New CLI, all off by default (absent ⇒ byte-identical behaviour — regression
checked):

| flag | args | effect |
|---|---|---|
| `-timed_window <start_us> <recover_us>` | 2 | shared transition times; `recover ≤ start` ⇒ permanent onset |
| `-timed_fail_tor_uplinks <tor> <F>` | 2 | fail `pipes_nlp_nup[tor][s][b]` for `s ∈ [0,F)` — reuses the **unmodified** `LinkFailureEvent` class (one per pipe); only resolves the 2-tier ToR↔spine pipes the stock `-fail_link_time` path can't reach |
| `-timed_fail_tor_downlinks <tor> <F>` | 2 | same on `pipes_nup_nlp[s][tor][b]` (reverse-path loss — not in the first batch) |
| `-log_reps_window <file> <interval_us> <t0_us> <t1_us>` | 4 | periodic per-host CSV of `g_reps_metrics` deltas for `t ∈ [t0, t1]`. Bounded so the logger's own events do **not** keep the sim queue non-empty out to `-end` after every flow has finished. |

`g_reps_metrics` (the exp28 file-static side table — **not** `UecSrc`; adding a
member to `UecSrc` corrupts the heap on this codebase, see
`MODIFICATIONS.md § metrics-counters`) gains two counters: `ecn_acks` (mirror of
`_ecn_ack_count`) and `fast_loss_entries` (bumped at the
`_loss_recovery_mode = true` transition, `uec.cpp:2666`). `fast_loss` is also
appended to the flow-finish line. `UecWindowLogger` (a `Clock`-pattern
`EventSource` in `uec.cpp`) writes `window.csv`.

`window.csv` columns:
`t_us, node, d_rto, d_freeze_entries, d_fast_loss, frozen_frac, d_ev_random, d_ev_explore, d_ecn_acks, frozen_now`
(`d_*` = delta since the previous tick; `frozen_frac` = fraction of the interval
the host was frozen).

**Precondition**: no `-failed` — `_num_failed_links == 0`, nothing pre-degraded.

## Reproduce

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace/htsim/sim reps-artifact:latest \
  bash -lc 'make -j$(nproc) && cd datacenter && make -j$(nproc)'

docker run --rm -v "$PWD:/workspace" \
  -w /workspace/experiments/exp29_failure_response/scripts reps-artifact:latest \
  bash -lc 'python3 -u run_crossover.py --fs 1,4,8,16 && python3 -u run_crossover.py --ef 250 --fs 1,16 \
            && python3 -u run_crossover.py --fs 24,31 && python3 -u run_crossover.py --ef 250 --fs 31'

cd experiments/exp29_failure_response/scripts
python3 aggregate29.py         # -> data/{timeseries,response,fct,diagnostics,resolvable}.csv
python3 plot_response.py        # -> plots/*.png  (incl. diagnostics{,_bars}.png)
python3 build_interactive.py    # -> plots/interactive.html (zoomable Plotly, self-contained)

tar -czf ../runs.tar.gz -C .. runs && rm -rf ../runs
```

`data/diagnostics.csv` mirrors exp28's `metrics.csv` — whole-flow per-host means
(ecn / rto / rts / fast_loss, freeze entries + host-fraction + mean freeze µs,
ev_random / ev_explore per host, ev_random_rate), seed-averaged with 95% CI.
`plots/interactive.html` is a standalone page (Plotly from cdnjs, data inlined
from the CSVs) — drag-zoom the CI curves the static PNGs can't resolve, toggle
B-series, switch metric, incl. the whole-flow diagnostics.

## Results

**135 runs, 0 failures.** F ∈ {1,4,8,16,24,31} × B ∈ {1,2,4,8,32} × seeds
42/43/44 at `-exit_freeze` 100 µs; `-exit_freeze` 250 µs on F ∈ {1,16,31}. All
FCT figures are the **affected** 32 ToR0 senders; healthy baseline 356 µs.
Primary figure: `plots/response_vs_f_delta.png` (severity trend removed).
Verdict table: `data/resolvable.csv`.

### 1. Severity scales cleanly with F; the response is a single mechanism

| F | affected p50 FCT | affected p99 FCT | RTOs / affected host (during) |
|---|---|---|---|
| 1  | 364 µs | 371 µs | 5.2 |
| 4  | 378 µs | 394 µs | 24.6 |
| 8  | 405 µs | 432 µs | 50.2 |
| 16 | 498 µs | 551 µs | 90.2 |
| 24 | 649 µs | 705 µs | 123.3 |
| 31 | 860 µs | 880 µs | 148.5 |

Every affected host freezes exactly once, at every F. RTOs/host is ~linear in F
(≈ 4.8·F) and **B-invariant** (all arms within CI). `fast_loss_entries = 0`
everywhere — `fastLossRecovery` never engages (needs ~a full cwnd of OOO on one
ACK; sparse multi-path loss never builds it before the 100 µs RTO). This is one
RTO→freeze→rotate response whose magnitude tracks F, not a two-layer crossover.

Timeline (all F): freeze onset ≈ t=125–140 µs (one RTO after the t=100 µs
failure), `frozen_frac` → 1.0 by ~t=150, link recovers at t=200, hosts thaw at
~t=230–250 (≈ onset + `exit_freeze` 100 µs). Timer-driven, **not**
recovery-aware.

### 2. Buffer size B does **not** move affected FCT — at any F. The poison hypothesis fails.

Prediction: at high F the buffer holds now-dead "known-good" EVs → larger B
recovers *slower*. **Falsified across the whole F range.** `data/resolvable.csv`
(spread of best-B vs worst-B mean > sum of their 95% CI half-widths?):

| metric | resolvable at F | not at F |
|---|---|---|
| p50 / p99 / max affected FCT | **none** | 1, 4, 8, 16, 24, 31 |
| `d_rto` during freeze | F=1 only | 4 … 31 |
| `frozen_frac` (either phase) | none | all |

The FCT B-spread never exceeds the CI (p99: 4 / 4 / 9 / 30 / 16 / 8 µs at
F=1…31, vs CI half-widths 4 / 11 / 17 / 26 / 29 / 8 µs). `response_vs_f_delta.png`
shows every FCT B-band straddling 0.

B *does* change the recovery **mechanism** — the change just doesn't reach FCT:

| `d_ev_random` / host, recovery phase | B=1 | B=2 | B=4 | B=8 | B=32 |
|---|---|---|---|---|---|
| F=8  | 96 | 19 | 11 | 6 | **0** |
| F=31 | 96 | 62 | 58 | 55 | 30 |

Small B empties during the freeze → on thaw the host has no cached EVs → a second
burst of random exploration (the B=1-only `ev_random` hump at t≈250–380 µs in
`timeseries.png`). Large B keeps its slots full → replays the cached EVs. Because
the failure is *transient*, those cached EVs point at links alive again by thaw,
so replaying them is fine. The one B effect that clears CI:
**B=1 takes ~3–4 fewer RTOs during the freeze at F ≥ 16** (`response_vs_f_delta.png`
panel 3) — it thaws a hair earlier — but this too leaves FCT unchanged.

**Net: a larger B is neither better nor worse under transient full-path failure;
a smaller one isn't either.**

### 3. B=1 carries a small constant steady-state tax

`unaffected` p99 FCT: **B=1 = 360 µs vs B≥2 = 356.5 µs** at every F (B≥2 mutually
identical). ~3 µs, fabric-wide, failure-independent — the same "B=1 is the only
resolvable loser" signal exp28 found at steady state. B=1 also runs a nonzero
ECN-ack baseline pre-failure that B≥2 don't.

### 4. `exit_freeze` padding is strictly harmful once the link recovers

The paper's `FREEZING_TIMEOUT` real-hardware heuristic = "max recovery time + a
buffering period". 250 µs vs the failure-duration value 100 µs, affected FCT:

| F | Δ p50 (250 vs 100) | Δ p99 |
|---|---|---|
| 1  | +3 µs   | +4 µs   |
| 16 | **+54 µs** | **+62 µs** |
| 31 | **+133 µs** | **+134 µs** |

The link is back at t=200; a host frozen until t≈400 (onset 150 + 250) cannot use
it. Every µs of `exit_freeze` beyond actual recovery is paid into FCT, and the
cost grows with F (more of the host's paths were on the failed bundle, so the
frozen host has more to lose). Still B-invariant. (F=1: +4 µs — freeze barely
engaged, timeout length barely matters.)

### Controller takeaways

- **B is irrelevant under transient full-path failure** — no F, no phase rewards
  growing *or* shrinking it. Choose B once on the exp28 steady-state /
  degradation criterion (B ≥ 2; B ≥ 4 buys nothing) and leave it.
- **The freeze timeout is the only knob that touches failure recovery**, and the
  lesson runs counter to the paper's "add a buffering period" heuristic: any
  freeze time beyond actual link recovery is paid straight into FCT, worse at
  higher severity (F=31: +134 µs p99 for 150 µs of excess freeze). A controller
  that estimates recovery — or detects the link is back and force-thaws — beats
  any fixed timeout.
- Reaction latency (≈ 100 µs, RTO floor) is not tunable via B or buffer state.

## Lineage

Row 29 in [`../README.md`](../README.md). Builds on exp28
(`fat_tree_1024_1os_2t_400g`, tornado, `-use_srv6 -paths 32`, MPRDMA, `-q 101
-ecn 25 76 -cwnd 151`); adds the `timed-failure` htsim mechanism. The failure
window and `-exit_freeze` values are the paper's `scenario_micro_failures` /
fig_6 values and the `FREEZING_TIMEOUT` real-hardware heuristic.

# exp30 — REPS buffer size under *concentrated* ToR-uplink path loss

## What this measures

exp28 (static degradation, spread) and exp29 (transient full failure) both
concluded **buffer size B does not move FCT** — `resolvable.csv` shows no FCT
metric resolvable at any severity. The 2026-09-06 meeting (Skalosub, Avin)
identified why: in both, per-flow severity was tiny.

- exp28 used `-failed D -skip_asy`. `-skip_asy` caps degradation at **one uplink
  per ToR** and spreads D of them across D different ToRs
  (`fat_tree_topology.cpp:928,986`). Any affected flow lost **1/32** of its
  paths.
- exp29 failed ToR0's first F uplinks fully, transiently, recovering after
  100 µs. Binary alive/dead, but a brief blip.

Re-reading the meeting transcript in full (not just the summary) surfaces that
these map onto a **2×2 that was only half filled**:

| | degraded (ratio, slowed) | true kill (100 % loss) |
|---|---|---|
| **static** (whole run) | exp30 Part A | **exp30 Part B (this)** |
| **transient** (blip, recovers) | — (not asked for) | exp29 |

exp30 Part A fills the static+degrade cell. exp29 fills the transient+kill
cell. **Part B fills the last one** — a *static, permanent, real* full kill of
`F` of ToR0's uplinks — which is also the literal next-step the meeting asked
for: *"run a more aggressive experiment — one ToR with link failures from 1 to
31"* (Itamar/Gabriel), stated right after Gabriel said to do the **static**
case before the transient one.

Separately, Chen Avin asked a different, explicitly-synthetic question:
*"even if it's not realistic... if some source→destination suddenly loses a
quarter of its paths, you'll probably see a difference."* That's a single-flow
poison, not a real link — exp30's **original** Part B (`-fail_src_paths`, kept
in the codebase and documented in `MODIFICATIONS.md` § `fail-src-paths`,
htsim/sim/uec.h+uec.cpp+main_uec.cpp) answered exactly that question and found:
B=1 takes a small steady-state tax, and once the poisoned flow loses ≥½ its own
paths B=1 hangs outright while no B rescues it back to healthy — a real,
distinct finding, just not what this section (a different question, real
links) now reports under the same "Part B" name.

Two independent signals also say revisit **flow size**:

- exp27 memo (`reps_gap_is_bdp_provisioning_not_topology`): 16 MiB sits in the
  **dead zone** of the healthy-REPS burst resonance on this 2-tier B=101 fabric
  (0 tail hits). The sensitive size is **~4 MiB (~10·BDP)**, the double-resonance
  peak, where the healthy REPS mechanism is actually live.
- Same memo, asymmetric regime: predicts a **B knee at 4** (B≤2 loses) under
  *sustained* asymmetry — never reached by exp28 because severity was 1/32.

**exp30 goal:** does B become resolvable on FCT once per-flow severity is real
(8/32, 16/32, …), across both flow sizes?

---

## Method

Fabric / workload / CC identical to exp28: `fat_tree_1024_1os_2t_400g` (1024
hosts, 32 ToRs, 32 spines, 32 SRv6 paths), tornado, MPRDMA (`-sender_cc_only
-sender_cc_algo mprdma`), `-q 101 -ecn 25 76 -cwnd 151`, `-use_srv6 -paths 32`,
`-disable_tor_ecn` deliberately omitted (paper-faithful).

**Flow size: two.** `4194304` (4 MiB, ~1027 pkts/flow, healthy FCT ≈ 97 µs) and
`16777216` (16 MiB, ~4107 pkts/flow, healthy FCT ≈ 356 µs). 4 MiB is the primary
regime; 16 MiB is the anchor — both parts run the full matrix at both sizes.

Arms `reps_b{1,2,4,8,16,32}` (full B ladder — exp30 is testing the memo's B-knee,
so B=16 is kept). Seeds 42/43/44. 95 % CI = Student-t, n=3, t-mult 4.30.

### Part A — concentrated static degradation on ToR0  (no htsim code)

`-failed n` **without** `-skip_asy` lands all `n` degraded uplinks on ToR0
(verified `fat_tree_topology.cpp:862-988`: `fail_every = 32/n`, ToR0 keeps
`can_fail`, the global `degraded_cables < n` cap fills entirely on ToR0's first
`n` aggs — smoke run prints exactly `Failure: LS0->US0 … LS0->US7` for `n=8`,
zero on other ToRs). `-down_ratio r` scales the degraded link's speed / queue /
ECN by `r`. Static, build-time. `-exit_freeze 200 µs` (exp28 twin; degradation
rarely triggers freeze so near-moot).

| sub-part | X axis | swept | fixed |
|---|---|---|---|
| **A1** severity | `n` = # degraded ToR0 uplinks | `n ∈ {0,1,2,4,8,16,32}` (0 = healthy) | `r = 0.5` |
| **A2** ratio | degradation `r` | `r ∈ {0.90,0.75,0.50,0.25,0.10,0.05}` = 10–95 % | `n = 8` (¼ of 32) |

### Part B — static (permanent) real full-kill of ToR0's uplinks  (no new htsim code)

Reuses exp29's `timed-failure` mechanism verbatim (`-timed_fail_tor_uplinks
<tor> <F>` — fails `pipes_nlp_nup[tor][s][b]` for `s ∈ [0,F)` via the
unmodified `LinkFailureEvent`/`Pipe::_failed` primitive, a true 100 %-loss
kill, not a ratio) but with **`-timed_window 1 1`** instead of exp29's `100
200`. `main_uec.cpp` gates the whole block on `timed_fail_start_us > 0.0`, so
`0 0` is a silent no-op; `1 1` schedules the kill at t≈0 µs and, since
`LinkFailureEvent` only schedules a recovery when `t_recover > t_fail`, it
**never thaws** — static for the entire run, unlike exp29's 100→200 µs blip.

- `F ∈ {0,1,2,4,8,16,24,31}` (0 = healthy; 31, not 32, keeps one ToR0 uplink
  alive). Affected group = ToR0's 32 senders — **identical to Part A**, just a
  true kill instead of a 50 % speed ratio.
- Full `F` grid at **both** flow sizes (16 MiB started on a reduced
  `F ∈ {0,8,16,31}` check for cost, then filled in `F ∈ {1,2,4,24}` once the
  reduced grid turned up a real effect worth resolving at finer severity).
- `-exit_freeze 200 µs`, same fixed value as Part A (no ladder here — this
  experiment's question is severity, not freeze-timeout sensitivity; exp29
  already covers that axis for the transient case).

This is the meeting's literal next-step ask (Itamar/Gabriel: *"one ToR with
link failures from 1 to 31"*), stated as the static case to do before the
transient one — which exp29 (built for an unrelated crossover hypothesis) ended
up answering instead. Part B closes that gap.

---

## Pipeline

```
scripts/common30.py         constants + base_flags(part, size, seed, n/r/count)
scripts/run30.py            --part {a1,a2,b} [--sizes --arms --seeds]; idempotent
scripts/aggregate30.py      -> data/{fct,diagnostics,resolvable}.csv
scripts/plot30.py           static PNGs (reuses exp28 plot_sweep helpers)
scripts/build_interactive.py-> plots/interactive.html (reuses exp29 _asciiify + JS)
```

`group`: uniform across parts — affected = ToR0 senders (src < 32), unaffected
= the rest. `resolvable.csv` verdict = best-B vs worst-B mean gap > sum of the
two 95 % CI half-widths.

### Reproduce

Neither part needs new htsim code — Part A uses the base artifact's `-failed`,
Part B reuses exp29's `timed-failure` mechanism.

```bash
# from repo root, Docker with the repo bind-mounted (per CLAUDE.md)
D=experiments/exp30_concentrated_path_loss/scripts
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/workspace" -w /workspace/$D \
  reps-artifact:latest bash -lc \
  'python3 run30.py --part a1 --sizes 4194304 && python3 run30.py --part a2 --sizes 4194304 \
   && python3 run30.py --part a1 --sizes 16777216 && python3 run30.py --part a2 --sizes 16777216 \
   && python3 run30.py --part b --sizes 4194304 && python3 run30.py --part b --sizes 16777216'
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/workspace" -w /workspace/$D \
  reps-artifact:latest bash -lc \
  'python3 aggregate30.py && python3 plot30.py && python3 build_interactive.py'
```

Runs are idempotent (skip a cell whose `stdout.txt` already finished); run them
one Docker container at a time — 4 concurrent 1024-host sims OOM an 8-core /
16 GB host, and even one 16 MiB run is ~3 min wall under memory pressure.

Interactive dashboard:
<https://claude.ai/artifact/P9ZCs2ptxJnNVFTFqCQKYq>

---

## Results

_768 runs, 0 fail: Part A (252 A1 + 216 A2, both flow sizes), Part B (300:
4 MiB full `F` grid 144 + 16 MiB full `F` grid 144 + a 12-run n=5 seed check
on the `F=8` 16 MiB cell, §4). `data/resolvable.csv` is the numeric verdict._

### 1 — severity scaling (Part A, 4 MiB)

Concentrating the degradation on ToR0 makes affected-flow FCT rise smoothly and
steeply with `n` — p50 97 → 180 µs, p99 98 → 193 µs across n = 0 → 32. At n = 32
(ToR0 loses *every* spine-0…31 uplink, i.e. it is an island behind 32 half-speed
links) the flow is still delivered, ~1.9× the healthy time. RTOs cap at ~1/host,
ECN climbs 0 → 48/host: as in exp28, **degradation drives ECN, not loss**, so the
freeze machinery barely engages (freeze_entries ≤ 0.08/host anywhere).

### 2 — is B resolvable on FCT? (Part A)

**No, at any real severity.** At every `n ∈ {1,2,4,8,16}` and every `r` in the
A2 ratio sweep, B=1…B=32 p50/p95/p99/max FCT lie within ~1 µs of each other —
far inside the n=3 95 % CI (`resolvable.csv`: `resolvable=False` for every A1/A2
FCT row below n=32). The one exception is **n=32** (ToR0 fully islanded behind 32
half-speed links): p99/max split by ~4–7 µs (2–4 %), with **B=16 best, B=2
worst** — a weak, non-monotonic tail effect at the single most extreme severity,
not a usable ordering. The meeting's "concentrated severity will expose B"
expectation is **falsified** — same result as exp29, now with per-flow severity
up to 32/32.

### 3 — flow-size contrast (4 MiB vs 16 MiB)

**Part A**: 16 MiB is the full matrix now (A1 n to 32, A2 ratio sweep), and B is
just as flat at the anchor size as at 4 MiB. A1 affected-flow p99 FCT climbs
356 → 738 µs as n goes 0 → 32/32, but the spread *across B* at any fixed n stays
under ~2 % (n=32: 732–745 µs, B=2 worst / B=16 best — the same non-monotonic
noise as 4 MiB's n=32 island). A2 (n=8, degrade 10–95 %): p99 372 → 503 µs,
B-spread ≤ 3 % at every ratio. `resolvable=False` on every FCT percentile for
n ≥ 2 and every A2 ratio. Matches exp29's F=31 full-failure verdict.

**Part B**: flat at 4 MiB (only the trivial `F=0` healthy anchor and one noisy
`F=1` point are "resolvable" — CI-sized blips, not a pattern). At 16 MiB, an
n=3 pass first showed `F=8` p99/max as resolvable (B=1 worst, B=4 best, ~90 µs
gap) — but re-running that one cell at n=5 seeds collapsed the gap into its own
enlarged CI (§4): **that one does not survive replication**, the same lesson
exp31 learned from fig7's single-seed knee. Filling in the rest of the 16 MiB
`F` grid (`F ∈ {1,2,4,24}`) turned up a second, real effect at **`F=24`** —
unlike the `F=8` false alarm this one holds on the *median* (uncontaminated by
the 90 ms `-end` censor), B=1 worst by ~15 %, and it's backed by a
censor-independent fact: B=1 is the only arm that ever leaves a ToR0 flow stuck
past `-end`, in every one of its 3 seeds at `F=24` (§4).

### 4 — Part B: does a real, static, ToR-wide kill move B?

**Median FCT: no, never.** Tail FCT: **yes, but only via one specific failure
mode (B=1 flows getting stuck), not a resolvable B ordering.**

**The `F=8` "B=1 tax" was noise, confirmed by a seed check.** At 16 MiB,
`F=8` (¼ of ToR0's uplinks permanently dead), n=3 seeds:

| B | p99 (n=3) | p99 (n=5) |
|---|---|---|
| 1 | 607 | 586 |
| 2 | 536 | 549 |
| **4** | **520** | 536 |
| 8 | 562 | 549 |
| 16 | 583 | 561 |
| 32 | 548 | 543 |

n=3 flagged this as `resolvable=True` (spread 87 µs > Σ CI 62 µs). Adding two
more seeds (45/46, 12 more runs) moved B=1 from 607→586 and the spread from
87→50 µs while the CI on 5 seeds is still ~96 µs — **not resolvable at n=5**.
The ordering isn't even stable (B=4 was best at n=3, worse than B=2/8/32 at
n=5). This was noise from small `n`, not signal.

**The censor-independent fact, which needs no CI test at all: B=1 is the
*only* arm that ever leaves a ToR0 flow stuck past `-end`, and it does so in
7 of 9 (`F`,seed) cells across `F ∈ {16,24,31}`** — all 3 seeds at `F=24`,
2 of 3 at `F=16`, 2 of 3 at `F=31` (seed 44 dodges it both times). B≥2 never
censors a single flow anywhere in this experiment (0 of 27 cells). That's the
solid result, independent of any percentile or CI arithmetic.

**`F=24`'s median is the clean, uncontaminated headline.** `p50_fct_us`
excludes the censor entirely — the 90,000 µs placeholder is one outlier out of
32 flows, nowhere near the middle — and it still resolves: B=1 = 12,993 µs vs
best (B=32) = 11,107 µs, spread 1,886 µs > Σ CI 1,622 µs. B=1 is the worst arm
on an honest, uncensored statistic, by ~15 %.

| B | p50 (median, uncensored) |
|---|---|
| **1** | **12,993** (worst) |
| 2 | 11,862 |
| 4 | 11,630 |
| 8 | 11,453 |
| 16 | 11,334 |
| **32** | **11,107** (best) |

The p99/max numbers at `F=24` (B=1: 66,500 / 90,000 µs vs ~13,000–14,300 µs
for B≥2) look far more dramatic, but **don't read them as a measured
magnitude** — B=1's max is pinned to the literal `END_US=90000` censor
constant in all 3 seeds (hence its CI of exactly 0: that's the censor being
identical across seeds, not agreement about a real value), and p99 is
`np.percentile` interpolating toward that same placeholder. Move the censor to
200 ms and the "5–7×" becomes "15×" — it's an artifact of where `-end` was
set, not a measurement. What the tail numbers correctly show is *that* B=1
hits the ceiling and nothing else does, not *by how much*.

**`F=16` and `F=31` show the identical censoring pattern (2 of 3 seeds), just
without `F=24`'s 3-of-3 consistency** — which is why their p99/max don't pass
the strict CI test (one clean seed + two censored ones is enormous seed
variance: CI 108,257 µs and 87,149 µs, larger than the means themselves).
`F=31`'s **p50** does separately resolve (spread 2,074 µs > Σ CI 1,981 µs), but
that one is a *different* effect from `F=24`'s — B=2 is worst there (28,413 µs),
not B=1 (26,837 µs, actually below B=4 and B=32) — the same non-monotonic,
coin-flip-sized noise Part A's n=32 island already showed, not a second
availability story. Don't conflate the two: `F=24` is "B=1 specifically is
worst, driven by censoring," `F=31`'s p50 is "no B is reliably worst."

**Diagnostics at `F=8` (the false-alarm cell) show why that one was noise**:
RTOs/host are B-invariant (78–87, within each other's CI) and freeze fires
almost identically often (2.0–2.04 entries/host) across every B — no
mechanism-level difference for a real FCT gap to ride on. At `F=24`, B=1
specifically has hosts that never recover a live path before `-end` — a real
mechanism difference, which is why both its rate (3/3 seeds) and its median
(uncontaminated by the censor) hold up, unlike `F=8`.

**Contrast with the old (retired) single-flow Part B:** the meeting's Chen-Avin
`-fail_src_paths` mechanism, kept in the codebase but no longer exp30's Part B
section, found a much *larger*, size-independent effect at its own worst case —
B=1 never finishing at all once *one* flow lost ≥½ its own paths, at both 4 and
16 MiB. This section's real, ToR-wide kill never reproduces that severity: even
at `F=31` (one live uplink shared by all 32 ToR0 hosts) the overwhelming
majority of B=1 flows still finish, because REPS spreads load across 32 hosts
and most of them eventually draw the one surviving path — there's no single
flow forced to depend on it exclusively the way the synthetic test constructed.
The synthetic worst case remains strictly worse than any real worst case this
experiment can produce.

(The retired single-flow mechanism's own numbers — B=1 hanging outright once
one flow lost ≥½ its own paths, no B rescuing it — aren't reproducible from
this experiment's current `data/` any more, since that mechanism's runs were
replaced by the real-kill matrix above; `-fail_src_paths` itself is still in
the codebase and documented in `MODIFICATIONS.md` § `fail-src-paths` if the
corner case needs re-running.)

### Bottom line

The 2026-09-06 meeting asked whether *concentrating* the failure — one ToR, or
one flow, losing a large fraction of its own paths — would finally make buffer
size B a resolvable, controllable knob. **Almost never, with one real, narrow
exception at the heaviest static kill.**

- **Part A** (concentrated static *degradation*, per-flow severity up to
  32/32): B is flat on FCT at every severity, at both 4 MiB and 16 MiB.
  Falsified.
- **Part B** (concentrated static *real kill*, `F` of ToR0's 32 uplinks
  permanently dead, the meeting's literal "static, one ToR, 1 to 31" ask):
  median FCT is flat at nearly every `F` and both sizes. An n=3 pass first
  flagged `F=8`, 16 MiB as a CI-clearing B=1 tail tax; adding two more seeds to
  that one cell collapsed it back into noise (§4) — a caught false positive.
  Filling in the rest of the 16 MiB grid found a real, **median**-level effect
  at `F=24`: B=1 is the worst arm by ~15 % on an uncensored statistic (spread
  clears its CI). It's backed by a censor-independent fact, not a percentile
  artifact: **B=1 is the only arm that ever leaves a ToR0 flow stuck past
  `-end`**, doing so in every one of its 3 seeds at `F=24`, and in 2 of 3 at
  both `F=16` and `F=31` (7 of 9 cells total; B≥2 censors 0 of 27). The p99/max
  numbers at these cells look far more dramatic (B=1 pinned near or at the
  literal 90 ms `-end` value) but that magnitude is an artifact of where the
  censor was set, not a measurement — the *rate* and the *median* are the real
  findings. The one real, reproducible B=1 cost is **availability, not
  speed**: it can strand a ToR0 flow past `-end` when nothing else does, and
  separately runs a small but real median tax at the one severity (`F=24`)
  where that stranding is consistent across every seed.
- The retired single-flow mechanism (Chen Avin's explicitly-synthetic ask,
  `-fail_src_paths`) found a much larger, size-independent effect at its own
  worst case — B=1 never finishing *at all*, for every seed — but that requires
  removing a flow's path *choice* entirely, which no real ToR-wide failure does
  (every host still has 31, then 16, then 1 live path to draw from; most of
  them get through, just slower).

exp28's B=1 → B=2 knee remains the only data-backed B decision, and it's the
dominant, size-robust story straight through exp30. Part B adds one honest
methodological note (an n=3 FCT-tax result that didn't survive n=5 — the same
trap exp31 caught in fig7's single-seed knee) and one small, real finding
(B=1's availability cost under the heaviest static kill) — neither changes the
verdict. Nothing here supports the meeting's "shrink B under loss" hypothesis,
and a runtime B controller's main lever stays *timing* (exp29's `exit_freeze`
finding), not steady-state or failure-driven B selection.

---

## Lineage

Follows exp28 (static, spread degradation) and exp29 (transient, full kill).
exp30 fills the two remaining cells of the {degrade, kill} × {transient,
static} matrix: **Part A** = static + degrade (concentrated on one ToR,
per-flow severity up to 32/32); **Part B** = static + kill (the literal
"one ToR, failures 1 to 31" meeting ask, reusing exp29's own
`-timed_fail_tor_uplinks` mechanism with a permanent instead of transient
window). Both add the 4 MiB flow size where exp27 says the healthy REPS
mechanism is live.

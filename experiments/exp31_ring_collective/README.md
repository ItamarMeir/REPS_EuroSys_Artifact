# exp31 — REPS buffer size vs ring all-reduce collective completion time (CCT)

## What this measures

exp26–30 all measured **FCT of independent tornado flows** — where a slow path
only slows its own flow and the fabric routes around it — and concluded buffer
size **B never resolves on FCT**. The 2026-09-06 meeting (Skalosub, Avin) named
the regime that framing misses: a **serially-dependent collective**. In a ring
all-reduce, hop *k+1* starts only when hop *k* finishes, so one slow link stalls
the whole ring on every one of its 2(N−1) cyclic steps, and **CCT** (not median
FCT) is where a bad path / an undersized buffer should finally bite.

exp26's `run_fig7.py` `ai` workload **is** a ring all-reduce
(`gen_allreduce 32 16 16` — a 16-rank ring, 4 MB/hop, 496 flows chained via
`send_done_trigger`). Its **single-seed** data hinted that B matters here:

| exp26 fig7 `ai`, seed 42 | b1 CCT | b2 | b4 |
|---|---|---|---|
| `fail_one_cable` | 1324 µs | **846** | 857 |
| `fail_one_switch` | 993 | **716** | 853 |
| `5_percent_failed_cables` | 1001 | **894** | 1269 |

A consistent **B=1 → B=2 knee** and b4 sometimes worse than b2 — the first sign
of a B effect exp28–30 never saw. **exp31 re-runs it with 3 seeds** (fig7 was
seed 42 only), a healthy baseline (fig7 has none), and degradation scenarios.

## Method

exp26 `run_fig7.py` `ai` recipe, held exactly: topo
`fat_tree_32_1os_2t_400g` (32 hosts, 4 paths → `-use_srv6 -paths 4`), MPRDMA,
`-q 101 -ecn 25 76 -cwnd 151 -other_location -disable_trim -connections_mapping`,
`-failures_input ../failures_input/<scenario>.txt` (omitted for healthy). Arms
**reps_b{1,2,4}** (no OPS — B-vs-B study). Seeds 42/43/44.

**Workload:** the committed `connection_matrices/allreduce.cm` fails to parse
with the current binary (`unknown id: oneshot at line 500` — a stale
encoding/version mismatch that `cat -A`/`od`/`diff` don't surface;
`all_red_ring_1mb.cm` with byte-identical structure parses fine). exp31
regenerates an equivalent (`common31.ensure_cm()` →
`gen_allreduce.py 32 16 16 4000000 0 42` → `exp31_ring_n32g16_4mb.cm`).
**Verified:** healthy CCT ≈ 91 µs; `fail_one_cable` seed-42 CCT
b1=1324 / b2=846 / b4=857 — **identical to exp26 fig7's `ai` numbers**, so exp31
reproduces fig7 exactly.

**12 scenarios** × 3 arms × 3 seeds = **108 runs** (~10 min). `degrade_one_switch`
dropped — htsim SIGFPE when the switch bitrate is driven to ~1000 bps and a
flow's pacing calc divides by it (crashed 2/9 cells); `degrade_one_cable` +
`10_percent_degraded_cables` cover the degradation regime.

**Metric:** CCT = max over the run's finished-flow `finished at`, censored at
`-end` (90 ms) when the ring never completes. `cct_pct_of_healthy` = failure as a
multiplier. Per-flow FCT series (flow-index order) = the cyclic-stall mechanism
evidence. `resolvable.csv` = best-B vs worst-B CCT gap vs Σ(95 % CI half-widths),
plus explicit b1−b2 (the knee) and b2−b4 columns.

## Results

### The fig7 knee does not survive replication

**B is not resolvable on ring CCT in any of the 12 scenarios**
(`resolvable.csv`: `resolvable=False` everywhere). The seed-to-seed CCT variance
*under failure* is enormous — CI half-widths of **200 µs to 10 ms** — and it
swamps every B effect. `fail_one_cable` per-seed:

| seed | b1 | b2 | b4 |
|---|---|---|---|
| 42 | 1324 | 846 | 857 |
| 43 | 932 | 652 | 542 |
| 44 | 805 | 835 | 343 |

The seed-42 "b1≫b2 knee" is one draw. Seed 44 has b1≈b2; b4 ranges 343→857 across
seeds. Mean b1=1020 ± 671, b4=581 ± 645 — **overlapping**. And the direction
flips between scenarios: `ber_cable_one_percent` has **b1 best, b4 worst**
(2396 vs 3863); `degrade_one_cable` has **b2 worst** by 2.3 ms. No consistent
"bigger B helps" or "bigger B hurts".

### Failure blows CCT up 5–40×, but not via a knob B controls

Healthy CCT ≈ 91 µs, flat across B, 0 RTOs. Under failure CCT jumps to
0.5–4 ms (5–45×), except two scenarios that stay at ~91 µs
(`fail_one_switch_one_cable`, `5_percent_failed_switches_and_cables`) — the
failure there never lands on a path the ring uses.

`steps.png` folds the per-flow FCT onto ring-hop position (the `.cm` is 16
serially-dependent chains of 31 hops; flowId order is chain-major). Under a
cable failure each chain shows the **same smooth mid-ring hump** — FCT climbs
from ~91 µs to a ~2.5× peak around hop 20, then drains back by hop 30. So the
mechanism *is* cyclic (congestion builds and clears once per ring pass), just
mild and smeared, not a sharp per-hop spike — on a 4-path fabric one dead cable
removes 25 % of the path set, so the slow hop is hit probabilistically, not
every cycle. B=1/2/4 traces sit on top of each other throughout.

**Two scenario files are the same experiment here.** `fail_one_cable` and
`fail_all_cables_except_one_path` produce byte-identical CCT for all 3 seeds and
all 3 arms (1020 / 778 / 581 µs). Both failure files carry
`Cable-Fail-Max-Percent: 1` (fail 1 % of cables), which on this 32-host / 4-path
fabric rounds to **exactly one cable** in both — the "all cables except one
path" name only bites on a much larger fabric. The verdict table's 12 rows are
effectively 11 distinct conditions.

### Bottom line

exp28–30: B doesn't move independent-flow FCT. **exp31: B doesn't move ring CCT
either** — the serial-dependency regime the meeting expected to expose B instead
shows CCT variance so high under failure that B is unmeasurable at n=3. The
exp26-fig7 single-seed knee was noise. A runtime B controller still has nothing
to act on; exp28's B=1→2 steady-state knee remains the only data-backed B
decision, and exp29's `exit_freeze` timing the only failure-response knob.

## Reproduce

```bash
D=experiments/exp31_ring_collective/scripts
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/workspace" -w /workspace/$D \
  reps-artifact:latest bash -lc \
  'python3 run31.py && python3 aggregate31.py && python3 plot31.py && python3 build_interactive.py'
```

Needs no htsim code change (`-failures_input` + `gen_allreduce.py` pre-exist).
Interactive dashboard:
<https://claude.ai/artifact/3NKvHXvtCt3zcxe7sYjZNp>

## Lineage

Follows exp28/29/30 (independent tornado flows, B never resolves). exp31 tests
the same question in a **serially-dependent ring all-reduce** — the regime the
meeting proposed — and reaches the same verdict, now for CCT.

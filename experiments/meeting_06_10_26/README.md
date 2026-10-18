# Meeting 2026-10-06: REPS buffer-size claims and experiments

Source meeting: 2026-10-06 (Itamar Meir, Gabriel Skalosub, Chen Avin). Transcript-based summary and plan: [`plans/meeting_summary_and_findings.md`](plans/meeting_summary_and_findings.md), [`plans/00_general_plan.md`](plans/00_general_plan.md), and [`../meetings/`](../meetings/).

The meeting asked one question: **does the size B of the REPS buffer (the circular buffer of recently good entropy values, EVs) matter, and when?** Earlier experiments (exp28 to exp31) found B hard to resolve on FCT. The meeting set two claims to test and a few sanity checks. This directory holds one folder per item; each has its own README with setup, results, caveats and the commands to reproduce.

## Vocabulary
- **B** - REPS buffer size (`-reps_buffer_size`). **Valid EV** - a buffer slot holding an EV that came back on a clean (not ECN-marked) ACK and has not been drawn yet. `fresh` in the event trace counts valid EVs.
- **k (send-time k)** - number of valid EVs in the buffer just before a SEND/RTX/RTS draw. A clean ACK adds one, a draw takes one, so k is a running sum of (clean ACKs per send slot - 1).
- **Draw sources** - *valid* (took a fresh EV), *random* (buffer empty, so a random or explore EV), *stale* (Freezing Mode replayed a slot that was already drawn).
- **Freezing Mode** - entered on a retransmission timeout (RTO): the sender stops sampling new EVs and replays the buffer until the `-exit_freeze` timer wipes it.
- **Healthy / degraded** - in these experiments, `x0` = no failures; `x32` = all 32 ToR0 uplinks at 50% speed (`-failed 32 -down_ratio 0.5`). **F** = number of ToR0 uplinks killed by a timed failure.
- **SoL (speed of light)** - the floor FCT from `path_static` (one dedicated path per flow) with a fixed, well-sized window (constant CC).

## The claims and the items

| Item | Question | Claim / expectation | Result | Where |
|---|---|---|---|---|
| [C1](C1/README.md) | How many valid EVs does the buffer hold outside Freezing Mode, with an always-backlogged sender? | Claim 1 (Gabriel): k sits at a small, stable value most of the time, so a big buffer is never filled and B above that value changes nothing. | Supported. Healthy: k is 2 to 3 for 87% of draws, max 5, identical for every B >= 8. Degraded: k is 1 (MPRDMA) or 0 to 1 (NSCC), max 3 (MPRDMA) / rare tail to 17 (NSCC). The stricter plan threshold "<= 2 valid EVs" fails when healthy (k = 3 for 30% of draws). Run for MPRDMA and NSCC (NSCC rerun at target delay 4.17 us). | `C1/` |
| [C1.1](C1.1/README.md) | Is k predictable from serialization time and ACK jitter? | Follow-up to C1: k should follow the packet spacing across link rates. | No: k distributions are nearly identical from 100G to 800G (k mostly 2 or 3). A collision-free `path_static` run still reconstructs to k = 3. The upward drift of real REPS k is unexplained. | `C1.1/` |
| [C2](C2/README.md) | Does a larger B drain more slowly in Freezing Mode? | Claim 2: more stale entries to flush, so slower recovery. | Not supported (null). Sends to last stale draw do not grow with B (about 1,200 for B <= 128). B = 256 is the only visibly worse cell (max FCT 537 vs about 510 us). One seed. | `C2/` |
| [C3](C3/README.md) | Does the C1 result hold for a bursty sender? | Chen: a pausing sender may let valid EVs accumulate, making B matter. | Partly. After a pause the buffer holds exactly `min(B, clean ACKs in the gap)` (up to about 120 valid EVs), but only the first B draws of a burst use them, and FCT is flat in B (within 0.4%). | `C3/` |
| [T1](T1/README.md) | Sanity: is FCT proportional to lost bandwidth? | FCT ratio = 64 / (64 - n) for n degraded uplinks. | Holds. REPS+NSCC p50 ratio at n = 32 is 1.93 (model 2.00). `path_static` degraded flows are 1.92x (4 MiB) / 1.98x (16 MiB) at every n. | `T1/` |

**What the set adds up to.** Under a backlogged sender the buffer stays shallow (k of 1 to 3) so B beyond about 4 to 8 is never used; in Freezing Mode there is no evidence that a bigger buffer slows recovery; a pausing sender fills a large buffer but gains nothing in FCT. This agrees with exp28 to exp31: the only data-backed B decisions remain B = 1 to 2 to 4. All results here are single-seed (T1 and C3 use three), so none carry confidence intervals.

## Shared setup
Unless an item says otherwise: fabric `fat_tree_1024_1os_2t_400g` (1024 hosts, 32 ToRs, 32 spines, 400G), tornado workload with 16 MiB flows, `-load_balancing_algo freezing -use_srv6 -paths 32`, `-q 101 -ecn 25 76 -cwnd 151`, packet trimming ON (the `exp30_packet_trimming_en` configuration), seed 42, metrics over the 32 ToR0 hosts only. The shared simulator flags come from `exp30_packet_trimming_en/scripts/common30.py` (`base_flags`). `-disable_tor_ecn` is not passed (inherited; C1.1 passes it). Every item logs the REPS event trace (`-log_reps_events`) and derives its metrics from it; traces are large and stay local (`traces/`, gitignored).

How the pieces connect: C1 is the baseline; C1.1 digs into why k has the value it has; C2 and C3 test the two situations where C1's assumption is dropped (Freezing Mode, bursty sender); T1 validates the degradation machinery all of them rely on; the speed-of-light reference built for C1 is reused as the floor in C2 and T1.

## Reproducing
Each item README ends with a `Reproduce` block. All commands run inside the `reps-artifact` container (paths under `/workspace`) with a freshly built `htsim_uec`. Interactive pages (`plots/interactive.html`) are not committed; regenerate them with each item's `build_*.py`, or see the thesis repo `REPS Buffer/` for the published ones. The event viewer used for buffer replays is [`../tools/`](../tools/).

## Known limitations (apply to all items)
- Single seed except T1 and C3; no confidence intervals for C1, C1.1, C2.
- The ToR-downlink ECN gap (`-disable_tor_ecn` missing with `-sender_cc_only`) in C1, C2, T1.
- C1's NSCC arm was rerun with `-target_q_delay 4.17` on 2026-10-18; the committed `exp30_packet_trimming_en/runs/` still holds the old 6 us stdout for those cells (see C1 README).
- NSCC leaves 55 to 80% of ACKs ECN-marked under degradation at these targets, which is why k is low there; whether a lower target restores healthy-like k is an open follow-up (listed in [`../README.md`](../README.md)).

## Existing evidence reused (not copied here)
- exp30 Part A, trim off: freeze under congested degradation. Baseline for C2 and T1.
- exp30 Part B, dead links: dead-path freeze and stuck-flow counts.
- exp30_packet_trimming_en: trim on, no RTOs under congestion; source of `base_flags`.
- exp28, exp29: static and transient failure background.
- `experiments/tools/reps_event_viewer.py`: runtime view of buffer content, used for all buffer-view pages.

## Open decisions
1. Shared research repo (text, references, figures; no code, no heavy data): hosting and collaborator handles. Not created.
2. SLRU / replacement policy was deferred until a speed-of-light oracle shows headroom.
3. NSCC x B, and the B = 32 vs B = 16 variance, were discussed but not assigned.

## Deleted
- `T2/` (Speed-of-Light oracle as a standing, scenario-dependent load-balancing algorithm) - deleted 2026-10-11. A generic `-load_balancing_algo oracle` was planned but never built: C1, C2 and T1 each got a minimal scenario-specific reference instead (C1: `path_static` + constant CC; C2: a bespoke timed-event ACK reroute; T1: plain `path_static`). Building the general mechanism before a second real use would have been premature.
- The original C3 ("B up to 256, scaling") - dropped because C2's own B ladder already runs 1 to 256. The bursty-sender question took the C3 slot (it was C4).

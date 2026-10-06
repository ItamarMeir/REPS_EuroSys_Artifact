# Plan: meeting 2026-10-06 experiments, metrics, and buffer-content tracing

## Context

The 2026-10-06 meeting (`experiments/meetings/2026-10-06_buffer_size_plan.md`) set two claims to test and a list of measurements. Earlier this session we found that freeze does fire with trim off under congested degradation (gated by `_last_rto_max_rtt < 1.65*base`, `htsim/sim/uec.cpp:5066`), and that trim-on freeze needs a dead path. This plan turns the meeting list into experiments.

The "buffer simulation of buffer content at runtime" already exists. Nothing new needs to be built for it:
- `-log_reps_events` (`htsim/sim/datacenter/main_uec.cpp:954`, writer in `uec.cpp` ~400-490) logs one row per SEND/RTX/RTS/ACK/NACK/FREEZE/UNFREEZE with a full slot snapshot (`slots` = `value:isValid:lifetime` per slot, `head`, `frozen_head`, `fresh`, `ev_src`). Schema in `experiments/tools/README.md`.
- `experiments/tools/reps_event_viewer.py` renders it as an interactive HTML with Play button, speed slider and step keys (`htm` controls at ~560-575). `test_reps_event_viewer.py` tests it.
- The same trace is what the "slow-motion ~500 packets" request asks for.

Two other grep hits, `exp29_*/scripts/build_interactive.py`, are plots of per-host counters, not buffer content. They are not the buffer replay.

## Facts established (verified in code)

- `isValid` is set on a clean ACK (`buffer_reps.cpp:35-39`) and cleared when the slot is popped (`:63-69`, `:100-104`, `:153`). So `fresh` (= `getNumberFreshEntropies()`) is exactly "valid EVs in buffer", the number Gabriel asked about. No snapshot parsing needed for that series.
- `ev_src` already splits every SEND/RTX/RTS draw: `explore | random | fresh_pop | frozen_pop | frozen_pop_valid | frozen_pop_stale | pxr_random | pxr_pop` (`uec.cpp:4010-4075`). `frozen_pop_valid/stale` appear only for `DUAL_MPRDMA_REPS(_CAP)`. For FREEZING, `frozen_pop` is unsplit, by design (byte-identical trace guarantee). Do not change `evSourceStr`.
- `-reps_buffer_size` accepts any integer (`main_uec.cpp:926`). Circular buffer has no hard cap. Caveat: `-use_srv6 -paths 32` gives 32 distinct EVs, so B>32 duplicates EVs.
- `_reps_events_max` defaults to 200000 rows (`uec.cpp:354`). Full runs will overflow; use `-log_reps_events_window` (ns) and `-log_reps_events_src`.

## Experiments

All runs: `-load_balancing_algo freezing`, `-use_srv6 -paths 32`, `fat_tree_1024_1os_2t_400g`, MPRDMA CC unless the row says otherwise. Same Y axis across B within a figure, same seed per cell (reproduction only). Metrics are ToR0 only: hosts are uniform, so max FCT is enough, plus a separate count of flows unfinished at `-end`. Trim is a column, not a default.

Rows come from the meeting's decided tasks (summary "tasks", "pending approval", "open questions"). Timestamps are the Zoom transcript [mm:ss].

| ID | Scenario | Trim | B ladder | CC | Checks (meeting item) | Metrics | Script |
|---|---|---|---|---|---|---|---|
| C1 | Healthy and degraded, always backlogged | off | 1,2,4,8,16,32 | MPRDMA | Claim 1: under backlog at most 1-2 valid EVs are in the buffer at any moment, so B>2 does not matter. Summary l.7; Gabriel 36:00-40:57; pending item l.36. Decided measurement: valid count sampled every ~1000 packets (distribution) plus a ~500-packet slow-motion view (task l.44-45). | valid-count distribution, slow-motion view from `-log_reps_events` | new `exp32_*/scripts/` |
| C2 | Partial degradation, trim off (exp30 a2, 90/95% slowdown, 4 MiB). Freeze firing here is already established by exp30 Part A run counts, so it is not re-tested; the runs are reused as the baseline. | off | 1,2,4,8,16,32 | MPRDMA | Claim 2: in Freezing Mode a larger B drains slower. Open question l.26; Gabriel 55:16-56:14, 90:05; pending item l.36. Also Gabriel's "force the system to rely only on its buffers and measure valid/stale/random" (72:18). Task "run without trim" (l.46). Per-packet split (task l.40). | per-packet split valid / stale-in-freezing / random (derived for FREEZING, see work item 2), drain metric: sends until stale fraction = 0 or UNFREEZE | same |
| C3 | Same scenario as C2, B scaled up | off | 64,128,256 | MPRDMA | Task l.41: scaling with large buffers. Gabriel 63:31: the B effect may only show at large B, in Freezing Mode. Part of the claim 2 test. | as C2 | same |
| C4 | Bursty sender (on/off), not always backlogged | off | 2,8 | MPRDMA | Pending item l.35 (does bursty traffic change the effect of B); open question l.30 (does claim 1 hold when send rate is not always above ACK rate); Chen 57:44, 64:22. | valid-count distribution | new generator in `experiments/workloads/` |
| T1 | All links healthy vs half links, bandwidth halved | off | 8 | MPRDMA | Sanity check, pending items l.33-34: FCT should be roughly proportional to lost bandwidth (~2x), up to CC effects. Chen 87:19. | FCT ratio with CI | same |
| T2 | Speed-of-Light oracle, per scenario (see below) | off and on | n/a | MPRDMA | Task l.42-43: an algorithm that knows the network state and sends only to live links. Use: headroom, noise reduction, normalization for C1-C4. Chen 38:52 gates SLRU on it (80:04). | FCT, FCT / oracle FCT | extend `path_rr` path selection with oracle rule |

Order: C1 (cheap, tests claim 1 directly), T2 (normalization for the rest), T1, C2, C3, C4.

Per-experiment plans live in each experiment folder (`../C1/PLAN.md` ... `../T2/PLAN.md`).

Decided, not experiments (apply to all rows):
- Same Y axis and same seed across B graphs, reproduction only (task l.47).
- ToR0 only; max FCT is enough because hosts are uniform (decision l.13; Gabriel 81:40). Keep the stuck-past-`-end` count.
- Formalize claims 1 and 2 (pending l.36). Analytic write-up attached to C1 and C2.
- Shared research repo: hosting and collaborator handles. Not created or invited.

Discussed, not decided (not in the table; revisit later):
- NSCC x B: only Itamar's hunch that buffer size does not change under NSCC (24:39). Not assigned.
- B=32 vs B=16 variance: observed, "unclear why" (52:21). Not assigned.
- Permanent vs temporary fail freeze counts (summary l.20): a finding, already in exp29/exp30 data.
- SLRU / LFU replacement policy (open question l.27; 74:38-79:42): explicitly deferred until T2 shows headroom.
- Itamar's "use stale instead of random outside Freezing Mode" (76:49): Gabriel said the cost is small and the question is not the research question.
- Dual window (summary l.22): done, no significant difference.

## Metrics

1. **Valid-EV count over time** = `fresh` column, filtered by `src_id`, sampled every ~1000 rows. Distribution, not only mean. Gabriel's claim 1 holds if the distribution is concentrated at 0-2 at backlog.
2. **Pop-source split per SEND/RTX/RTS**:
   - for DUAL: read `ev_src` directly.
   - for FREEZING: derive `valid` vs `stale` offline. For a frozen pop, read the slot at `frozen_head` in the previous row of the same `src_id`; valid if `isValid`, else stale. Validate by running one dual arm (native labels) and checking the derived label matches. Add this check to `test_reps_event_viewer.py`.
   - report 4 buckets: fresh, frozen-valid, frozen-stale, random+explore. Present as Gabriel's 3 (valid / stale / random) with explore separate.
3. **Drain metric (claim 2)**: after each FREEZE row, track stale fraction among occupied slots against sends since freeze, per B. Report sends until stale fraction = 0 or until UNFREEZE.
4. **FCT**: ToR0 max plus p50/p95/p99. Separate count of flows still unfinished at `-end` (B=1 strands flows, exp30 Part B). Max is censored at 90 ms; report the count alongside it.
5. **Normalization**: FCT / oracle FCT (T2), once T2 is available.

## Speed-of-Light oracle (T2): design depends on the scenario

The oracle knows the network state and sends with zero feedback delay. It is a LB-only baseline: same MPRDMA CC as the B arms. Its rule changes with the failure type:

- **Dead link (kill, exp30 Part B and `-timed_window`)**: never send on a path whose route crosses a `Pipe::_failed` pipe. Among live paths, round-robin. Fixed mask for static kill, switching at fail/recover for timed. Expect no RTO, so no freeze. This is the "send only to links that did not fail" rule from the meeting.
- **Degradation (C2, T1, half-speed links)**: nothing is dead, so excluding paths is wrong. Rule: weighted round-robin with weight = min link speed on the route (from `_downlink_speeds` / `_failed_link_ratio`, `fat_tree_topology.cpp:724`). Equal weights would give the B=1..32 arms nothing to beat under degradation, so this is the only meaningful oracle there.
- **Dead + degraded mixed**: combine: exclude dead, weight live by speed.
- Oracle also has no buffer, so it is a bound for backlog only. Note this for C4.

Implementation: new LB variant (or flag on `PATH_RR`) with its own ADDED banner and MODIFICATIONS row. Needs checking: that `Route` exposes its pipes so `_failed` and speed are readable per path (not yet verified; first work item). Also check that the same `_paths` index maps to the same physical links in SRv6 (`uec.cpp:4617`, `route_path_idx = ev % _paths.size()`).

## Work items

1. Confirm `buffer_reps.h` `getNumberFreshEntropies()` matches valid-count semantics in a small trace (one flow, 50 rows).
2. Write the derivation of valid/stale for FREEZING and add it to the viewer test.
3. Pick trace windows: around freeze (C2) and steady state (C1). Do not log the full run.
4. Confirm B=64..256 work in `slots` write path (comment near `uec.cpp:408` says exp23 went to 64), and that the viewer grid stays usable at 256.
5. Oracle (T2): verify `Route` exposes pipes; map SRv6 path index -> physical uplink for ToR0; implement dead-exclude and speed-weighted rules as above; check it matches the exp30 Part B failure schedule.
6. Bursty generator (C4): check `experiments/workloads/` and `.cm` start times first.

## Verification

- `python -m unittest experiments/tools/test_reps_event_viewer.py` passes, including the new derived-label check.
- Derived valid/stale labels match native `frozen_pop_valid/_stale` on one dual-window arm (100% match on pop rows).
- Valid-count series: check sum of ev_src buckets = total SEND+RTX+RTS rows for each run.
- Sanity (T1): FCT ratio between half-link and full-link runs within the CI expected from exp30 A1 (~1.9-2.1x).
- Each new experiment follows `experiments/RUNNING_EXPERIMENTS.md sec 11` checklist and gets a row in `experiments/README.md` lineage.
- New C++ (if any, e.g. a bypass of the 1.65x gate) gets an ADDED banner, a row in `MODIFICATIONS.md`, and an ARCHITECTURE note. Only if C2 results show the gated runs are too sparse.

## Open decisions for the user

1. "Buffer simulation at runtime": the viewer and `-log_reps_events` already exist. Plan assumes we wire them into the new experiments and do not build a new one. If you meant a separate offline Python model of the buffer, say so and it becomes its own deliverable.
2. Shared research repo (text, refs, figures, no code): hosting and Gabriel/Chen handles. Not created or invited.

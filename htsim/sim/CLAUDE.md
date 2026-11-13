# htsim/sim — simulator-code guide

Loaded only when working on files under `htsim/sim/`. Repo-wide rules (Docker-only builds, `-disable_tor_ecn`, validation checklist) are in the root `CLAUDE.md`.

## Rule for every new mechanism

Every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====` banner at every modification site, (ii) a section in `experiments/MODIFICATIONS.md` (see "When to read and edit" at the bottom), (iii) an ARCHITECTURE doc under `experiments/`.

What has NOT been changed:
- No original lines deleted from `htsim/sim/`. Every modification is an addition or a wrap.
- With all new flags absent, the binary produces byte-identical behavior to vanilla NSCC + REPS/FREEZING.

## Extensions overview

All gated behind CLI flags:
1. **State-aware NSCC + REPS** (`-state_aware_ecn`) — binary ECN gate driven by REPS freeze/unfreeze events + dynamic link-failure machinery. Experiments: exp01–03.
2. **Smart filter** (`-smart_filter_mode`) — continuous, evidence-based dampening of NSCC's MD step using REPS buffer saturation. Mutually exclusive with state-aware. Experiments: exp06.
3. **WTD in NSCC** (`-wtd_in_nscc`) — paper's "Wait to Decrease" (SMaRTT-REPS §3.6.1), gates MD on `_exp_avg_ecn ≥ 0.25`. Mutually exclusive with state-aware and smart-filter. Experiments: exp07 (complete; null result — see exp07 README §Results).
4. **PATH_RR** (`-load_balancing_algo path_rr`) — true round-robin over distinct physical paths using full source routing; bypasses per-hop ECMP. Clean baseline for comparing against entropy-spray algorithms.

5. **REPS-Bank** (`-reps_bank`) - second "bank" buffer of clean, fast-RTT EVs used instead of a random draw when the REPS buffer is empty (non-frozen only). See `experiments/REPS_BANK_ARCHITECTURE.md`.

Later mechanisms (Swift CCs, Ofan, constant-rate sender, per-link degrade, ...) are listed in `experiments/MODIFICATIONS.md` (index command at the bottom of this file).

## The state-aware NSCC + REPS extension

### What it does

Every incoming ACK carries an ECN bit. The architecture splits how that bit is consumed:

- **Load Balancer (REPS or FREEZING)** — always sees the real ECN bit. ECN-marked ACKs rotate out the EV naturally.
- **Congestion Controller (NSCC)** — sees a *gated* ECN bit. The CC honors ECN only when the sender's internal flag `_network_is_asymmetric` is set. Otherwise the CC sees ECN=0, holds rate, and lets the LB handle spatial collisions.

The `_network_is_asymmetric` flag is set organically when the LB enters frozen mode (triggered by RTO, which fires when a link failure kills ACKs), and cleared when the LB exits frozen mode. No control-plane broadcast required.

### CLI flags added

| Flag | Effect |
|---|---|
| `-state_aware_ecn` | Master toggle (off by default). Enables CC gate + asymmetric-flag wiring. Forces `repsUseFreezing = true`. |
| `-disable_tor_ecn` | Enables leaf exception (`force_disable_tor_ecn = true`). **Required whenever `-sender_cc_only` is also passed.** |
| `-fail_link_time <fail_us> <recover_us>` | Schedules dynamic Agg↔Core pipe failure and recovery. |
| `-fail_link_target <agg> <core>` | Repeatable. Selects which Agg↔Core link(s) to fail. |
| `-log_reps_state <file>` + `-log_reps_state_src <id>` | Per-ACK CSV diagnostic log. |
| `-log_reps_events <file>` + `-log_reps_events_src <id>` | Unified send+ACK+freeze event trace (SEND/RTX/RTS/ACK/NACK/FREEZE/UNFREEZE, slot-indexed buffer snapshot per row). Independent file and schema from `-log_reps_state`. See `experiments/tools/README.md` for the CSV schema and the `reps_event_viewer.py` interactive HTML viewer. |

`-exit_freeze <picoseconds>` already existed; our experiments use `200000000` (= 200 ms) to suppress mid-run thaws.

### Key code locations

<!-- Line numbers drift with every edit to uec.cpp — grep the function/anchor name
     in the right column rather than trusting the number alone. -->

| What | File | Line(s) |
|---|---|---|
| CC ECN-masking gate | `htsim/sim/uec.cpp` | `bool cc_ecn_view = pkt.ecn_echo();` in `processAck()`, ~1855 |
| FREEZING freeze entry + asymmetric-flag set | `htsim/sim/uec.cpp` | `rtxTimerExpired()`, ~4590-4620 |
| FREEZING unfreeze + asymmetric-flag clear | `htsim/sim/uec.cpp` | `processEv_freezing()`, ~3954 |
| REPS freeze entry + flag set | `htsim/sim/uec.cpp` | state-aware `_load_balancing_algo == REPS` branch inside `rtxTimerExpired()`, ~4666-4677 |
| REPS unfreeze + flag clear | `htsim/sim/uec.cpp` | `processEv_REPS()`, ~3443 |
| `_network_is_asymmetric` flag declaration | `htsim/sim/uec.h` | ~static toggle + per-source flag |
| `Pipe::_failed` flag + early-drop | `htsim/sim/pipe.h` ~42-48, `pipe.cpp` ~65 |
| Leaf-ECN re-enable gotcha | `htsim/sim/datacenter/main_uec.cpp` | ~739 |
| `LinkFailureEvent` class | `htsim/sim/datacenter/main_uec.cpp` |
| `_enable_ecn_on_tor_downlink` guards | `htsim/sim/datacenter/fat_tree_topology.cpp` | ~737, 754, 783 |

### REPS vs FREEZING — which to use

**Always use `-load_balancing_algo freezing` (= paper-REPS, 8-slot bounded buffer)** for any paper-comparable or state-aware work.

`-load_balancing_algo reps` is a code-only simpler variant (unbounded `_next_pathid` list). It's retained for archaeology. The buffer instrumentation column to track is `fresh` (FREEZING) vs `recycle` (REPS).

### Future directions (not implemented)

1. **v4 buffer-fill gate**: change CC ECN-masking from `cc_ecn = ecn && asymmetric` to `cc_ecn = ecn && (asymmetric || fresh ≤ 1)`. One-line change at the `cc_ecn_view` assignment in `processAck()`. Justified by exp02's `fresh=0 ⇒ P(ECN)≈1.0` finding (see `experiments/CLAUDE.md`).
2. **Long-failure stress**: early experiments used a 150 μs failure window (50→200 μs). A 1-10 ms window would exercise the freeze-expiry / auto-thaw path, which was never reached.
3. **Real-CDF workloads**: Datamining/Hadoop/Websearch CDFs (used in the paper) instead of synthetic permutations.
4. **Topology sweep**: extend exp03 to k=8 2-tier and 1024-host 3-tier topologies.
5. **EV-lifetime sweep**: implement the buffer-cache idea via `-reps_lifetime N` and re-run exp02-style instrumentation. The mechanism already exists (`repsMaxLifetimeEntropy`) but is gated off. Hypothesis: REPS' bounded buffer should cache known-good EVs (lifetime > 1) across draws instead of invalidating per use.

---

## Modifications inventory

Source of truth for the original-vs-added boundary in `htsim/sim/`: [`experiments/MODIFICATIONS.md`](../../experiments/MODIFICATIONS.md). One section per mechanism (`### [ADDED: <name>]` or `### [FIX: <name>]`) with the files touched, the gate flag and design notes. Outside `htsim/sim/`: [`PROVENANCE.md`](../../PROVENANCE.md).

Index of mechanisms and their gates (run from repo root):
```bash
grep -n '^### `\[' experiments/MODIFICATIONS.md
```

### Rule: any change under `htsim/sim/`

- New mechanism, algorithm, CC/LB or logging: follow skill `add-mechanism` (it includes the mandatory `validate-mechanism` gate and the MODIFICATIONS / ARCHITECTURE doc steps).
- Fix or extension of an existing mechanism: read its section in `MODIFICATIONS.md` first, then run `validate-mechanism` and update that section (`[FIX: <name>]` if behavior changes without a new flag).
- Do not report the work as done before the Verification subsection exists in the MODIFICATIONS entry.

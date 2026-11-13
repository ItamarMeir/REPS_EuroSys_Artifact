# Modifications inventory — full detail

Split out of the root `CLAUDE.md` to keep the loaded `CLAUDE.md` context small. This file is
the **source of truth for the original-vs-added boundary** in `htsim/sim/`. The nested `htsim/sim/CLAUDE.md` links here instead of keeping a duplicate index;
list mechanisms with `grep -n '^### `\[' experiments/MODIFICATIONS.md`.

Every addition to `htsim/sim/` is tagged `[ADDED: <name>]` in code comments and below.
**Rule for future additions:** every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====`
banner at every modification site, (ii) a section in this file, (iii) an ARCHITECTURE doc under
`experiments/`.

### `[ORIGINAL]` — paper artifact, untouched

All of `htsim/sim/` except the sections listed below. `artifact_scripts/` and `artifact_results/`
are fully untouched.

### `[ADDED: state-aware]` — gated by `-state_aware_ecn`

Architecture doc: [`experiments/ARCHITECTURE.md`](ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_state_aware_ecn_enabled` static, `_network_is_asymmetric` per-source flag + setters | `-state_aware_ecn` |
| `htsim/sim/uec.cpp` | CC ECN-masking gate (~L1209); freeze/unfreeze flag hooks for REPS (~L3022, ~L2310) and FREEZING (~L3040, ~L2653); REPS-buffer CSV instrumentation | `-state_aware_ecn` |
| `htsim/sim/pipe.h/.cpp` | `Pipe::_failed` flag + early-drop in `receivePacket` | `Pipe::setFailed()` call |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-state_aware_ecn`, `-fail_link_time`, `-fail_link_target`, `-log_reps_state`, `-log_reps_state_src`; `LinkFailureEvent` class | own flags |

### `[ADDED: smart-filter]` — gated by `-smart_filter_mode`

**Mutually exclusive with state-aware and wtd-in-nscc** (binary errors out if any two are set together).
Architecture doc: [`experiments/exp06_smart_filter_v6/ARCHITECTURE.md`](exp06_smart_filter_v6/ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `SmartFilterMode`/`SmartFilterCounter` enums, three statics, `_ecn_buffer_counter`/`_sf_md_gain` per-source fields, `smartFilterCounter()`/`smartFilterEcnThresh()` accessors | `-smart_filter_mode` |
| `htsim/sim/uec.cpp` | Static defs; accessor bodies; counter update + gain scratch in `processAck()` (~L1185); `else if` branch in ECN gate (~L1225); Mode A gain + Mode B delay blend in `multiplicative_decrease()` (~L1428); 9 extra CSV columns in `fprintf` (~L1238) | `-smart_filter_mode` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-smart_filter_mode`, `-smart_filter_counter`, `-smart_filter_ecn_thresh`; 3-way coexistence guard; CSV header update | own flags |

### `[ADDED: wtd-in-nscc]` — gated by `-wtd_in_nscc`

**Mutually exclusive with state-aware and smart-filter** (3-way coexistence guard in main_uec.cpp).
Paper reference: SMaRTT-REPS §3.6.1. Reuses `_exp_avg_ecn` (α=0.125, already computed every ACK).
Gate: if `_nscc_wtd_enabled && _exp_avg_ecn < _wtd_threshold (0.25)`, skip MD entirely.
The `_exp_avg_ecn = 1.0` reset on RTO (uec.cpp ~L2093) is preserved so WTD doesn't block MD after a timeout.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_nscc_wtd_enabled` (bool, false) and `_wtd_threshold` (double, 0.25) statics | `-wtd_in_nscc` |
| `htsim/sim/uec.cpp` | Static defs; WTD gate in `updateCwndOnAck_NSCC()` MD dispatch (~L1611); 2 extra CSV columns (`wtd_enabled`, `wtd_can_decrease`) in `fprintf` | `-wtd_in_nscc` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-wtd_in_nscc`; 3-way coexistence guard; CSV header update (+2 columns) | own flag |

### `[ADDED: ev-health-counter]` — activated by `-smart_filter_counter evhealth`

Extension of the smart-filter mechanism. Replaces the broken `fresh_inv` counter with a per-EV ECN-state tracker: counts how many EVs currently in the REPS buffer had their last ACK ECN-marked. This is the true outlier-EV signal — it is near 0 at full bisection (diffuse congestion) and rises when specific EVs are persistently congested (low-load spatial collision regime). Uses `CircularBufferREPS::getValidEntropies()` accessor (O(B²) = O(64) per ACK, acceptable). Counter stored in existing `_ecn_buffer_counter` field; `sf_counter_used=2` in CSV. Compatible with both Mode A and Mode B filter modes.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/buffer_reps.h` | `getValidEntropies()` declaration; added `#include <vector>` | always compiled |
| `htsim/sim/buffer_reps.cpp` | `getValidEntropies()` implementation (returns valid buffer contents as `std::vector<T>`) | always compiled |
| `htsim/sim/uec.h` | `SF_COUNTER_EVHEALTH = 2` in `SmartFilterCounter` enum; `_ev_last_ecn_state` per-source `vector<uint8_t>` | `-smart_filter_counter evhealth` |
| `htsim/sim/uec.cpp` | Lazy-init of `_ev_last_ecn_state`; EV-health update block in `processAck()` smart-filter section; updated `smartFilterCounter()` comment | `-smart_filter_counter evhealth` |
| `htsim/sim/datacenter/main_uec.cpp` | `evhealth` parsed in `-smart_filter_counter` handler | own value |

### `[ADDED: swift-cc]` — gated by `-sender_cc_algo {swift,lswift,mswift,mnscc}`

New CCA implementations for paper reproduction (arXiv:2509.07907v2). No existing code paths
are modified; new cases are added to the dispatch table only.
Architecture + results: [`experiments/exp12_paper_repro_reps/README.md`](exp12_paper_repro_reps/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/delay_median_buffer.h` | New file. `DelayMedianBuffer` class: MAX_H=32 circular ring, `push(delay)`, `percentile(p)`, `setCapacity(H)`. Shared by MSwift and MNSCC. | always compiled |
| `htsim/sim/uec.h` | `SWIFT`, `LSWIFT`, `MSWIFT`, `MNSCC` appended to `Sender_CC` enum; statics `_swift_ai`, `_swift_beta`, `_swift_max_mdf`, `_lswift_dup_threshold`, `_swift_median_pct`; per-source fields `_swift_rtt`, `_swift_last_decrease`, `_swift_consec_high_d`, `_swift_consec_round_start`, `_median_delay_buf`; method declarations. | `-sender_cc_algo swift/lswift/mswift/mnscc` |
| `htsim/sim/uec.cpp` | Static defs; dispatch table entries (4 cases); `updateCwndOnAck_Swift`, `_updateCwndOnAck_LSwift_core` (RTT-round-based threshold), `updateCwndOnAck_LSwift`, `updateCwndOnAck_MSwift`, `updateCwndOnNack_Swift`, `_updateCwndOnAck_NSCC_core` (extracted helper), `updateCwndOnAck_MNSCC` | own algo flags |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-sender_cc_algo {swift,lswift,mswift,mnscc}`, `-swift_beta`, `-swift_max_mdf`, `-swift_ai`, `-swift_median_pct`, `-lswift_dup_threshold` | own algo flags |

### `[ADDED: min-rto-flag]` — gated by `-min_rto <us>`

Single-flag override for the RTO floor (`UecSrc::_min_rto`). htsim auto-computes RTO from
`network_max_unloaded_rtt + queue_drain_time` (~7-15 µs at typical params). Paper 1 §4.1
specifies RTO = 70 µs explicitly. The flag is parsed early (~L285) and applied AFTER the
auto-compute at ~L1018 so the user value wins. Used by exp13 paper-1 runs.
Architecture + results: [`experiments/exp13_papers_reps_repro/README.md`](exp13_papers_reps_repro/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `min_rto_us_override` local (~L170); CLI flag `-min_rto` parser (~L285); override apply (~L1024) | `-min_rto` |

### `[ADDED: swift-md-counter]` — always compiled, no gate

Per-source `uint64_t _swift_md_fires` counter incremented inside the Swift per-ACK MD branch
(`uec.cpp:~L1733`) and the LSwift counter-driven MD branch (`uec.cpp:~L1787`). Logged at flow
finish as a new `swift_md_fires N` column. Diagnostic-only — no behaviour change. Used in Phase D
of exp13 to verify that the `-target_q_delay` flag actually takes effect.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_swift_md_fires` per-source field (~L613) | always |
| `htsim/sim/uec.cpp` | 2 increment lines at MD branches (~L1733, ~L1787); new log column (~L1055) | always |

### `[ADDED: per-host-lb]` — gated by `-host_lb_overrides "host:algo,host:algo,..."`

Per-host LB algorithm override. Each `UecSrc` whose `_srcaddr` is in the map runs the named
algorithm (e.g. `ecmp`, `oblivious`, `freezing`) regardless of the global `-load_balancing_algo`.
Implemented by extracting the constructor's LB dispatch into `_dispatchLB(LoadBalancing_Algo)`
and calling `applyHostLBOverride()` after `setSrc()`. Verified by overriding all 128 hosts to ECMP
under a `freezing` global producing output bit-identical to global `-load_balancing_algo ecmp`.
Caveat: runtime checks of `_load_balancing_algo == X` (e.g. `uec.cpp:1391`) still see the global
value; only the LB function pointers and per-algo init are overridden.
Used in Phase D.9 of exp13 to test paper Fig 4 OPS-column setup (elephants:ECMP + sprayed:OPS).
Architecture + results: [`experiments/exp13_papers_reps_repro/RESULTS_DIAGNOSTIC.md`](exp13_papers_reps_repro/RESULTS_DIAGNOSTIC.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_per_host_lb_override` static map (~L385); `_parseLBName`/`_parseHostLBString` (~L387); `applyHostLBOverride()` (~L181); `_dispatchLB` private (~L677) | `-host_lb_overrides` |
| `htsim/sim/uec.cpp` | Static defs + parsers + `applyHostLBOverride` (~L125); `_dispatchLB` helper (~L185); constructor calls `_dispatchLB(_load_balancing_algo)` (~L635) | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flag `-host_lb_overrides` parser (~L290); `applyHostLBOverride()` call after `setSrc()` (~L1233) | `-host_lb_overrides` |

### `[ADDED: per-host-cwnd]` — gated by `-host_cwnd_overrides "host:cwnd_bytes,host:cwnd_bytes,..."`

Per-host cwnd override, mirroring `per-host-lb`'s map pattern. Each `UecSrc` whose `_srcaddr` is in
the map gets `setCwnd()`/`setMaxWnd()` called with the overridden byte value right after
`applyHostLBOverride()`; every other host keeps the global `-cwnd`. Added to isolate a CONSTANT-CC
cwnd sweep (which never updates cwnd after init, so the window is frozen at whatever this sets) to
one subset of hosts without under/over-provisioning the rest of the run's flows. Used in meeting
2026-10-06 C1's SoL degraded-cell cwnd smoke test: the 32 ToR0 hosts swept 32-1024 packets while the
other 992 hosts stayed at a fixed non-bottlenecking cwnd. Verified to produce numbers identical to an
earlier global-cwnd sweep at every matching value (no cross-interference on this topology), confirming
the isolation is correct and changes nothing when it doesn't need to.
Results: [`experiments/meeting_06_10_26/C1/RESULTS.md`](meeting_06_10_26/C1/RESULTS.md) (SoL section).

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_per_host_cwnd_override` static map; `_parseHostCwndString()`; `applyHostCwndOverride()` | `-host_cwnd_overrides` |
| `htsim/sim/uec.cpp` | Static def + parser + `applyHostCwndOverride()` (calls `setCwnd`/`setMaxWnd`) | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flag `-host_cwnd_overrides` parser; `applyHostCwndOverride()` call after `applyHostLBOverride()` in the connection-setup loop | `-host_cwnd_overrides` |

### `[FIX: target-qdelay-respect-cli]` — applied 2026-05-30

`UecSrc::initNsccParams()` at `htsim/sim/uec.cpp:195` unconditionally
overwrote `_target_Qdelay = 6 µs` AFTER CLI parsing, silently rejecting every `-target_q_delay X`
flag passed to the binary. This made all of exp12 and the initial exp13 Paper 2 runs use a 6 µs
target instead of the paper-requested 1 µs, masking LSwift/MSwift differentiation and producing
the misdiagnosed "L2 limitation". Fix: comment out the L195 reset (the L79 static default
preserves 6 µs as the no-flag fallback). Affects all NSCC/Swift-family CCs.

| File | Lines / what | Effect |
|------|-------------|--------|
| `htsim/sim/uec.cpp` | L195 reset line disabled with banner `// ===== FIX (target-qdelay-respect-cli) =====` | `-target_q_delay X` now actually takes effect |

### `[FIX: median-buf-paper-faithful]` — applied 2026-06-01

`DelayMedianBuffer` (used by MSwift + MNSCC) had two deviations from Paper 2
(arXiv:2509.07907v2) §III.B + Eqs (8-9):

1. **`MAX_H = 32`** silently clamped MSwift's window when Eq (8) `H = max(W/2, 1)`
   exceeded 32 (BDP cwnd ≈ 120 pkts → paper H = 60). Raised to 128; sort cost
   per ACK grows from ~160 to ~640 comparisons — still negligible.
2. **`setCapacity` flushed the buffer on shrink**, discarding all history right
   after MD-driven cwnd drops. Paper has no flush rule. Now keeps the most-recent
   `newCap` samples (the ring buffer already organises them tail-aligned, so
   only `_count` is truncated).

Both changes are mechanical paper-fidelity items, not algorithmic. Effect on
Paper 2 Fig 4 MSwift: 71 % → 75 % (small in this regime). MNSCC unaffected
because its own H-cap of 4 is tighter than MAX_H.

| File | Lines / what | Effect |
|------|-------------|--------|
| `htsim/sim/delay_median_buffer.h` | `MAX_H = 32 → 128`; `setCapacity` truncates `_count` instead of flushing; banner `// ===== FIX (median-buf-paper-faithful) =====` | MSwift's H now follows paper Eq (8) up to W ≈ 240; median window survives MD-induced cwnd drops |

### `[FIX: circular-buffer-reps-leak-fix]` — applied 2026-08-21

`code-review.md` finding 12 (was N3): `UecSrc::startFlow()` (`uec.cpp:2662-2663`)
allocates `circular_buffer_reps` with `new` on every call, including reactivations of a
long-lived source (`activate()`, `uec.cpp:4013-4015`), silently overwriting the previous
pointer each time and leaking it for the rest of the run. A destructor was deliberately
**not** added — `UecSrc` is never itself `delete`d anywhere in the tree (grep-confirmed),
so a destructor would never run. Fix instead tracks ownership: a new
`_owns_circular_buffer_reps` flag is `true` only when this instance allocated the buffer
itself, `false` when it's borrowed from `CONNECTION_INFO_MAP` under `-connections_mapping`
(that path is shared/owned by the map across reactivations and must never be deleted here,
or it would double-free/corrupt shared state). `startFlow()` now deletes the previous
buffer before reassigning, gated on the flag.

| File | Lines / what | Effect |
|------|-------------|--------|
| `htsim/sim/uec.h` | `_owns_circular_buffer_reps` member added, banner `// ===== ADDED (circular-buffer-reps-leak-fix) =====` | Tracks whether this `UecSrc` owns `circular_buffer_reps` |
| `htsim/sim/uec.cpp` | `startFlow()` guarded `delete` before reassignment + flag set in both branches, same banner | Fixes in-run leak on reactivation without `-connections_mapping`; no behavior change on the `-connections_mapping` path |

**Verification:** Docker build clean, normal and `-fsanitize=address`. Short `reps` runs
clean on both branches (owned buffer / `-connections_mapping` borrowed buffer), no
crash/double-free. Trigger-chained `.cm` reactivation test built to directly exercise the
leak path found the connection-matrix engine spawns a new `UecSrc` per triggered
connection rather than reactivating one instance — so this fix's severity may be more
theoretical/latent than originally stated (finding not directly reproduced under stress;
see `code-review.md` finding 12).

### `[ADDED: swift-sack-hole-md]` — gated by `_sender_cc_algo == SWIFT`, always compiled

Paper 2 (CC4Spraying, arXiv:2509.07907v2) §IV.B explicitly states the Swift CCA collapses under
packet spraying because it MDs on SACK holes from out-of-order arrivals. Their footnote says
they had to correct htsim's Swift to match this. This patch implements the same correction:
inside `UecSrc::processAck()`, immediately after the per-ACK CCA dispatch, when the active CCA
is `SWIFT` and the receiver-attached out-of-order count `pkt.ooo() > 0`, apply Swift's
reordering-sensitive MD (`_cwnd *= 1 - _swift_max_mdf` with the standard per-RTT cooldown via
`_swift_last_decrease` / `_swift_rtt`). LSWIFT/MSWIFT (which are the paper's *reordering-resilient*
variants by definition) and NSCC/MNSCC are gated out and unchanged. With this fix, Paper 2 Fig 4
Swift CCT inflation jumps from 355 % to ~1577 % (paper 1308 %, within 20 %).

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.cpp` | New block in `processAck()` after the CCA dispatch (~L1444); banner `// ===== ADDED (swift-sack-hole-md) =====` | `_sender_cc_algo == SWIFT && ooo > 0` |

### `[ADDED: path-rr]` — gated by `-load_balancing_algo path_rr`

True round-robin over distinct physical paths using **full source routing** — bypasses per-hop
ECMP entirely. At flow setup, `get_bidir_paths(src, dst)` enumerates all distinct end-to-end
`Route*` objects and stores them in `UecSrc::_paths`. Each packet is created with the next
route in the cycle as its explicit route (not just an entropy value). Switches never run their
ECMP hash on these packets. `processEv_path_rr` is a no-op (pure RR, no feedback).
Architecture doc: [`experiments/PATH_RR_ARCHITECTURE.md`](PATH_RR_ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RR` appended to `LoadBalancing_Algo` enum; `_path_rr_idx` per-source field; `setPaths()` / `setPathRRStartIdx()` methods; `nextEntropy_path_rr` / `processEv_path_rr` declarations; `PathRRStartMode` enum + static | `-load_balancing_algo path_rr` |
| `htsim/sim/uec.cpp` | `_parseLBName` entry; `_dispatchLB` case; `processEv_path_rr` (no-op); `nextEntropy_path_rr` (advances `_path_rr_idx`); `effective_route` override in `sendNewPacket` and `sendRtxPacket`; `_path_rr_start_mode` static def | `-load_balancing_algo path_rr` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `path_rr` parsed in `-load_balancing_algo` handler; `-path_rr_start_mode {zero\|src_mod\|dst_mod\|srcdst_hash\|src_mod2}`; `get_bidir_paths` + `setPaths` + `setPathRRStartIdx` call per flow after `connectPort` | `-load_balancing_algo path_rr` |

### `[ADDED: path-rr-npaths]` — gated by `-path_rr_npaths_override "host:N,..."`

Per-host cap on the number of PATH_RR paths. After `get_bidir_paths` builds `full_paths`,
truncates the vector to at most N entries for any host in the override map. Purely a
`main_uec.cpp` change — no uec.h/uec.cpp modifications. Used in exp19 to simulate one
host having access to only 3 of 4 physical paths (fabric failure / misconfigured routing).
Results: [`experiments/exp19_path_rr_asymmetry_v19/README.md`](exp19_path_rr_asymmetry_v19/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `path_rr_npaths_override` local map (~L214); CLI flag `-path_rr_npaths_override` parser (~L371); truncate `full_paths` before `setPaths` in PATH_RR setup block | `-path_rr_npaths_override` |

### `[ADDED: path-rr-startslot]` — extends `-path_rr_start_mode`

Adds a fifth start-slot mode `src_mod2`: each flow's RR start index is `(src × 2) % np`. With
`np=4` this yields slots [0,2,0,2,...] — 2 distinct slots vs 4 for `src_mod`. Tested in exp18
alongside the existing `zero` and `src_mod` modes against PATH_STATIC reference.
Results: [`experiments/exp18_path_rr_startslot_v18/README.md`](exp18_path_rr_startslot_v18/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RR_START_SRC2` appended to `PathRRStartMode` enum | `-path_rr_start_mode src_mod2` |
| `htsim/sim/datacenter/main_uec.cpp` | `src_mod2` branch in `-path_rr_start_mode` parser; `PATH_RR_START_SRC2` case in `setPathRRStartIdx` switch: `start_idx = (src * 2) % np` | `-path_rr_start_mode src_mod2` |

### `[ADDED: drb]` — faithful DRB stand-in: `-path_rr_start_mode random` and `-path_rr_order agg_fast`

Two opt-in knobs on `path_rr` to approximate DRB (Cao et al. CoNEXT 2013; Ofan paper S3.4/App. D: independent periodic flows with RANDOM phase, round-robin over the core switches). (1) `-path_rr_start_mode random`: each flow's start slot is `rand() % np` (simulator RNG, seeded by `-seed`; one draw per flow at setup, only when the mode is selected, so all other runs keep their RNG stream byte-identical). (2) `-path_rr_order {native|agg_fast}` (default `native`): `agg_fast` permutes the inter-pod 3-tier path list so index `i` uses Agg `i%A` and core `i` (consecutive packets take different first hops, the sequence is the cores in index order). Native enumeration is agg-major (`idx = a*L + l`), so `L` consecutive packets share one Agg/ToR uplink. ACKs under `path_rr` are NOT source-routed (`UecAckPacket::newpkt(..., NULL, ...)`): they follow the switch FIB/ECMP with the echoed path id, so they are neither pinned nor synchronised and no separate ACK pointer was added. Verified: `baseline.sh` hashes identical, `path_rr` smoke (zero, srcdst_hash) stdout identical before/after. Results: [`exp32_ofan/V_C_theory_figures.md`](exp32_ofan/V_C_theory_figures.md) section "DRB faithfulness".

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RR_START_RANDOM` appended to `PathRRStartMode` enum | `-path_rr_start_mode random` |
| `htsim/sim/datacenter/main_uec.cpp` | `random` branch in `-path_rr_start_mode` parser; `-path_rr_order` parser + local `path_rr_order_aggfast`; `agg_fast` permutation of `full_paths` before `setPaths` (3-tier inter-pod, PATH_RR only); `PATH_RR_START_RANDOM` case in start-idx switch | `-path_rr_start_mode random`, `-path_rr_order agg_fast` |

### `[ADDED: path-random]` — gated by `-load_balancing_algo path_random`

Per-packet uniform-random path selection using the same source-routing infrastructure as PATH_RR.
Reuses `UecSrc::_paths[]` populated by `get_bidir_paths` at flow setup. On every packet,
`rand() % _paths.size()` is stored into `_path_rr_idx` (scratch register) before the route is
selected, so route and pathid are consistent. `processEv_path_random` is a no-op.
Results: [`experiments/exp16_path_random_v16/README.md`](exp16_path_random_v16/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RANDOM` appended to `LoadBalancing_Algo` enum; `nextEntropy_path_random` / `processEv_path_random` declarations | `-load_balancing_algo path_random` |
| `htsim/sim/uec.cpp` | `_parseLBName` entry; `_dispatchLB` case; `processEv_path_random` (no-op); `nextEntropy_path_random` (returns scratch `_path_rr_idx`); `rand()` roll in `sendNewPacket` and `sendRtxPacket`; `effective_route` guard extended to cover `PATH_RANDOM` | `-load_balancing_algo path_random` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `path_random` parsed in `-load_balancing_algo` handler; path-population condition extended to `PATH_RR || PATH_RANDOM` | `-load_balancing_algo path_random` |

### `[ADDED: path-static]` — gated by `-load_balancing_algo path_static`

Each flow is pinned to a single fixed path for its entire lifetime. Path is chosen at flow-setup
time by a **greedy edge-load algorithm**: for each new flow, pick the path whose
maximum-loaded edge (`PacketSink*`) has the minimum current load, then increment load counts
for all edges on the chosen path. `Route*` objects reuse the same `Queue*`/`Pipe*` pointers for
shared physical links, so tracking `PacketSink*` identity correctly identifies shared links
without any topology-specific knowledge. For balanced workloads like tornado, all 16 flows are
assigned with `max_edge_load=0` — truly no shared data-path edges.

**Reverse-path routing for ACK/PULL:** The NIC sends control packets (PULLs, ACKs, NACKs) by
calling `sink->getPortRoute(port)`, which by default returns only the first hop (dst→ToR) and
relies on ECMP for the rest. In bidirectional tornado, ECMP hash collisions on the return path
caused a bimodal FCT distribution (~80 µs gap). The fix: after the greedy selects `best`, build
`rev = new Route(*orig_r->reverse(), *uec_src->getPort(p))` and call
`uec_snk->getPort(p)->setRoute(*rev)`, overriding the sink port's route with the full source-routed
reverse path. All 16 flows now finish at identical times (zero FCT spread), and PATH_STATIC achieves
`1.0334×` avg/max slowdown — best of all five algorithms tested.
Results: [`experiments/exp17_cwnd_corrected_v17/`](exp17_cwnd_corrected_v17/)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_STATIC` appended to `LoadBalancing_Algo` enum; `nextEntropy_path_static` / `processEv_path_static` declarations | `-load_balancing_algo path_static` |
| `htsim/sim/uec.cpp` | `_parseLBName` entry; `_dispatchLB` case; `processEv_path_static` (no-op); `nextEntropy_path_static` (`_path_rr_idx % 1` → always 0); `effective_route` guard extended to cover `PATH_STATIC` | `-load_balancing_algo path_static` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `path_static` parsed; `path_static_edge_load` map; greedy selection; `get_bidir_paths` called with `reverse=true`; reverse route built and registered via `uec_snk->getPort(p)->setRoute(*rev)`; cross-linked with `set_reverse` for trim safety | `-load_balancing_algo path_static` |

### `[ADDED: srv6]` — gated by `-use_srv6`

SRv6 source routing substrate: orthogonal to the LB algorithm. When `-use_srv6` is passed, the
sender converts the EV chosen by whatever LB algorithm is active into a physical-path index
(`ev % _paths.size()`) and uses the corresponding pre-computed `Route*` from `_paths[]` instead
of relying on per-hop ECMP hashing. Switches simply follow the explicit hop list.

**EV-to-path mapping faithfulness**: for the 3-tier K=4 fat tree, `get_bidir_paths` enumerates
inter-pod paths in Agg-major, Core-minor order. `ev % 4` maps EV bit[0]=Core choice (= paper
"plane") and bit[1]=Agg choice (= paper "T0 uplink") — exactly the SRv6 uSID bit decomposition
described in MRC §2.3 (Fig. 3).

**Timing constraint**: `effective_route` must be determined before `newpkt()` locks the route,
but `nextEntropy()` is normally called after packet creation. Solution: SRv6 pre-draw block calls
`nextEntropy()` early in `sendNewPacket`/`sendRtxPacket`, stores the EV in `_srv6_pending_ev`,
and sets `route_path_idx`. The original `nextEntropy()` dispatch is then replaced by returning
the cached value — the LB state machine advances exactly once per packet.

Can be combined with any existing LB algorithm: `-load_balancing_algo freezing -use_srv6`,
`-load_balancing_algo ecmp -use_srv6`, etc.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_use_srv6` static bool; `_srv6_pending_ev` per-source scratch field | `-use_srv6` |
| `htsim/sim/uec.cpp` | static def; SRv6 pre-draw block + `route_path_idx` local + `effective_route` condition extended + `nextEntropy` guard in `sendNewPacket` and `sendRtxPacket` | `-use_srv6` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI `-use_srv6`; path-population condition extended to include `_use_srv6` | `-use_srv6` |

**Verification tests**: `experiments/test_srv6/scripts/run_tests.sh` — 13/13 pass.
Tests verify: (1) FREEZING+SRv6 smoke, (2) PATH_RR FCT identical with/without SRv6 (within 0.1%),
(3) 1-path SRv6 stalls when path[0]=(agg=0,core=0) is failed, (4) 1-path SRv6 unaffected when
other links fail, (5) 4-path SRv6 shows ≥3× FCT degradation when each path's (agg,core) link fails,
(6) ECMP+SRv6 completes tornado workload.

### `[ADDED: freezing-pxr]` — gated by `-load_balancing_algo freezing_pxr`

Path-eXcluding REPS. On RTO, adds the triggering EV (captured from `sendRecord::sent_ev`) to a
per-source **excluded set** and refreshes a sliding deadline (`now + _pxr_window`). Normal REPS
sampling continues but skips excluded EVs on every draw. When the deadline elapses with no new
RTO, the entire excluded set is cleared atomically. Never enters frozen mode.

Unlike FREEZING, there is no frozen-mode cycling of stale buffer entries. The sender simply keeps
drawing from the remaining healthy EVs, giving ~31% P99 FCT improvement over FREEZING B=8 under
51 failed links (exp23).

`sendRecord` was extended to store `sent_ev` so the RTO handler can identify which EV caused
the timeout. `createSendRecord` updated to accept and forward `ev` at all 3 call sites.

Experiment + results: [`experiments/exp23_freezing_pxr_v23/README.md`](exp23_freezing_pxr_v23/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `FREEZING_PXR` in `LoadBalancing_Algo` enum; `_pxr_excluded_evs` + `_pxr_clear_deadline` per-source fields; `_pxr_window` public static; `nextEntropy_freezing_pxr` / `processEv_freezing_pxr` declarations; `sent_ev` added to `sendRecord`; `createSendRecord` declaration updated | `-load_balancing_algo freezing_pxr` |
| `htsim/sim/uec.cpp` | `_pxr_window` static def (200 ms default); `_parseLBName` entry; `_dispatchLB` case; `nextEntropy_freezing_pxr` (timer check + saturation guard + filtered REPS draw); `processEv_freezing_pxr` (filtered buffer add); RTO branch (exclusion + sliding deadline); `createSendRecord` stores `ev`; `rto_trigger_ev` captured before erase; `pxr_excluded_count` + `pxr_excluded_evs` CSV columns | `-load_balancing_algo freezing_pxr` |
| `htsim/sim/datacenter/main_uec.cpp` | `freezing_pxr` in `-load_balancing_algo` handler; `-pxr_window_us <N>` flag; CSV header update | own flags |

### `[ADDED: reps-event-trace]` — gated by `-log_reps_events`

Unified send+ACK+freeze event trace for the REPS/FREEZING/FREEZING_PXR circular buffer,
independent of `-log_reps_state` (that CSV's schema is untouched — exp07/08/09/11/23 runner
scripts parse it). Where `-log_reps_state` logs only the ACK side (one row per received ACK),
this trace also captures SEND/RTX/RTS (with EV-draw provenance), NACK (which does *not* recycle
its EV — invisible in the old log), and FREEZE/UNFREEZE transitions, each with a full
slot-indexed snapshot of the buffer (value/valid/lifetime per slot, plus head and frozen-mode
read pointer) instead of the old `buf_contents`'s unordered valid-EV list. The time column is
named `time_ns` and holds `eventlist().now()/1000` — numerically identical to the pre-existing
`-log_reps_state` time column (which is labelled `time_us` but also holds nanoseconds), so the
two files line up row-for-row. Feeds a Python-generated
self-contained interactive HTML viewer that replays the trace as a circular-buffer cell grid with
a step-through event log (like the hand-driven teaching simulator it mirrors).

Feature-off cost is one null-pointer test at each of 7 call sites — no allocation, no formatting.

**Fix (2026-10, found while investigating dual-window trim-enabled behavior):** the
`EvSource`→string table (`evSourceStr()`, `uec.cpp` next to `logRepsEvent()`) never gained
cases for `EVSRC_FROZEN_POP_VALID`/`EVSRC_FROZEN_POP_STALE` when `dual-window-reps-mprdma`
added them — every dual-window frozen-mode draw logged `ev_src=""` instead of
`frozen_pop_valid`/`frozen_pop_stale`. Cosmetic only (the string is never read back into
control flow — `evSourceToWindowTag()` switches on the enum directly, not this string), but it
silently broke any analysis joining on `ev_src` for `DUAL_MPRDMA_REPS`/`DUAL_MPRDMA_REPS_CAP`
traces. Fixed by adding the two missing `case`s. Traces captured before this fix show the old
blank-string behavior; no data pipeline (dashboards, aggregators) ever read this column, so
nothing downstream needed re-running.

Tool + docs: [`experiments/tools/README.md`](tools/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/buffer_reps.h`/`.cpp` | `SlotView` struct; `getSlots()` (slot-indexed view, incl. invalid slots — unlike `getValidEntropies()`); `getHead()`/`getFrozenHead()`/`getMaxSize()` accessors | always compiled |
| `htsim/sim/uec.h` | `EvSource` enum + `_last_ev_source` scratch register (draw provenance); `_reps_events_log`/`_reps_events_log_srcs`/`_reps_events_max`/`_reps_events_rows`/`_reps_events_t0`/`_reps_events_t1` statics; `_reps_events_traced` per-source membership cache (the allow-lists are fixed at CLI parse time, so the set lookup runs once per source, not once per packet); `logRepsEvent()` declaration | `-log_reps_events` |
| `htsim/sim/uec.cpp` | Static defs; `logRepsEvent()` impl (src/window/cap gating, slot snapshot formatting, one `fprintf`); `_last_ev_source` set at every return in `nextEntropy_freezing`/`nextEntropy_freezing_pxr`/`nextEntropy_REPS`; 7 call sites — SEND (`sendNewPacket`), RTX (`sendRtxPacket`), RTS (`sendRTS`), ACK (`processAck`, logs `pkt.acked_psn()` as `seqno` for PSN cross-reference), NACK (`processNack`), FREEZE ×3 (`rtxTimerExpired`'s two FREEZING branches + the state-aware REPS branch), UNFREEZE (`processEv_freezing`) | `-log_reps_events` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-log_reps_events <file>`, `-log_reps_events_src <id>` (repeatable, falls back to `-log_reps_state_src` if never given), `-log_reps_events_max <N>`, `-log_reps_events_window <t0_ns> <t1_ns>` | own flags |
| `experiments/tools/reps_event_viewer.py` | new — CSV parser, filters, `--verify` invariant checker, self-contained HTML viewer generator (buffer grid, event log, PSN cross-reference + RTT, theme-aware palette) | n/a |
| `experiments/tools/test_reps_event_viewer.py` | new — unit tests | n/a |

### `[ADDED: reps-fifo-trace]` — `fifo` column, gated by `-log_reps_events`

Extends the event trace with the **unbounded** `_next_pathid` FIFO that plain REPS and MIXED
recycle EVs through (`push_back` on a clean ACK in `processEv_REPS`, `pop_front` on reuse in
`nextEntropy_REPS`). Before this column, a REPS trace showed an all-zero `slots` snapshot,
because `slots` views only `circular_buffer_reps` — which REPS never touches. That reads as
"this algorithm has no buffer", when in fact it has a different one. The two buffers are
disjoint: exactly one is meaningful per trace, and the viewer now shows whichever applies and
says so explicitly rather than rendering a permanently empty grid.

The column is appended, so it is a backward-compatible schema widening: the viewer accepts both
the 17- and 18-column form, and pre-existing traces (exp21/exp22 FREEZING runs) still parse and
render unchanged. `-` distinguishes "algorithm has no FIFO" from an empty FIFO. Unlike `slots`,
the field is capped (128 entries + a `+N` elision count) because the list is genuinely unbounded;
observed depth on the exp21/exp22 tornado workload peaks at 89, so no elision occurs there.

`--verify` gains two FIFO invariants, both validated against deliberately corrupted traces
(a mutation of the popped EV, of the tail behind it, and of an ACK's appended value are each
caught): a `fresh_pop` draw must take the current front and leave the tail untouched, and an
ACK that grows the FIFO must append exactly the acked EV at the back.

### `[ADDED: c3-burst-host-id]` — `srcaddr` finish-line field + trace column

`_node_num` (`_global_node_count++`, assigned once per `UecSrc` *object*) identifies a flow,
not a physical host — under a multi-flow-per-host workload (several `.cm` lines for the same
host with `-connections_mapping`, e.g. meeting_06_10_26/C3's bursty sender) each flow gets a
different `_node_num`, so neither the flow-finish printf nor `-log_reps_events_src`'s allow-list
(both keyed on `_node_num`) can identify "this host" once it has more than one flow. `_srcaddr`
(set via `setSrc()`) is the physical host id and is stable across a host's flows. Prints it on
the finish line and appends it as a trailing column (after `fifo`) on the event trace, so
post-hoc analysis can regroup a host's several flows without relying on `.cm` generation order.
Purely additive on both: existing C1/C2 traces/finish lines are unaffected and don't need
re-running; `reps_event_viewer.py` accepts the old (17-col), `fifo`-only (18-col), and new
(19-col, `fifo`+`srcaddr`) trace widths.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.cpp` | `" srcaddr " << _srcaddr` appended to the flow-finish `cout` line; `srcaddr` column appended to `logRepsEvent()`'s `fprintf` | always compiled (finish line); `-log_reps_events` (trace column) |
| `htsim/sim/datacenter/main_uec.cpp` | `srcaddr` appended to the event-trace CSV header line | `-log_reps_events` |
| `experiments/tools/reps_event_viewer.py` | `EXPECTED_COLUMNS_WITH_FIFO_AND_SRCADDR`; `parse_row`/`load_events` accept all 3 widths; `srcaddr` added to the parsed event dict (`None` for older traces) | n/a |

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.cpp` | `logRepsEvent()`: `uses_fifo` test (`REPS`/`MIXED`), `fifo_str` build with 128-entry cap + `+N` overflow token, extra `%s` in the `fprintf` | `-log_reps_events` |
| `htsim/sim/datacenter/main_uec.cpp` | `fifo` appended to the event-trace CSV header | `-log_reps_events` |
| `experiments/tools/reps_event_viewer.py` | `EXPECTED_COLUMNS_WITH_FIFO` + dual-width header/row acceptance; `parse_fifo()`; two FIFO invariants in `verify_events()`; FIFO grid + legend + `fifoDepth` state field in the HTML viewer | n/a |

## `core-downlink-queue-log`

New `CoreDownlinkQueueSampler` class, banner `// ===== ADDED (core-downlink-queue-log) =====`.
Samples core→agg **downlink** queue depth (`queues_nc_nup[core][agg][0]`) — opposite
direction from the pre-existing `CoreQueueSampler` (agg→core uplink, `queues_nup_nc`) — for
the first N core switches (N and the sample interval are constructor args, not separate CLI
flags; currently called with N=16, interval=0.2 µs, both exp25-specific constants). Built to
check whether REPS's first-window round-robin (exp24) produces a synchronized queue spike at
flow start; see [`experiments/exp25_queue_dynamics_v25/README.md`](exp25_queue_dynamics_v25/README.md)
for the (non-confirming) result.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `CoreDownlinkQueueSampler` class (after `TorQueueSampler`); `log_core_downlink_queues_file` local; `-log_core_downlink_queues <file>` CLI parser; construction wired next to the existing core/tor samplers | `-log_core_downlink_queues <file>` |

## `metrics-counters`

Per-source diagnostic counters, banner `// ===== ADDED (metrics-counters) =====`.
Always compiled, **no behaviour change** (same category as `swift-md-counter` /
`ecn-counter`). Five quantities appended to the flow-finish `cout` line
(`uec.cpp` `checkFinished`), after `ecn_acks`:

    rtos <n>            RTO fires for this flow (rtxTimerExpired)
    freeze_entries <n>  transitions into FREEZING frozen mode
    freeze_us <t>       cumulative time this source spent frozen (any open
                        interval at finish is folded in)
    ev_explore <n>      forced post-unfreeze exploration draws (EVSRC_EXPLORE)
    ev_random <n>       random EV draws — buffer empty / no fresh entropy
                        (EVSRC_RANDOM), both FREEZING branches

`ecn_acks` (per-flow ECN-marked ACK count) and `RTS` were already on the line;
exp28's aggregator sums `ecn_acks` per host and derives a random-EV rate as
`(ev_random + ev_explore) / total_packets`.

**The counters live in a file-static side table** (`std::unordered_map<int,
RepsMetrics>` keyed by `_node_num`), NOT in new `UecSrc` members: growing
`UecSrc` by even one member deterministically corrupts the heap during init on
this codebase (a latent layout-sensitive OOB write elsewhere). The side table
leaves `sizeof(UecSrc)` and every member offset untouched.

Consumed by [`experiments/exp28_link_degradation_sweep/`](exp28_link_degradation_sweep/README.md).

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.cpp` | anon-namespace `RepsMetrics` struct + `g_reps_metrics` map + `RM()`/`accrueFreeze()`/`totalFreeze()` helpers (after `using namespace std`); `RM(_node_num).rto++` in `rtxTimerExpired`; `accrueFreeze()` at end of `rtxTimerExpired` and top of `nextEntropy_freezing`; `ev_explore`/`ev_random` bumps at the `EVSRC_EXPLORE`/`EVSRC_RANDOM` returns in `nextEntropy_freezing`; 5 fields appended to the `checkFinished` finish line | always compiled |

---

## `timed-failure`

Transient link failure on a schedule + a per-host metric time-series log, banner
`// ===== ADDED (timed-failure) =====`. Always compiled, **no behaviour change
when the flags are absent** (regression-checked: a plain run's finish line is
byte-identical). Built for
[`experiments/exp29_failure_response/`](exp29_failure_response/README.md).

### New CLI flags (`htsim/sim/datacenter/main_uec.cpp`)

    -timed_window <start_us> <recover_us>
        Shared transition times for the timed failures below. recover <= start
        => permanent onset (no recovery).

    -timed_fail_tor_uplinks <tor> <F>
        Fail pipes_nlp_nup[tor][s][b] for s in [0, F), all bundle links b, for
        t in (start, recover). One `new LinkFailureEvent(el, pipe, nullptr,
        ts, tr)` per pipe -- the LinkFailureEvent class (State-Aware lineage) is
        REUSED UNMODIFIED; only its instantiation is new. The stock
        -fail_link_time path only resolves 3-tier Agg<->Core pipes
        (pipes_nup_nc, resized only when _tiers==3), so it is inert on the
        2-tier fabric; this flag resolves the 2-tier ToR->spine pipe array
        (pipes_nlp_nup, resized unconditionally).

    -timed_fail_tor_downlinks <tor> <F>
        Same on pipes_nup_nlp[s][tor][b] (spine s -> ToR tor). Reverse-path
        loss. Secondary.

    -log_reps_window <file> <interval_us> <t0_us> <t1_us>
        For t in [t0, t1], every interval_us, write one CSV row per node that
        has an entry in g_reps_metrics:
          t_us,node,d_rto,d_freeze_entries,d_fast_loss,frozen_frac,
          d_ev_random,d_ev_explore,d_ecn_acks,frozen_now
        d_* are deltas since the previous tick; frozen_frac =
        (totalFreeze(now) - totalFreeze(prev)) / interval, a duty cycle in
        [0,1] (a host frozen the whole window contributes exactly interval, so
        the raw delta saturates -- report the fraction, not the duration).
        The [t0, t1] bound is load-bearing: the logger is a re-arming
        EventSource, so an unbounded one keeps the sim event queue non-empty
        and drags the run out to -end (~90 ms) long after every flow finished
        (~356 us). It stops re-arming once now + interval > t1.

### `g_reps_metrics` side-table growth (`htsim/sim/uec.cpp`)

Two `uint64_t` fields added to the anon-namespace `RepsMetrics` struct (a plain
local struct -- NOT `UecSrc`, so the layout heap-bug from `metrics-counters`
does not apply):

    ecn_acks          bumped alongside _ecn_ack_count++ (uec.cpp ~1506)
    fast_loss_entries bumped at the `_loss_recovery_mode = true` transition in
                      fastLossRecovery() (uec.cpp ~2666)

`fast_loss` is also appended to the flow-finish `cout` line (after the
`metrics-counters` block). `ecn_acks` is not (it duplicates `_ecn_ack_count`,
already on the line) -- it exists only so the window log has it per-host.

### `UecWindowLogger` (`htsim/sim/uec.cpp`)

A `Clock`-pattern `EventSource` (arm first tick absolute at `t0` via
`sourceIsPending`, re-arm via `sourceIsPendingRel`, stop re-arming once
`now + interval > t1`) that iterates `g_reps_metrics` each tick and writes the
deltas. Lives in `uec.cpp` (anon namespace) so it can read the file-static side
table. Started from `main_uec.cpp` via `UecSrc::startRepsWindowLog(el, path,
interval_ps, t0_ps, t1_ps)` (declared in `uec.h` -- a `static` method, so no
instance-layout change), which fopens the file, writes the header, and `new`s
the logger after topology build.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `static void startRepsWindowLog(...)` declaration (after the `reps-event-trace` block) | always compiled |
| `htsim/sim/uec.cpp` | `ecn_acks`/`fast_loss_entries` in `RepsMetrics` + 2 bump sites; `fast_loss` on finish line; `UecWindowLogger` class + `UecSrc::startRepsWindowLog` (after the `metrics-counters` anon-namespace block) | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | 4 CLI flags (`-log_reps_window` takes 4 args) + locals; instantiation block right after the existing `LinkFailureEvent` block (2-tier pipe resolution -> reused `LinkFailureEvent`; `startRepsWindowLog` call with `t0`/`t1` bounds) | always compiled |

---

## `fail-src-paths`

Targeted single-source path loss, banner `// ===== ADDED (fail-src-paths) =====`.
Always compiled, **no behaviour change when `-fail_src_paths` is absent** (the
static map is empty -> `pathDeadForThisSrc()` returns on the first line).
Regression-checked byte-identical: the same healthy 4 MiB run's finish line is
identical across (a) the pre-patch binary, (b) the patched binary with no flag,
(c) the patched binary with `-fail_src_paths 0 0` (map populated, `0 < 0` false).
Built for
[`experiments/exp30_concentrated_path_loss/`](exp30_concentrated_path_loss/README.md)
Part B.

### New CLI flag (`htsim/sim/datacenter/main_uec.cpp`)

    -fail_src_paths <src> <count>
        For source host <src> ONLY, physical SRv6 path indices [0, count) are
        dead. A data/rtx packet whose route_path_idx (= ev % _paths.size()) lands
        in that range is `p->free()`d at the emit site instead of `p->sendOn()` --
        exactly what a first-hop failed Pipe does (pipe.cpp:67-70). The sender
        still bumps _highest_sent / _rtx_packets_sent and arms the RTO, so
        recovery (RTO -> freeze -> EV rotation) runs identically to a real
        fabric drop. Scoped to one src by construction: no shared fabric pipe is
        both per-path and private to a single source, so fabric-level failure
        (`-failed`, `-timed_fail_tor_uplinks`) cannot express "1/4 of ONE flow's
        paths". Static (whole-sim). Repeatable for multiple sources.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `static std::map<int,int> _fail_src_paths` (after the `srv6` block); inline `bool pathDeadForThisSrc(uint64_t) const` (after `sendRTS()` decl) | always compiled |
| `htsim/sim/uec.cpp` | static def `UecSrc::_fail_src_paths` (after `_use_srv6` def); one guard before `p->sendOn()` in `sendNewPacket` and in `sendRtxPacket` | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | `-fail_src_paths` parse (2 args), right after `-use_srv6` | always compiled |

## `dual-window-reps-mprdma` — two independent MPRDMA-AIMD windows for REPS+FREEZING

Banner `// ===== ADDED (dual-window-reps-mprdma) =====`. New `Sender_CC` value, used
together with `-load_balancing_algo freezing` (paper-REPS) only — **not** the separate,
sticky-single-path `-load_balancing_algo mprdma`, which shares the MPRDMA name but is
otherwise unrelated (CLI hard-errors if the two are combined).

**Mechanism.** Each flow (`UecSrc`) keeps two independent MPRDMA AIMD windows instead of
one shared `_cwnd`:

- **`_win_safe`** — gates/updates from EVs verified valid at pop time: a normal fresh
  buffer pop (`EVSRC_FRESH_POP`), a frozen-mode pop where `is_valid_frozen()` was true at
  draw time (new `EVSRC_FROZEN_POP_VALID`), or a FREEZING_PXR filtered pop
  (`EVSRC_PXR_POP`).
- **`_win_random`** — gates/updates from unverified EVs: random draws (`EVSRC_RANDOM`),
  post-unfreeze forced exploration (`EVSRC_EXPLORE`), a frozen-mode pop where
  `is_valid_frozen()` was false (new `EVSRC_FROZEN_POP_STALE`), or a FREEZING_PXR random
  draw (`EVSRC_PXR_RANDOM`).

EV/path selection is **unchanged** — still `nextEntropy_freezing()`. Only cwnd admission
and the MPRDMA AI/MD update are split and re-attributed by trust tier. Both windows run
the *identical* MPRDMA formula (AI: `cwnd += bytes*mtu/cwnd`; MD: `cwnd -= bytes/4`,
floored at 1 MTU — kept exactly as MPRDMA's existing floor, not a new tunable) — the only
difference between them is which packets/ACKs feed which window's state.

**Locked design decisions** (see the design conversation / `experiments/ARCHITECTURE.md`
for the full rationale):
- Admission is **fully independent per window** (not a shared budget): a packet can only
  send if its window's own `cwnd > in_flight`.
- Each window gets the **full existing `_maxwnd`** ceiling independently (not split) —
  aggregate in-flight can exceed `1.5*BDP` if both windows are simultaneously near full;
  accepted trade-off vs. underutilizing a skewed traffic mix. This is unchanged in this
  (v1, `DUAL_MPRDMA_REPS`) mechanism. It's the confirmed cause (see exp29 dashboard
  investigation) of dual-window B=8 showing far higher ECN/RTO/random-EV-draw counts than
  plain MPRDMA B=8 at the same F: dual-window's summed cwnd runs up to ~2x MPRDMA's single
  ceiling, not a REPS/LB-layer difference. **Now addressed by a v2 variant**,
  `DUAL_MPRDMA_REPS_CAP` (`-sender_cc_algo dual_mprdma_reps_cap`) — see the
  `dual-window-cwnd-cap` section below. v1 itself is intentionally left as-is (not
  retrofitted) so this section and every already-published exp29/exp30 result built from
  v1 stay exactly reproducible.
- Each window's init defaults **asymmetrically**: `_win_safe` starts at the full ceiling
  (`_maxwnd`) so its first clean ACK after a reset doesn't underutilize; `_win_random`
  starts at the same conservative `cwnd_init_total` NSCC/MPRDMA use. Both independently
  overridable (`-dual_safe_cwnd_init`, `-dual_random_cwnd_init`, in packets; 0 = default).
- Each window resets to its **own** init value — at flow start, at REPS unfreeze (both
  windows, since unfreeze wipes buffer state entirely), and independently on a per-window
  idle timer (`-window_idle_reset_rtts N`, default 2, measured against `_base_rtt`, never
  both windows at once — an idle-but-still-in-flight window never resets, to avoid
  breaking the in-flight invariant below).
- **1-MTU MD floor kept exactly as MPRDMA's** (`max(_mtu, cwnd)`), not raised. Known,
  deliberately-deferred consequence: a window pinned at the floor admits only 1 outstanding
  packet, so exploration under sustained ECN pressure on the random window caps near 1
  attempt/RTT. Documented here as a tunable worth revisiting (raise the floor to 2-4 MTUs)
  rather than implemented now.
- A retransmitted packet keeps the window tag it was **originally** attributed to at first
  send, even though the retransmit draws a fresh EV that may land in the other trust tier
  (never re-derive the tag from the EV — by ACK/NACK/RTO time the buffer slot may already
  be popped, invalidated, or wiped by `resetBuffer()`). Consequence worth remembering: the
  safe window's in-flight count can include bytes currently traveling on a random EV.
- ECN is one bit per (possibly aggregate) ACK, not per constituent packet: an ACK spanning
  both windows' packets marks both. The MD floor is the defense against random-window
  collapse, not clean per-window ECN signal separation.

**Correctness machinery, not just the AIMD math:**
- `CircularBufferREPS::peek_earliest_fresh()` (new, non-destructive) plus the already
  non-mutating `is_valid_frozen()` let `predictWindowForNextEntropy_freezing()` predict,
  read-only, which window the *next* (not-yet-drawn) EV will land in — needed because the
  admission gate must decide before the real (destructive) draw happens. Single-threaded
  event-driven sim guarantees nothing mutates the buffer between predict and draw; a
  runtime mismatch counter (`_dual_predict_mismatch_count`, printed on flow finish) is the
  proof, not just the comment. One caveat found and fixed during verification: `startFlow()`
  has its own send loop that calls `sendNewPacket()` directly, bypassing the
  `_sender_based_cc` admission gate entirely for *every* CC algo (not just this one) — no
  prediction precedes those sends, so the mismatch check only counts a round where
  `_dual_gate_predicted_tag != WIN_NONE`.
- The window tag is decided once, at send time, and stored on `sendRecord.win_tag`
  (`createSendRecord`'s new parameter) — never re-derived later. NACK/RTO paths read it
  from the `_tx_bitmap` entry *before* erasing it (mirrors the existing `sent_ev` capture
  pattern). Retransmission carries the tag forward via a small side map
  (`_rtx_win_tag: seqno -> WindowTag`), since `_rtx_queue`'s value type is a bare `mem_b`.
- `_win_safe.in_flight` / `_win_random.in_flight` (on the new `MprdmaWindow` struct) are
  the single source of truth for per-window in-flight bytes — deliberately *not* mirrored
  into separate top-level fields, to avoid two counters that could silently diverge.
  Runtime-asserted invariant (gated to this algo only, so zero cost/risk for every other
  run): `_win_safe.in_flight + _win_random.in_flight == _in_flight`, checked at the end of
  `processAck`, `processNack`, and `rtxTimerExpired`.
- `handleAckno`/`handleCumulativeAck` gained optional `safe_bytes`/`random_bytes` output
  params: each function already walks `_tx_bitmap` entries per-ACK to erase them, so the
  per-window byte split rides that existing walk for free.
- `mark_packet_for_retransmission()` — a third site (besides ACK/NACK) that touches
  `_in_flight` and `_cwnd` together on RTO — gained a `WindowTag` parameter, easy to miss
  if only the ACK/NACK/RTO triad is checked.

**A real bug was caught and fixed during verification** — worth stating plainly rather
than folding into the "verified" summary. The aggregate `_in_flight -= newly_recvd_bytes`
(receiver-reported cumulative counter) and the per-window decrement (a sender-side
reconstruction, summed from which `_tx_bitmap` entries this ACK round actually erased)
can diverge under real loss/reordering — flagged as an accepted approximation while
designing, but not recognized as something that could break the hard invariant until a
16-flow tornado run under real congestion tripped `assertDualWindowInvariant()`. Fix:
for `DUAL_MPRDMA_REPS`, `_in_flight` is corrected to track the *same* sum the per-window
counters use (`processAck`, right after the per-window decrement) instead of trusting
`newly_recvd_bytes` independently — makes the invariant true by construction rather than
by accident, for this algo only, everyone else unaffected.

**A second false alarm, not a bug**: several single-flow crashes hit while widening test
coverage (bigger flow, more paths, smaller cwnd, a 1024-node topology) all turned out to
be **stale incremental build artifacts** inside the Docker test container — switching
source files into a live container across several experiments without `make clean`
between them produced a binary that segfaulted at flow start, and crashed *identically*
under baseline `mprdma` too (which made it look pre-existing at first). A full `make
clean` in both `htsim/sim/` and `htsim/sim/datacenter/` resolved it; every one of those
configs then ran cleanly on both algos. Lesson for next time: this is the in-container,
incremental-build sibling of the host-vs-container `GLIBCXX`/`GLIBC` gotcha CLAUDE.md
already documents for the bind-mount workflow — when reusing one container across
several source pushes, `make clean` before trusting a crash.

Verified, on a clean Docker build:
- **Flag-off**: `-sender_cc_algo mprdma` produces identical core simulated behavior
  (finish time, cwnd trajectory, packet/RTS counts) to the pre-change tree.
- **Single-flow, healthy fabric**: completes, invariant clean, `predict_mismatch_count=0`.
  Safe window's AI branch exercised (its cwnd is pinned at `_maxwnd` the whole run only
  because it starts there by design and never sees an ECN mark in a healthy single flow —
  not because the branch didn't run).
- **Single-flow, injected link failure** (141 RTOs, 1 freeze/unfreeze cycle, both
  `EVSRC_FROZEN_POP_VALID` and `EVSRC_FROZEN_POP_STALE` exercised): completes, invariant
  clean, mismatch 0.
- **16-flow tornado, real congestion** (the run that caught the bug above, post-fix):
  all 16 flows complete, invariant clean and mismatch 0 on every one, ECN activity
  58-757 marks/flow, and — the coverage gap the two single-flow runs left open — the
  safe window's **MD** branch fires too (`safe_cwnd` ends visibly below `_maxwnd`,
  506102-910782 across the 16 flows, instead of pinned at the 937926 ceiling).
- `-disable_tor_ecn` confirmed present (`enable on tor downlink 0` in stdout) in every
  test command.
- CLI correctly hard-errors when `dual_mprdma_reps` is combined with a non-`freezing`
  LB algo.

**Not yet exercised**: the idle-reset path (`-window_idle_reset_rtts`, needs a flow with
a genuine idle gap on one window while the other stays active); non-default
`-dual_safe_cwnd_init`/`-dual_random_cwnd_init` values; `EVSRC_PXR_POP`/`EVSRC_PXR_RANDOM`
(the `FREEZING_PXR` LB variant was noted as lower-priority throughout and was not run).

**Code-review pass found and fixed four real issues** after the above verification:
1. `dualWindowBlocked()` (and the matching idle-reset call in `processAck`) called
   `maybeIdleReset()` *before* checking `_loss_recovery_mode` — an idle window (0
   in-flight) could get reset to its full ceiling mid-recovery, silently undoing
   whatever MD had already applied to it. Fixed: loss-recovery check now runs first;
   idle-reset only runs when the flow isn't in recovery.
2. `-window_idle_reset_rtts` took an unchecked `(uint32_t)atoi(...)` — a negative
   argument wrapped to `UINT32_MAX`, silently disabling idle-reset instead of erroring.
   Fixed: rejects non-positive values with a clear CLI error.
3. The `DUAL_MPRDMA_REPS`/`freezing` compatibility guard only checked the global
   `-load_balancing_algo`, not per-host `-host_lb_overrides` — a host overridden to a
   non-freezing algo never sets `_last_ev_source`, guaranteeing an invariant-assert abort
   on that host's first ACK. Fixed: guard now rejects any override that isn't `freezing`.
4. No guard existed against combining `dual_mprdma_reps` with `-state_aware_ecn`/
   `-smart_filter_mode`/`-wtd_in_nscc` — those are NSCC-specific extensions that
   `updateCwndOnAck_DualMPRDMA` never consults, so the flags would silently no-op rather
   than error. Fixed: guard now rejects the combination explicitly.

All four were re-verified: single-flow healthy, single-flow with failure, 16-flow tornado
congestion, and combined tornado+failure all still complete cleanly (invariant clean,
mismatch 0) on a clean Docker build after the fixes; each new guard confirmed to fire with
a clear error on the misconfiguration it targets.

A fifth, cosmetic finding (three widened function signatures — `handleAckno`,
`handleCumulativeAck`, `mark_packet_for_retransmission` — lacked an `// ===== ADDED =====`
banner directly on the changed signature line, per this repo's own convention) was also
fixed; no behavior change.

Four review findings were about **pre-existing code this task didn't touch**. One
(`-fail_src_paths` blackholing 100% of a source's traffic instead of a fraction when used
without SRv6/PATH_RR/RANDOM/STATIC) was flagged and left unfixed as out of scope, at the
user's direction. The other three were fixed at the user's later request — see
`reps-metrics-per-host-key` and `timed-failure-guards` in `htsim/sim/CLAUDE.md`'s
modifications table: `g_reps_metrics` rekeyed from `_node_num` (per-flow) to `_srcaddr`
(per-host, matching its own "per-host" framing); `-timed_window`/`-timed_fail_tor_uplinks`/
`-timed_fail_tor_downlinks` now hard-error if combined with `-fail_link_time`/
`-fail_link_target` (previously silently overlapping) or run on a non-2-tier topology
(previously silently mislabeled ToR<->Agg links as "uplink tor", implying spine/core).

**A second, independent Opus-model review pass** (requested by the user specifically to
re-check the dual-window mechanism after the first round's fixes) found five further real
issues, the first two severe enough to be worth detailing:

1. **HIGH — permanent `_in_flight` leak.** The rtx-queue give-back branches in
   `handleAckno`/`handleCumulativeAck` (`_in_flight += pkt_size`, restoring bytes for a
   packet that got cumulatively ACKed before its queued retransmit actually fired) exist
   only to cancel a double-decrement against the *receiver-reported* `newly_recvd_bytes`
   counter — a cancellation this algo's own correction (found by the first bug, see above)
   already made unnecessary, since `_in_flight` no longer follows `newly_recvd_bytes` for
   this algo. Applying the give-back anyway created a **permanent phantom increment on
   both `_in_flight` and the per-window counter** for a packet that no longer exists — the
   invariant assert couldn't catch it because both sides leaked equally. Left unbounded,
   this eventually wedges a window's admission gate shut forever (`maybeIdleReset`
   requires `in_flight == 0`, which becomes unreachable). Fixed: the give-back is now
   skipped entirely for this algo in both functions.
2. **HIGH — RTS control-packet records (tagged `WIN_NONE`, since RTS isn't attributed to
   either window and never increments `_in_flight` when sent) broke the invariant on
   RTO/NACK and could get silently misattributed into the random window.** Fixed in four
   places: `updateCwndOnAck_DualMPRDMA`/`updateCwndOnNack_DualMPRDMA` now early-return on
   `WIN_NONE` instead of a `(tag==WIN_SAFE)?safe:random` ternary that silently mapped it to
   random; `mark_packet_for_retransmission`, `processNack`, and `fastLossRecovery` now skip
   the aggregate `_in_flight -=` for a `WIN_NONE` record (it was never added, so it must
   not be subtracted); `queueForRtx` now always records a tag (including `WIN_NONE`,
   previously skipped) so `sendRtxPacket`'s lookup can tell "genuinely untagged" apart from
   "not found" — its fallback on a miss changed from `WIN_RANDOM` (silent misattribution)
   to `WIN_NONE` (inert).
3. **HIGH — no guard required `-sender_cc_only` alongside `dual_mprdma_reps`.** Without it,
   `receiver_driven` stays true, `initRccc` runs instead of `initNscc` (only the latter
   initializes the dual windows), both windows' `cwnd` stay at their default-member value
   of 0, the admission gate wedges shut immediately (`0 <= 0`), and — since `startFlow()`'s
   own send loop bypasses the gate — the first ACK divides by a zero `cwnd` in
   `updateCwndOnAck_DualMPRDMA`'s AI branch (integer division by zero, SIGFPE). Fixed with
   an explicit startup guard, plus a defensive floor (`if (w.cwnd < _mtu) w.cwnd = _mtu;`)
   in the AI branch itself as cheap belt-and-suspenders.
4. **MEDIUM — `_cwnd` itself never grows under this algo** (its update is dispatched
   explicitly, bypassing the shared `updateCwndOnAck`/`updateCwndOnNack` pointers entirely)
   **but several pre-existing readers still consult it**: the RTS-gate check in
   `rtxTimerExpired`, `fastLossRecovery`'s threshold/pacing, `computePullTarget`'s clamp.
   Left alone, `_cwnd` only ever decayed toward `_mtu` and never recovered, so every RTO
   spuriously sent an RTS instead of retransmitting immediately (an extra RTT added to
   every loss-recovery cycle in exactly the failure scenarios this mechanism targets).
   Fixed: new `syncDualCwnd()` keeps `_cwnd` as a derived mirror of
   `_win_safe.cwnd + _win_random.cwnd`, called after every write to either window's cwnd
   (AI/MD, idle-reset, RTO decrement, init, unfreeze) — every pre-existing reader now gets
   a sane aggregate value without needing to be individually made dual-aware.
5. **LOW (two items).** `startFlow()` didn't clear `_rtx_win_tag`/`_dual_gate_predicted_tag`
   on flow reactivation (a real path for long-lived `UecSrc` objects, per the existing
   `_owns_circular_buffer_reps` comment) — fixed, both now reset alongside the existing
   `_in_flight` resets there. `timeToSend`'s loose post-send re-check ignored loss
   recovery (the single-window branch it replaces honors it) — fixed to match
   `dualWindowBlocked()`'s own loss-recovery exception.

All five re-verified: single-flow healthy, single-flow-with-failure, 16-flow tornado
congestion, and combined tornado+failure all still complete cleanly (invariant clean,
mismatch 0) on a clean Docker build; the new `-sender_cc_only` guard confirmed to fire.
One informational-only note from this pass, not acted on: `CircularBufferREPS::peek_earliest_fresh`
(added for the predictor) ended up unused — `predictWindowForNextEntropy_freezing` only
ever needs the trust tier, not the EV value, so it gets by with the buffer's existing
state accessors. Left in place as a correct, documented utility rather than removed.

### New CLI flags (`htsim/sim/datacenter/main_uec.cpp`)

    -sender_cc_algo dual_mprdma_reps
        New Sender_CC value. Requires -load_balancing_algo freezing (hard error otherwise).

    -window_idle_reset_rtts <N>          (default 2)
        A window with no ACK/NACK attributed to it for N*_base_rtt, and currently
        zero in-flight bytes, resets to its own configured init value.

    -dual_safe_cwnd_init <pkts>          (default 0 = _maxwnd)
    -dual_random_cwnd_init <pkts>        (default 0 = existing -cwnd / _maxwnd fallback)
        Per-window init/reset target, independently overridable.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `EvSource`: `EVSRC_FROZEN_POP_VALID`/`EVSRC_FROZEN_POP_STALE` appended; `WindowTag` enum + `MprdmaWindow` struct + `evSourceToWindowTag()` decl (public, near `EvSource`); `Sender_CC`: `DUAL_MPRDMA_REPS` appended; `sendRecord` gains `win_tag`; `_win_safe`/`_win_random`/`_safe_cwnd_init`/`_random_cwnd_init`/`_dual_predict_mismatch_count`/`_dual_gate_predicted_tag`/`_rtx_win_tag` fields; `_dual_safe_cwnd_init_flag`/`_dual_random_cwnd_init_flag`/`_dual_window_idle_reset_rtts` public statics (CLI-set); new method decls (`updateCwndOnAck_DualMPRDMA`, `updateCwndOnNack_DualMPRDMA`, `predictWindowForNextEntropy_freezing`, `maybeIdleReset`, `dualWindowBlocked`, `dualPeekNextWindowTag`, `assertDualWindowInvariant`); `createSendRecord`/`queueForRtx`/`mark_packet_for_retransmission`/`handleAckno`/`handleCumulativeAck` signatures extended with optional tag/output params | `-sender_cc_algo dual_mprdma_reps` |
| `htsim/sim/uec.cpp` | Static defs for the 3 new CLI-set statics; `nextEntropy_freezing()`'s frozen-pop branch split (gated to this algo); `predictWindowForNextEntropy_freezing`/`evSourceToWindowTag`/`maybeIdleReset`/`dualPeekNextWindowTag`/`dualWindowBlocked`/`assertDualWindowInvariant` impls; `updateCwndOnAck_DualMPRDMA`/`updateCwndOnNack_DualMPRDMA` (MPRDMA formula, per-window); `DUAL_MPRDMA_REPS` case in the CC dispatch switch (bound to no-op stubs — real dispatch is explicit at the ACK/NACK call sites, not through the shared function pointer); 3 admission-gate sites (`sendIfPermitted`, `timeToSend` pre-send + loose post-send recheck) branch on the algo; `processAck` accumulates per-window ACKed bytes across `handleCumulativeAck`/the SACK loop and calls the dual update twice; `processNack`/`fastLossRecovery`/`rtxTimerExpired` capture `win_tag` before erasing the `_tx_bitmap` entry and thread it through `queueForRtx`/`mark_packet_for_retransmission`; `handleAckno`/`handleCumulativeAck` gain the output params and the rtx-queue give-back branches restore per-window in-flight via `_rtx_win_tag`; `sendNewPacket`/`sendRtxPacket` resolve/carry the tag and pass it to `createSendRecord`; `initNscc` seeds `_safe_cwnd_init`/`_random_cwnd_init`/both windows' cwnd when this algo is active; unfreeze branch in `processEv_freezing` resets both windows to their own init; flow-finish log line prints the mismatch counter + final window state when this algo is active | `-sender_cc_algo dual_mprdma_reps` |
| `htsim/sim/buffer_reps.h`/`.cpp` | `peek_earliest_fresh()` — non-destructive counterpart to `remove_earliest_fresh()`, same offset arithmetic, no mutation, returns `false` instead of throwing | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | `dual_mprdma_reps` branch in `-sender_cc_algo` parsing; `-window_idle_reset_rtts`/`-dual_safe_cwnd_init`/`-dual_random_cwnd_init` flags; post-parse compatibility guard (hard error if this algo is selected without `-load_balancing_algo freezing`) | own flags |

## `dual-window-cwnd-cap` — combined safe+random cwnd budget (v2 of `dual-window-reps-mprdma`)

Banner `// ===== ADDED (dual-window-cwnd-cap) =====`. New `Sender_CC` value
`DUAL_MPRDMA_REPS_CAP` (`-sender_cc_algo dual_mprdma_reps_cap`), a v2 of `DUAL_MPRDMA_REPS`
sharing the same EV/window-attribution plumbing but enforcing
`_win_safe.cwnd + _win_random.cwnd <= _maxwnd` (a combined budget) instead of each window
getting its own independent `_maxwnd` ceiling — v1's confirmed cause (see the note in the
section above) of dual-window B=8 running far higher ECN/RTO than plain MPRDMA B=8 at the
same severity.

**By explicit user request, this is implemented as a separate algo/new parallel functions,
not a flag on `DUAL_MPRDMA_REPS`** — every original dual-window function (`updateCwndOnAck_DualMPRDMA`,
`maybeIdleReset`, `initNscc`'s v1 branch, the unfreeze reset block) is **byte-for-byte
untouched**; v2 adds new sibling functions (`updateCwndOnAck_DualMPRDMA_Cap`,
`maybeIdleReset_Cap`) and a new `initNscc` branch, and reuses v1's shared plumbing (admission
gate, EV→window tagging, `sendRecord.win_tag` threading, the invariant assert, NACK/MD,
`mark_packet_for_retransmission`) by widening each dispatch condition to recognize
`DUAL_MPRDMA_REPS_CAP` too (verified: every `_sender_cc_algo == DUAL_MPRDMA_REPS` site in
`uec.cpp`/`uec.h`/`main_uec.cpp` was audited and either widened or deliberately left
unwidened, per rule below). Confirmed via test: `DUAL_MPRDMA_REPS` runs produce byte-identical
`safe_cwnd=625284 random_cwnd=626650` finish-line output before and after this change.

**Locked design** (resolved with the user + an advisor consult this session — the user's
initial literal wording for the normal-state rule had a real flaw, caught and revised before
implementing, see below):

1. **Flow start (`initNscc`)**: both windows default to **1x `_bdp`**, not v1's asymmetric
   `_maxwnd`/`_cwnd` defaults — a deliberate revision, not an oversight (the two windows now
   share one budget, so starting both at the same conservative value is the correct
   baseline). Still independently overridable via the same `-dual_safe_cwnd_init` /
   `-dual_random_cwnd_init` flags v1 uses.
2. **Freeze entry**: no change — cwnd already updates normally through frozen mode for both
   v1 and v2.
3. **Freeze exit (unfreeze)**: **no special-case at all**, by explicit user correction (an
   earlier "safe inherits random's cwnd" idea was dropped as unnecessary complexity) — cwnd
   just continues through the unfreeze event unchanged. Implemented as an *absence*: v2 is
   simply not added to `processEv_freezing`'s reset-to-init condition, so it never matches.
4. **Idle reset**: new `maybeIdleReset_Cap(w, init_val, other)` — target is
   `min(init_val, max(_mtu, _maxwnd - other.cwnd))` instead of v1's flat `init_val`, so an
   idle window can't single-handedly re-inflate the combined sum past the cap. Never touches
   `other.last_active`.
5. **Normal-state AI** (sum-before-this-ACK `<= _maxwnd`) — **headroom-first**: own window
   always gets the full AI increment; only reach into the other window for the *overflow* if
   growing would cross the cap. Chosen over the user's initial literal "grow one, shrink
   other by the same amount" wording, which was flagged and revised because it makes the
   combined sum permanently non-recoverable after any MD event (redistribution nets to zero,
   so nothing ever grows the sum — an MD's reduction would be permanent for the rest of the
   flow) and would stall warmup (sum could never climb from ~1 BDP toward the 1.5 BDP cap).
6. **Over-cap state** (sum-before-this-ACK `> _maxwnd`, reachable e.g. right after warmup
   when both windows start at 1x BDP, summing to ~1.33x the cap): own window does not grow;
   shrink the other window by the plain AI increment (~1 MTU/RTT). Verified in a real run
   (exp29-style F=31 scenario): sum starts at `max_sum_ratio_x1000=1333` (1.333x cap, exactly
   matching 2x BDP / 1.5x BDP), converges to exactly `sum == _maxwnd` within ~40us
   (`last_over_cap_at_us`), stays there for the remainder of the ~350-400us flow.
7. **MD / NACK / RTO / `mark_packet_for_retransmission`**: unchanged, fully independent per
   window, shared with v1 (dispatch conditions widened, function bodies untouched) — these
   only ever decrease a window's cwnd, so they can't violate the cap.

**Verification aids** (`DUAL_MPRDMA_REPS_CAP` only, finish-line print): `max_sum_ratio_x1000`
(peak observed `(win_safe.cwnd+win_random.cwnd)/_maxwnd`, x1000) and
`last_over_cap_at_us` (0 if the sum was never seen over cap) — lets a run be checked for
whether/how often the cap actually binds without re-instrumenting. Since the designed startup
overshoot (rule #6 above, ~1.333x) dominates `max_sum_ratio_x1000` on every default-init flow,
a second field, `max_sum_ratio_after_converge_x1000`, tracks the peak only from the first time
the sum is seen at-or-under cap onward (via a shared `trackDualCapSumRatio()` helper, called
from both the AI/MD update and `maybeIdleReset_Cap` — the idle-reset floor
`max(_mtu, _maxwnd-other.cwnd)` can itself leave the sum slightly over cap, a case the AI/MD-
only version of this diagnostic missed) — a materially-elevated *post*-convergence value would
flag a real regression the startup-dominated field can't distinguish. Added during the Opus
code-review pass (see below), not the initial implementation.

**Verified this session**: build clean (after an intervening stale-incremental-build segfault —
see CLAUDE.md's Docker gotcha; `make clean` + full rebuild resolved it, not a real regression);
targeted runs (v1 F=8/F=31 unaffected-baseline checks, v2 F=8/F=24/F=31 at seed 43 — the
scenarios that originally surfaced the RTS-retransmit `_in_flight` leak bug fixed earlier this
session — plus a healthy no-failure run) all complete with `assertDualWindowInvariant` never
firing and `predict_mismatch_count=0`. The RTS-retransmit bug's fix (`sendRtxPacket`'s
`WIN_NONE` guard on the aggregate `_in_flight +=`) was explicitly re-verified as extended to
`DUAL_MPRDMA_REPS_CAP` too, not just v1, since the same bug would otherwise apply identically
there. **Independent Opus subagent code review** (requested explicitly, full transcript in
session history): no HIGH/MEDIUM findings; confirmed v1 is byte-for-byte untouched (every v1
function absent from the diff, or widened only in provably-equivalent ways), every
`_win_safe`/`_win_random` mutation site accounted for, the RTS-leak guard correctly widened at
all 6 `_in_flight` sites plus the tag-lookup site, and the arithmetic verified correct by hand.
5 LOW/informational findings, all addressed: two diagnostic-only gaps (the
`max_sum_ratio_after_converge_x1000` field above, and resetting the new per-flow diagnostic
fields on `startFlow()` reactivation, matching the existing pattern for `_rtx_win_tag` etc.)
and a new startup warning if `-dual_safe_cwnd_init`/`-dual_random_cwnd_init` are set to sum
above `_maxwnd`. Two findings left as documented, intentional behavior (not fixed): the startup
overshoot itself (design consequence, not a bug) and a negligible (~1 `inc`) within-ACK
ordering bias favoring the safe window when one ACK covers both windows.

    -sender_cc_algo dual_mprdma_reps_cap
        New Sender_CC value, v2 of dual_mprdma_reps. Same compatibility requirements
        (-load_balancing_algo freezing, -sender_cc_only, no -host_lb_overrides with a
        non-freezing algo, incompatible with -state_aware_ecn/-smart_filter_mode/-wtd_in_nscc)
        as dual_mprdma_reps - the existing compatibility guard block was widened to check
        for either algo rather than duplicated.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `Sender_CC`: `DUAL_MPRDMA_REPS_CAP` appended (after `DUAL_MPRDMA_REPS`); new method decls `updateCwndOnAck_DualMPRDMA_Cap`/`maybeIdleReset_Cap`; new fields `_dual_cap_max_sum_ratio_x1000`/`_dual_cap_last_over_cap_at` | `-sender_cc_algo dual_mprdma_reps_cap` |
| `htsim/sim/uec.cpp` | New functions `updateCwndOnAck_DualMPRDMA_Cap`/`maybeIdleReset_Cap` (rules #4-#6); new `initNscc` branch (rule #1); `dualWindowBlocked()` dispatches to the capped idle-reset internally when this algo is active; every `_sender_cc_algo == DUAL_MPRDMA_REPS` plumbing check widened to also recognize this algo (admission gate, EV/window tagging, invariant assert, `syncDualCwnd`, NACK dispatch, the RTS-retransmit-bug guard in `sendRtxPacket`, the CC dispatch switch's no-op case) — audited exhaustively, one site (`processEv_freezing`'s unfreeze reset) deliberately *not* widened per rule #3; finish-line print extended with the two new diagnostic fields | `-sender_cc_algo dual_mprdma_reps_cap` |
| `htsim/sim/datacenter/main_uec.cpp` | `dual_mprdma_reps_cap` branch in `-sender_cc_algo` parsing; compatibility guard condition widened to include this algo | own branch, shared guard |

## `dual-cwnd-log` — per-window cwnd time series for `dual-window-reps-mprdma`/`-cwnd-cap`

New CSV logger, banner `// ===== ADDED (dual-cwnd-log) =====`. No existing logger captured
`_win_safe.cwnd`/`_win_random.cwnd` separately over time — `-log_cwnd` only logs the combined
`_cwnd`, `-log_reps_state`/`-log_reps_events` don't carry cwnd at all, and the one place both
windows print separately was a `cout` debug line gated on `_debug_flowid`, which no CLI flag
ever wired up. Hooked into `syncDualCwnd()` (the single choke point every dual-window cwnd
mutation already calls through — init, AI, NACK/MD, RTO-path decrease, idle reset, unfreeze
reset — verified exhaustively against every `_win_safe.cwnd =`/`w.cwnd =` assignment site)
rather than the ACK/NACK call sites, so RTO and idle-reset dynamics are captured, not just
per-ACK state. Values are raw bytes, not divided into packets — per-ACK AI increments are
sub-packet and would truncate to 0 under `-log_cwnd`'s `cwnd / get_avg_pktsize()` convention.
Filtered on `_srcaddr` (physical src id — what every experiment's "affected" grouping uses),
not `_node_num` — the same distinction `reps-metrics-per-host-key` above already had to fix
once for a different counter table. Shared by both `DUAL_MPRDMA_REPS` and
`DUAL_MPRDMA_REPS_CAP` (`syncDualCwnd()` already early-returns for every other algo, so the new
log call inherits that gate with no extra condition). Feature-off cost: one pointer null-check
per `syncDualCwnd()` call, no allocation, no formatting — same overhead class as `-log_cwnd`.

CSV columns: `time_us,srcaddr,node_num,flow_id,safe_cwnd,random_cwnd,maxwnd,safe_in_flight,
random_in_flight,frozen`. No combined-cwnd column (trivially `safe_cwnd + random_cwnd`).
`frozen` reads `circular_buffer_reps->isFrozenMode()` at the same instant, so a trace can be
read standalone to see cwnd behavior across a freeze/unfreeze cycle; join on `time_us` against
a `-log_reps_events` run of the same source for FREEZE/UNFREEZE/RTX/NACK event context.

Schema documented in [`experiments/tools/README.md`](tools/README.md) alongside
`-log_reps_state`/`-log_reps_events`.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `static FILE* _dual_cwnd_log;` / `static std::set<uint32_t> _dual_cwnd_log_srcs;` (next to the existing `-log_cwnd` statics) | `-log_dual_cwnd` |
| `htsim/sim/uec.cpp` | Static defs; one `fprintf` block inside `syncDualCwnd()`, after the existing `_sender_cc_algo` early-return and the `_cwnd = ...` sync line | `-log_dual_cwnd` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-log_dual_cwnd <file>` (opens file, writes header), `-log_dual_cwnd_src <id>` (repeatable, empty = log all dual-window sources) | own flags |

### `[ADDED: reps-soft-replay]` — gated by `-reps_soft_replay`

Continuous randomize<->safety knob on `nextEntropy_freezing()`'s **non-frozen fallback branch
only** (the `isEmpty() || getNumberFreshEntropies() == 0` case, which today is always a pure
random draw). With probability `_exp_avg_ecn` (the flow's own existing per-ACK ECN EWMA, α=0.125
-- original NSCC code, not another addition's state), the fallback instead replays a
recently-seen EV from the ring instead of drawing fully random. With probability `1 -
_exp_avg_ecn`, draws random as today -- a continuous blend, not a threshold, so there's no
flip-flop point.

Replay candidate selection cycles `_soft_replay_cursor` over EV-id space `[0, _no_of_paths)`
(bounded, cheap under SRv6 where EV<->path is 1:1), checking each candidate against
`containsEntropy()` -- an **original** `CircularBufferREPS` method that matches a slot's stored
value whether or not that slot is still marked valid, so it finds EVs the buffer has forgotten
were ever "fresh" as well as ones still formally in the fresh pool. Skips any candidate this
feature's own new per-EV scoreboard (`_soft_replay_ev_ecn`) last saw ECN-marked, so a replayed EV
that comes back ECN-marked drops out of the eligible set on its own -- the mechanism can't get
stuck repeatedly replaying a path it already knows is congested. If every candidate is skipped,
or the buffer is completely empty (`getSize() == 0`), falls through to the original unconditional
random draw unchanged.

**Depends only on original code** (`CircularBufferREPS::containsEntropy`/`getSize`,
`UecSrc::_exp_avg_ecn`/`average_ecn_bytes()`) -- does not read, require, or depend on any other
addition's gated state (e.g. `ev-health-counter`'s `_ev_last_ecn_state` or `freezing-pxr`'s
`_pxr_excluded_evs`). This feature's own scoreboard (`_soft_replay_ev_ecn`) is a new,
self-contained field with the same shape as `ev-health-counter`'s for reference only, not a
dependency on it -- works standalone with no other addition's flag set.

**Scope (v1)**: non-frozen mode only. `processEv_freezing`, `add()`, `resetBuffer()`, and
`explore_counter` are all untouched -- frozen-mode behavior, the unfreeze reset, and the
forced-random explore burst after unfreeze are all byte-identical to vanilla FREEZING regardless
of this flag. No original line was deleted or edited in place; every change is a new branch
reached only through the new `if (_reps_soft_replay ...)` guard.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `static bool _reps_soft_replay;` (next to `_nscc_wtd_enabled`); per-source `uint16_t _soft_replay_cursor` + `vector<bool> _soft_replay_ev_ecn` (next to `_crt_path`) | `-reps_soft_replay` |
| `htsim/sim/uec.cpp` | Static def; scoreboard update in `processAck()` right after the existing `average_ecn_bytes()` call; replay branch inside `nextEntropy_freezing()`'s non-frozen fallback, ahead of the original random-draw line | `-reps_soft_replay` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-reps_soft_replay` (bool flag, no argument); `-reps_soft_replay_fixed_p <val>` (validation ablation -- fixes `P` instead of using `_exp_avg_ecn`, e.g. `1.0` for an always-attempt-replay arm); `-reps_soft_replay_no_filter` (validation ablation -- disables the ECN-skip filter) | own flags |

**Validation ablation knobs**: `-reps_soft_replay_fixed_p`/`-reps_soft_replay_no_filter` exist
solely to let the brainstorm plan's 4-arm comparison (baseline / fixed-P=1 / EWMA-gated /
EWMA-gated-no-filter) reuse one code path instead of four separate implementations. Both are
no-ops unless `-reps_soft_replay` is also passed.

### `[ADDED: upstream-sync-2026-03]` — inert hooks ported from Broadcom/csg-htsim, no gate

Ports upstream commits `0639f63`, `20b2297`, `841d9e7` (HEAD `841d9e7`, 2026-03-23). Upstream's public tree has no consumer for any of these; they exist for API compatibility and future merges. Behavior is unchanged unless a `.cm` file uses the new `addon` token (which still only sets an unread field).

| File | What |
|------|------|
| `htsim/sim/eth_pause_packet.h` | `_pausedClass` member (default 0) + `getPausedClass()`/`setPausedClass()` |
| `htsim/sim/datacenter/connection_matrix.h` | `connection::addOnTriggerSignal` (default `false`, so the other `new connection` sites are initialized too) |
| `htsim/sim/datacenter/connection_matrix.cpp` | `.cm` connection token `addon` sets the field |
| `htsim/sim/trigger.h` / `trigger.cpp` | `BarrierTrigger::_n_members`, `activate(bool re_arm)` overload; **one original line edited**: `assert(_targets.size() > 0)` in `BarrierTrigger::activate()` commented out (as upstream) |

Skipped: upstream's `sim/tests/main_dumbell_tcp.cpp` hunk (file not present here). Upstream's `952f643` (`CNP` enum) already present.

### `[ADDED: ofan]` — gated by `-strat ofan`

Switch-side Ofan load balancer (arXiv 2610.07230): one round-robin pointer per destination group (dest edge switch at ToR, dest pod at Agg) and packet type on northbound hops, port order from a global permutation. Hosts unchanged. Architecture doc: [`experiments/OFAN_ARCHITECTURE.md`](OFAN_ARCHITECTURE.md); results: [`exp32_ofan/README.md`](exp32_ofan/README.md). With the flag absent, output is byte-identical (regression hashes in `exp32_ofan/baseline/`).

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/ofan_order.h` | New header-only math module (`namespace ofan`) | included by `fat_tree_switch.cpp` |
| `htsim/sim/datacenter/fat_tree_switch.h` | `OFAN = 6` in `routing_strategy`; statics `_ofan_hash_small`, `_ofan_identity_order`, `_ofan_count`, `ofan_dump_counts`; per-switch `_ofan_ptrs`; `ofan_choose()` | `-strat ofan` |
| `htsim/sim/datacenter/fat_tree_switch.cpp` | `ofan_choose()` and counter map; `case OFAN` in `getNextHop`; both `permute_paths` call sites for up-route vectors skipped when `_strategy == OFAN` (keeps a stable port order per switch) | `_strategy == OFAN` |
| `htsim/sim/datacenter/main_uec.cpp` | `-strat ofan` (sets `ECMP_FIB`, `path_entropy_size=1`); `-ofan_ack_mode spray\|hash`, `-ofan_identity_order`, `-log_ofan_counts`; post-parse guard (error with `-use_srv6`, `path_*` LB, `-host_lb_overrides`; re-forces `path_entropy_size=1`); counts dump at end of run | `-strat ofan` / the flags |

### `[ADDED: routing-convergence]` � gated by `-routing_convergence_us <G>`

Failure-knowledge model for switch-side load balancers (paper "Modeling routing convergence": one parameter G, the same for every switch). A pipe failed at `t_fail` and restored at `t_recover` is *known down* iff `t_fail+G <= now < t_recover+G`; before that switches keep forwarding into the dead pipe (`Pipe::_failed` drops the packets). Once known, every multi-entry FIB set is filtered to the entries that still reach the destination ToR. Applied identically to `ofan`, `ecmp_host`, `ecmp_ar`, `ecmp_rr`, `rr_ecmp`, `ecmp_host_ar`. Under the flag Ofan's legacy instant local `Pipe::isFailed()` skip is disabled. Hard errors: `-failures_input`, `-routing_check` without the flag. Out of scope: `-failed N` degradation, host links, FAILURE_GENERATOR failures. Design and limits: [`OFAN_ARCHITECTURE.md`](OFAN_ARCHITECTURE.md) section "Failure convergence model". With the flag absent, output is byte-identical (regression hashes in `exp32_ofan/baseline/`, checked after this change).

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/pipe.h` / `pipe.cpp` | static `_rc_drop_hook`, `_rc_drops_before_known`, `_rc_drops_after_known`; counted in the existing `_failed` drop branch | hook non-NULL only with the flag |
| `htsim/sim/datacenter/fat_tree_switch.h` | `namespace RoutingConvergence` (failure view, epoch, counters, check API); `RcKey/RcEntry` cache, `rc_lookup`, `rc_agg_reaches`, public `rc_compute_mask`; `ofan_choose` gets optional mask arg | `RoutingConvergence::enabled` |
| `htsim/sim/datacenter/fat_tree_switch.cpp` | failure view (time-derived epoch), `rc_compute_mask`/`rc_lookup` (cache per source FIB vector pointer x dst ToR x epoch; original vector returned untouched when all entries valid; dead end => unfiltered), filtering in `getNextHop`, decision counter, flowlet-AR map clear per epoch + index guard, legacy Ofan local skip disabled, independent brute-force reference + `run_check` | `RoutingConvergence::enabled` / `check` |
| `htsim/sim/datacenter/main_uec.cpp` | `LinkFailureEvent` registers each pipe it fails; flags `-routing_convergence_us <G us, fractional ok, huge = never converges>`, `-routing_check`, hidden `-routing_check_random <trials> <seed> <p>`; errors listed above; check events at t=0 and every knowledge transition + final check; end-of-run `ROUTING_CONV decisions_to_known_dead=<n> drops_before_known=<n> drops_after_known=<n>` and (check) `ROUTING_CHECK mismatches=<n>` | the flags |
| `htsim/sim/datacenter/main_uec.cpp` + `fat_tree_switch.cpp` (hidden flag) | `-routing_check_random <trials> <seed> <p>`: knowledge-only test; random subset (prob p) of ALL pipes of the reference edge list (4 arrays, all bundle members) as the known-down set, `Pipe::_failed` untouched, synthetic production-vs-reference comparison for every (switch, dst ToR), real known set restored; requires `-routing_check`. Also: hard errors for source-routed algos / `-fail_src_paths` / `-sol_avoid_timed_failure` / non-finite or negative G; `-routing_check` exits 1 at end of run when mismatches > 0; `drops_after_known` uses the failure interval in force at the drop. | the flag |
| `experiments/exp32_ofan/scripts/rc_random.sh`, `rc_random_suite.sh`, `topologies/fat_tree_32_bundle2_3t_400g.topo`, `workloads/derange{8,32,432}_1mb_s42.cm` | driver for the random test over 16/54/128/432 3-tier, 32 2-tier and two bundle topologies (`*.cm` gitignored: regenerate with `gen_derangement.py`) | manual |
| `experiments/exp32_ofan/scripts/rc_check.py` | G2 driver: random failed-pipe sets x G x strategy on 16/54/128-host 3-tier and 32-host 2-tier | manual |
| `htsim/sim/datacenter/fat_tree_switch.{h,cpp}` + `main_uec.cpp` (`// ===== ADDED (ofan-trace) =====`) | `-log_ofan_trace <tsv>` (hard-requires `-strat ofan`; zero behaviour change when absent, baseline SHA256 identical): per `ofan_choose` decision one TAB line `D time_ps switch TOR/AGG swid pkttype size dst d Nd t w ptr_before chosen_fib_idx egress_queue`, once per (switch,key) an `I` line (data+ACK initial pointers), once per w a `P` line (shared permutation). Consumed by `experiments/exp32_ofan/scripts/ofan_reference.py` (independent model from paper Sec.4/App.F.2 eq.16-18, with corruption self-tests); driver `scripts/run_vtrace.sh`. Traces under `data/vtrace/` are not committed. | manual |
| `experiments/exp32_ofan/workloads/derange128_1mb_s42.cm`, `perm32_1mb_s42.cm` | check workloads (`*.cm` is gitignored: regenerate with `gen_derangement.py <out> 128 16 1048576 42`; `perm32` = seeded 32-host derangement) | n/a |

### `[ADDED: queue-stats]` — gated by `-log_queue_stats <file>`

Per-queue statistics dump used to validate Ofan (max data-queue occupancy, bytes, trims, drops, per fat-tree layer E->A, A->C, C->A, A->E, E->H). The counters in `CompositeQueue` are always updated (one compare/add per enqueue/dequeue, no behaviour change); the dump only runs with the flag. Analysis: `exp32_ofan/scripts/link_overload.py`.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/compositequeue.h` / `.cpp` | `_stat_max_low`, `_stat_max_total`, `_stat_bytes_low`, `_stat_bytes_high`, `_stat_pkts_low`; trims/drops reuse `_num_stripped` / `num_drops()` | counters always on; output gated |
| `htsim/sim/datacenter/main_uec.cpp` | `-log_queue_stats` flag and TSV writer | `-log_queue_stats` |

### `[ADDED: switch-baselines]` — gated by `-strat ecmp_rr_fixed|ecmp_random|ecmp_p2c` and `-ar_method exact`

Switch-side baselines for the Ofan paper reproduction (exp33; arXiv 2610.07230). Data-sized packets only; packets < 128 B (Simple RR) / < 100 B (others) are ECMP-hashed exactly like the existing `RR`/`ADAPTIVE_ROUTING` cases, so ACK/header handling matches the existing baselines. All three set `route_strategy = ECMP_FIB`, `path_entropy_size = 1` at parse time (use `-load_balancing_algo ecmp`; unlike `-strat ofan` there is no post-parse override, so a later `-paths` is not forced back to 1 and there is no `-use_srv6`/`path_*` guard). With a `-routing_convergence_us` failure model they run on the filtered vector through the generic path (verified by smoke run: all flows finish, `decisions_to_known_dead=0`).

| Flag | Paper name | Behaviour |
|------|-----------|-----------|
| `-strat ecmp_rr_fixed` (`RR_FIXED = 7`) | Simple RR | Like `ecmp_rr` but WITHOUT the per-round `permute_paths`: fixed port order, one switch-wide pointer `_crt_route` (shared by all destinations), `ptr % n_hops`. The two `permute_paths` call sites of the FIB build (TOR up-routes, AGG up-routes) are skipped for this strategy (same guard as OFAN), otherwise the order would still be a random-but-fixed shuffle per destination. |
| `-strat ecmp_random` (`RANDOM = 8`) | RSQ | Per-packet uniform random uplink `random() % n_hops`. Same libc `random()` stream as AR tie-breaking, so with `-q` large enough that every quantized queue reads 0 `ecmp_ar` is byte-identical to `ecmp_random` (observed, a useful sanity check). |
| `-strat ecmp_p2c` (`P2C = 9`) | Choice/P2C | Wires the previously unused `adaptive_route_p2c`: 2 uniform random draws (with replacement), pick the smaller exact `queuesize()`. |
| `-ar_method exact` | JSQ | New comparator `compare_queuesize_exact` on exact `queuesize()`; use with `-strat ecmp_ar`. Ties broken uniformly at random by the existing `adaptive_route`. The existing `queue` comparator is quantized to 5% of `maxsize()` (+ update period) and so degenerates to random at the large `-q` used for no-CCA runs. |

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/fat_tree_switch.h` | `RR_FIXED/RANDOM/P2C` enum values; `compare_queuesize_exact` | new strategies / `-ar_method exact` |
| `htsim/sim/datacenter/fat_tree_switch.cpp` | `compare_queuesize_exact`; three `case`s in `getNextHop`; `permute_paths` guards extended to `RR_FIXED` | as above |
| `htsim/sim/datacenter/main_uec.cpp` | `-strat` handlers and `-ar_method exact` | as above |
| `experiments/exp33_ofan_paper_repro/scripts/verify_baselines.sh` | 54 hosts, 1 MB permutation, no-CCA, per-layer max queue | manual |

### `[ADDED: dctcp-debug-gate]` — behaviour-preserving

The unconditional per-ACK `cout` at the top of `UecSrc::updateCwndOnAck_DCTCP` (`htsim/sim/uec.cpp`) is now guarded by `if (_debug)` (static `UecSrc::_debug`). No state change; only removes stdout volume (multi-GB at 432 hosts) for `-sender_cc_algo dctcp` runs.


### `[ADDED: ofan-weighted]` — `-strat ofan_weighted` (extension; not in the Ofan paper)

Ofan with the schedule weighted by the number of live shortest paths through each ToR uplink. Needs `-routing_convergence_us` (weights come from the known-down set). Implemented as `_strategy == OFAN` plus the static flag `FatTreeSwitch::_ofan_weighted`, so all existing OFAN branches apply unchanged. When the valid entries have equal weights the plain Ofan code path runs (byte-identical to `-strat ofan`). Design and results: `experiments/exp32_ofan/W1_weighted_ofan.md`. To revert: `git revert` the commit, or delete every `ADDED (ofan-weighted)` block.

| File | What | Gate |
|------|------|------|
| `htsim/sim/datacenter/ofan_order.h` | `gcd_int`, `normalize_weights`, `weighted_port`, `weighted_step` (new functions only; `step/pick/pi` untouched) | only called when weights differ |
| `htsim/sim/datacenter/fat_tree_switch.h` | `_ofan_weighted`; `ofan_choose(..., rc_weight)`; `_ofanw_ptrs`; `RcEntry::weight`; `rc_agg_paths`, `rc_compute_weights` | `-strat ofan_weighted` |
| `htsim/sim/datacenter/fat_tree_switch.cpp` | weighted branch in `ofan_choose`; weights in `rc_lookup` (an all-valid but unequal entry is returned); `rc_agg_paths`/`rc_compute_weights`; brute-force path-count reference (`ref_count`, `ref_weights`) in `-routing_check`; `ROUTING_CHECK_WEIGHTS` line | as above; check output only with `-routing_check` and the strategy |
| `htsim/sim/datacenter/main_uec.cpp` | `-strat ofan_weighted` handler; errors if used without `-routing_convergence_us` or with `-log_ofan_trace` | as above |
| `experiments/exp32_ofan/scripts/` | `run_w1.sh`, `summarize_w1.py`, `predict_link_load.py`, `gate_weighted.sh`, `rc_random_w.sh`, `rc_random_suite_w.sh`, `rc_check_w.py` | manual |


### `[ADDED: fail-pipes-file]` — `-fail_pipes_file <file>` (static random-failure sets)

Fails an arbitrary set of cables of a 3-tier fat-tree from 0.01 us for the whole run (both directions, bundle 0), reusing `LinkFailureEvent` so the failures are registered with the routing-convergence model. File lines: `C <agg> <core>` (Agg<->Core, global agg id) or `E <tor> <agg>` (ToR<->Agg, global ToR and agg ids); `#`/blank lines ignored. Errors if combined with `-fail_link_time`, on a non-3-tier topology, or for an unknown link. Used by exp33 E6 (Ofan paper Fig 9) with `scripts/fig9_instance.py`. Flag absent: no change.

| File | What | Gate |
|------|------|------|
| `htsim/sim/datacenter/main_uec.cpp` | variable `fail_pipes_file`, argument parsing, one block after the `-fail_link_*` scheduling | `-fail_pipes_file` |


### `[ADDED: rate-const-sender]` — `-rate_const_gbps <R>` (constant-rate sender; NIC egress shaper by default, `-rate_const_data_only` = old data-only pacer)

Per-source sender that injects data packets (new and retransmitted) at most at R Gbps of wire rate (packet size incl. header, i.e. `_mtu`-sized packets), independent of ACK arrival. Requires `-sender_cc_algo constant`; `cwnd` is forced to 1,000,000 packets so the window never binds. Gate `rateGate()` is checked at every data-send entry point; `rateCharge()` advances an absolute per-source schedule after each emitted data packet; a lazily-created `UecRatePacer` event wakes `sendIfPermitted()` at the next permitted time. RTS/control packets are not charged. Design and validation: [`RATE_CONST_ARCHITECTURE.md`](RATE_CONST_ARCHITECTURE.md). Flag absent: byte-identical (verified: full flow-finish lines incl. times and counters identical, tornado NSCC x32, 1024 lines).

**Semantics change (`rate-const-nic`, 2026-10-24).** The description above is the `-rate_const_data_only` behaviour. By default `-rate_const_gbps R` now shapes the whole NIC egress: port busy time of every packet the `UecNIC` sends (data, rtx, ACK/NACK/control) is `size/R` instead of `size/linkspeed` (`UecNIC::_egress_bps`, `egressSpeed()`), and the per-source pacer is bypassed (`rateGate()` true, `rateCharge()` no-op unless `-rate_const_data_only`). Motivation: in tornado every host also returns ACKs through the same (degraded) ToR uplinks, so a data-only rate of 200G offers 203G to a 200G uplink (rho 1.015) and REPS saw ~50% random EVs from standing-queue ECN marking; at R=197G data-only it was ~1% (meeting_23_10_26 M4 README). Requires a single-port NIC (error otherwise). Flag-absent and `-rate_const_data_only` runs are byte-identical to the pre-change binary (validation in `RATE_CONST_ARCHITECTURE.md`).

| File | What | Gate |
|------|------|------|
| `htsim/sim/uec.h` | `UecNIC::_egress_bps`, `egressSpeed()`; `UecSrc::_rate_const_data_only` | `rate-const-nic` |
| `htsim/sim/uec.cpp` | `startSending()` and `sendControlPktNow()` use `egressSpeed()`; `rateGate()`/`rateCharge()` bypass unless data-only | `_egress_bps > 0` |
| `htsim/sim/datacenter/main_uec.cpp` | `-rate_const_data_only` parse; sets `_egress_bps`; single-port check | `-rate_const_gbps` |

| File | What | Gate |
|------|------|------|
| `htsim/sim/uec.h` | `class UecRatePacer`; `UecSrc::_rate_const_bps`, `_rate_next_send`, `_rate_pacer*`, `rateGate/rateCharge/rateWake` | `_rate_const_bps > 0` |
| `htsim/sim/uec.cpp` | gate calls in `startFlow()` loop, `sendIfPermitted()`, `timeToSend()`, RTO-rtx path in `rtxTimerExpired()`; `rateCharge()` at the end of `sendNewPacket()` / `sendRtxPacket()` | as above |
| `htsim/sim/datacenter/main_uec.cpp` | flag parse; error unless constant CC; cwnd override | `-rate_const_gbps` |

### `[ADDED: per-link-degrade]` — `-degrade_links_file <file>` (non-uniform ToR uplink degradation)

Lines `tor agg ratio` (`#` comments ok, ratio in (0,1]) slow that ToR->agg uplink to ratio x speed; queue size and both ECN thresholds scale with the same ratio (same behavior as `-failed`/`-down_ratio`, but per link). Independent of `-failed`/`-skip_asy`/`-down_ratio`; uplinks only (downlink degrade is disabled in the existing code). Works on 2-tier fat trees (unlike `-fail_pipes_file`, which kills links in 3-tier only). Validation: uniform 0.5 on ToR0 uplinks reproduces `-failed 32 -down_ratio 0.5` byte-identically (full flow-finish lines identical, 1024 lines); non-uniform (even agg 0.25, odd 0.75) prints 32 `Failure:` lines summing to 16/32 of healthy capacity. Flag absent: no change.

| File | What | Gate |
|------|------|------|
| `htsim/sim/datacenter/fat_tree_topology.h/.cpp` | static `_degrade_links` map and `_alloc_ratio_override`; `alloc_queue` uses the override ratio when set; new branch in the ToR->agg uplink loop | non-empty map |
| `htsim/sim/datacenter/main_uec.cpp` | `-degrade_links_file` parser | flag |

**Extension (`per-link-degrade-speedup`, 2026-10-25):** the ratio column now accepts values in (1, 4]; a ratio above 1 speeds that uplink up (queue size and ECN thresholds scale with it, the same code path). Used only by the M4 `investigate_k` controls (native 200G fabric with 400G uplinks). Files with ratios <= 1 and the flag-absent run are unchanged.

**Extension (`per-hop-degrade`, 2026-10-25):** `-degrade_links_file` also accepts `all_adown <r>` and `all_hdown <r>` lines (r in (0, 4]) that scale every agg->ToR link, resp. every ToR->host link, to r x speed (queue size and ECN thresholds scale with it, same `alloc_queue` path; ToR downlinks keep ECN off under `-disable_tor_ecn`). Also `hdown_tor <tor> <r>` (scale the ToR->host links of one ToR). Used only by the M4 `investigate_k` per-hop interventions. Sites: `FatTreeTopology::_degrade_all_adown/_degrade_all_hdown` (`fat_tree_topology.h/.cpp`), parse in `main_uec.cpp`. Flag-absent and files without these lines: byte-identical (over/healthy B=8 seed 42: all 1024 finish lines identical to the stored cell, re-checked after each of the three rebuilds).

**Extension (`per-link-degrade-agg-core`, 2026-10-30):** `-degrade_links_file` also accepts `agg_core <agg> <core> <r>` lines (r in (0, 4]) that scale the agg->core uplink of that (agg, core) pair to r x speed (3-tier only; queue size and both ECN thresholds scale with it, same `alloc_queue` path as the ToR->agg hook; the downlink core->agg stays healthy). A key that is not a connected pair of the topology (agg or core out of range, core not reached by that agg, or a 2-tier fabric) is a startup error, never a silent no-op. Each hooked link prints `Failure: US<a>->CS<c>(b) linkspeed set to <Gbps>`. Used by T2 sub-experiment B (`meeting_26_10_26/T2/agg_core`). Sites: `FatTreeTopology::_degrade_agg_core` (`fat_tree_topology.h/.cpp`; hook at the `queues_nup_nc` allocation, connectivity check after the agg->core loop), parse in `main_uec.cpp` next to `hdown_tor`. Agg a, uplink l reaches core `a % agg_per_pod + agg_per_pod * l`.

*Verification (3-tier k=8, 128 hosts, tornado 16 MiB, matched 200G, B=8, seed 42; script `meeting_26_10_26/T2/scripts/validate_agg_core.py`, binaries `pre-agg-core` = clean build of HEAD, `agg-core` = clean build with the change):*
- v1 flag absent (healthy): 128 flow-finish lines identical old vs new, new binary deterministic (`experiments/tools/regress.sh`).
- v2 ToR->agg-only file (T2 A, 5/95): 128 lines identical old vs new, deterministic.
- v3 `agg_core` ratio 1.0 on all 16 pod0 links: the 128 flow-finish lines equal the healthy run's (stdout differs only by the 16 `Failure:` lines).
- v4 `agg_core` 5/95 file (even uplink 0.05, odd 0.95): 16 `Failure: US->CS` lines with speeds {20, 380} Gbps, 128 flows finish. The old binary rejects the unknown key (`bad -degrade_links_file line`), so a file with `agg_core` lines cannot be run silently on a binary without the hook.
- v5 negative controls: unconnected pair (agg 0, core 1), agg 99, core 99, ratio 0, ratio 5, missing field: each exits 1 with an error before any flow runs.
- v6 T1 r005 B=8 seed 42 (2-tier, 1024 hosts, `degrade_r005.txt`): 1024 flow-finish lines identical old vs new, deterministic.
- Known-answer speed proof (T2 smoke, B=8 seed 42, from `-log_queue_stats`): with the 5/95 file the 8 degraded A->C queues of pod0 achieve 17.9-19.1 Gbps (cap 20) and the 8 healthy ones 358-370 Gbps (cap 380); trims 986 in total, all on the degraded links (0 elsewhere). The ToR->agg 5/95 cell shows the same pattern (18.2-19.6 and 362-370, 998 trims, 0 outside scope). Healthy reference: no trims.
- Not run: a build with the hook but the file absent is the same code path as v1; tiers other than 3 only exercise the connectivity error (v5 covers the range checks, a 2-tier agg_core file was not run).

**Extension (`per-link-extra-latency`, 2026-10-30):** `-degrade_links_file` also accepts `latency_tor_agg <tor> <agg> <extra_ns>` lines (0 <= extra_ns <= 1e6) that add extra one-way propagation delay to the ToR->agg pipe of that pair (data direction; ACKs of flows into that ToR cross the same pipe, so a packet that goes through one such pipe and its ACK through another sees RTT + the sum). Speed, queue size and ECN thresholds are unchanged. A tor or agg outside the topology is a startup error. Each hooked link prints `Failure: LS<t>->US<a>(b) extra latency set to <ns> ns`. Used by `meeting_26_10_26/T3/investigate_8` (Test J). Sites: `FatTreeTopology::_extra_lat_tor_agg` (`fat_tree_topology.h/.cpp`; the `Pipe` constructor call for `pipes_nlp_nup` adds the extra delay, original line kept in a comment), range check after the agg->core loop, parse in `main_uec.cpp` next to `hdown_tor`.
*Verification (2-tier, 128 hosts radix 8, tornado, matched 200G, 5/95 file, B=8, seed 42; script `meeting_26_10_26/T3/investigate_8/validate_extra_lat.py`; old = `htsim_uec.agg-core` (HEAD + agg_core), new = `htsim_uec.extra-lat`, both clean builds of the datacenter directory):*
- v1 flag absent: 128 flow-finish lines identical old vs new.
- v2 `latency_tor_agg ... 0` lines on all 128 uplinks: finish lines identical to no lines (stdout differs only by 128 `Failure:` lines).
- v3 known answer: +10000 ns on all 128 ToR->agg uplinks, every data packet and every ACK crosses exactly one such pipe, so RTT +20 us: median flow-finish time 700.29 -> 720.07 us (+19.78, predicted +20.0; the 0.2 us gap is not separately explained).
- v4 negative controls: tor 16 (range 0..15), agg 8 (range 0..7), negative ns, missing field: each exits 1 with the error text before any flow runs.
- Not run: determinism rerun of the new binary on a latency file (the sim has no randomness source added), 3-tier fabrics (the hook sits on the ToR->agg pipes, common to both).

### `[ADDED: sink-arrival-log]` — `-log_sink_arrivals <file>` (+ `-log_sink_arrivals_flow <id>`, repeatable)
One CSV row per data packet reaching a `UecSink` (`time_ps,flow_id,epsn,path_id,size`); no `-log_sink_arrivals_flow` = all flows. Diagnostic only: no behaviour change, flag-absent output byte-identical (checked on over/healthy B=8 seed 42). Sites: `UecSink::_arrival_log` / `_arrival_log_flows` (`uec.h`, `uec.cpp`, top of `UecSink::processData`), parse in `main_uec.cpp`. Added for the M4 `investigate_k` per-packet check that the last hop evens out data arrivals at the receiver.

### `[FIX: connection-info-cwnd-overflow]` — applied 2026-11-01
`ConnectionInfo::cwnd` (`uec.h`) is an `int`. The constant-rate sender (`-rate_const_gbps`) sets `cwnd = 1000000` packets (`main_uec.cpp`, rate-const-sender block, overrides `-cwnd`), i.e. 4.15e9 bytes, which wraps to -144,967,296 in the `int`. With `-connections_mapping` the next flow on the same src-dst pair restores that value in `UecSrc::startFlow()` and starts with a negative window ("cantSend, limited by sender CWND"), so **no later message on a pair ever sends** with the constant-rate sender. Found with `-debug` on a 2-message matrix (`startflow ... CWND -144967296`).
Fix: new field `mem_b cwnd_wide` in `ConnectionInfo` (the original `int cwnd` is still written, unchanged), saved next to it at flow finish and restored (overriding the narrowed value) in `startFlow()`. Banners `// ===== FIX (connection-info-cwnd-overflow) =====` at the 3 sites (`uec.h` struct, `uec.cpp` save and restore). No flag; behaviour changes only where the old code overflowed (constant sender + `-connections_mapping`, second and later flows on a pair).
**Verification** (container `m23-dev`, clean build of `htsim/sim` and `datacenter`; old = binary built before the change, new = after; `knee/scripts/run_knee.py` flags, 128 hosts radix 8, B=8, seed 42, flow-finish lines compared):
- flag-absent / no-overflow cells identical old vs new: tornado 16 MiB + mapping, constant sender (128 lines); 512 messages (128 pairs x 4) with the NSCC sender + mapping (cwnd below 2^31, 512 lines); 512 messages, constant sender, no mapping (512 lines).
- negative control (the check can fail): 512 messages, constant sender + mapping: old binary finishes 128 flows (later messages stall), new binary finishes 512.
- known answer: with the fix, message k on the same pair has the same mean FCT as the first (51.97 / 52.21 / 52.02 / 52.07 us for messages 0 to 3, unmapped runs 51.97 / 52.14 / 51.93 / 52.06): the fabric is idle between messages and only the REPS buffer carries over.
- determinism: two runs of the new binary on the 512-message cell give identical flow-finish lines (checked 2026-11-01).
- earlier results: the stall needs `-rate_const_gbps` (cwnd = 1e6 packets) + `-connections_mapping` + a second flow on the same src-dst pair; the only experiments passing both flags are the M4 family via `run_m4.flags()` (M4, T1, T2, T3, knee), all with tornado matrices (one flow per pair), so none was affected. Signature of the bug: finished flows < connections in stdout.
- not run: other CC algorithms with cwnd above 2^31.

### `[ADDED: link-swap]` — `-swap_tor_uplinks <tor> <period_us> <until_us>`
Time-varying degradation: every `period_us` (until `until_us`) the service rates of the ToR uplink queue pairs (agg 2k, agg 2k+1, every bundle index) of one ToR are exchanged, so with a `-degrade_links_file` pattern (even agg r, odd agg 1 - r) the degraded and the healthy halves swap places and the capacity of each pair is conserved. 2-tier only (hard error otherwise); the swap is `BaseQueue::update_bit_rate()` (existing, `queue.h`), driven by a new `LinkSwapEvent : EventSource` in `main_uec.cpp` (flag parse, variables, creation after the topology exists; banners `// ===== ADDED (link-swap) =====`). Added for `experiments/meeting_26_10_26/knee` dial G (stale-EV hypothesis). Flag absent: no code path changes.
**Validity bound.** The rate is sampled when a packet starts service; if the period is shorter than about two serialization times at the slow rate (4150 B at 20 Gbps = 1.66 us), the slow phase dominates and the pair's capacity is not conserved (period 1 us: max FCT 1966 us against 708 static). Use periods of 8 us and above.
**Verification** (container `m23-dev`, h128_p8 5/95, B=8, seed 42, baseline = binary saved before the change `htsim_uec.pre-link-swap`):
- flag absent: 128 flow-finish lines and the whole stdout identical old vs new.
- a swap that never fires (period 100000 us): finish lines identical to the static run.
- equal ratios (0.5 / 0.5, uniform file) with a swap every 5 us: identical to the same cell without swap (max FCT 702.156 both).
- the log shows the first pair alternating 380 / 20 Gbps (`[link_swap] swap #1 at 1 us, first pair now 380/20 Gbps`, next 20/380).
- bad arguments: ToR 99, period 0, until < period each exit 1 with an error before any flow runs.
- missed prediction (reported): "a period far below the RTT behaves like the uniform case": at 1 us it does not (see the validity bound).
- not run: determinism rerun of the new binary on a swap cell (the event adds no randomness), 3-tier fabrics (rejected with an error), swap on ToRs other than 0.

### `[ADDED: reps-draw-weights]` — `-reps_draw_weights capacity|w0,..,w(P-1)` (+ `-reps_draw_hosts all|a,b-c`, `-reps_draw_scope fallback|explore|both`, `-reps_draw_invert`)
"God mode" for the REPS random draw. Files: `uec.h` (statics, per-source `_draw_*` members, `drawBiasApplies`), `uec.cpp` (`initDrawWeights`, `drawRandomEv`, three one-line call sites in `nextEntropy_freezing`), `datacenter/main_uec.cpp` (flag parsing, startup checks). Every site carries `// ===== ADDED (reps-draw-weights) =====`; no original line is deleted (each call site is a guarded `return` placed before the original `return rand() % _no_of_paths;`).
- **What it does.** The uniform draw `rand() % _no_of_paths` of the empty-buffer / no-fresh-EV branch (and of the frozen-mode empty branch, scope `fallback`; and of the `explore_counter` branch, scope `explore`; `both` = all three) becomes one weighted draw with the same number of `rand()` calls (one). Weight of EV e: `capacity` = bottleneck speed in Mbit/s (minimum `BaseQueue::_bitrate` over the route `_paths[e % _paths.size()]`, so it needs `-use_srv6`), or an explicit integer list of length `-paths`. `-reps_draw_invert` maps w to max + min - w (negative control). `-reps_draw_hosts` limits it to source hosts (`_srcaddr`); empty / `all` = every host. A source whose weights are all equal (e.g. a healthy ToR) keeps the original uniform draw, so the output is byte-identical there. The trace label of a weighted draw stays `random` (or `explore`), so analysis scripts need no change. A source that activates the weights prints `reps_draw_weights: src <host> weights ...` once.
- **Does not change.** Recycling, deposits, buffer size, trimming, freezing logic, CC, ECN. Weights are computed once, lazily, at the first draw of a source (no RNG use, no buffer access); they are NOT updated afterwards, so `update_bit_rate` (link swaps) and failures are not tracked. Only `-load_balancing_algo freezing` is wired (the `freezing_pxr` and dual-window predictors are not).
- **Startup errors (exit 1).** `-reps_draw_hosts/-scope/-invert` without `-reps_draw_weights`; any other `-load_balancing_algo`; `capacity` without `-use_srv6`; a list whose length is not `-paths` or whose sum is 0; non-numeric list; bad scope.
- **Design note.** Under SRv6 the EV selects the physical path (`_paths[ev % N]`), so the weight of an EV is a property of its route and there is no per-flow hash to model (under ECMP the EV -> uplink map depends on a per-switch salt, so this mechanism is SRv6-only).
- **Verification** (container `m23-dev`; baseline = binary `htsim_uec.pre-reps-draw-weights` copied before the first edit, md5 `cc22e4898551`; new = clean build of `htsim/sim` and `datacenter`, 0 errors; smoke driver `knee/scripts/draw_smoke.py`, log in `knee/data/draw_smoke.log`):
  - Tier 1, one connection host 0 -> 64, 4 x 4 MiB, 5/95 degrade, B = 2: flow-finish lines identical to the baseline with the flag absent, a uniform list `1,1,1,1,1,1,1,1`, `capacity` on a healthy fabric (all speeds equal), `capacity` with `-reps_draw_hosts 5` (the flow is host 0), and `capacity` with scope `explore` (no explore draws exist). On the full sweep cell (512 flows, `h128_p8_msgN_lat1000`, B 8, seed 42, `regress.sh`): flag absent identical + deterministic; uniform list with all hosts, `capacity` on hosts 64-127 only, and `capacity` with scope explore also identical (hosts 0-7 weights print only when selected: 32 sources for `capacity` on all hosts).
  - Tier 2b, distribution of the `random` sends of the flow (even EV = 5% uplink), 3 seeds pooled, expected value written before the run: uniform 52.7% (347 draws, expected 50%, z +1.0); `capacity` 5.3% (188 draws, expected 5%, z +0.2) and the per-EV counts have chi-square 3.49 against the 20:380 weights (7 dof, 0.001 critical value 24.3); inverted capacity 95.4% (2092 draws, expected 95%, z +0.8); list `1,0,1,0,..` exactly 100% (7579 draws); list `0,1,0,1,..` exactly 0% (153 draws); `capacity` with `-reps_draw_hosts 0-7` and with scope `both`: the same 5.3% (the flow is host 0 and no other branch fires). Sends per ToR0 uplink in the queue stats follow the draws (5%-class uplinks carry about 150 packets each under `capacity` against about 900 uniform).
  - Negative control: the same checks with the wrong expectation fail (uniform draws against an expected 5%: z about +40); inverted weights give the opposite class.
  - Hard errors: the 7 startup errors above each exit 1 with a message before any flow runs.
  - Determinism: `regress.sh` rerun of the new binary identical on the 512-flow cell.
  - Sanity of a full god-mode cell (`msgNhG`, lat 1 us, B 8, seed 42): 512 flows, 0 RTOs, 0 freeze entries, no `enable on tor downlink 1`, 0 trims on the 5% uplinks (REPS: 1216).
  - Explore and frozen-mode-empty branches (`knee/scripts/draw_freeze_smoke.py`; the sweep has 0 freezes, so they need a forced RTO: `-fail_src_paths 0 4` blackholes 4 of 8 paths of the source, `-exit_freeze 100000000`; 3 seeds pooled, expected share of draws on the 5% class written before the run): after thaw the `explore` draws (300) are 4.0% even-EV under scope explore and both, 50.3% under fallback, 47.3% with the flag absent (expected 5% / 50% / 50%); the normal `random` draws (407-653) are 4.4-4.5% under fallback and both, 50.8% under scope explore, 48.7% absent. With all 8 paths blackholed (`-fail_src_paths 0 8 -end 400`, the buffer stays empty so the frozen-mode-empty branch fires), the 6471 frozen-empty `random` draws are 4.6% under fallback and both, 50.5% under scope explore and with the flag absent (z -1.5 and +0.7); all 8 scope/branch combinations pass |z| < 4. These runs are not completions (flows finish 12/12 with 4 dead paths, 0/12 with 8).


### `[ADDED: dps]` — `-load_balancing_algo dps` + `-dps_dist <name> [args]` (+ `-dps_perm <seed>`)
Distribution Packet Spraying: every packet draws its EV independently from a given distribution over the EV space; no buffer, no feedback (OPS with a non-uniform pmf). Design doc: [`DPS_ARCHITECTURE.md`](DPS_ARCHITECTURE.md). Files: new `htsim/sim/dps_dist.h` (pure pmf families uniform / list / file / capacity / normal / poisson / binomial / geometric / zipf, permutation, CDF sampler), `uec.h` (enum `DPS`, `EVSRC_DPS`, statics and per-source `_dps_*` members), `uec.cpp` (`initDps`, `nextEntropy_dps`, empty `processEv_dps`, dispatch branch, `_parseLBName`, `evSourceStr`), `datacenter/main_uec.cpp` (flags, startup checks). Every site carries `// ===== ADDED (dps) =====`; no original line is deleted (the `LoadBalancing_Algo` enum line and the `EVSRC_FROZEN_POP_STALE` line each gain one token, as for path-random).
- **What it does.** `nextEntropy_dps`: one `rand()` per packet, none at init (the CDF is built lazily at the source's first draw): `u = rand() / (RAND_MAX + 1.0)`, EV = first index whose CDF exceeds u. If all raw weights are exactly equal it returns `rand() % _no_of_paths`, which is `nextEntropy_oblivious`, so DPS with a manual uniform distribution is byte-identical to OPS. `capacity` uses the same weight rule as `-reps_draw_weights capacity` (bottleneck `BaseQueue::_bitrate` of route `e % P`, Mbit/s; code duplicated, `initDrawWeights` is untouched); a source with <= 1 route (same-ToR pair) has nothing to weight and draws OPS, with one printed note. Retransmissions and RTS redraw; ACK/ECN/NACK never touch DPS state.
- **Does not change.** CC, ECN, trimming, REPS buffer (unused), any other LB algorithm. Flag absent: byte-identical to the baseline binary.
- **Startup errors (exit 1).** `dps` without `-dps_dist`; `-dps_dist` / `-dps_perm` without `dps` (global or `-host_lb_overrides`); unknown name; wrong argument count or non-numeric argument; list/file length != `-paths`; negative, NaN or zero-sum weights; `capacity` without `-use_srv6`; unreadable file.
- **Design note.** The weights are over EV indices; under SRv6 the EV is the path. Without SRv6 the pmf is over ECMP hash inputs and does not give a controlled link share. Weights are fixed at the first draw (not updated on link swaps or failures).
- **Verification** (container `dps-dev` = `reps-artifact` image, repo bind-mounted at `/workspace`; baseline = `.baseline/htsim_uec.pre-dps`, a clean `make clean` build of the working tree before the first DPS edit, md5 `e1342fc86f0b`; new = final build (clean build, then an incremental rebuild after the single-route fix below), md5 `3e24eb394cc7`, 0 errors; expected values were written in the header of `knee_16paths/scripts/dps_smoke.py` before the first run; log `knee_16paths/data/dps_smoke.log` (final binary), 55 PASS, 0 FAIL; the first quick run had 2 FAILs, both fixed and re-run: the smoke script traced only 1 of the 4 message flows, so the uplink identity compared 1 flow of sends with 4 flows of packets; and the error message of a missing numeric argument named the next flag):
  - Standalone known-answer test `experiments/tools/dps_dist_test.cpp` (no simulator; `g++ -std=c++17`): 36 PASS. pmf identities from the definitions (poisson p[3] = e^-5 5^3/3!, mean = var = lambda; binomial(10,0.3) mean 3, var 2.1; geometric ratio 1-p; zipf ratio 2^-s; normal mean mu, var sigma^2 + 1/12; list 1,2,3,4 -> .1 .2 .3 .4; capacity 20/380 -> 5% on slow EVs), permutation is a deterministic bijection, 9 startup-error cases, chi-square of 2e6 draws of the libc `rand()` stream for 7 families (all within the far-tail bound, 0 draws on zero-mass EVs). Negative controls: sampling zipf(1.2) against zipf(1.3) gives chi-square 16282, uniform against a 2%-shifted pmf gives 111, both above the bound.
  - Tier 1 (cell: one connection host 0 -> 256, 4 x 4 MiB, 5/95 degrade, SRv6 16 paths, 200G constant sender, B = 2): flow-finish lines identical to the baseline with the flag absent on the REPS cell, the god cell (`-reps_draw_weights capacity`), the healthy-fabric cell and the `oblivious` cell; DPS capacity deterministic.
  - **DPS with manual uniform == OPS** (the requested sanity check): `dps_dist uniform`, `list 1,..,1` and `list 7,..,7` give flow-finish lines AND the full EV sequence of the traced flows (1032 sends) identical to `-load_balancing_algo oblivious`. Negative control: `list` with one weight 1 -> 2 differs.
  - Tier 2b, 3 seeds pooled, expected value written before the run: uniform 50.7% on the 5% class (n = 3093, expected 50%); `capacity` 5.29% (n = 3081, expected 5%, z +0.74), per-EV chi-square 15.3 (df 15) against the 20:380 weights; list 1,0,1,0.. -> 100% (3878 of 3878) on the 5% class; list 0,1,0,1.. -> 0% (0 of 3081); all mass on EV 5 -> every send on EV 5 and uplink 5 carries all data packets. For zipf 1.2, poisson 4, geometric 0.3, binomial 10 0.3, normal 5 2: the pmf printed by the simulator equals an independent python pmf to 6 digits and the per-EV chi-square is within the far-tail bound (10.9 / 22.8 / 22.3 / 12.1 / 14.7 at df 15 / 11 / 15 / 8 / 11). `-dps_perm 7`: the printed pmf is a permutation of zipf(1.2) and differs from it, the counts fit it (chi-square 18.4, df 15) and do not fit the unpermuted pmf (17512).
  - Identities: sends per `ev % 16` equal data + trims + drops of ToR0 uplink j for all 16 j; configuration from the output (`SRv6 source routing enabled`, `distinct_paths` 16, no `enable on tor downlink 1`), 4 flow-finish lines, 0 RTOs. B-invariance: DPS flow-finish lines identical for `-reps_buffer_size` 2, 8, 64 (negative control: the REPS cell differs between B = 2 and 64).
  - Memorylessness on the loaded cell (512 hosts, 2048 flows, lat 250 ns, 5/95 ToR0, hosts 0-15 traced): share of sends on even EVs by the last feedback seen by the source (ECN ACK / clean ACK / NACK): DPS uniform 0.497 / 0.502 / 0.498 (overall 0.500), DPS capacity 0.051 / 0.048 / 0.054 (overall 0.049), all within 4 binomial sigma; positive control REPS (freezing) 0.093 / 0.044 / 0.180, spread 0.136, so the test can detect feedback dependence.
  - Hard errors: 12 startup errors each exit 1 with a message before any flow runs.
  - Tier 6 (added after review, final binary): `-dps_dist file` with a weights file == `-dps_dist list` with the same weights, flow-finish lines and EV sequence (4284 sends) identical; `-host_lb_overrides 0:dps` under global freezing: all 4108 traced sends of host 0 have `ev_src = dps`; `-host_lb_overrides 5:dps` (host 0 not overridden): no dps sends and flow-finish lines identical to plain freezing; a same-ToR pair 0 -> 1 with `capacity` (the source has 1 route, nothing to weight, no exit, one printed note) completes and is identical to `oblivious`. This is the single-route fix: `initDps` first exited with an error for `capacity` with no routes, which would have killed any run containing an intra-ToR pair; it now draws OPS.
  - Loaded flag-absent regression (`knee_16paths/scripts/dps_loaded_regress.py`, log `data/dps_loaded_regress.log`; 512 hosts, 2048 flows, lat 250, B 8, seed 42): REPS cell and god cell give 2048 identical flow-finish lines, identical `-log_reps_events` trace (md5 020aee0e / 7f359d8e) and identical `-log_queue_stats` (md5 be463be0 / dca27b27) between the baseline and the new binary.
  - Sweep provenance: the 21 sweep cells ran on the binary before the single-route fix (which changes nothing for sources with 16 routes); one cell (`h512_p16_msgNhDcap_lat250`, B 8, seed 42) re-run on the final binary gives 2048 flow-finish lines identical to the stored sweep output. Identities on 7 sweep cells (all latencies): sends per `ev % 16` = data + trims + drops of ToR0 uplink j for all 16 j, NACK classes = trim classes, 0 mismatches (`knee_16paths/data/dps_identity_checks.log`).


### `[ADDED: reps-bank]` - `-reps_bank` (+ `-reps_bank_size N`, `-reps_bank_timer_us T`, `-reps_bank_target_rtt_us R`, `-log_reps_bank <file>`)
Second "bank" buffer next to the REPS buffer (design in `REPS_BANK_ARCHITECTURE.md`). Admission: clean ACK (no ECN) with an RTT sample <= target (default `_base_rtt + _target_Qdelay`; `-reps_bank_target_rtt_us 0` admits nothing = plain REPS). Send order in `nextEntropy_freezing` (non-frozen): REPS fresh pop, oldest live bank slot, random. Full ring overwrites the oldest slot; slots expire after the timer (lazy, age strictly greater than timer); a pop invalidates the slot. Per-flow bank; frozen mode and explore burst unchanged. Hard errors: needs `-load_balancing_algo freezing`; exclusive with `-reps_soft_replay` and the dual-window sender CCs; bank knobs without `-reps_bank`.

| File | What | Gate |
|---|---|---|
| `htsim/sim/bank_buffer.h` (new) | `BankBuffer` ring | included always, used only when on |
| `htsim/sim/uec.h`, `uec.cpp` | statics, `_bank_buf`, admission block in `processAck`, pop in `nextEntropy_freezing`, `EVSRC_BANK_POP`, `bankLog`, `BANK_STATS` line | `-reps_bank` |
| `htsim/sim/datacenter/main_uec.cpp` | flags, startup checks, resolved-config line | flag |
| `experiments/tools/bank_buffer_test.cpp`, `bank_log_check.py` | unit test + independent log replay checker | n/a |

**Verification** (Docker; baseline `.baseline/htsim_uec.pre-reps-bank`, copied before the first edit, not rebuilt with `make clean`).
- Unit test (ASAN/UBSAN): 12M differential ops vs a deque reference, 0 mismatches; 5 deliberately broken buffers all caught. PASS.
- Replay checker (`bank_log_check.py`) PASS on healthy, degraded (4 seeds), heavy-ECN, timer sweep and 3-tier link-failure/freeze cells; 5 log corruptions all detected.
- Tier 1 (final binary, 5 workloads incl. 2 degraded; same on the earlier build): flag absent byte-identical to baseline and deterministic (`regress.sh`). Inert settings byte-identical to baseline on 4 cells: `-reps_bank_size 0`, `-reps_bank_target_rtt_us 0` (sanity check: target RTT 0 == plain REPS), target 0 with a 1 s timer. Plain `-reps_bank` differs as intended. Startup errors verified (rc 1): knobs without `-reps_bank`, non-freezing LB, `-reps_soft_replay`, dual-window CC, negative timer.
- Tier 2b: P2 (`inserted == acks - ecn_acks`, rej_rtt 0, per flow), P3 (sends = fresh+bank+random, bank_pop == popped), P4 boundary at `R_min` (target R_min-1ps admits 0 and matches baseline; target R_min admits, first ADD equals the baseline row), P6 timer sweep (expiries 1578 / 801 / 0 for 1ps / 0.5us / >=2us), heavy ECN collapses insertion and FCT ~ baseline: all as predicted.
- **Missed prediction P5**: predicted rej_rtt small vs rej_ecn in the degraded cell; measured 3497 vs 13787 (~25%), 4 seeds consistent. Cause not investigated.
- Observation (one cell, 4 seeds, no cause claimed): degraded-uplink cell, bank cuts random draws ~72% but mean FCT rises ~9% (388 -> 424 us); healthy cell FCT unchanged.
- Boundary on the final binary: target `R_min-1ps` (8337119 ps, exact after rounding fix) admits 0 and equals baseline; `R_min` admits 39, first ADD equals the baseline row.
- Sim-level negative control: a build with `>` changed to `>=` in the expiry test (`.baseline/htsim_uec.mutant_ge`), run with the timer set to a real pop age (709880 ps): `bank_log_check.py` FAILS on it (`EXPIRE age == timer`), and passes on the real binary.
- (Superseded in part, see Round 2: the checks above ran on the first build, where the bank was per flow.)

**Round 2: bank per connection, like the REPS buffer (user request), plus verification gap closing.**
Design change: `ConnectionInfo` has a `bank` pointer. Under `-connections_mapping` a finished flow hands its bank to `CONNECTION_INFO_MAP[src_dst]` and the next flow of that pair borrows it in `startFlow` (never frees a borrowed bank); without `-connections_mapping` each flow owns its bank, as REPS does. `BANK_STATS` counters are per-flow deltas plus `valid_at_start` and `end_ps`; `-log_reps_bank` gained a last column `conn`; checker conservation is `inserted + valid_at_start == popped + expired + overwritten + valid_at_end`. Banner `reps-bank` at every new site; no original line deleted.
- Step 0 reduction (prediction written first): without `-connections_mapping` the per-connection binary equals the previous per-flow binary (`.baseline/htsim_uec.reps-bank-perflow`). Result: full stdout identical apart from the two new BANK_STATS tokens on 4 cells (symm16, symm16 degraded, perm128, symm16 with size 2 / timer 5 us); log columns 1-8 identical. PASS.
- Unit test extended with a two-flow shared-bank case (slots and timestamps survive, per-flow conservation with snapshots): PASS under ASAN/UBSAN, 12M differential ops 0 mismatches, 5 broken buffers still caught.
- A1 baseline rebuilt properly: the tree was copied to `.baseline/src_pre_bank`, all `reps-bank` hunks stripped mechanically (203 lines in 3 files, `bank_buffer.h` removed, 0 remaining `reps_bank` references), `make clean`, built in Docker, stored as `.baseline/htsim_uec.pre-reps-bank-clean` (same size as the older copy; bytes differ, as expected for a different build path). Flag absent: full stdout identical (0 diff lines) and deterministic on 9 cells: symm16 seeds 20 and 7, symm16 degraded, perm128, perm128 degraded, 3-tier link failure with freeze (8 RTOs, seeds 20 and 21), incast 128, and the `-connections_mapping` message cell. PASS.
- A2 with the bank on, 6 cells (symm16, symm16 degraded, perm128, 3-tier failure, incast, mapping cell): two identical runs have identical stdout; adding `-log_reps_bank` and `-log_reps_events` leaves stdout and BANK_STATS identical (logging does not perturb); `-reps_bank_size 0` and `-reps_bank_target_rtt_us 0` equal the clean baseline (0 diff lines; the BANK_STATS and config lines excluded); plain `-reps_bank` differs, as intended. PASS.
- Sharing cell (`make_messages_cm.py 128 3 524288 P`, `-connections_mapping`, 3 sequential 0.5 MiB messages per pair, 384 flows, 8-slot bank, timer 100 us). Predictions were written first (P7 in the ARCHITECTURE doc). P=300 us (gap above the timer): `valid_at_start` 1024 = 8 x 128 for messages 2 and 3, `expired` 1024 for each, i.e. every inherited slot expired on the first pop. P=80 us (gap about 60 us, below the timer): `valid_at_start` 1024, `expired` 0, `popped` 411 -> 1717 -> 1880. Control without the bank: first send of messages 2 and 3 has `fresh` 7 (REPS buffer carried over), so the cell exercises the sharing path. Host 0's random draws in the first window: baseline 106 / 102 / 99 for messages 1 / 2 / 3; bank at P=80: 104 / 88 / 93 with 2 / 16 / 14 bank pops. Replay checker (keyed by connection) PASS on both periods; 6 log corruptions detected, including the new `cross_conn`.
- Observation, not explained: in the P=80 cell mean FCT of messages 2 and 3 rises with the bank (21.5 and 22.9 us vs 20.6 and 20.6 baseline; message 1 equal at 20.3); at P=300 the rise is small (20.5, 20.8). One cell, one seed.
- Checker finding: one flow (P=80) logged a NOSAMPLE row 0.13 us after its BANK_STATS line (a late ACK reaching a finished flow). Not a bank bug (no tx-bitmap sample, so no state change), but the checker flagged a mismatch. Fixed in the tool by printing `end_ps` in BANK_STATS and excluding post-finish rows from the per-flow counters (any state-changing row after `end_ps` is an error).
- B, trace join (`experiments/tools/bank_trace_join.py`; bank log joined to `-log_reps_events` of the same run, 4 hosts, plus 12 flows in the mapping cell). Prediction: every logged RTT and ECN bit equals what the trace says, every POP has a `bank_pop` send row at the same time and EV, and vice versa. Result: healthy 16428 ACK rows joined, 16428 RTTs exact (ACK time minus latest send time of that seqno), 302 POP rows matched 1:1 to 302 `bank_pop` sends; degraded 16428 / 16428 exact, 5982 / 5982 POPs; mapping cell 1548 joined, 1419 exact RTTs, 131 / 131 POPs. 0 mismatches. 129 ACKs in the mapping cell are NOSAMPLE although their seqno was sent and never acked before (their tx-bitmap entry was already gone; consistent with the cumulative-ACK path), counted, not a mismatch. Negative controls (corrupt one row of a traced source: RTT +5 ns, ADD->REJ_ECN, POP EV flipped, POP row dropped) all detected. Note: the first version of the negative control corrupted a row of an untraced source and was "not detected"; fixed to pick traced rows.
- A3, full-simulation ASAN/UBSAN (separate build `.baseline/htsim_uec.asan`, `-O1 -fsanitize=address,undefined`, built from a copy of the source tree so the production build was untouched). 11 cells with the bank on: smoke, degraded, 3-tier failure with freeze, size 1, size 1024, timer 1 ps, huge timer and target, target 0, mapping cell with gap 80 us and 300 us (384 flows), incast 128. Prediction: 0 ASAN errors, 0 UBSAN reports, and the only leak reports are end-of-run (the simulator never destroys its `UecSrc` objects; the REPS buffer and every packet pool leak the same way, about 2.8 MB in the smoke cell). Result: 0 ASAN errors and 0 UBSAN runtime errors in all 11 cells, all flows finished (8 / 8 / 8 / 8 / 8 / 8 / 8 / 8 / 384 / 384 / 127). The process exit code is 1 on every cell only because of LeakSanitizer. `BankBuffer` appears in the leak report as one object per flow allocated in `startFlow` (8 objects in the smoke cell; the size-1024 cell shows 196608 bytes for 8 objects, i.e. it scales with bank size but not with run length), reachable only at process exit. No double free or use-after-free with borrowed banks (mapping cells). Not a regression: no destructor existed for the REPS buffer either.
- C1, stale bank entries after a link failure (prediction P8 in the ARCHITECTURE doc, written before running). Cell: 3-tier 128 hosts, symm16, link 0-0 down 50-200 us, seeds 20-22, 8 hosts traced, timer 1 / 10 / 100 / 1000 us (12 runs, replay checker PASS on all). Loss fraction = share of SENDs in [50, 200) us whose seqno was later retransmitted, by draw source, pooled over 3 seeds. Baseline REPS: fresh_pop 174/11659 (1.5%), frozen_pop 316/30585 (1.0%), random 53/824 (6.4%). Bank on: bank_pop 7/924 (0.8%), fresh_pop 171/11542 (1.5%), frozen_pop 740/29877 (2.5%) at timers 10, 100 and 1000 us (identical), and frozen_pop 1239/29080 (4.3%) at 1 us. **Predictions missed:** (1) I predicted the bank_pop loss fraction would exceed fresh_pop's; measured 0.8% vs 1.5%, from only 7 losses, so no evidence of stale-entry harm in this cell, but also not a clean negative. (2) I predicted no bank pops at a 1 us timer; there were 924, the same count as at longer timers, so the window's bank pops all happen within 1 us of a bank insertion (bursts of ACKs) before the freeze; and 10 / 100 / 1000 us give identical runs, so the timer does not matter here. Likely reason, not tested: freezing starts at the first RTO, after which `nextEntropy_freezing` takes the frozen branch and the bank is not consulted, so the cell barely exercises the bank during the failure. (3) Not predicted: with the bank on, frozen_pop loss rises from 1.0% to 2.5% (4.3% at 1 us), so the post-freeze phase differs from baseline; cause not investigated (the frozen buffer contents differ because the bank changes which EVs the REPS buffer sees before the freeze). Conclusion: the stale-entry question is not answered by this cell; a test would need a failure that does not trigger a freeze quickly (or with freezing disabled in the bank-relevant phase).
- **C3 interactions (P9)**: the bank is reachable only with `-load_balancing_algo freezing` (hard error otherwise), so DPS, PATH_RR, PXR, OPS and the other LB algos cannot combine with it. Cell: symm16 degraded (`-failed 4 -skip_asy`), seeds 20-22, 8 hosts traced, `-reps_bank` plus one of: nothing, `-state_aware_ecn`, `-smart_filter_mode md_gain`, `-wtd_in_nscc`, `-reps_draw_weights <64-entry list 1,4,1,4,...>` with `-paths 64`. Prediction (written first, ARCHITECTURE P9): checker and trace join pass, conservation holds, no new hard error needed. Result: held. 12/12 plain/state-aware/smart-filter/wtd runs and 3/3 draw-weights runs finished all 8 flows, `bank_log_check.py` PASS, `bank_trace_join.py` PASS with 0 mismatches (draw-weights: 32856 ACK rows with exact RTT, 12047/12081/12134 POPs matched 1:1 to `bank_pop` sends). Caveat: `-smart_filter_mode md_gain` and `-wtd_in_nscc` produced `finished at` lines identical to the plain bank run (0 diff), so in this cell they are inert and the combination is only shown not to crash or break the invariants, not shown to interact. `-state_aware_ecn` does change the run (18 diff lines) and passes. Draw weights: the random fallback keeps the bias (random EVs odd:even about 4:1, matching the 4:1 weights), the bank pops are echoed EVs and are not re-biased (bank_pop about 77% odd, i.e. they inherit the bias of the paths that returned clean ACKs); bank pops replace about 75% of the random draws (random 4670 vs 18689 with weights alone, seed 20). `-reps_draw_weights capacity` needs `-use_srv6` and was not run. Freezing mode is out of scope by user instruction, so C2 was not run.
- **D, P5 attribution (H1 ruled out in its stated form, cause unexplained)**: the degraded cell (`-failed 4 -skip_asy`) degrades 4 ToR uplinks to ratio 0.5 (200G), not 0.25 as an earlier note said (`Failure: ... linkspeed set to 200`). H1 said clean ACKs exceed the target because queueing just below kmin takes longer on the slow uplink. Data (seeds 20-22, bank log): target 14.337 us (base_rtt 8.337 + 6); `REJ_RTT` ACKs sit tightly 2.2 us above it (median 2.21, p90 2.65, p99 3.3, max 4-5 us), i.e. about 8.2 us of queueing, which is the same size as the drain time of one FULL queue (415000 B at 400G, 207500 B at 200G, both 8.3 us), above kmax (76%, about 6.3 us) and far above kmin (about 2.1 us). That figure is the TOTAL queueing along the path (ToR uplink, agg, ToR-to-host, ACK return), so it fits one nearly full queue and equally well the sum of several partial queues; the ECN thresholds scale with the link, so the slow uplink does not change the kmin drain time. `-log_queue_stats` shows every ToR0 uplink queue reaching its maximum (the 8 hosts offer 3200G to 3000G of uplink capacity). So H1 is not supported. Why these ACKs are unmarked despite that much queueing is not explained (candidates, untested: the delay is on the ACK return path; marking depends on the queue state at another point). The pre-registered classification of `REJ_RTT` by whether the EV crosses the degraded uplink was not run (no EV-to-path map); a per-EV proxy (ECN+RTT-reject rate of EVs with at least one `REJ_RTT` vs the others) gave 0.52 vs 0.51, no separation. The P5 line stays flagged missed.
- **E, FCT rise (degraded cell, symm16, seeds 20-24 for E1, 20-22 for the rest)**:
  - E1 (prediction: bank puts a lower share of packets on the degraded uplink): MISSED. Share of ToR0 uplink data packets on the degraded uplink is 6.70% baseline and 6.63-6.90% with the bank; fair capacity share is 6.67%. Baseline REPS is already at capacity share, so there is nothing to lower. Mean FCT 375.3 us baseline vs 411-415 us bank in 5 of 5 seeds (+9.6%).
  - New finding: trims at the ToR0 uplinks rise about 7x with the bank (baseline 245-332, bank 2124-2261, 5/5 seeds); no drops in either; CV of packet counts across the 7 healthy uplinks 0.0055 -> 0.0164.
  - E2 (prediction: more repeated EVs, fewer distinct paths): HELD, large. Trace of 8 hosts, seeds 20-22: share of sends repeating an EV the same host sent within the previous 8 us is 0.3-0.4% baseline and 57-59% with the bank; 97-98% of bank pops repeat an EV just sent; distinct EVs per host 2160-2190 -> 570-590. Cause in the design: a clean ACK puts its EV into the REPS buffer AND the bank, so it is sent again right after the fresh pop, placing consecutive packets on one path. Consistent with this explaining the trims and the FCT rise; no intervention was run (that would be a design change).
  - E3 dose-response (prediction written first, ARCHITECTURE P10: stale-EV account, monotone in timer and size): MISSED. Target 0 equals baseline exactly (trims 300/304/245, FCT 375.8/375.0/375.2). Timer 2 us already gives the full effect (trims 2217, FCT 411.7); timers 10, 30, 100, 1000 us give identical runs (trims 2222, FCT 411.8), same as C1: bank slots are consumed within microseconds, so the timer never binds in this cell. Size 1: trims 1774, FCT 391.2; size 8: 2222, 411.8; size 64: 2056, 410.8 (size 64 slightly below 8, so not monotone). The stale-EV explanation is not supported; the repeat-EV explanation fits (size 1 reduces repeats the least harmful way but still repeats). Staleness after a failure remains untested (C1 froze too early).
- **F, breadth**: incast_128 (127 flows), 5 seeds: bank mean FCT 4643 vs baseline 4665 us (-0.5%, 4 seeds lower, 1 higher, max FCT unchanged); no mechanism claim. `bank_log_check.py` PASS on all 5 incast runs and on bank sizes 1, 8 and 1024 (symm16 degraded, seed 20); `bank_trace_join.py` PASS on the same 8 runs. No code changed in this round after the rebuild, so `bank_buffer_test.cpp` was not re-run.
- **Warm-up gate: tried and removed**. It kept the bank off for the first BDP/MTU draws of a flow because the premise was a BDP random burst at connection start. Code reading showed REPS has none (`explore_counter` is 0 at start and set only at unfreeze, `uec.cpp:3978, 4716`); its first window is random because the buffer is empty before the first ACK, and the bank is empty then too. The gate was verified (first bank pop at draw 102-110, draws before it equal the baseline's 816/816, gate 0 equals the previous binary) and then removed on the user's decision. Removal verified: `uec.h`, `uec.cpp`, `datacenter/main_uec.cpp` and `bank_buffer.h` are byte-identical to the pre-gate source copy (`.baseline/src_asan/htsim/sim`), line endings unchanged (LF), and the clean rebuild is byte-identical (31909880 bytes, `cmp`) to the pre-gate binary (`.baseline/htsim_uec.reps-bank-prewarmup`). So every Round 2 result measured on the pre-gate binary (A1-A3, B, C1, C3, D, E, F) applies unchanged to the final binary. `-reps_bank_warmup_pkts` no longer exists in the tree.
- **Final-binary reruns (after the gate removal; binary byte-identical to the pre-gate one)**:
  - A1: 9 flag-absent cells, 0 stdout diff lines vs the clean stripped baseline, deterministic (same cells as before). A2: 6 bank-on cells, determinism 0, log twin 0, size 0 and target 0 equal baseline (0), bank-on differs from baseline as intended. Sharing cell (P=80 and P=300 us): all 384 flows finished, checker PASS, P=300 `EXPIRE=2048` as before.
  - A3: the 11 ASAN/UBSAN cells on the existing sanitizer binary (source verified identical): 0 ASAN errors, 0 UBSAN reports, all flows finished; exit 1 only from end-of-run leaks, byte counts identical to the first A3 run.
  - Unit test `bank_buffer_test.cpp` under ASAN/UBSAN: 12000024 differential ops, 0 mismatches, 5 of 5 negative controls caught. `bank_log_check.py` injects `pop_ev`, `pop_age`, `drop_add`, `dup_pop`, `swap_order`, `cross_conn` all DETECTED on a final-binary log; the `stats` control is applied to a copy of the stdout (BANK_STATS `inserted` +1) and is detected ("stats inserted=1896 but log has 1895 ADD rows"); passing `--inject stats` to the checker does nothing, it is not a log-row injection. `bank_trace_join.py` injects `rtt`, `ecn`, `popsend`, `dropsend` all DETECTED.
  - Startup hard errors (all exit 1 with the message): bank knob without `-reps_bank` (size, log), negative timer, negative target, algo other than `freezing`, `-reps_soft_replay`, dual-window CC. The removed `-reps_bank_warmup_pkts` is an unknown flag: the simulator prints its usage and exits 1.
  - Not re-run for the sharing cell: the trace join (it was run on the earlier mapping cell, binary identical).
- **C3 additions**: `-reps_draw_weights capacity -use_srv6` with `-reps_bank` (degraded cell, seeds 20-22): all flows finished, checker PASS, trace join PASS, 11341/11293/11310 pops. Smart filter (`md_gain`, counters `ecn` and `fresh`) and WTD gave identical flow-finish-time multisets to the plain bank run on symm16, perm128 and incast128 (seed 20), so in those cells they are inert and nothing about the interaction was exercised (checker and join PASS). Interaction exercised on exp07's own cell: 3-tier `fat_tree_128_1os_3t_400g`, `perm_128n_128c_128MB_s44.cm`, seed 44, `-end 5000`, flags taken from `v7_run_matrix.sh` (`-sack_threshold 4000 -paths 65535 -sender_cc_only -sender_cc_algo nscc -load_balancing_algo freezing -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 -disable_tor_ecn`). With the bank OFF the current binary reproduces exp07's recorded flow-finish-time checksums exactly (vanilla b7fc689f, WTD 2f118f79, smart-filter md_gain/ecn 4665cfcd), a cross-check of the binary on a different machine's earlier runs. Variants differ from each other with the bank off and with it on (WTD and smart filter do change the run here), all 128 flows finished in every run, `bank_log_check.py` PASS on the full logs (about 360 MB each). Trace join (hosts 11, 58, 93; the event trace is capped at 200000 rows, `_reps_events_max`, ending at about 3.15-3.17 ms, so the bank log was cut to that time and to those hosts first): PASS for vanilla, WTD and smart filter, 93.3-93.6k ACK rows joined, 84.9-85.2k exact RTTs, 26.8-28.5k POPs matched 1:1 to `bank_pop` sends. About 8.2-8.6k NOSAMPLE ACKs per run are first ACKs of a sequence number that was sent (the tx-bitmap entry was already cleared by an earlier ACK); recorded as counts, not mismatches. One seed, one cell: this shows the combinations run and keep every bank invariant, not that the bank's benefit or harm carries over.
- **D follow-up (P5 exclusion control)**: turning ECN on at the ToR downlinks (no `-disable_tor_ecn`, one labeled diagnostic, not a paper-comparable configuration) leaves the rejection counts unchanged (REJ_RTT 3499 vs 3499, 3328 vs 3326, 3420 vs 3424; REJ_ECN within 0.1%), so queueing ABOVE kmin on the ToR-to-host queues is not what leaves these ACKs unmarked. This does not rule out ToR-to-host queueing as a contributor: the E->H maxima in the queue stats (87-141 KB, about 1.7-2.8 us) are around kmin (about 104 KB) and most of that queueing is below kmin and unmarked with ECN on or off, and it is the same size as the 2.2 us excess. Code reading (`compositequeue.cpp:116-143`): marking is decided on dequeue from the backlog left BEHIND the departing packet, with probability rising from kmin to kmax; a packet that waited behind a nearly full queue but is among the last of a draining burst leaves with a small backlog and goes out unmarked while its RTT includes the full wait. This is one candidate among several (the others: the delay is mostly sub-kmin ToR-to-host queueing, or on the ACK return path); none was tested (no per-packet queue-depth trace). The cause is open.
- **Stale entries after a failure**: not tested (freezing is out of scope). Recorded bounds: exposure lasts from the failure to the first RTO; C1 had 924 `bank_pop` sends inside the failure window [50, 200) us, of which 7 were later retransmitted; the timer never binds above 2 us (E3), so a longer timer does not make entries staler in these cells.
- **Not run in this round**: frozen-mode checks (C2; freezing is out of scope by user instruction), stale entries after a failure, any intervention on the repeated-EV finding (design change, not decided), a per-packet queue-depth test of the dequeue-marking explanation, EV-to-path classification of D, more than one seed on the exp07 interaction cell.

# Modifications inventory — full detail

Split out of `CLAUDE.original.md` to keep the loaded `CLAUDE.md` context small. This file is
the **source of truth for the original-vs-added boundary** in `htsim/sim/`. `CLAUDE.md` keeps
only a one-line-per-entry index pointing here.

Every addition to `htsim/sim/` is tagged `[ADDED: <name>]` in code comments and below.
**Rule for future additions:** every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====`
banner at every modification site, (ii) a row in this file, (iii) an ARCHITECTURE doc under
`state_aware_experiments/`.

### `[ORIGINAL]` — paper artifact, untouched

All of `htsim/sim/` except the sections listed below. `artifact_scripts/` and `artifact_results/`
are fully untouched.

### `[ADDED: state-aware]` — gated by `-state_aware_ecn`

Architecture doc: [`state_aware_experiments/ARCHITECTURE.md`](ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_state_aware_ecn_enabled` static, `_network_is_asymmetric` per-source flag + setters | `-state_aware_ecn` |
| `htsim/sim/uec.cpp` | CC ECN-masking gate (~L1209); freeze/unfreeze flag hooks for REPS (~L3022, ~L2310) and FREEZING (~L3040, ~L2653); REPS-buffer CSV instrumentation | `-state_aware_ecn` |
| `htsim/sim/pipe.h/.cpp` | `Pipe::_failed` flag + early-drop in `receivePacket` | `Pipe::setFailed()` call |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-state_aware_ecn`, `-fail_link_time`, `-fail_link_target`, `-log_reps_state`, `-log_reps_state_src`; `LinkFailureEvent` class | own flags |

### `[ADDED: smart-filter]` — gated by `-smart_filter_mode`

**Mutually exclusive with state-aware and wtd-in-nscc** (binary errors out if any two are set together).
Architecture doc: [`state_aware_experiments/exp06_smart_filter_v6/ARCHITECTURE.md`](exp06_smart_filter_v6/ARCHITECTURE.md)

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
Architecture + results: [`state_aware_experiments/exp12_paper_repro_reps/README.md`](exp12_paper_repro_reps/README.md)

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
Architecture + results: [`state_aware_experiments/exp13_papers_reps_repro/README.md`](exp13_papers_reps_repro/README.md)

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
Architecture + results: [`state_aware_experiments/exp13_papers_reps_repro/RESULTS_DIAGNOSTIC.md`](exp13_papers_reps_repro/RESULTS_DIAGNOSTIC.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_per_host_lb_override` static map (~L385); `_parseLBName`/`_parseHostLBString` (~L387); `applyHostLBOverride()` (~L181); `_dispatchLB` private (~L677) | `-host_lb_overrides` |
| `htsim/sim/uec.cpp` | Static defs + parsers + `applyHostLBOverride` (~L125); `_dispatchLB` helper (~L185); constructor calls `_dispatchLB(_load_balancing_algo)` (~L635) | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flag `-host_lb_overrides` parser (~L290); `applyHostLBOverride()` call after `setSrc()` (~L1233) | `-host_lb_overrides` |

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
Architecture doc: [`state_aware_experiments/PATH_RR_ARCHITECTURE.md`](PATH_RR_ARCHITECTURE.md)

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
Results: [`state_aware_experiments/exp19_path_rr_asymmetry_v19/README.md`](exp19_path_rr_asymmetry_v19/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `path_rr_npaths_override` local map (~L214); CLI flag `-path_rr_npaths_override` parser (~L371); truncate `full_paths` before `setPaths` in PATH_RR setup block | `-path_rr_npaths_override` |

### `[ADDED: path-rr-startslot]` — extends `-path_rr_start_mode`

Adds a fifth start-slot mode `src_mod2`: each flow's RR start index is `(src × 2) % np`. With
`np=4` this yields slots [0,2,0,2,...] — 2 distinct slots vs 4 for `src_mod`. Tested in exp18
alongside the existing `zero` and `src_mod` modes against PATH_STATIC reference.
Results: [`state_aware_experiments/exp18_path_rr_startslot_v18/README.md`](exp18_path_rr_startslot_v18/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RR_START_SRC2` appended to `PathRRStartMode` enum | `-path_rr_start_mode src_mod2` |
| `htsim/sim/datacenter/main_uec.cpp` | `src_mod2` branch in `-path_rr_start_mode` parser; `PATH_RR_START_SRC2` case in `setPathRRStartIdx` switch: `start_idx = (src * 2) % np` | `-path_rr_start_mode src_mod2` |

### `[ADDED: path-random]` — gated by `-load_balancing_algo path_random`

Per-packet uniform-random path selection using the same source-routing infrastructure as PATH_RR.
Reuses `UecSrc::_paths[]` populated by `get_bidir_paths` at flow setup. On every packet,
`rand() % _paths.size()` is stored into `_path_rr_idx` (scratch register) before the route is
selected, so route and pathid are consistent. `processEv_path_random` is a no-op.
Results: [`state_aware_experiments/exp16_path_random_v16/README.md`](exp16_path_random_v16/README.md)

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
Results: [`state_aware_experiments/exp17_cwnd_corrected_v17/`](exp17_cwnd_corrected_v17/)

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

**Verification tests**: `state_aware_experiments/test_srv6/scripts/run_tests.sh` — 13/13 pass.
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

Experiment + results: [`state_aware_experiments/exp23_freezing_pxr_v23/README.md`](exp23_freezing_pxr_v23/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `FREEZING_PXR` in `LoadBalancing_Algo` enum; `_pxr_excluded_evs` + `_pxr_clear_deadline` per-source fields; `_pxr_window` public static; `nextEntropy_freezing_pxr` / `processEv_freezing_pxr` declarations; `sent_ev` added to `sendRecord`; `createSendRecord` declaration updated | `-load_balancing_algo freezing_pxr` |
| `htsim/sim/uec.cpp` | `_pxr_window` static def (200 ms default); `_parseLBName` entry; `_dispatchLB` case; `nextEntropy_freezing_pxr` (timer check + saturation guard + filtered REPS draw); `processEv_freezing_pxr` (filtered buffer add); RTO branch (exclusion + sliding deadline); `createSendRecord` stores `ev`; `rto_trigger_ev` captured before erase; `pxr_excluded_count` + `pxr_excluded_evs` CSV columns | `-load_balancing_algo freezing_pxr` |
| `htsim/sim/datacenter/main_uec.cpp` | `freezing_pxr` in `-load_balancing_algo` handler; `-pxr_window_us <N>` flag; CSV header update | own flags |

## `core-downlink-queue-log`

New `CoreDownlinkQueueSampler` class, banner `// ===== ADDED (core-downlink-queue-log) =====`.
Samples core→agg **downlink** queue depth (`queues_nc_nup[core][agg][0]`) — opposite
direction from the pre-existing `CoreQueueSampler` (agg→core uplink, `queues_nup_nc`) — for
the first N core switches (N and the sample interval are constructor args, not separate CLI
flags; currently called with N=16, interval=0.2 µs, both exp25-specific constants). Built to
check whether REPS's first-window round-robin (exp24) produces a synchronized queue spike at
flow start; see [`state_aware_experiments/exp25_queue_dynamics_v25/README.md`](exp25_queue_dynamics_v25/README.md)
for the (non-confirming) result.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `CoreDownlinkQueueSampler` class (after `TorQueueSampler`); `log_core_downlink_queues_file` local; `-log_core_downlink_queues <file>` CLI parser; construction wired next to the existing core/tor samplers | `-log_core_downlink_queues <file>` |

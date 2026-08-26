# PATH_RR Load Balancing — Architecture & Design Notes

Added: 2026-06-04
Tag: `[ADDED: path-rr]`

---

## Motivation

All existing NSCC load-balancing algorithms in this simulator (INCREMENTAL, OBLIVIOUS, BITMAP,
REPS, FREEZING, …) share the same routing mechanism:

1. The sender assigns an **entropy value (EV)** to each packet.
2. At every switch hop, the switch hashes `(flow_id, EV, per-switch random salt)` and uses
   the result modulo the number of available uplinks to pick a port.

Because the hash salt at each switch is an independent random value, two different EVs can
produce the *same* sequence of port choices through the entire topology — they map to the same
physical path. This means INCREMENTAL (which just cycles EV = 0, 1, 2, …) and OBLIVIOUS
(uniform random EV) do **not** guarantee cycling over distinct physical paths.

PATH_RR implements a **true round-robin over distinct physical paths** by bypassing per-hop
ECMP entirely and using full **source routing**.

---

## How It Works

### Setup (once per flow, before first packet)

`main_uec.cpp` calls `FatTreeTopology::get_bidir_paths(src, dst, false)` immediately after
`connectPort()`.  This topology utility enumerates every distinct end-to-end path between
`src` and `dst` as pre-allocated `Route` objects (a `Route` is an ordered list of
`PacketSink*` — queues and pipes — that the packet traverses).

The result is stored in each `UecSrc`'s `_paths` vector via `setPaths()`.

Number of distinct paths by host placement in a k-port fat tree:
| Placement | Distinct paths |
|---|---|
| Same ToR rack | 1 |
| Same pod, different rack | K/2 (through different Agg switches) |
| Different pod | (K/2)² (all Agg + Core combinations) |

For k=4: same-pod → 2 paths; different-pod → 4 paths.

### Per-packet selection

On every new or retransmitted data packet, `sendNewPacket` / `sendRtxPacket` does:

```
effective_route = _paths[_path_rr_idx % _paths.size()]
```

and creates the packet with `effective_route` as its route instead of the usual NIC-provided
host→ToR stub.  `nextEntropy_path_rr()` is then called (as part of the standard `nextEntropy`
function-pointer dispatch), which:

1. Returns the current `_path_rr_idx % _paths.size()` as the packet's `pathid` field
   (harmless — no switch will hash it since the packet follows an explicit source route).
2. Increments `_path_rr_idx`.

The two reads of `_path_rr_idx` (in the route selection and inside `nextEntropy_path_rr`) are
separated by only a few lines of single-threaded code with no interleaving, so they always
refer to the same packet's slot.

### Why switches don't do ECMP on these packets

An htsim `Route` is a complete sequence of `PacketSink*`.  When a packet is created with a
full source route, each network element (pipe, queue, switch input port) receives the packet
and passes it to the next element in the `Route` list without consulting the switch FIB or
running the ECMP hash.  The switch's `getNextHop()` / ECMP logic is never reached for
source-routed packets.

### Feedback

`processEv_path_rr()` is a no-op.  PATH_RR is a pure round-robin; network feedback
(ECN marks, NACKs, timeouts) is intentionally ignored.  Adding feedback-aware path eviction
is a straightforward future extension (gate on the `path_rr` algo check, swap out a slot in
`_paths` using `get_bidir_paths` or a global path table).

---

## Code Locations

| What | File | Lines |
|---|---|---|
| `PATH_RR` enum value | `htsim/sim/uec.h` | `LoadBalancing_Algo` enum |
| `_path_rr_idx` field | `htsim/sim/uec.h` | near `_hklb_send_idx` |
| `setPaths()` method | `htsim/sim/uec.h` | near `get_paths()` |
| `nextEntropy_path_rr` / `processEv_path_rr` decls | `htsim/sim/uec.h` | near other `nextEntropy_*` decls |
| `_parseLBName` entry | `htsim/sim/uec.cpp` | `"path_rr"` → `PATH_RR` |
| `_dispatchLB` case | `htsim/sim/uec.cpp` | after `HKLB` block |
| `processEv_path_rr` impl | `htsim/sim/uec.cpp` | after `processEv_incremental` |
| `nextEntropy_path_rr` impl | `htsim/sim/uec.cpp` | after `nextEntropy_oblivious` |
| `effective_route` injection | `htsim/sim/uec.cpp` | `sendNewPacket`, `sendRtxPacket` |
| CLI `-load_balancing_algo path_rr` | `htsim/sim/datacenter/main_uec.cpp` | in LB algo parser |
| `setPaths` call per flow | `htsim/sim/datacenter/main_uec.cpp` | inside `connectPort` loop, `ECMP_FIB` case |

---

## CLI Usage

```bash
./htsim_uec \
    -load_balancing_algo path_rr \
    -sender_cc_algo nscc \
    -disable_tor_ecn \
    -sender_cc_only \
    ...
```

At startup, for each flow the simulator prints:
```
PATH_RR: <src>-><dst> plane=0 distinct_paths=<N>
```

Verify `N` matches the expected value for the topology (2 or 4 for k=4 fat tree, 1 for
same-ToR pairs).

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Source routing instead of EV enumeration | Per-switch `_hash_salt` is private; deriving which EVs map to distinct paths would require exposing salts and simulating the full hash chain per flow. Source routing is exact and requires no topology internals beyond `get_bidir_paths`. |
| `_paths` populated after `connectPort` | `src`/`dst` addresses (`_srcaddr`/`_dstaddr`) are only set by `setSrc`/`setDst`, which are called before `connectPort`. `_dispatchLB` runs at constructor time before these are known, so path enumeration must be deferred. |
| `_path_rr_idx` read before `nextEntropy` advances it | The effective route for a packet must be selected at the same RR position that `nextEntropy` will report. Reading `_path_rr_idx` just before packet creation and advancing it inside `nextEntropy_path_rr` (called a few lines later) keeps them in sync without any extra state. |
| `processEv_path_rr` is a no-op | A pure RR baseline ignores congestion feedback by definition. |
| Same-ToR flows get `_paths.size() == 1` | `get_bidir_paths` returns a single path for same-ToR pairs. The RR cycle over a single element is correct (the packet always takes the one available path). |

---

## Caveats and Limitations

- **Multi-plane topologies** (`-planes N > 1`): each plane gets an independent path
  enumeration via the per-plane `topo[p]` call.  Tested only with `planes=1`.
- **Dynamic workloads**: each `UecSrc` object has a fixed `(src, dst)` pair and its own
  `_paths` buffer.  Flows spawned at different simulation times each get a fresh
  `get_bidir_paths` call at their own setup point.  No shared mutable state across flows.
- **Concurrent flows, same (src, dst)**: independent `_path_rr_idx` counters — no
  coordination.  Both flows cycle independently through the same path set (no head-of-line
  avoidance across flows).
- **No congestion response**: PATH_RR does not react to ECN/NACK/timeout.  It is intended
  as a clean baseline, not a production algorithm.
- **`per-host-lb` override** (`-host_lb_overrides`): the `_parseLBName` function maps
  `"path_rr"` to `PATH_RR`, so per-host overrides work.  However, `setPaths` is called
  globally for all flows when the global algo is `PATH_RR`; per-host PATH_RR overrides
  with a non-PATH_RR global would need a separate `setPaths` call after
  `applyHostLBOverride`.

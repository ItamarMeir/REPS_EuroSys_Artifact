# Ofan switch-side load balancer: architecture

Implements the switch-based Ofan algorithm of McClure et al., "Ofan: Optimal Load Balancing for AI Training" (arXiv 2610.07230, sections 4 and App. F). Gated by `-strat ofan`; with the flag absent the simulator output is byte-identical to before (checked by `experiments/exp32_ofan/scripts/baseline.sh`). Results: [`exp32_ofan/README.md`](exp32_ofan/README.md).

## Idea

On a fat tree only the upward path is a free choice; the downward path to a destination is unique. Ofan keeps, in each edge/aggregation switch, one round-robin pointer per *destination group* and uses it to pick the northbound port:

- **Edge (ToR) switch:** key `d` = destination edge switch (`FatTreeTopology::HOST_POD_SWITCH(dst)`), `Nd` = number of edge switches.
- **Aggregation switch (3-tier, going up):** key `d` = destination pod (`HOST_POD(dst)`), `Nd` = number of pods.
- Each key has two pointers: type `t=0` full data packets, `t=1` everything else (ACK, NACK, PULL, trimmed headers). The ACK pointer starts `floor(w/2)` slots away from the data pointer; the data pointer starts at a random slot. `w` = number of uplinks in the FIB set.

The pointer indexes a *slot*, mapped to a physical port by the per-key permutation of App. F.2 (`ofan_order.h`):

```
id  = d + Nd*t;  b = ceil(log2 w);  id1 = id mod 2^b;  id2 = floor(id / 2^b)
pi(i) = ( xor_w(P[i], id1) + id2 ) mod w,   xor_w(v,x) = v^x if v^x < w else v
```

`P` is one global seeded permutation of `{0..w-1}` shared by all switches (local `mt19937_64`, does not touch the global RNG). Each step outputs `pi(ptr)` then `ptr = (ptr+1) mod w`, so any `w` consecutive packets of a key use every port exactly once.

## Where it lives in the code

| Piece | Location |
|---|---|
| Port-order math (header-only, no htsim deps) | `htsim/sim/datacenter/ofan_order.h` |
| Strategy enum `OFAN = 6`, per-switch `_ofan_ptrs` (key id -> pointer), `ofan_choose()` | `fat_tree_switch.{h,cpp}` |
| Hook in the per-strategy `switch` of `FatTreeSwitch::getNextHop` | `case OFAN:` after `RR_ECMP` |
| CLI: `-strat ofan`, `-ofan_ack_mode spray\|hash`, `-ofan_identity_order`, `-log_ofan_counts <tsv>` | `main_uec.cpp` |
| Per-queue statistics for validation: `-log_queue_stats <tsv>` | `compositequeue.{h,cpp}`, `main_uec.cpp` |

`ofan_choose` returns the index into the FIB entry vector. It only owns northbound sets (`getDirection()==UP` on a TOR or AGG switch). Any other multi-entry set (DOWN sets with `bundlesize>1`, CORE switches) falls back to the ECMP hash and is therefore unchanged.

### Port order must be stable

`FatTreeSwitch::permute_paths` shuffles FIB vectors, and the AGG up-vector is rebuilt and shuffled per destination. That would map slot `i` to different physical ports for different destinations of the same key and break consolidation. Under `OFAN` both `permute_paths` call sites (verified load-bearing by a mutation test, see exp32 README) in the FIB-building code are skipped, so every destination of a switch sees the same construction order (core index order; the TOR `_uproutes` vector is already shared).

### Failures

If some first-hop pipe is failed (`Pipe::isFailed()`), `ofan::pick` skips to the next slot whose port is live and commits the pointer past it, so each live port still receives one packet per round. **This is weaker than the paper**, which assumes BGP-style reachability: a failure that is not on the choosing switch's own first hop (for example the Core->Agg downlink of another pod) is not seen. exp32 S7 shows the consequence.

## Interaction with hosts and congestion control

Ofan changes only which port a switch picks; hosts are unchanged.

- **Entropy:** switches ignore `pathid`, so use `-load_balancing_algo ecmp` (constant entropy). `-strat ofan` forces `path_entropy_size = 1` after argument parsing (a later `-paths` cannot override it) and exits with an error if combined with `-use_srv6`, `path_*` load balancing or `-host_lb_overrides`, because source-routed packets bypass the FIB and Ofan would silently do nothing. REPS/FREEZING feedback is meaningless under Ofan.
- **Reordering:** per-packet spraying reorders packets. The receiver handles this with its bitmap; `-enable_fast_loss_recovery` must stay off (default). No `uecMaxInFlightPkts` abort occurred in any exp32 run.
- **ACKs/NACKs:** they are ordinary packets routed by destination, so they traverse the same `getNextHop`; their key is the *original sender's* edge switch/pod, on the `t=1` pointer. Trimmed data headers (data direction) share the `t=1` pointer of their key with ACKs/NACKs flowing the other way. `-ofan_ack_mode hash` pins small packets per flow with the ECMP hash instead (ablation).
- **CCAs:** NSCC, MSwift and constant-window CC are per-flow and see only ECN/RTT. Balanced queues remove ECN marks and trims, so the CC rarely engages (exp32 S6).
- **Timing:** the decision is made on arrival at the switch (before the switching-latency pipe), like the existing adaptive-routing modes.

## Validation hooks

`-log_ofan_counts` counts packets per (switch, key, type, packet class, physical egress queue); `check_balance.py` asserts every key's counts differ by at most 1 across ports. `-log_queue_stats` dumps per-queue max occupancy and bytes per layer (E->A, A->C, C->A, A->E, E->H); `link_overload.py` turns it into the paper's per-layer worst-link overload.

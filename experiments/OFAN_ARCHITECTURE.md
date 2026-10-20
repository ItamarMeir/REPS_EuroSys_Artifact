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

## Failure convergence model (`-routing_convergence_us G`)

The legacy Ofan behaviour in "Failures" above (instant skip of a *locally* failed first hop, nothing else) is an oracle-local model and is kept only for backward compatibility when the flag is absent. New experiments must pass `-routing_convergence_us`, which models what the Ofan paper assumes ("continue to use existing routing protocols such as BGP W-ECMP to propagate information about failures", App. I) with the single parameter of the predecessor paper (arXiv 2507.21372, section 5.2): **G is the same for every switch, including the local one**. `G=0` = failure known the instant it happens, large G = never reconverges. Gated on the flag; absent => byte-identical output. Code is marked `// ===== ADDED (routing-convergence) =====`; inventory in `MODIFICATIONS.md` (`[ADDED: routing-convergence]`).

### Knowledge

`LinkFailureEvent` (`main_uec.cpp`) registers each directed pipe it fails with `(t_fail, t_recover)` (no recovery if `t_recover <= t_fail`). A pipe is *known down* iff `t_fail + G <= now < t_recover + G`. Before `t_fail + G` switches keep sending into the dead pipe (the existing `Pipe::_failed` drops them), so nothing is known early. The *epoch* is the number of knowledge transitions (`t_fail+G`, `t_recover+G`) that are `<= now`. Deviation from the first design sketch: the epoch is derived from simulated time rather than bumped by `EventSource`s, so there is no ordering race between a packet arriving at exactly `t_fail+G` and an epoch event; it also adds no events (a huge G cannot extend the run). The only events are the `-routing_check` ones.

### Reachability mask

For a multi-entry FIB set of switch S toward destination ToR T, `valid[i]` says entry i leads to T over pipes not known down (`FatTreeSwitch::rc_compute_mask`; A = aggs per pod, core of agg g's uplink l = `l*A + g%A`, dest agg of core c in pod P = `P*A + c%A`):

| Set | Entry valid iff |
|---|---|
| ToR, up via agg k | the entry's own first-hop pipe live AND k reaches T: 2-tier or same pod: some live bundle `pipes_nup_nlp[k][T][*]`; other pod: some uplink l with a live bundle k->c, a live bundle c->dest agg and a live bundle dest agg->T |
| Agg, up via core c (3-tier, other pod) | own pipe live AND some live bundle `pipes_nc_nup[c][dagg]` AND some live `pipes_nup_nlp[dagg][T]` (`dagg = P*A + c%A`) |
| Agg or Core, down (incl. bundles) | own first-hop pipe live (entry level only) |

Since `dagg` is the same for every core, two destination ToRs of one pod give different masks at an Agg going up only when all entries are invalid (dead end); this is what lets the pod-level Ofan pointer keep its once-per-round property.

**Dead end** (no valid entry): the unfiltered set is used, as in the paper (fn. 5). Singleton sets are never filtered.

### Applying the mask

Cache key: (source FIB vector pointer, dst ToR, epoch), per switch; a pointer is needed because the ToR up-vector is shared by all destinations while non-Ofan Agg up-vectors are per-destination and shuffled. When every entry is valid the **original vector is returned untouched** (so behaviour with no known failure equals the flag-off one, modulo the epoch bookkeeping).

- **Ofan:** the mask goes to `ofan::pick` on the full vector (pointer semantics and `w` preserved, so each live port still gets one packet per round). Sets Ofan does not own (down bundles) hash over the filtered vector. The legacy `isFailed()` skip is disabled under the flag.
- **ECMP, ECMP_ADAPTIVE, ADAPTIVE_ROUTING, RR, RR_ECMP:** the strategy runs on the cached filtered vector (index into it). RR permutes the *filtered copy*; the original may be permuted in place when used for a destination with an all-valid mask, so the invalid set is stored by entry identity, not index (found by the decision counter: index-based comparison produced false "known dead" decisions with `ecmp_rr`).
- **Flowlet AR (`-ar_granularity flow`):** `_flowlet_maps` (egress index into the vector) is cleared at every epoch change, plus an index bound guard.

### Counters (printed at end of run)

`ROUTING_CONV decisions_to_known_dead=<n> drops_before_known=<n> drops_after_known=<n>`:

- `decisions_to_known_dead`: `getNextHop` choices (multi-entry sets, non-dead-end) of an entry that is invalid in the mask or whose own first-hop pipe is known down. **Must be 0** (the gate for "no cheating / no stale use").
- `drops_*`: packets dropped by `Pipe::_failed`, split by `now < min t_known(pipe)` vs `>=`. `drops_after_known` is not expected to be 0: packets already in the output queue or in the switching-latency pipe at `t_known` still drain into the dead pipe (bounded by queue occupancy / link rate + switch latency).

### `-routing_check` (debug)

Requires the flag. At t=0, at every knowledge transition and at the end, for every (switch, dst ToR) it builds the FIB-equivalent entry set from the topology's `queues_*` arrays, computes the production mask and an **independent brute-force reference**, and counts mismatches. The reference uses only `queues_*` / `getRemoteEndpoint()` and the paired pipe (not the index formulas above): it finds the intact-graph minimal valley-free (up* then down*) hop count and searches live valley-free paths of exactly that length; downward first hops are first-hop liveness only. It additionally asserts the pod-level property above. During the run, every real FIB vector for which a cache entry is computed is compared against the reference too. Output: `ROUTING_CHECK_INFO runs=.. synthetic_pairs=.. real_fib_vectors=..` and `ROUTING_CHECK mismatches=<n>`. Driver: `exp32_ofan/scripts/rc_check.py`.

**`-routing_check_random <trials> <seed> <p>`** (hidden, requires `-routing_check`): knowledge-only test, no packets involved. Per trial it draws a random subset (each pipe independently with probability p) of **all** pipes of the reference edge list (`queues_nlp_nup`, `queues_nup_nlp`, `queues_nup_nc`, `queues_nc_nup`, every bundle member) as the known-down set, overwrites the real known set **without touching `Pipe::_failed`**, runs the synthetic production-vs-reference mask comparison for every (switch, dst ToR), and restores the real set. It exists because the failure injectors only fail Agg<->Core (3-tier) or ToR<->Spine (2-tier) pipes, so the 3-tier ToR<->Agg legs and bundles (`Bundle > 1`) were never exercised. The same-pod "agg masks agree outside dead end" check is skipped in this mode (it assumes only Agg<->Core failures). Drivers: `exp32_ofan/scripts/rc_random.sh` (one case) and `rc_random_suite.sh`. Bundle topologies: `htsim/sim/datacenter/topologies/test.topo` (tier-2 bundle 2) and `exp32_ofan/topologies/fat_tree_32_bundle2_3t_400g.topo` (bundle 2 at tiers 1 and 2; loads, routes, all 32 flows finish).

### Limits and usage rules

- **`G=0` with a mid-run failure is instant global knowledge (cheating).** It equals the paper's "converged" case only for failures present at t=0. For mid-run failures use `G >= ~1 RTT`; state this next to any G=0 result.
- Directed pipes; `-fail_link_*` fails both directions of an Agg<->Core link, `-timed_fail_*` (2-tier) one direction per pipe. Host links are not modelled.
- `-failures_input` (FAILURE_GENERATOR) failures are invisible to the model => hard error. `-failed N` link degradation is out of scope.
- Hosts are unchanged: REPS/RTO still recover on their own timescale on top of the pruned switch ECMP.
- Only `topo[0]` is registered/checked.
- **Hard errors** at startup: `-routing_convergence_us` combined with `-failures_input`, `-use_srv6`, `-load_balancing_algo path_rr|path_random|path_static`, `-fail_src_paths` or `-sol_avoid_timed_failure` (source-routed packets bypass the switch FIB, so the model would silently do nothing); a negative or non-finite G. `-routing_check` exits with status 1 at the end of the run if any mismatch was counted.
- **Cache size.** `_rc_cache` has one entry per (source FIB vector, dst ToR) actually looked up and is overwritten in place when the epoch changes (never shrunk). Worst case over the fabric is on the order of (#aggs x #hosts) entries, each holding a mask plus the filtered/invalid vectors of the fan-out size. Fine for the 16-432 host runs here; revisit before using it at 8192 hosts.
- **ECMP rehash.** The ECMP strategies pick `hash % filtered.size()`. A failure therefore changes the modulus and re-hashes every flow at that switch (unlike resilient hashing, where only the flows on the dead port move). This inflates reordering for `ecmp_host` at each epoch change; it is a property of the modelled ECMP, not of the knowledge model, but it matters when reading the ecmp_host numbers.
- Not verified here: time behaviour beyond the counters (the G3 timing gate and balance gate G4 are separate work).

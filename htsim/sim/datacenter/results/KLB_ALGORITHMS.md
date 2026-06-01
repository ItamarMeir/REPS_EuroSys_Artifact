# KLB / SKLB / HKLB — Algorithm Reference

Three open-loop load-balancing algorithms for the K-LB family, implemented in `htsim/sim/uec.{h,cpp}` as variants of `UecSrc::LoadBalancing_Algo`. All three:

- Maintain a small per-flow set of *Entropy Values* (EVs); each EV deterministically maps to one physical core-tier path at the switch.
- Bypass per-flow congestion control: cwnd is set far above the BDP (`-cwnd 10000` packets ≫ BDP ≈ 96 packets at 400 Gbps × 8 µs RTT) and held constant via `-sender_cc_algo constant`, so the sender injects at line rate and ECN is used purely as a routing signal. The exact cwnd value is not load-bearing — anything ≥ a few × BDP behaves identically; we use 10 000 packets so the same flag works across topologies without recomputation.
- Differ in **how the active EV set is maintained** in response to PATH_ECN feedback.

The three algorithms are designed for, and evaluated on, a Clos / fat-tree where the Top-of-Rack downlink ports do **not** mark ECN (the "Leaf Exception"); core and aggregation tiers do. Buffer depth at the leaf is large so that destination incast is absorbed without packet drops.

> **Common parameter**: `_klb_k` = active-set size (CLI: `-klb_k <K>`).
> **Common signal**: ACK carries `pkt.ev()` (path ID) and `pkt.ecn_echo()` (bool), dispatched via `processEv(path_id, PATH_GOOD | PATH_ECN | PATH_NACK | PATH_TIMEOUT)`.

---

## 1. KLB — *K-Load Balancer*

**Idea.** Maintain exactly K active EVs. On each send, round-robin through the K EVs. On PATH_ECN for an active EV, **probabilistically** evict and replace it with a different path.

### State

```cpp
int                  _klb_k;            // active-set size (CLI -klb_k)
std::vector<uint16_t> _klb_active_evs;  // K active path IDs
uint32_t              _klb_send_idx;    // round-robin counter
```

### Initialization (`uec.cpp:586–609`)

Fill the K slots with **distinct** path IDs via partial Fisher–Yates shuffle, so that the initial active set never duplicates a path (which would waste a slot). If K > N_paths, the surplus slots are filled with `rand() % _no_of_paths` (duplicates allowed beyond N).

### Path selection — `nextEntropy_KLB()` (`uec.cpp:2426–2430`)

```cpp
uint16_t ev = _klb_active_evs[_klb_send_idx % _klb_k];
_klb_send_idx++;
return ev;
```

Deterministic round-robin — equal load over the K active EVs.

### ECN handling — `processEv_KLB()` (`uec.cpp:2432–2461`)

```
on PATH_ECN for ev:
    find slot s with _klb_active_evs[s] == ev      // ignore stale ACKs
    draw x ∈ [0, 1) uniformly
    if x ≤ 1/K:
        keep ev                                     // ignore ECN (lottery)
    else:
        _klb_active_evs[s] = klb_pick_fresh_path(s) // distinct from other slots
```

The (K − 1)/K replacement probability is K-LB's distinguishing feature: at K=1, ECN is **never** acted on (single-path forever); at K=∞, ECN is always honored. The replacement helper `klb_pick_fresh_path(s)` guarantees the new EV does not clash with any other active slot.

### Optional fixes (`-klb_enable_fixes`)

- **Fix A — EV cooldown**: just-evicted EV is blocked for ~6 µs (1 RTT) via `_ev_quiet_until[ev]`, preventing immediate re-selection of a known-congested path.
- **Fix B1 — ECN hysteresis**: require **2 consecutive ECNs** on a slot before considering eviction (per-slot streak counter, reset on PATH_GOOD).

Both fixes were measured to be inert in the open-loop steady state (see `KLB_SKLB_RESULTS.md`); leaving them off makes KLB's behaviour deterministically traceable.

### Properties

- **Stateless switches**. The switch sees only ECN at queue threshold; no per-flow state.
- **Steady-state convergence to non-zero ECN**. With cwnd large and N senders fighting for ≤ N paths, the system reaches an equilibrium with persistent residual marking. (See *no LB converges to zero ECN* in `ECN_SWEEP_RESULTS.md`.)
- **K = N is not optimal.** When K ≥ N_paths, all paths are perpetually in rotation; the round-robin re-creates the static-mapping problem KLB was designed to break. K ≈ ⅔ N_paths was best on a k=10 fat-tree.

---

## 2. SKLB — *Stateful K-Load Balancer*

**Idea.** Same sender state as KLB, but the **switch enforces incumbent advantage** via a small per-port table of (flow, EV) tuples. Sender always replaces on ECN (no lottery), because the lottery's role of avoiding synchronized retry is now played by the switch state.

### State (sender)

Same as KLB: `_klb_k`, `_klb_active_evs`, `_klb_send_idx`. (The two algorithms share initialization at `uec.cpp:586`.)

### State (switch — `StatefulECNQueue`)

Each downstream queue maintains a map keyed by `(flow_id, path_id)`:

```cpp
struct SubflowKey  { flowid_t flow; uint16_t path; };
struct Entry       { simtime_picosec last_seen; };
std::map<SubflowKey, Entry> _incumbents;   // capped at _max_incumbents
simtime_picosec _idle_timeout_ps;          // default 6 µs (≈ 1 RTT)
```

On packet arrival (`statefulecnqueue.cpp:26-56`):

1. If `(flow, ev)` is already in the map → **incumbent**: clear ECN, refresh `last_seen`, mark packet as *admitted*.
2. Else lazily evict map entries with `now − last_seen > idle_timeout`.
3. If map has room → admit `(flow, ev)`, clear ECN, mark packet as *admitted*.
4. Else → **reject**: set ECN on this packet (not admitted).
5. **Absolute incumbent advantage**: queue-depth ECN (`queuesize + pkt.size > _ecn_threshold`) is applied **only to non-admitted packets** (rejected newcomers). Admitted sub-flows — incumbents and newly-admitted — are never re-marked by queue depth. This protects the K admitted sub-flows on each port from being evicted by SKLB's deterministic replacement when the queue is deep due to their own legitimate use.

CLI: `-queue_type stateful_ecn -max_incumbents <K> -idle_timeout_us <us>`.

The Leaf Exception is enforced by `fat_tree_topology.cpp:789-801`: ToR-downlink queues get `tracking_on = false` *and* skip `set_ecn_threshold()`, so they emit zero ECN regardless of queue depth.

### Path selection — `nextEntropy_SKLB()` (`uec.cpp:2463–2467`)

Identical to KLB (round-robin over K EVs).

### ECN handling — `processEv_SKLB()` (`uec.cpp:2469–2489`)

```
on PATH_ECN for ev:
    find slot s with _klb_active_evs[s] == ev
    _klb_active_evs[s] = klb_pick_fresh_path(s)  // deterministic eviction
```

No probabilistic gate — every ECN evicts. This is safe because the switch already prevents incumbents from getting ECN (unless congestion is genuine), so PATH_ECN almost always means **"this EV is a newcomer that got rejected"** rather than "this established EV is contributing to queue buildup".

### Properties

- **Co-designed**: SKLB's deterministic 100% replacement at the sender pairs with the switch's rejection-on-full at the queue. Decoupling them (KLB sender + Stateful queue, or SKLB sender + Composite queue) breaks the invariant.
- **`max_incumbents` sizing matters.** Should be ≥ expected number of concurrent EVs per link. On a permutation TM each ToR-uplink sees K sub-flows from each of its hosts, so `max_incumbents = min(K, N_paths)` is the rule of thumb encoded in the eval scripts.
- **`idle_timeout` must be tight.** With the original `30 µs` (≈ 5 RTT), ghost entries kept slots occupied long after their sender had abandoned the EV; replacement EVs landed on a full map and bounced. Reducing to `6 µs` (≈ 1 RTT) eliminated this. (Documented in `KLB_SKLB_RESULTS.md` §2.)
- **Competitive with KLB after the absolute-incumbent-advantage fix.** Originally the queue's congestion-ECN check re-marked incumbents, causing the SKLB sender to thrash them out → newcomer admitted → queue still deep → next incumbent evicted (loop). The fix (skip queue-depth ECN for admitted sub-flows) drops SS_core ECN by ~75-97 % and closes ≈ 50 % of the FCT gap to KLB at the same K (see `ECN_SWEEP_RESULTS.md` §Update). On k=10 at ECN=25, `sklb_k16` mean FCT improved from 825.8 µs → 796.3 µs, within 31 µs of `klb_k16` (765.1 µs).
- **ECN-threshold insensitive after the fix.** Since admitted sub-flows ignore queue depth and rejected newcomers always get ECN, the threshold value (5 vs 15 vs 25) becomes a no-op for K-LB family + StatefulECN. SKLB and HKLB+SE rows are identical across the ECN sweep.

---

## 3. HKLB — *Hybrid K-Load Balancer*

**Idea.** Start with an **empty** active set. Send oblivious random EVs (discovery phase). Promote an EV to the active set when it returns a clean ACK. Once the active set has K members, round-robin over them (steady state). On PATH_ECN for an active EV, fall back to KLB's probabilistic eviction.

### State

```cpp
std::unordered_set<uint16_t> _hklb_active_set;   // O(1) membership test
std::vector<uint16_t>        _hklb_active_list;  // ordered for round-robin
uint32_t                     _hklb_send_idx;     // round-robin counter
```

### Initialization (`uec.cpp:610–620`)

`_klb_k = min(_klb_k_param, N_paths)` — capping is essential: if K > N_paths, the active set (which holds distinct path IDs) can never reach size K and the sender stays in discovery forever.

### Path selection — `nextEntropy_HybridKLB()` (`uec.cpp:2491–2509`)

```
_hklb_send_idx++
if _hklb_active_set.size() >= K:
    return _hklb_active_list[_hklb_send_idx % K]   // steady state
else:
    return rand() % N_paths                         // discovery probe
```

During discovery, every send is a probe. Multiple probes are in flight simultaneously (one per outstanding packet), so it typically takes ≪ 1 RTT to collect K clean PATH_GOOD ACKs.

### ECN handling — `processEv_HybridKLB()` (`uec.cpp:2511–2543`)

```
on PATH_GOOD for ev:
    if ev not in active_set and active_set.size() < K:
        active_set.add(ev);  active_list.push_back(ev)

on PATH_ECN for ev:
    if ev not in active_set:
        return  // probe got ECN — just won't be promoted; no state change
    draw x ∈ [0, 1) uniformly
    if x > 1/K:
        active_set.erase(ev);  remove ev from active_list
    // else keep (KLB-style 1/K lottery)

on PATH_NACK / PATH_TIMEOUT for ev:
    if ev in active_set: always evict
```

### Properties

- **No convergence tax.** KLB commits K random EVs at flow start and pays the full RTT for the bad ones to surface as ECN. HKLB never adds an EV until it has been *demonstrated clean*, so the active set is implicitly filtered. This shows up as flat FCT vs K — see `ECN_SWEEP_RESULTS.md`:
  ```
  hklb (k=10, ECN=25): K=4 → 786, K=8 → 785, K=16 → 802, K=32 → 804 µs
  klb  (k=10, ECN=25): K=4 → 884, K=8 → 803, K=16 → 765, K=32 → 809 µs
  ```
  HKLB is far more K-insensitive: the discovery phase auto-tunes the effective active set.
- **Falls back to KLB on incumbent ECN.** Once an EV is in the active set, an ECN on it is treated identically to KLB — probabilistic (K-1)/K eviction. This prevents synchronized retry waves at steady state.
- **NACK / TIMEOUT always evict.** Unlike PATH_ECN (a soft congestion signal), these are hard failures and bypass the lottery.

### Optional combinations

- **HKLB + StatefulECN** (`-load_balancing_algo hklb -queue_type stateful_ecn ...`): the switch's incumbent map sharpens the discovery signal — probes that arrive at a full link receive a *definitive* rejection rather than a queue-buildup-driven probabilistic mark. After the absolute-incumbent-advantage fix, HKLB+SE on k=10 matches HKLB+Composite at K=16 (801.6 vs 802.6 µs mean FCT) and achieves the lowest core ECN of any K-LB variant (0.029 at K=32 — almost 10× lower than HKLB+Composite). Small K=4 still loses because admission rejection wastes early discovery probes.

---

## Side-by-Side Comparison

| Aspect                       | KLB                          | SKLB                              | HKLB                                  |
|------------------------------|------------------------------|-----------------------------------|---------------------------------------|
| Sender active set            | K fixed slots (Fisher–Yates init) | K fixed slots (Fisher–Yates init) | Grows from 0 to K via discovery       |
| Path selection (steady)      | Round-robin over K           | Round-robin over K                | Round-robin over confirmed-clean K    |
| Path selection (start)       | Round-robin over K (initial random) | Same                       | **Oblivious random** until K clean   |
| PATH_ECN response            | Evict slot with prob (K-1)/K | **Evict slot deterministically**  | Evict from set with prob (K-1)/K     |
| Replacement candidate        | Distinct from other slots (Fisher–Yates–style) | Same         | Re-discovered via subsequent probes  |
| Switch state required        | None                         | `(flow, EV)` incumbent table       | None (or optional Stateful)          |
| Behavior when K = N_paths    | Static rotation over all paths (perpetual rotation) | Same | Cap'd to K = N; equivalent           |
| Behavior when K > N_paths    | Tolerated; duplicate EVs     | Tolerated; switch map thrashes     | **Cap'd to N internally**            |
| Best K (k=10 fat-tree, ECN=25) | K=16 (765 µs)            | K=16 (826 µs)                      | K=4-8 (~786 µs, flat thereafter)     |
| K-sensitivity                | High (U-shaped curve)        | High (U-shaped curve)              | Low (flat from K=4)                  |

## Relationship to REPS

REPS (uec.cpp:2313, *Recycled Entropy Packet Spraying*) maintains a **dynamic recycle queue** rather than a fixed set:

```cpp
// nextEntropy_REPS
if first window: round-robin all N paths
else if _next_pathid empty: random
else: pop _next_pathid.front()         // consume the EV

// processEv_REPS
if PATH_GOOD: _next_pathid.push_back(path_id)
// PATH_ECN ignored entirely
```

REPS *consumes* an EV when used and re-enqueues it only when a later clean ACK confirms it; the active set is therefore (a) unbounded and (b) re-ordered by traffic. KLB-family algorithms cap the set at K and rotate over a fixed order. The two designs solve the same problem (decentralized path-set adaptation under ECN) with different memory-vs-fairness trade-offs.

> **K=N KLB is not REPS.** Confirmed both in code and empirically: `klb_k32 > N=25` on k=10 has 0.265 core ECN; `reps_linerate` has 0.224. The static round-robin of KLB phase-aligns across senders in a way REPS naturally breaks.

---

## File Map

| File                                | Contents                                          |
|-------------------------------------|---------------------------------------------------|
| `htsim/sim/uec.h`                   | `LoadBalancing_Algo` enum (KLB, SKLB, HKLB); per-instance state; method declarations |
| `htsim/sim/uec.cpp:586–621`         | Initialization (function-pointer wire-up, Fisher–Yates) |
| `htsim/sim/uec.cpp:2401–2424`       | `klb_pick_fresh_path()` — distinct-path picker with cooldown |
| `htsim/sim/uec.cpp:2426–2461`       | `nextEntropy_KLB()` / `processEv_KLB()` |
| `htsim/sim/uec.cpp:2463–2489`       | `nextEntropy_SKLB()` / `processEv_SKLB()` |
| `htsim/sim/uec.cpp:2491–2543`       | `nextEntropy_HybridKLB()` / `processEv_HybridKLB()` |
| `htsim/sim/statefulecnqueue.{h,cpp}`| `StatefulECNQueue` — incumbent-advantage switch queue used by SKLB |
| `htsim/sim/datacenter/main_uec.cpp` | CLI parsing for `-load_balancing_algo`, `-klb_k`, `-klb_enable_fixes`, `-queue_type stateful_ecn`, `-max_incumbents`, `-idle_timeout_us` |

## CLI examples

```bash
# KLB at K=8 on k=10 fat-tree
./htsim_uec -load_balancing_algo klb -klb_k 8 \
            -topo topologies/reps/fat_tree_250_1os_3t_400g.topo \
            -tm connection_matrices/perm_250n_250c_32MB_s42.cm \
            -paths 25 -sender_cc_only -sender_cc_algo constant -disable_tor_ecn \
            -ecn 25 25 -q 100 -cwnd 10000 -end 90000 -seed 42

# SKLB at K=8 — must request StatefulECN queue + size the incumbent table
./htsim_uec -load_balancing_algo sklb -klb_k 8 \
            -queue_type stateful_ecn -max_incumbents 8 -idle_timeout_us 6 \
            -topo ...  # remaining flags identical

# HKLB at K=4
./htsim_uec -load_balancing_algo hklb -klb_k 4 \
            -topo ...  # remaining flags identical
```

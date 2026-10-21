# V_B: cross-validation of our Ofan against the authors' simulator fork

Fork: github.com/smcclure20/csg-htsim, commit bb725a5 (2026-02-01), first author of the Ofan paper (arXiv 2610.07230) and of
arXiv 2507.21372. The fork is untrusted code; it was built only inside container `ofan-dev` under /tmp/mc (Makefiles and
drivers were read first). Our side used the frozen binary /tmp/frozen/htsim_uec_frozen. Nothing under `htsim/` in this repo
was touched. The fork copy has a small instrumentation patch (see section 2).

## 1. What the fork implements (file:line, relative to sim/datacenter/)

There are three related code paths. Only the DRB one is reachable from the drivers that expose LLSS.

**Driver and selection.** `main_const_llss.cpp` (also `main_const_erase_drb.cpp`) parses `-strat` at L217-264:
`ecmp`, `pkt_ar` (per-packet AR), `fl_ar`, `ecmp_ar`, `rr`, `rr_ecmp`, `llss` -> `PER_POD_IWRR`, `llss_perm` -> `PER_POD_IWRR_PERMUTE`,
`fib_llss` -> `FIB_LLSS`, `fib_llss_perm` -> `FIB_LLSS_PERMUTE`. Enum in `fat_tree_switch_drb.h:91`. Build target
`htsim_constcca_llss` (Makefile). `main_const.cpp` (non-DRB) has NO llss option, so `FIB_LLSS` in `fat_tree_switch.cpp`
is unreachable from `main_const`; `main_const_erase.cpp:231` does expose `fib_llss`.

**`fat_tree_switch.cpp` L511-528 (`FIB_LLSS`, earliest form).** Key `dest_id` = dest ToR at a ToR (`HOST_POD_SWITCH(dst)`), dest pod
otherwise (`HOST_POD`). `ptr_idx = dest_id*2 + is_ack` with `is_ack = (type==CONSTCCAACK || SWIFTACK)` (L520). Pointer is initialised to a random
32-bit value `_rng()` (L521-524, the switch's `_rng` is seeded from `_hash_salt = random()`), port = `ptr % available_hops->size()`, then `ptr++`.
`available_hops` is the FIB entry list for that destination in fixed port order (no per-switch shuffle). Pointer arrays sized `num_tors*2` (ToR) or `num_pods*2` (L30-32).
No weights, no size classes, no permutation.

**`fat_tree_switch_drb.cpp` L810-835 (`FIB_LLSS`/`FIB_LLSS_PERMUTE`).** Same pointer (`ptr_idx = dest*2 + is_ack`, random init, `% available_hops->size()`),
but it is used only `if (_ft->has_failures())` (L812; `fat_tree_topology_drb.h:161`: failed-link descriptions non-empty or `failed_links>0`). Otherwise it
falls through to the `PER_POD_IWRR` code. `FIB_LLSS_PERMUTE` adds (L827-831): when `ptr - wrap_start > 10*size`, `ptr += 1` and reset `wrap_start`, i.e. every ~10 rounds the
pointer skips one position.

**`fat_tree_switch_drb.cpp` L838-915 (`PER_POD_IWRR`, `PER_POD_IWRR_PERMUTE`), the "llss" proper.**
- Downward hop (`getDirection()==DOWN`, L843): plain 5-tuple hash ECMP over the single/few down routes.
- Uplink: one weighted schedule per destination pod, `_llss_schedules[dest_pod]` (L851-855), built lazily on first use or eagerly by
  `forcePopulateLlssSchedules()` (L446-451, called from `populate_all_routes`, `fat_tree_topology_drb.cpp:1422-1431`).
- Pointer key: `ptr_key_id = dest_leaf` at a ToR, `dest_pod` at an Agg (L863); `ptr_idx = key*2 + is_ack` (L864). Random init `i = _rng() % m` (L868).
  For the non-adaptive variants the sibling (data<->ACK) pointer is initialised at the same time with a fixed offset of half a schedule:
  ACK pointer = `(i + m/2) % m`, data pointer = `(i - m/2) % m` (L875-884). That is the "ACK-pointer offset".
- `PER_POD_IWRR_PERMUTE` (L890-895): when the pointer has wrapped >=10 times, pointer += 1 (mod schedule size). That is the only "permutation".
- Selection (L899-913): walk the schedule from the pointer, take the first port with `_is_path_valid(dst, port)`, advance the pointer, count wraparounds.
- Schedule construction (`_generate_llss_schedule`, L598-657): weights reduced by their GCD, ports listed in port-index order, then
  `std::shuffle(ports, _rng)` unless exp_mode (`IWRR_EXP/DET/A_RR` keep fixed order), then interleaved round robin (each round emits one entry per port with remaining weight).
  So the cyclic order is a random permutation drawn once per switch per dest pod; different switches get different orders.
- Weights: ToR (`_get_llss_leaf_weights`, L660-693) = 0 if the uplink is failed (`getFailed()`); intra-pod 1; inter-pod =
  `|reachable_cores(src agg) ∩ reachable_cores(symmetric agg in dest pod)|` ("symmetric spine proxy", `get_reachable_cores`, `fat_tree_topology_drb.cpp:1480-1511`, counts a core if any link of the bundle is not `getFailed()`).
  Agg (`_get_llss_spine_weights`, L695-715) = 1 if the core is reachable from the symmetric dest agg, else 0.

**Size classes.** None. The only split is data vs ACK (`is_ack`); there is no quantised-packet-size dimension in the pointer key.

**XOR/addition permutation (paper App. F.2).** Not present anywhere in the fork. `grep -niE "xor|permut|shuffle|id1|id2"` finds only: the
every-10-wraps `+1` rotation above, a leftover `permute_schedule()` (L588, Fisher-Yates, call commented out at L891), `permute_paths` for plain RR, and the one-off `std::shuffle` of the port order.
There is no per-destination-id derived XOR/add constant: ordering diversity comes from a per-switch random shuffle, not from `id1/id2`.

**Failure handling.** `failure_manager_drb.cpp`: `-ftime <fail_us> <route_us> <weight_us>` (main_const_llss.cpp L159-163; flows only if `-failpct -1.0 -fails N`).
- At `fail_time`: `add_failed_link` (`fat_tree_topology_drb.cpp:1288`): `setDropAll(true)` black-hole + `setFailed(true)` on both directions of the Agg-Core link. If `fail_time==0`, `populate_all_routes()` builds the FIB and LLSS schedules first so they are stale after the failure (L38-42).
- Nothing changes until `route_update_time` (absolute time): then `precompute_drb_paths`, `reset_llss_state()` (clears schedules + pointers, `clearLlssState` L453-468), `update_routes()` clears FIBs (L58-72). Schedules regenerated lazily then see `getFailed()` and recompute weights. A separate `weight_update_time` updates ToR FIB weights (`update_weights_tor_*`).
  So convergence is a delayed, user-set parameter, equivalent to our `-routing_convergence_us G` (G = route_update_time - fail_time; the fork additionally has an independent weight delay). Recovery times are separate (`setReturnTime`).
- `_is_path_valid` (L487) is a no-op returning true unless `g_enable_bgp`; `set_enable_bgp(true)` is commented out in the failure manager (L63), only `main_const_erase_drb.cpp:207` enables it. In `main_const_llss` the BGP-style downstream check is therefore off.
- Packets forwarded to a dead port before convergence are black-holed (no local repair). Intra-pod schedules use weight 1 for every non-failed uplink.

Fork experiments: the runscripts (`runscripts25/*.sh`, `sim/datacenter/runscripts/`) run `htsim_consterase` (erasure-coded transport, `-k 0` = no coding), 128 nodes, `alltoall_128n_2MB.cm` or `perm_128n_128c_s1_2MB.cm`, `-q 100`/`-q 1000`, `-ratecoef 1`, 10 repetitions
(`for i in {1..10}`), strategies `ecmp, rr, spray, sprayad, ecmp_ar, fl_ar, pkt_ar, llss...`, failures via `-failpct -1.0 -fails 1 -ftime 50 route weight`.
For the constant-CCA/sack path: `-sack 32 -nofr -dup 32`.

## 2. Authors' parameters (paper TeX, `8-sensitivity.tex` L12-22; and fork scripts)

(a) The fork contains no scripts or configs for the paper's `plotNN`/`figNN` ids (`grep` for plot ids, K12, derang: none; no plotting code, no derangement generator;
`connection_matrices/` only has perm/ring/podring/alltoall/incast matrices and generators). The 128-node (k=8) run scripts of `runscripts25` are the nearest, and the paper's K=12 runs are not reproducible from the repo.

(b) Parameters the paper states for its default configuration: 432 nodes, 3-tier fat tree, K=12 radix, 800 Gbps links, 0.5 us link latency, RoCE-v2 packets (4096 B payload, 62 B header, 64 B ACK, 20 B inter-frame gap),
800 KB per-port buffers (only used in CCA cases; otherwise "practically infinite"), ECN threshold 80 KB (10 % of buffer; 10 packets for 64 KB packets), each scenario run at least 10 times, error bars = SEM.
Workloads: all-to-all and random permutation/derangement; default permutation message 1 MB (figure filenames use M=256, in 4096-B packets, = 1 MiB; M=1024 = 4 MiB for the CCA figures, "to give 6.8 RTTs"; propagation RTT about 150 packets).
No-CCA = sources paced at a fixed rate, not slowed by congestion control (appendix proofs: "sources are paced at a fixed rate", infinite buffers). CCAs for comparison: DCTCP, NSCC, MSwift. Other figure parameters from filenames:
fig17/18/19/22 K=4 (node-count scaling; M=256 or 32), fig20/21 K=8 (M=127 ATA / M=16140 derangement), fig14/15 K=10 (packet-size sweep), fig31 K=64, fig24-29 K=16 FSDP (M=119/418/1533), fig32-36 K=8 matrix (MoE, M=11122/8398), fig5 K=12 inter-pod perm link loads, fig6 K=12 failure-rate sweep. MoE: k=8, 128 GPUs, 8192 B per token copy.

(c) Fork-side runs used here: 128 hosts (k=8), constant-rate sources, 400 Gbps, 1 MiB messages, default fork MTU (4178 B on the wire, 4096 B payload), `-q 20000` (queue) unless stated.

## 3. Experiment: no-CCA 1 MiB permutation / inter-pod derangement, k=8, 128 hosts, 400 G

Workloads (`/tmp/vb/wl`, generated with `experiments/exp32_ofan/scripts/gen_derangement.py`, same files for both simulators):
`der_s{1,2,3}.cm` (inter-pod derangement, `gen_derangement.py <out> 128 16 1048576 <seed>`) and `perm_s{1,2,3}.cm` (`... <seed> perm`). `single.cm` = one flow 0->64 for the lower bound.

Fork commands (driver `/tmp/run_vb.sh fork` and a variant `run_vb2.sh`):
```
htsim_constcca_llss -end 0 -tm <wl> -nodes 128 -linkspeed 400000 -q 20000 -cwnd 400 -ratecoef 1 -sack 32 -nofr -dup 32 -strat <S> [-q 193] [-fails 1 -failpct 1.0] -of out.csv
  S in: ecmp | pkt_ar (also with -q 193) | rr | llss | llss_perm | fib_llss and fib_llss_perm (both with -fails 1 -failpct 1.0, see below)
```
Our commands (frozen binary, same shape as exp33 `run_e1.sh`/exp32 S5):
```
htsim_uec_frozen -tm <wl> -topo htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo -linkspeed 400000 -seed 42 -end 200000 -connections_mapping
  -sender_cc_only -sender_cc_algo constant -cwnd 400 -mtu 4160 -disable_trim -ecn 19 19 -disable_tor_ecn -load_balancing_algo ecmp -q 20000
  -strat {ofan | ecmp_host | ecmp_rr | ecmp_ar [-q 193]} -log_queue_stats <tsv>
```
Notes on equivalence: the fork's constant CCA is a paced sender (interpacket delay = packet bits/linkspeed, window re-derived from RTT); `-nofr -sack 32 -dup 32` matches the authors' own settings in `bigbuffer-newfails-innetwork.sh` and prevents
fast-retransmit duplicates (first attempt without it inflated all reordering schemes by about 14 % extra packets and 10-20 % worse CCT, so those rows are not shown). `fib_llss*` only takes the plain-pointer path when `has_failures()` is true,
so `-fails 1 -failpct 1.0` was used as a hack: failure bandwidth fraction 1.0 leaves the link at full rate, the flag only sets `failed_links=1` (no link is marked failed). Queue stats were added to the fork copy only:
`ECNQueue::receivePacket` records the high-water mark in bytes and data bytes (non-ACK), dumped per layer at the end of `main_const_llss`. "maxq" is the largest per-link high-water mark, in packets (fork 4178 B; ours 4150 B);
"ovl" = (max link data bytes / mean over layer - 1) x 100 (same formula as `link_overload.py`). CCT = last flow completion in microseconds (fork: sender-side completion time, ours: last "finished at"); CCT inc % is relative to that simulator's single-flow time (fork 33.4 us, ours 33.7 us).
Averages over seeds 1-3, k=8.

### Derangement (inter-pod), maxq pkts / ovl %

| sim | strategy | CCT us | CCT inc % | E->A | A->C | C->A | A->E | E->H |
|---|---|---|---|---|---|---|---|---|
| ours | ofan | 34.5 | 2.2 | 5.0 / 0.0 | 6.0 / 0.0 | 6.0 / 0.0 | 6.0 / 0.0 | 6.0 / 0.0 |
| fork | llss (IWRR) | 34.5 | 3.3 | 4.0 / 0.0 | 5.0 / 0.0 | 6.3 / 0.0 | 5.0 / 0.0 | 5.6 / 0.0 |
| fork | llss_perm | 34.5 | 3.4 | 4.0 / 0.0 | 5.0 / 0.0 | 5.9 / 0.0 | 5.0 / 0.0 | 5.7 / 0.0 |
| fork | fib_llss_perm (plain pointer + skip) | 35.0 | 4.9 | 13.3 / 3.4 | 7.6 / 3.0 | 7.7 / 2.9 | 8.7 / 3.8 | 7.9 / 0.0 |
| fork | fib_llss (plain pointer) | 44.4 | 33.0 | 124.5 / 50.0 | 5.0 / 12.5 | 12.7 / 12.5 | 41.9 / 50.0 | 5.7 / 0.0 |
| ours | ecmp_ar q193 | 37.7 | 11.8 | 14.4 / 3.6 | 13.7 / 5.5 | 36.4 / 13.7 | 25.7 / 11.1 | 11.0 / 0.0 |
| fork | pkt_ar q193 | 37.8 | 13.1 | 13.5 / 4.4 | 13.5 / 6.5 | 34.2 / 14.1 | 24.6 / 12.9 | 11.2 / 0.0 |
| ours | ecmp_ar q20000 | 37.9 | 12.4 | 43.1 / 13.7 | 38.1 / 15.5 | 34.1 / 16.1 | 22.1 / 13.0 | 11.7 / 0.0 |
| fork | pkt_ar q20000 | 38.5 | 15.2 | 40.3 / 14.2 | 31.6 / 15.2 | 33.8 / 17.6 | 27.5 / 18.4 | 11.7 / 0.0 |
| ours | ecmp_rr | 45.6 | 35.4 | 2.0 / 0.0 | 137.7 / 49.6 | 88.9 / 48.6 | 27.7 / 14.5 | 20.7 / 0.0 |
| fork | rr | 40.9 | 22.4 | 41.5 / 14.3 | 53.5 / 24.1 | 65.0 / 34.1 | 35.9 / 20.8 | 17.8 / 0.0 |
| ours | ecmp_host (hash ECMP) | 112.1 | 232.5 | 600 / 233 | 499 / 300 | 457 / 300 | 319 / 267 | 2.0 / 0.0 |
| fork | ecmp | 117.8 | 252.9 | 749 / 300 | 547 / 333 | 560 / 400 | 249 / 233 | 3.6 / 0.0 |

### Permutation (random, includes intra-pod pairs)

| sim | strategy | CCT us | CCT inc % | E->A | A->C | C->A | A->E | E->H |
|---|---|---|---|---|---|---|---|---|
| ours | ofan | 34.4 | 1.9 | 5.0 / 1.3 | 5.0 / 3.6 | 5.7 / 3.6 | 6.0 / 1.3 | 6.7 / 0.0 |
| fork | llss | 34.4 | 3.0 | 4.0 / 1.3 | 4.6 / 3.6 | 5.0 / 3.6 | 4.6 / 1.3 | 5.7 / 0.0 |
| fork | llss_perm | 34.4 | 3.1 | 4.0 / 1.3 | 4.6 / 3.6 | 5.0 / 3.6 | 5.0 / 1.3 | 5.0 / 0.0 |
| fork | fib_llss_perm | 34.9 | 4.7 | 14.2 / 5.4 | 5.6 / 7.0 | 6.0 / 6.7 | 9.4 / 5.7 | 8.0 / 0.0 |
| fork | fib_llss | 44.5 | 33.1 | 124.8 / 52.0 | 4.9 / 19.8 | 5.0 / 20.0 | 44.6 / 52.0 | 5.3 / 0.0 |
| ours | ecmp_ar q193 | 36.9 | 9.4 | 14.4 / 5.2 | 12.4 / 13.8 | 23.4 / 20.6 | 29.1 / 13.3 | 13.4 / 0.0 |
| fork | pkt_ar q193 | 36.9 | 10.4 | 13.6 / 5.8 | 12.3 / 14.4 | 23.2 / 16.3 | 26.0 / 13.9 | 12.3 / 0.0 |
| ours | ecmp_ar q20000 | 37.5 | 11.2 | 39.8 / 13.1 | 26.7 / 21.6 | 22.1 / 18.0 | 29.7 / 15.3 | 13.0 / 0.0 |
| fork | pkt_ar q20000 | 37.6 | 12.5 | 41.1 / 15.3 | 20.2 / 18.4 | 21.6 / 19.4 | 26.8 / 14.7 | 11.6 / 0.0 |
| ours | ecmp_rr | 37.1 | 10.1 | 2.0 / 1.3 | 38.8 / 26.3 | 33.1 / 20.5 | 33.7 / 13.1 | 15.0 / 0.0 |
| fork | rr | 38.4 | 14.9 | 38.2 / 14.4 | 33.8 / 27.3 | 41.6 / 27.5 | 40.0 / 20.3 | 15.4 / 0.0 |
| ours | ecmp_host | 105.0 | 211.5 | 601 / 238 | 414 / 276 | 369 / 390 | 365 / 271 | 2.0 / 0.0 |
| fork | ecmp | 124.4 | 272.5 | 585 / 238 | 543 / 313 | 591 / 471 | 228 / 272 | 2.9 / 0.0 |

Raw outputs lived in container `ofan-dev:/tmp/vb/{fork,fork2,ours}` (not persisted in the repo; `fork` = without `-nofr`, `fork2` = reported). Statistics are 3 seeds on one workload each, k=8, so differences of a few percent in CCT are within noise; no CIs were computed.

### Findings

1. Same qualitative ranking in both simulators: Ofan/LLSS-IWRR (CCT +2-3 %) < AR (+9-15 %) < RR (+10-35 %) << hash ECMP (+210-270 %). AR numbers are almost the same in both simulators layer by layer (e.g. q193 C->A 36 vs 34 pkts, q20000 E->A 43 vs 40 pkts), which validates the shared transport/timing setup. Hash ECMP agrees to within 25 % in every queue and CCT.
2. The fork's IWRR "llss" and our Ofan agree: every layer is bounded by 4-8 packets with 0 % overload under derangement (single digit overload under random permutation where intra-pod pairs and a few colliding ToR destinations exist), E->A bounded at 4-5 pkts in both. We saw no layer where the fork's llss is materially different from ours (E->A included).
3. The fork's plain `FIB_LLSS` pointer (no per-switch order shuffle, no permutation) is NOT bounded: E->A reaches 125 pkts and A->E 42-45 pkts with 50 % overload, CCT +33 %. Cause: every switch and every destination uses the same fixed port order with only a random start, so pointers of different destinations at a ToR stay phase-locked and pick the same uplink in bursts. Adding the "every 10 wraps skip one position" rule (`fib_llss_perm`) removes most of that (E->A 13 pkts, CCT +5 %) but is still about 3x worse than the shuffled-schedule version. This gives a useful anchor: the paper's XOR/add permutation is meant to produce the diversity that the fork gets from a per-switch random shuffle.
4. The fork's RR is much better than ours at A->C and C->A under derangement (54/65 vs 138/89 pkts) but worse at E->A (41 vs 2). The two are different RRs (fork: counter shared across destinations with a full re-shuffle every 5 rounds; ours `ecmp_rr`: global counter without re-shuffle, so the ToR counter is perfectly interleaved at the edge). Not an Ofan issue.
5. Fork-level artifact worth noting: without `-nofr` the fork's sender fast-retransmits on reordering for every sprayed scheme (about 14 % more packets), which inflates E->H overload to 30-40 % and CCT by 10-20 points for llss, AR and RR. The authors' own spraying scripts use `-sack 32 -nofr -dup 32`.

## 4. Differences between the fork and the paper text / our implementation

- Permutation: the paper (App. F.2) uses `pi(i) = (xor_w(P[i], id1) + id2) mod w` per destination with a hard-wired P; the fork has neither XOR nor id-derived constants. It uses (a) a random shuffled port order per switch (drawn once per switch, shared by all destinations and, via the shuffle of `ports`, per dest pod), (b) random start per pointer, (c) a `+1` pointer skip every 10 wraparounds in the `*_PERMUTE` variants. Our implementation follows the paper; the fork is an earlier algorithm with the same bounded-queue behaviour in the failure-free symmetric case.
- Weights/IWRR: the fork builds a weighted interleaved schedule (GCD-reduced weights) per dest pod using reachable-core intersections; Ofan in the paper consolidates by pointers/levels, and in a failure-free tree the fork's weights are all 1 so it degenerates to a shuffled round robin. Under failures the weights come from `getFailed()` at schedule-build time (stale until `route_update_time`), not from a live per-packet validity test (`_is_path_valid` is a no-op unless BGP is enabled, which `main_const_llss` never does).
- Key granularity: dest ToR at ToR, dest pod at Agg (same as our description of the paper's top consolidation levels); no pipe/slice consolidation, no per-pipe pointer counts.
- ACK handling: separate pointer per (destination, data/ACK) and a deliberate half-schedule offset between the data and ACK pointers of the same key (only in `PER_POD_IWRR*`); the plain FIB variants have independent random starts. No size-class dimension (paper: quantised packet size).
- Down path: below the top, the fork uses hash ECMP over down routes (single route in a standard fat tree).
- Failure model: convergence is user-set absolute times (`-ftime fail route weight`), applied globally and instantly per switch at `route_update_time`; no per-switch staggered convergence. Failure injection is Agg-Core only (assert on AGG type), black-hole drop.
- Plain `FIB_LLSS` is only taken under failures in DRB code; without failures `fib_llss` silently equals `llss`. Anyone reproducing "llss without failures" gets IWRR, not the plain pointer.
- Transport: constant-rate paced CCA + erasure/sack reliability, not the UEC sender; queues are byte-counted ECN FIFOs; RTT and header overheads differ from the paper's RoCE sizes (fork default 4178 B on wire vs paper 4096+62+20); the fork has no 800 Gbps / 0.5 us / 800 KB defaults (we ran 400 Gbps with the fork's default link latency, not 0.5 us).

## 5. What could not be done / caveats

- The paper's K=12/800 G configuration, 10 repetitions, SEM, CCA runs (DCTCP/NSCC/MSwift) and the failure experiments (fork `-ftime`) were not run; only k=8, 3 workload seeds. The fork does not contain scripts for the paper's plot ids.
- The fork binary's `-seed` is `srand(time(NULL))`: runs are not reproducible, and the per-switch random shuffle makes IWRR results vary run to run (the reported numbers use one execution per cell).
- The fork's link latency/hop latency defaults were not matched to our 500 ns per hop (single-flow LB 33.4 us vs ours 33.7 us suggests they are close).
- Fork modifications are instrumentation only (`queue.h` `_hwm`/`_data_bytes`, `ecnqueue.cpp` update in `receivePacket`, a stats dump at the end of `main_const_llss.cpp`), in the container copy /tmp/mc.
- During cleanup of a hung first fork attempt (`-mtu 4160` made the fork run forever without completing) I issued `kill -9` against `xargs`/`timeout`/`htsim_constc*` processes in the shared container; one stale `timeout` zombie (pid 30455, parent of a defunct `htsim_uec`) may have belonged to another agent's run. Please check that nothing of the other agent's was lost.

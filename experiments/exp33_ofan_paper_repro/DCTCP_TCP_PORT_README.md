# Plan: run htsim's TCP-based DCTCP over our switch load balancers (Ofan paper Fig 12, DCTCP column)

Status: **scoping only; nothing implemented.** This file is written so a new agent with no memory of the earlier conversation can implement it. All code references were read from source, not compiled or run, so treat line numbers as pointers to verify. Paths are relative to the repo root `C:\git_repos\REPS_EuroSys_Artifact` unless stated.

## 1. Why this task exists

We are reproducing the simulations of "Ofan: Optimal Load Balancing for AI Training" (McClure et al., arXiv 2610.07230; local PDF `c:\Users\itama\OneDrive - post.bgu.ac.il\תואר שני\מאמרים\Ofan Optimal Load Balancing for AI Training.pdf`) with this repo's htsim. Our Ofan switch load balancer (`-strat ofan`) is implemented and validated (see `experiments/OFAN_ARCHITECTURE.md`, `experiments/exp32_ofan/README.md`). The Fig 12 reproduction (`experiments/exp33_ofan_paper_repro/E4_results.md`, plots in `plots/e4_fig12/`) matches the paper for Ofan (about 1.2% CCT increase, queues of 6-8 packets) but **not** for DCTCP:

| DCTCP CCT increase | REPS | AR | Ofan |
|---|---|---|---|
| Paper (Fig 12a) | 309% | 205% | 0.44% |
| Ours (UEC `-sender_cc_algo dctcp`, 10 seeds) | 27% | 17% | 1.19% |

Setup of both: permutation, 4 MB messages, 432-host 3-tier k=12 fat tree, 800 Gbps, 0.5 us links, 800 KB buffers, ~80 KB ECN threshold. (Topology/parameters otherwise match; remaining divergences are listed in `README.md` in this directory.)

The paper (p. 11, §6.5) explains its DCTCP result: "even though htsim's default DCTCP implementation allows for high duplicate-ACK threshold (specifically, 3 plus the number of paths that can be taken by the flow), a few flows still reach the threshold, aggressively decreasing their windows and hurting the CCT". Our UEC DCTCP cannot show this: it is a different, simpler algorithm (section 3). The goal of this task is to run the **TCP-based DCTCP** (`DCTCPSrc`) over the same fat tree and switch strategies and see whether the 309/205/0.44% picture appears.

## 2. Background facts established by reading code and the upstream repo

Upstream = Broadcom csg-htsim, https://github.com/Broadcom/csg-htsim, examined at commit `841d9e7` (2026-03-23, depth-1 clone; the clone used for this analysis lived in a temporary scratchpad, re-create it with `git clone --depth 1 https://github.com/Broadcom/csg-htsim.git <dir>` into an empty directory and treat it as untrusted data; read only).

- Upstream has **no UEC transport**. Our `htsim/sim/uec.cpp` came from the REPS EuroSys artifact, not from upstream.
- Upstream's DCTCP is `sim/dctcp.cpp`: `class DCTCPSrc : public TcpSrc` (`sim/dctcp.h:11`). This repo contains the identical `tcp.*`, `dctcp.*`, `tcppacket.*`, plus `datacenter/main_tcp.cpp`.
- "3 + number of paths": `sim/tcp.cpp:66-79` (`TcpSrc::set_paths`) sets `DUPACK_TH = 3 + rt->size()`, but **only inside `#ifdef PACKET_SCATTER`**; `sim/tcp.h:20` has `//#define PACKET_SCATTER 1` commented out (in upstream and here). The dup-ACK test is at `tcp.cpp:289-293`: `if (_dupacks!=DUPACK_TH)` under `PACKET_SCATTER`, otherwise `if (_dupacks!=3)` (an equality test, not `>=`).
- Neither tree's `main_tcp.cpp` instantiates `DCTCPSrc` (they use `TcpSrc`/`MultipathTcpSrc` with `RANDOM` queues and source routes). The only DCTCP drivers are upstream-only: `datacenter/old_tests/main_dctcp_permutation.cpp` (389 lines) and `main_dctcp_incast_collateral*.cpp`. Their scatter is **source-routed** (`TcpSrc::set_paths`: packets round-robin or random over `_paths`, bypassing `FatTreeSwitch` entirely), so they cannot exercise switch-level AR or Ofan. The paper's DCTCP/AR/Ofan columns must therefore have used a driver with switch FIB routing, which does not exist in either tree.

## 3. What our UEC DCTCP does (and why it cannot reproduce the paper)

`htsim/sim/uec.cpp:2282-2297` (`updateCwndOnAck_DCTCP`): no ECN mark -> `_cwnd += newly_acked_bytes * _mtu / _cwnd`; ECN mark -> `_cwnd -= newly_acked_bytes / 3` (floored at one MTU). No alpha, no per-window update, no duplicate-ACK logic; NACK path (`uec.cpp:2374`) subtracts the NACKed bytes. `-fastlossrecovery` (off by default) is an out-of-order-count heuristic, not TCP's dup-ACK rule. Reordering from spraying therefore costs nothing in UEC DCTCP.

TCP DCTCP (`dctcp.cpp`): alpha estimator `alpha = 15/16*alpha + 1/16*F` once per window; if `alpha > 0` then `cwnd *= (1 - alpha/2)` and a marked ACK exits slow start (`ssthresh = cwnd`); loss path `deflate_window()` halves ssthresh. TCP base (`tcp.cpp`): NewReno-like fast retransmit with no SACK: at the dup-ACK threshold `deflate_window(); retransmit_packet(); _cwnd = _ssthresh + 3*_mss; fast recovery` (`tcp.cpp:287-333`). Under per-packet spraying, reordering produces dup-ACKs; a threshold of 3 triggers spurious fast retransmits and window halvings, which is the mechanism the paper describes.

## 4. Effort estimate

About **1-2 focused days to a validated 16-host run, plus about 1 more day for the 432-host Fig 12 cells** (my estimate; the code changes are small and mechanical, the unknowns are the paper's TCP parameters, see section 9). Work items:

| # | Item | Size |
|---|---|---|
| 1 | New driver `htsim/sim/datacenter/main_dctcp.cpp` modelled on `main_uec.cpp` (args, `FatTreeTopology::load`, `FatTreeSwitch::set_strategy`, ECN params, FIB routes, `addHostPort`, `.cm` loading) | M, ~250-350 LOC |
| 2 | Makefile target `htsim_dctcp` (copy the `htsim_ndp` rules in `htsim/sim/datacenter/Makefile`) | S |
| 3 | Packet-field initialisation for TCP packets (section 6) | S, ~20 LOC |
| 4 | Ofan packet-class fix so TCP data counts as data (section 6) | S, 1-3 LOC |
| 5 | Dup-ACK threshold made settable at run time (section 7) | S |
| 6 | Min-RTO setter / remove the 250 ms clamp (section 7) | S |
| 7 | Queue configuration in the driver (section 8) | S |
| 8 | Host-side per-packet spraying hook for `TcpSrc` in FIB mode (section 6) | S-M, 30-60 LOC |
| 9 | Flow-finish logging fix (section 10) | S |
| 10 | Initial cwnd / ssthresh options (section 7) | S |
| 11 | Validation (16 hosts), then 432-host runs and an aggregation script adapted from `experiments/exp33_ofan_paper_repro/scripts/aggregate_e4.py` | M |

## 5. The old driver and what breaks against our tree

Old driver `datacenter/old_tests/main_dctcp_permutation.cpp` (upstream only) does: `TcpPacket::set_packet_size(9000)`; end time 0.21 s; args `-o -sub -conns -nodes -ssthresh -q -fail`; `Logfile`, `TcpSinkLoggerSampling(10 ms)`, `TcpTrafficLogger`, `TcpRtxTimerScanner(10 ms)`; `new FatTreeTopology(nodes, linkspeed, queuesize, 0, &eventlist, ff, ECN, failed_links)`; `ConnectionMatrix::setPermutation(conns)`; per connection `new DCTCPSrc(NULL,NULL,eventlist)`, `new TcpSink()`, `set_ssthresh(...)`, a random path from `top->get_paths(src,dest)` as source route `routeout` (+ `tcpSnk`) and the reverse path `routein` (+ `tcpSrc`), `tcpSrc->connect(*routeout,*routein,*tcpSnk,0)`; optional `#ifdef PACKET_SCATTER` block calling `set_paths`; infinite flows (no sizes); no ECN parameters; no switch strategy.

Breakages against our `htsim/sim`:
1. `EventList eventlist;` (global) fails to compile: our `EventList` is a singleton. Use `EventList& eventlist = EventList::getTheEventList();` as `datacenter/main_tcp.cpp:50` does.
2. Its local `ntoa()`/`itoa()` definitions (end of file) cause link errors: `config.cpp:127,133` already define them. Delete the copies.
3. The 8-argument `FatTreeTopology` constructor still exists (`fat_tree_topology.h:69-70`, and `main_tcp.cpp:181` uses it) but gives 1 us hop latency (`fat_tree_topology.cpp:339-344`). For the paper's 0.5 us links use `FatTreeTopology::load(topo_file, queue_logger_factory, eventlist, queuesize, qt, sender_qt)` (`fat_tree_topology.h:62`; usage at `main_uec.cpp` ~L1722) with `experiments/exp33_ofan_paper_repro/topologies/fat_tree_432_1os_3t_800g.topo` (also 16/54/128/250/1024-host files there, generated by `scripts/gen_topo.py`). Static setters (`FatTreeTopology::set_ecn_parameters`, `FatTreeSwitch::_disable_trim`, `FatTreeSwitch::_trim_size`) must be set **before** constructing the topology because queues capture them at construction.
4. `queue_type` enum (`fat_tree_topology.h:21-24`) gained `STATEFUL_ECN`; otherwise compatible. `ECN` exists but is unparameterised (section 8).
5. **Real gap: switches.** Our `FatTreeTopology` always builds `FatTreeSwitch` objects (`fat_tree_topology.cpp:849-860`). Source routes from `get_bidir_paths()` bypass them. To make switches route, copy the UEC FIB pattern from `main_uec.cpp` ~L2042-2060 (see section 6). Call `FatTreeSwitch::set_strategy(...)` **exactly once** (it asserts `_strategy == NIX`, `fat_tree_switch.h` ~L169; leaving it NIX aborts on the first multi-hop choice, `fat_tree_switch.cpp` ~L490). Available strategies: `ECMP`, `ADAPTIVE_ROUTING` (`-strat ecmp_ar`; `PER_PACKET` default), `OFAN`, `RANDOM`, `RR_FIXED`, `RR`, `P2C`, etc.
6. `TcpPacket::set_packet_size(...)` must run before anything calls `Packet::data_packet_size()` (including `memFromPkt()` and `DCTCPSrc`'s constructor; asserts in `network.h:81-95`). Use 4150 (matches E4's wire accounting; E1 used `-mtu 4160`).
7. The `.cm` format changed: use `ConnectionMatrix::load(file)` (`connection_matrix.cpp` ~L676-830; format `Nodes N`, `Connections C`, lines `src->dst id I start T size B`, start 0 is safe) instead of `setPermutation`. Existing workloads: `experiments/exp33_ofan_paper_repro/workloads/perm432_4mb_s{1..10}.cm` (4,194,304 B flows, plain permutation, intra-pod pairs allowed) and `single432_4mb.cm` (`0->216`, single-flow baseline). Regenerate with `experiments/exp32_ofan/scripts/gen_derangement.py` (`perm` mode).
8. `Logfile`/loggers are optional (pass `NULL`); parse stdout instead.
9. Build/run: **Docker only** (container `ofan-dev`, repo bind-mounted at `/workspace`, `MSYS_NO_PATHCONV=1` in Git Bash; see `CLAUDE.original.md` "Docker environment"; build script `experiments/exp32_ofan/scripts/build.sh [clean]`). `htsim/sim/datacenter/Makefile` has `htsim_tcp` but no `htsim_dctcp`; `tcp.o dctcp.o tcppacket.o` are already in libhtsim. Lean link line template: see the `htsim_uec` rule; objects `main_dctcp.o firstfit.o fat_tree_topology.o fat_tree_switch.o connection_matrix.o ... -L.. -lhtsim`. After touching `tcp.h` or `tcppacket.h` run `make clean` in both `htsim/sim` and `htsim/sim/datacenter` (header dependencies are not fully tracked).

## 6. Routing TCP packets through `FatTreeSwitch` (the main technical work)

FIB mode (as UEC does): route handed to `TcpSrc::connect` / `TcpSink` ends at the host's ToR; switches fill in the rest (`FatTreeSwitch::receivePacket` -> `getNextHop`, `pkt.set_route(*nh)`).
- Source route (to ToR): `[queues_ns_nlp[src][tor][0], pipes_ns_nlp[src][tor][0], queues_ns_nlp[src][tor][0]->getRemoteEndpoint()]`; likewise `dsttotor` for the reverse direction (`main_uec.cpp` ~L2042-2050, `topo[p]->HOST_POD_SWITCH(host)` = ToR id). Pass them to `tcpSrc->connect(*srctotor, *dsttotor, *tcpSnk, start)` (verify `TcpSrc::connect` signature in `tcp.cpp:~112`; UEC uses `Route(const Route&, PacketSink&)`-style endpoints, see `main_uec.cpp:~2090`).
- Register endpoints at the ToRs: `topo->switches_lp[HOST_POD_SWITCH(src)]->addHostPort(src, flowid, tcpSrc)` and the same for `dest`/`tcpSnk` (`main_uec.cpp` ~L2059-2060). `flowid = tcpSrc->getFlowId()` (`tcp.h:49`; unique via the `PacketFlow` constructor counter, `network.cpp:~295`; data and ACK share `TcpSrc::_flow`). `getHostRoute(dst, flow_id)` (`fat_tree_switch.cpp` ~L653-655).

`TcpPacket` / `TcpAck` do **not** initialise fields the switch needs (`tcppacket.h:20-31, 46-56`; `newpkt` -> `set_route(flow,route,size,id)` in `network.cpp:27-39` only sets size/id/route/nexthop/`_is_header`/`_flags`). Consequences and fixes (item 3):

| Field | Problem | Required fix |
|---|---|---|
| `_dst` | only set if `set_dst` was called (`tcp.cpp:389,463,484,519,705`) | call `tcpSrc->set_dst(dest)` and `tcpSnk->set_dst(src)` after `connect` |
| `_pathid` | initial value `UINT32_MAX`; `Packet::pathid()` asserts `!= UINT32_MAX` (`network.h:117-119`); asserts are live in our builds; every ECMP/AR/RR/RANDOM small-packet hash calls `pkt.pathid()` (`fat_tree_switch.cpp` ~L496,502,542,548,567,579,587,595,601) | set `p->set_pathid(x)` for every data/ACK/SYN packet: constant 0 for flow-level ECMP, per-packet random or round-robin for host-side spraying (item 8) |
| `_src_dest` | never initialised (`network.h:177`); UEC sets it in `uec.h:588-598` (`stoi(to_string(from)+to_string(to))`); `freeBSDHash(pkt.flow_id_src_dest(), ...)` would read uninitialised memory (non-deterministic) | set a deterministic per-flow value (same formula as UEC or any hash of src,dst,flowid) in `TcpSrc::send_packets`, `retransmit_packet` and `TcpSink::send_ack` |
| `_direction` | `TcpPacket`/`TcpAck` come from a packet pool (`PacketDB`) and are never reset; a reused packet keeps `DOWN`, next `set_direction(UP)` hits `abort()` (`network.h:141-149`) | in `newpkt` set `p->_direction = NONE; p->_bounced = false;` |

Packet classes seen by our strategies: data = full `_mss` (>100 B); SYN is a `TcpPacket` of size 1 (`tcp.cpp:388`); `TcpAck` is `ACKSIZE` = 40 B. `ecmp_ar`/`ecmp_random`/`ecmp_p2c` hash packets `< 100 B`, `RR`/`RR_FIXED` hash `< 128 B`; data is adaptively/randomly/round-robin routed. **Ofan needs a code change (item 4):** `ofan_choose` (`fat_tree_switch.cpp` ~L398) uses `int t = (pkt.type() == UECDATA && !pkt.header_only()) ? 0 : 1;`, so TCP data would be classified as "small" (t=1) and share the ACK pointer. Change to `t = ((pkt.type()==UECDATA || (pkt.type()==TCP && pkt.size()>100)) && !pkt.header_only()) ? 0 : 1;` (check the actual packet type enum names in `network.h:~53`) and extend the `-log_ofan_counts` class labels (~L459-462). Keep the change gated/neutral for UEC (regression: `experiments/exp32_ofan/scripts/baseline.sh`, all five hashes in `experiments/exp32_ofan/baseline/SHA256SUMS` must stay identical).

Host-side spraying options for TCP (REPS itself does not exist for TCP; the paper's "REPS" column is entropy-based spraying):
- (a) FIB mode with per-packet entropy in `pathid` hashed by the switch ECMP strategy (like UEC `-load_balancing_algo oblivious/ecmp`): add a flag and a small hook in `TcpSrc` (random or round-robin value per packet; optional number-of-paths modulus). Recommended.
- (b) Source-routed scatter via `set_paths` (old driver / `PACKET_SCATTER`): packets bypass the switches, so AR and Ofan are not exercised. Could serve as a "DRB/RPS-like" reference only.

## 7. Dup-ACK threshold, RTO, initial window

- **Dup-ACK threshold.** Option 1 (smallest): define `PACKET_SCATTER` in `tcp.h`, never call `set_paths`, and set `tcpSrc->DUPACK_TH = 3 + npaths` from the driver (`DUPACK_TH` and `_crt_path` are public members, `tcp.h:69-72`). Option 2 (cleaner): replace the literal 3 with a runtime member `_dupack_th` (default 3) and a setter, without `#ifdef`. Either changes `TcpSrc`'s layout, so rebuild everything. Number of paths in the k=12 3-tier fat tree: inter-pod 36 (6 aggs x 6 cores; `get_bidir_paths` in `fat_tree_topology.cpp` ~L1346-1352), same pod 6, same ToR 1, giving thresholds 39, 9, 4; use `top->get_paths(src,dst)->size()` per flow (this is "3 plus the number of paths that can be taken by the flow") or a constant. Our plain permutation includes intra-pod pairs. Run both threshold = 3 and = 3 + paths as an ablation: the paper's claim is about the high threshold.
- **RTO.** `TcpSrc::_rto` starts at 3000 ms (`tcp.cpp:43`); `DCTCPSrc` sets 10 ms (`dctcp.cpp:20`), **but `tcp.cpp:183-184` clamps it to a minimum of 250 ms on every ACK** (`if (_rto<timeFromSec(0.25)) _rto = timeFromSec(.25);`; `DCTCPSrc::receivePacket` calls `TcpSrc::receivePacket`). Any timeout would add 250 ms to a CCT of tens of microseconds. Add a min-RTO setter (item 6) and decide explicitly; the paper does not say. `TcpRtxTimerScanner` wakes every 10 ms and re-arms forever, so `eventlist.setEndtime()` is mandatory.
- **Windows.** Defaults: `_cwnd = 10*_mss`, `_ssthresh = 100*_mss`, `_maxcwnd = 0xffffffff` (`tcp.cpp:30-32`; setters `set_cwnd`, `set_ssthresh` exist). BDP at 800 Gbps / ~6.4 us RTT is about 625-640 KB, i.e. about 150 packets (the paper says the same). The old driver used ssthresh=15 packets. With these defaults the single-flow baseline is dominated by slow-start/ramp-up, so initial cwnd and ssthresh decide every percentage; expose them as driver options and report the choice. No receiver window (`MODEL_RECEIVE_WINDOW` off).

## 8. Queues, ECN, loss for TCP

- Use `COMPOSITE` queues with trimming disabled (`FatTreeSwitch::_disable_trim = true`), buffer `memFromPkt(193)` (800,950 B at 4150 B), `FatTreeTopology::set_ecn_parameters(true, ecn_on_tor_downlink, memFromPkt(19), memFromPkt(19))` (equal min/max = step marking at 78,850 B; `compositequeue.cpp` `decide_ECN` ~L99-108; marking on dequeue from the low queue). Experiments so far used `-disable_tor_ecn` (project rule with `-sender_cc_only`); for TCP there is no such flag, decide and document (ToR-downlink ECN on/off).
- **Trimming must be off.** With trimming on, a full queue turns the packet into a header-only `TcpPacket` that `TcpSink::receivePacket` (`tcp.cpp:637-685`) does not check with `header_only()`, so it would ACK data that never arrived (silent corruption). With `_disable_trim` the packet is freed and counted in `_num_drops` (`compositequeue.cpp` ~L383-398). Note that overflow is not strictly drop-tail (arriving packet dropped with probability 0.5, otherwise the oldest low-priority packet is dropped).
- The legacy `ECN` queue type (`fat_tree_topology.cpp:760-761`) hard-codes K = 15 packets and ignores ECN options: not recommended.
- Host queues are `FairPriorityQueue` and never drop; `TcpPacket::priority()` = `PRIO_LO`, `TcpAck::priority()` = `PRIO_HI`.
- ECN echo: the sink echoes CE per packet (`TcpSink::send_ack`, `tcp.cpp:708-711`); `ECN_ECHO` = 4 (`ecn.h`).

## 9. Unknowns the paper does not settle (document whatever you choose)

Initial cwnd, ssthresh, min RTO, ECN threshold K (assumed ~80 KB as in the paper's setup), ToR-downlink ECN, whether flows start with a SYN handshake (TCP adds about 1 RTT; the single-flow baseline absorbs it), and what the paper's "REPS" column means for TCP (probably random/entropy spraying; REPS needs UEC ACK feedback). Whether the paper used source-routed scatter for the REPS/RPS column and FIB mode for AR/Ofan is unknown; scatter cannot exercise AR/Ofan.

## 10. Logging and CCT

`TcpSrc::receivePacket` prints `"Flow " << nodename() << " finished at " << timeAsMs(now)` whenever `seqno >= _flow_size` (`tcp.cpp:186-188`): prints repeatedly, `nodename()` is the constant `"tcpsrc"`, unit is ms. Change (item 9) to print once per flow with flow id, src, dst and `timeAsUs(now - start)` in the same shape our parsers expect (`aggregate_e4.py` greps `"finished at"`; UEC format at `uec.cpp:1627`, `... finished at <us> flowSize ...`). `set_flowsize(bytes)` sets `_flow_size = bytes + _mss` (`tcp.h:45`): flows send about one extra packet (~0.1% at 4 MiB); document. CCT = max over flows of (finish time); lower bound = single-flow run (`single432_4mb.cm`), as in E4 (UEC bound 48.81 us; the TCP bound will differ).

## 11. Recommended order and validation gates

1. Items 1-3, 7 (driver, Makefile, packet fields, queues). Run **16 hosts, ECMP, no spraying** (`fat_tree_16_1os_3t_800g.topo`). Gate: all flows finish; no abort/assert (especially `pathid()` and `set_direction`); no uninitialised-memory reads (run once under valgrind or ASAN in the container).
2. Single flow (`-strat ecmp`): CCT sane against ideal (about 42 us serialisation at 800 Gbps plus ramp-up). Tune initial cwnd/ssthresh here and record them.
3. Items 5, 8: host spraying on 16 hosts. Gate: dup-ACK counts and fast-retransmit counts visible (add counters), and threshold 3 vs 3+paths clearly different. This is the mechanism the paper describes.
4. Items 4: AR and Ofan. Gates: Ofan queue bound as in exp32 (a few packets at ToR uplinks), per-uplink counts balanced within +-1 using `-log_ofan_counts` (update its classifier for TCP), 0 drops in Ofan runs; regression hashes (`baseline.sh`) unchanged.
5. Scale to 432 hosts: one seed, then 10 seeds (seed = permutation seed and simulator seed, as E4); strategies: host spraying (+ default ECMP), `-strat ecmp_ar`, `-strat ofan`; optionally `ecmp_random`/`ecmp_rr_fixed`. Each 4 MB 432-host run took about 25-40 s for UEC; max 2 simulator processes in parallel on the shared 8-core / 7.8 GB machine.
6. Write `E5_results.md` next to `E4_results.md`, compare against the paper's 309 / 205 / 0.44% honestly (match or mismatch, with hypotheses), update `experiments/exp33_ofan_paper_repro/README.md` (item 7), add MODIFICATIONS.md rows (`// ===== ADDED (<name>) =====` banners at every sim edit; flag-absent output byte-identical), and a plot in the style of `plots/e4_fig12/` (paper-style bars; linear axis per CCA, see `scripts/paperstyle.py`, `scripts/plot_e4.py`; matplotlib is only in the container).

## 12. Risks

- Paper parameters unknown (section 9): the CCT-increase percentages depend on the baseline and window choices; matching 0.44% for Ofan needs a window that avoids ramp-up-limited CCT.
- A 250 ms min-RTO clamp turns any drop into a huge CCT; random spraying with 800 KB buffers can drop. Decide the RTO policy deliberately.
- `htsim_tcp` was never run in this repo; the old driver was not compiled against our tree, so more breakages than listed are possible.
- Changing `tcp.h` forces full rebuilds; stale `.o` files can crash (project gotcha: `make clean` in `htsim/sim` and `htsim/sim/datacenter` before trusting a crash).
- Not verified: `FAILURE_GENERATOR` hooks on host-feeder queues (probably irrelevant: no failure flags set), `getHostRoute` when a TCP flow's src and dst share a ToR (should work; test with an intra-ToR pair).

## 13. Conventions to follow

Read `CLAUDE.original.md` (project guide), `experiments/RUNNING_EXPERIMENTS.md`, `experiments/MODIFICATIONS.md` (banner rule, one row per mechanism), `experiments/OFAN_ARCHITECTURE.md`. Branch `ofan-lb`; do not modify `artifact_scripts/` or `artifact_results/`; do not commit raw runs/`*.tar.gz`/derived CSVs; commit only when the user asks. Edit `CLAUDE.original.md` rather than `CLAUDE.md`.

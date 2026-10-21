# V-C: Ofan paper theory-level figures (Figs 3, 17, 16/18) against our implementation

Paper: "Ofan: Optimal Load Balancing for AI Training", arXiv 2610.07230 (Fig 3 p. 4; App. D-F, Figs 16-18, pp. 21-25). Everything here was run with the frozen binary `/tmp/frozen/htsim_uec_frozen` in container `ofan-dev` (at most two simulations in parallel), repo mounted at `/workspace`. No simulator source was changed. Paper values are read by eye from the figures (about +-1 unit for the queue plots, +-3 points for Fig 3 bars); the paper gives no tables for these figures.

Common setup (all parts): 3-tier fat tree, 800 Gbps, 0.5 us links, one flow per host, all starting at t=0, inter-pod random derangement from `scripts/gen_derangement.py` (the 432/36 case uses its swap-repair fallback), no congestion control and effectively infinite buffers:
`-linkspeed 800000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160 -disable_trim -disable_tor_ecn -ecn 19 19 -q 20000` (same flags as exp33 E1, plus the strategy flags listed per row). Wire size is 4160 B per packet, so "packets" below are 4160 B (the paper: 4096 B payload plus header and gap; see exp33 README divergence 1). Seeds 1-5 change the workload, ECMP hashing and pointers.

Data and scripts (all under `experiments/exp32_ofan/`):

| Item | Path |
|---|---|
| Part 1 driver / aggregator | `scripts/run_vc1.sh`, `scripts/aggregate_vc1.py` (uses `scripts/link_overload.py` definition of overload) |
| Part 2 driver / aggregator | `scripts/run_vc2.sh`, `scripts/aggregate_vc2.py` |
| Part 3 driver / reducer | `scripts/run_vc3.sh`, `scripts/ts_vc3.py` |
| Raw runs (compressed at the end) | `data/vc/runs.tar.gz` (part 1: `runs/<strat>_s<seed>.{cmd,out,time,tsv}`), contents `runs2/` (part 2: `<strat>_n<hosts>_s<seed>.*`), `ts/` (part 3: `*_series.csv`, `*_qs.tsv`, `*.out`), `workloads/` |
| Summaries | `data/vc/vc1_summary.{md,csv}`, `data/vc/vc2_summary.md` |
| New topology | `../exp33_ofan_paper_repro/topologies/fat_tree_686_1os_3t_800g.topo` (k=14, 686 hosts, pod size 49; `gen_topo.py --k 14`) |

Every run finished all flows (432, resp. N, "finished at" lines per run) with 0 drops and 0 trims.

## 1. Fig 3: worst-link overload per stage (432 hosts, 1 MB, inter-pod derangement)

Metric: max over links of a layer of data bytes / mean over the layer's links - 1, in percent (`link_overload.py`; zero-byte links count in the mean). Mean +- SEM over 5 seeds. Strategy flags:

| Row | Flags (after the common flags) |
|---|---|
| Ofan | `-load_balancing_algo ecmp -strat ofan` |
| Simple RR | `-load_balancing_algo ecmp -strat ecmp_rr_fixed` |
| JSQ | `-load_balancing_algo ecmp -strat ecmp_ar -ar_method exact` |
| AR (default, `-q 20000`) | `-load_balancing_algo ecmp -strat ecmp_ar` |
| AR (`-q 193`) | same, with `-q 193` instead of `-q 20000` |
| RSQ | `-load_balancing_algo ecmp -strat ecmp_random` |
| RPS | `-load_balancing_algo path_random` |
| REPS | `-load_balancing_algo freezing -paths 65535` |
| DRB-like | `-load_balancing_algo path_rr` (start slot 0 for every flow, the default), plus two start-slot variants `-path_rr_start_mode srcdst_hash` and `src_mod` |

Command: `docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_vc1.sh` (then `STRATS="drb_hash drb_src"`), `python scripts/aggregate_vc1.py`.

| Strategy | E->A ours | A->C ours | C->A ours | A->E ours | Paper (Fig 3) | Verdict |
|---|---|---|---|---|---|---|
| Ofan | 0.8 +- 0.0 | 1.6 +- 0.1 | 1.7 +- 0.1 | 0.8 +- 0.0 | about 0 in all four | match (residual = packet granularity, 256 packets per flow) |
| Simple RR (`ecmp_rr_fixed`) | 0.0 | 0.0 | 141 +- 11 | 140 +- 6 | uplinks about 0; downlinks about 120 (C->A) and 122 (A->E) | match in shape; our downlinks are about 15-20 points higher |
| JSQ (exact, random tie-break) | 1.2 +- 0.1 | 1.2 +- 0.1 | 24.3 +- 0.8 | 19.2 +- 0.6 | uplinks about 0; A->E about 72, C->A about 56 | partial: uplinks about 0 and downlinks clearly bad, but 3x smaller than the paper |
| AR (default, `-q 20000`) | 16.3 +- 0.9 | 18.4 +- 1.2 | 18.9 +- 1.1 | 17.3 +- 0.8 | about 15-18 everywhere | match (but see below: identical to RSQ) |
| AR (`-q 193`) | 4.3 +- 0.1 | 6.2 +- 0.1 | 18.3 +- 0.9 | 15.2 +- 0.9 | about 15-18 everywhere | partial: uplinks better than the paper, downlinks the same |
| RSQ | 16.3 +- 0.9 | 18.4 +- 1.2 | 18.9 +- 1.1 | 17.3 +- 0.8 | about 17-20 | match |
| RPS | 16.6 +- 0.4 | 20.2 +- 1.5 | 18.7 +- 1.2 | 17.6 +- 0.8 | about 17-20 | match |
| REPS | 17.0 +- 0.9 | 20.2 +- 1.1 | 20.5 +- 0.9 | 17.4 +- 0.4 | about 17-20 | match |
| DRB-like, start slot 0 | 7.8 +- 0.0 | 12.5 +- 0.0 | 12.5 +- 0.0 | 7.8 +- 0.0 | about 0 | mismatch |
| DRB-like, `srcdst_hash` start | 4.9 +- 0.3 | 2.3 +- 0.1 | 2.4 +- 0.1 | 4.3 +- 0.2 | about 0 | partial |
| DRB-like, `src_mod` start | 5.5 +- 0.0 | 0.0 +- 0.0 | 2.3 +- 0.1 | 4.5 +- 0.4 | about 0 | partial |

Max queue per layer in packets (mean over seeds, E->A / A->C / C->A / A->E): Ofan 6.0 / 7.8 / 8.4 / 7.2; Simple RR 5 / 5 / 371 / 260; JSQ 8 / 7 / 67 / 43; AR 51 / 40 / 37 / 30; RSQ 51 / 40 / 37 / 30; RPS 47 / 43 / 39 / 30; REPS 49 / 49 / 36 / 27; DRB (slot 0) 32 / 32 / 15 / 20.

Notes and hypotheses.

- The headline structure of Fig 3 reproduces: destination-aware Ofan is flat; Simple RR is perfect on the uplinks and terrible on the downlinks; JSQ is perfect on uplinks and bad on downlinks; spraying/AR-style schemes sit at about 15-20% everywhere.
- AR and RSQ rows are bit-identical because with `-q 20000` our AR quantises queue sizes against the buffer size (exp33 README divergence 3), so every queue looks empty and AR degenerates to random choice. The `-q 193` variant is the meaningful AR; the paper's AR configuration is not specified well enough to know which one it shows. Our `-q 193` AR clearly balances the uplinks (4-6%) while the paper shows AR at about 15%.
- JSQ downlinks are 3x lower than the paper (24/19 against 56/72). Likely cause: our JSQ breaks ties randomly among equal-queue ports, which de-synchronises switches; if the paper's JSQ breaks ties deterministically (lowest port index) the same sources keep landing on the same downlink. Not tested (no source change allowed).
- Simple RR downlinks are about 140 against the paper's about 120. Its overload depends on pointer start and flow pattern; the SEM is 6-11 points, and in the paper it is a single reading. I treat this as the same effect with a different constant.
- DRB-like: the paper's DRB (and Ethereal) is about 0% at every stage. Our `path_rr` with the default start slot makes every host start at path index 0 of the same enumeration order, which is the worst case for DRB's synchronisation (SEM 0.0 over seeds: the structure, not the permutation, sets the number). A flow of 1 MB is 256 packets over 36 paths = 7.1 packets per path, so a packet-granularity overload of 8/7.1 = 12.5% is what a path-synchronised scheme produces (A->C and C->A show exactly 12.5%). With a per-flow start offset (`srcdst_hash`, `src_mod`) it drops to 0-5%, but not to the paper's 0. So a DRB baseline is only roughly approximated by `path_rr`; the paper's DRB presumably randomises the path order and phase per flow, which `path_rr` does not offer (no random-start mode) and the paper's 1 MB case also has the same packet-granularity limit. Verdict stays partial/mismatch for this row only; the `path_rr` ACK routing works (all 432 flows finish, 0 drops, in every variant).

## 2. Fig 17: ratio of max queue DRB / Ofan vs number of hosts (4 MB)

Max queue = maximum `max_q_bytes` over all switch queues of all five layers (E->A, A->C, C->A, A->E, E->H) from `-log_queue_stats`, per run. Workload: inter-pod derangement (`gen_derangement.py`, pod size 16/25/36/49/64 for 128/250/432/686/1024 hosts), 4 MB messages, seeds 1-5 (the paper: 30 runs). Ratio computed per seed (same workload for both) and averaged; mean +- SEM. Command: `docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_vc2.sh` (default `ofan drb`), then `VARIANTS="drb_hash drb_src" run_vc2.sh`, `python scripts/aggregate_vc2.py`.

| Hosts | Paper ratio (read from Fig 17) | Ofan max q (pkts) | `path_rr` slot 0: max q / ratio | `path_rr` `srcdst_hash`: max q / ratio | `path_rr` `src_mod`: max q / ratio |
|---|---|---|---|---|---|
| 128 | about 1.24 | 7.0 | 16.6 / 2.37 +- 0.03 | 12.8 / 1.83 +- 0.12 | 13.2 / 1.89 +- 0.03 |
| 250 | about 1.30 | 7.6 | 27.0 / 3.56 +- 0.12 | 16.8 / 2.22 +- 0.15 | 19.4 / 2.56 +- 0.07 |
| 432 | about 1.42 | 9.0 | 38.8 / 4.31 +- 0.04 | 24.0 / 2.67 +- 0.07 | 30.4 / 3.38 +- 0.03 |
| 686 | about 1.48 | 10.0 | 52.6 / 5.26 +- 0.12 | 32.2 / 3.22 +- 0.12 | 41.8 / 4.18 +- 0.02 |
| 1024 | about 1.57 | 10.2 | 67.2 / 6.60 +- 0.16 | 36.6 / 3.60 +- 0.18 | 55.0 / 5.40 +- 0.10 |

Verdict: trend match, magnitude mismatch. Ofan's max queue is nearly flat in network size (7 to 10 packets; it grows slowly, one packet per layer-level effect) and the DRB-like scheme's max queue grows with size, so the ratio rises monotonically as in the paper. But our ratios are 1.5-4x larger than the paper's 1.24-1.57, and they rise faster. Hypotheses: (a) `path_rr` is a harsher DRB than the paper's: even the best start-slot variant has a higher max queue than the paper's DRB (the paper's 1.24 at 128 hosts means a DRB max queue of only about 9 packets); (b) the paper's number may be an average of per-run ratios using queue statistics other than the single worst queue (not stated); (c) 4160 B packets and a start-in-phase workload (all flows start at t=0 with the same window and no jitter) concentrate the first-window bursts for any round-robin scheme. DRB max queue (slot 0) at 1024 hosts is 67 packets, right at the paper's E->A bound for DRB, k^2/4+1 = 65 packets (see Part 3).

## 3. Figs 16 / 18: average queue vs time per layer (1024 hosts, 4 MB)

k=16, 1024 hosts, `w = k/2 = 8`, 4 MB inter-pod derangement, seeds 1 and 2. Average queue = mean over all queues of a layer (idle ones count as 0) as sampled by the simulator's samplers at 1 us: `-log_tor_queues` (E->A, all 1024 queues), `-log_core_queues` (A->C, all), `-log_core_downlink_queues` (C->A, first 16 of 64 cores only, a simulator constant). A->E and E->H are not sampled by the simulator, so for them only the per-run max queue (from `-log_queue_stats`) is available. `-log_link` was tried first and rejected: it does not log source-routed `path_rr` packets, and never logs A->E / E->H. Reported plateau = mean over t in [10, 40) us; messages finish at about 47 us as in the paper. Command: `run_vc3.sh` (variants `ofan`, `drb` = `path_rr` slot 0, `drb_hash`).

Paper values (read from the plots; plateau, KB = 1000 B; 1 packet = 4.16 KB here):

| Layer | Fig 16 DRB (paper) | Fig 18 Ofan (paper) | Ofan ours (seed 1 / 2) | `path_rr` slot 0 ours (s1 / s2) | `path_rr` `srcdst_hash` ours (s1 / s2) |
|---|---|---|---|---|---|
| E->A | about 8.5-9 (model dotted about 9) | about 8.7 (model dotted about 9) | 8.8 / 9.0 | 120.7 / 120.7 | 43.0 / 42.7 |
| A->C | about 14 (model dashed about 16) | about 9 | 14.9 / 14.9 | 120.6 / 120.6 | 15.7 / 16.7 |
| C->A | about 14.5 | about 10 | 15.9 / 15.9 | 32.9 / 31.0 | 24.1 / 23.3 |
| A->E | about 9 | about 12.5 (model dashed about 12.5) | not sampled | not sampled | not sampled |
| E->H | about 8.5 | about 13 | not sampled | not sampled | not sampled |

Max queue (packets, 4160 B) per layer from `-log_queue_stats`, E->A / A->C / C->A / A->E / E->H:

| Variant (seed 1 / seed 2 identical where one number) | max q (pkts) |
|---|---|
| Ofan | 7 / 10 / 10 / 8 / 9 |
| `path_rr` slot 0 | 61-62 / 60 / 20-23 / 32 / 64-65 |
| `path_rr` `srcdst_hash` | 36-39 / 11-12 / 16-18 / 33-37 / 23 |

Bounds from App. D/F: Ofan edge uplink queue is at most w+1 = 9 packets for any message size. Ours: max E->A = 7 packets (below the bound) in both seeds, and 6-7 across the Part 1/2 runs; the time series of the average E->A queue is flat at 8.7-8.8 KB (about 2.1 packets) from 1 us to the end of the message, as in Fig 18 (flat about 8.7 KB). DRB edge uplink bound is k^2/4+1 = 65 packets; `path_rr` slot 0 reaches 61-62, i.e. it is nearly tight, while `srcdst_hash` reaches 36-39.

Verdicts.

- Ofan E->A: match. Plateau 8.8-9.0 KB against the paper's about 8.7-9 KB, flat in time, and the exact bound w+1 holds (7 <= 9).
- Ofan A->C and C->A: partial. The paper's Ofan plot (Fig 18) has about 9-10 KB for both core layers, whereas ours are 14.9 and 15.9 KB (about 3.6-3.8 packets). Interestingly ours match the paper's Fig 16 DRB values for these two layers (about 14-14.5 KB) better than its Fig 18 Ofan values. The flatness and independence of message size match; the level is 1.5x higher. Hypotheses: (a) initial synchronised start at t=0 of all 1024 hosts with identical windows (the paper's start may be jittered or its first-pointer position random, App. F.5 mentions the first pointer is picked at random); (b) the paper's average may exclude the packet in service (we count it, using queue depth in bytes as the simulator reports it); (c) the paper's averaging over sampled bins may include idle queues differently.
- Ofan A->E and E->H: not comparable (not sampled). Max queues are 8 and 9 packets, i.e. at most 33-37 KB peak, consistent with a plateau of about 12-13 KB being well below that.
- `path_rr` as DRB: mismatch. The paper's DRB average queues are at most about 14.5 KB in every layer; ours with the default slot-0 start are 120 KB at E->A and A->C (29 packets average, with the max at the 65-packet bound). With `srcdst_hash` start, A->C (15.7-16.7 KB) agrees with the paper's about 14 KB, C->A (23-24) is 1.6x higher and E->A (43 KB) is 5x higher. The synchronised start in `path_rr` is the likely main reason (all hosts of an edge switch hit the same uplink at the same time); the paper's Appendix D says DRB flows have "random phases", and its model assumes it.

## Summary table

| Figure | Verdict |
|---|---|
| Fig 3, Ofan | match |
| Fig 3, Simple RR | match (downlinks about 140 vs 120) |
| Fig 3, JSQ | partial (right shape, downlink overload 3x lower) |
| Fig 3, AR / RSQ / RPS / REPS | match (AR with `-q 20000` is identical to RSQ; with `-q 193` uplinks are better than the paper) |
| Fig 3, DRB | mismatch with `path_rr` default start, partial with per-flow start offsets (2-5%) |
| Fig 17 | trend match (ratio rises with size), magnitude mismatch (2.4-6.6 against 1.24-1.57; best DRB variant 1.8-3.6) |
| Fig 16/18 Ofan edge uplink (bound w+1, flat avg) | match |
| Fig 18 Ofan core layers | partial (14.9-15.9 KB against about 9-10 KB) |
| Fig 16 DRB | mismatch for `path_rr` slot 0 (120 KB), partial for `srcdst_hash` |

Overall: Ofan's own behaviour (flat 0-2% overload, w+1 edge-uplink bound, queues independent of size) matches the paper's theory; the discrepancies are concentrated in the DRB stand-in (`path_rr`, which synchronises all flows at path 0 and has no random per-flow phase) and in the JSQ tie-break and AR quantisation details of the comparators. A faithful DRB baseline would need a random per-flow path permutation and phase, which is a source change not made here.

## Caveats

- Paper figure values are visual readings.
- Part 3 uses 2 seeds, Part 1/2 five (the paper: 30 runs for Fig 17).
- Part 2's max queue includes E->H (all five layers); I did not compute the fabric-only variant.
- A first launch of part 2 was accidentally overlapped with its own retry for a few minutes (4 simulators at once, briefly one xargs was killed); all affected outputs were regenerated by the idempotent driver and verified (every run has N finished flows).

## DRB faithfulness: random per-flow phase and Agg-fastest path order (added later)

Source change (`// ===== ADDED (drb) =====`, see `../MODIFICATIONS.md`): `-path_rr_start_mode random` (uniform random start slot per flow from the seeded simulator RNG) and `-path_rr_order agg_fast` (inter-pod 3-tier path list permuted so consecutive packets use different Aggs; path index i = Agg i%A, core i). Existing modes are byte-identical (baseline.sh hashes and a `path_rr` smoke are unchanged). Variants below: `drb` = slot 0 native order (old), `drb_hash` = srcdst_hash native (old), `drb_rand` = random phase, native order, `drb_af` = slot 0, agg_fast order, `drb_af_rand` = random phase + agg_fast order (the faithful DRB stand-in). Same flags/workloads/binary-family as Parts 1-3 (new binary built from the changed source; old variants reused from the frozen-binary data, which the unchanged modes reproduce byte-for-byte). Driver `scripts/run_vc_drb.sh {1|2|3}`, summaries and new runs in `data/vc_drb/` (`runs.tar.gz`, `vc1_summary.md`, `vc2_summary.md`, `vc3_summary.md`).

ACK direction: `path_rr` ACKs are not source-routed (route NULL in `UecSink::sendAck`); they follow the switch FIB with the echoed path id, i.e. they are neither pinned nor synchronised with the data pointer. So no separate half-rotation ACK pointer was added (the paper's separate ACK pointers only matter for ACK/data queue interaction; ACKs are 64 B and cannot explain a 10x queue gap).

Why two knobs: the native `get_bidir_paths` order is agg-major (path index = a*L + l, L = cores per Agg = 6 at 432 hosts), so L consecutive packets of a flow stay on one Agg, i.e. on one ToR uplink. With random phase alone the 6 hosts of a ToR are at random slots, but each burst of L packets still loads one uplink: E->A overload 4.7%. DRB round-robins over core switches, whose natural fat-tree sequence alternates Aggs on every packet.

### Fig 3 (432 hosts, 1 MB, 5 seeds; worst-link overload %, mean +- SEM; paper DRB about 0 at every stage)

| Variant | E->A | A->C | C->A | A->E |
|---|---|---|---|---|
| Ofan (ours) | 0.8 +- 0.0 | 1.6 +- 0.1 | 1.7 +- 0.1 | 0.8 +- 0.0 |
| `drb` slot 0 | 7.8 +- 0.0 | 12.5 +- 0.0 | 12.5 +- 0.0 | 7.8 +- 0.0 |
| `drb_hash` | 4.9 +- 0.3 | 2.3 +- 0.1 | 2.4 +- 0.1 | 4.3 +- 0.2 |
| `drb_rand` | 4.7 +- 0.3 | 2.6 +- 0.2 | 2.6 +- 0.3 | 4.8 +- 0.4 |
| `drb_af` (slot 0) | 0.8 +- 0.0 | 12.5 +- 0.0 | 12.5 +- 0.0 | 0.8 +- 0.0 |
| `drb_af_rand` | 0.8 +- 0.0 | 2.6 +- 0.2 | 2.6 +- 0.3 | 0.8 +- 0.0 |

Edge layers drop to the Ofan floor (0.8% = packet granularity, 256 packets over 6 uplinks); core layers 2.6% (a flow of 256 packets over 36 cores is 7.1 packets per core, so +-1 packet is 12.5% on a single flow; averaging over flows leaves 2.6%). Max queues (pkts) E->A/A->C/C->A/A->E for `drb_af_rand`: 5.4/12.8/12.4/6.8 vs Ofan 6.0/7.8/8.4/7.2. Verdict: the paper's "about 0%" (read with +-3 points) is matched within reading error; slot-0 alone (`drb_af`) fixes only the edge layers and random phase alone only the core layers; both are needed.

### Fig 17 (ratio of max queue DRB / Ofan, 4 MB; paper 1.24-1.57)

| Hosts | Ofan max q (pkts) | `drb` slot 0 | `drb_hash` | `drb_rand` (3 seeds) | `drb_af` (3 seeds) | `drb_af_rand` max q / ratio (3 seeds) |
|---|---|---|---|---|---|---|
| 128 | 7.0 | 2.37 | 1.83 | 1.76 +- 0.05 | 2.29 +- 0.08 | 9.7 / 1.38 +- 0.05 |
| 250 | 7.7 | 3.56 | 2.22 | 2.14 +- 0.13 | 3.45 +- 0.20 | 11.7 / 1.52 +- 0.08 |
| 432 | 9.0 | 4.31 | 2.67 | 2.63 +- 0.16 | 4.19 +- 0.04 | 13.7 / 1.52 +- 0.10 |
| 686 | 10.0 | 5.26 | 3.22 | 2.90 +- 0.10 | 5.20 +- 0.06 | 15.3 / 1.53 +- 0.09 |
| 1024 | 10.0 | 6.60 | 3.60 | 3.70 +- 0.10 | 6.90 +- 0.10 | 17.0 / 1.70 +- 0.06 |

(Ratios per seed, mean +- SEM; Ofan column for seeds 1-3 where 3-seed variants are compared.) `drb_af_rand` gives 1.38-1.70 against the paper's 1.24-1.57: the trend and the magnitude now agree (1024 hosts 0.1-0.15 above the top of the paper's range; previous best variant was 1.8-3.6, slot 0 2.4-6.6).

### Fig 16 (1024 hosts, 4 MB, plateau of average queue t in [10,40) us, KB; paper DRB: E->A about 8.5-9, A->C about 14, C->A about 14.5, A->E about 9, E->H about 8.5)

| Variant | seed | E->A | A->C | C->A | max q E->A/A->C/C->A/A->E/E->H (pkts) |
|---|---|---|---|---|---|
| Ofan | 1 / 2 | 8.8 / 9.0 | 14.9 / 14.9 | 15.9 / 15.9 | 7/10/10/8/9 |
| `drb` slot 0 | 1 / 2 | 120.7 / 120.7 | 120.6 / 120.6 | 32.9 / 31.0 | 61-62/60/20-23/32/64-65 |
| `drb_hash` | 1 / 2 | 43.0 / 42.7 | 15.7 / 16.7 | 24.1 / 23.3 | 36-39/11-12/16-18/33-37/23 |
| `drb_rand` | 1 / 2 | 43.4 / 43.2 | 16.8 / 16.4 | 22.1 / 24.9 | 36-39/12-13/16-19/32/23 |
| `drb_af` | 1 / 2 | 18.7 / 18.7 | 120.7 / 120.7 | 33.1 / 31.7 | 11/60/21-22/31-33/68 |
| `drb_af_rand` | 1 / 2 | 9.2 / 9.5 | 23.6 / 20.5 | 21.9 / 24.3 | 7-8/15-17/15-16/8/11-14 |

### Verdict

A random per-flow phase alone does NOT close the gap (it is equivalent to `srcdst_hash`: E->A 43 KB, ratio 1.8-3.7). The decisive extra ingredient is the path order: rotating the Agg (first hop) fastest, i.e. round-robin over the core switches as DRB does. Random phase + that order (`drb_af_rand`) closes Figs 3 and 17 and the edge-layer part of Fig 16 (E->A 9.2-9.5 KB vs paper 8.5-9, max q 7-8 packets, A->E max 8 packets equals Ofan; E->H max 11-14 packets vs Ofan 9). Remaining mismatch: Fig 16 core layers, A->C 20-24 KB and C->A 22-24 KB against the paper's about 14 / 14.5. Note that our Ofan core layers are also 1.5x above the paper's Fig 18 Ofan (14.9 / 15.9 vs about 9-10 KB), and the DRB/Ofan core ratio here (1.4-1.6) is about the paper's (14 vs 9-10), so the residual is consistent with the same unexplained constant factor on the core layers that Ofan shows, not with a DRB-specific defect. That constant factor is a hypothesis, not tested.

Caveats: Fig 3 uses 5 seeds, Fig 17 uses 3 seeds for the new variants (old ones 5), Fig 16 uses 2 seeds. `agg_fast` is only defined for 3-tier inter-pod flows (other flows keep native order). Our `path_rr` has one pointer per flow (permutation workloads: one flow per host), not per (destination, packet-size quantum); with a one-flow-per-host permutation this is equivalent.

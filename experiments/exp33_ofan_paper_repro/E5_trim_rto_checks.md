# E5 - Is trimming responsible for the mismatches? Fig 12 without trimming, and the Fig 7a REPS-degradation hypothesis

Two read-only checks on the frozen simulator (`/tmp/frozen/htsim_uec_v2`, private copy, no source edit, no rebuild, at most 2 simulator processes at a time). Driver `scripts/run_trimrto.sh` (idempotent), summary `scripts/summarize_trimrto.py`; outputs in `data/trimrto/` (`e5_summary.md` full tables, `e5_rto_runs.csv`, `driver_all.log`, `runs.tar.gz` with every `.out`, `.cmd`, `-log_queue_stats` `.tsv`; `workloads/`).

## Summary

1. **Fig 12: trimming is irrelevant for the reproduction.** All 30 E4 cells (432 hosts, 4 MiB permutation, NSCC and DCTCP, REPS / AR / Ofan, buffers `-q 193 -ecn 19 19`, seeds 1-5) rerun with `-disable_trim` are bit-for-bit identical to the E4 trim-on runs (every flow-finish line and the whole queue-statistics TSV). The 193-packet buffer never fills (worst queue 89 packets), so the trimming code path is never reached. The mismatches with the paper in Fig 12 are therefore not caused by trimming. Only when the buffer is made small enough to overflow (`-q 40`) does trimming matter, and then it helps the baselines (it does not explain the paper's larger baseline inflation either, see A2).
2. **Fig 7a REPS degradation: reproducible, but only with an RTO shorter than the peak queueing delay, and it is not caused by freezing in our simulator.** The default RTO in the infinite-buffer no-CCA setup is 3,334 us (an artefact of the formula, see B1), 20x longer than the whole 16 MB transfer, so no RTO can ever fire there. With `-min_rto 20` at 64 MB, REPS rises from +3.96% to +56.7% (paper: roughly +50 to +100%), AR from +6.9% to +28.2%, Ofan stays at +0.44%. The mechanism is a spurious-RTO / retransmission feedback loop (111,785 RTOs for REPS), with a single freeze entry, so the paper's "freezing mode" conjecture is not what produces it here. With `-min_rto 10` at 16 MB REPS collapses completely (hundreds of times the lower bound, freezing does occur) while AR degrades by +54%. The paper's AR value (about +2% at 64 MB) is not reproduced in the degraded regime (ours +28%), so the match is partial.

## A. Fig 12 without trimming

### A1. E4 cells with `-disable_trim` (identical flags otherwise)

Flags per cell exactly as `run_e4.sh` plus `-disable_trim`: `-sender_cc_only -disable_tor_ecn -q 193 -ecn 19 19 -sender_cc_algo {nscc|dctcp}`, LB REPS = `-load_balancing_algo freezing -paths 65535`, AR = `-strat ecmp_ar -load_balancing_algo ecmp`, Ofan = `-strat ofan -load_balancing_algo ecmp`; seed s = permutation s = `perm432_4mb_s<s>.cm`.

Result: **30 / 30 cells identical** to E4 (flow-finish lines compared as text, and the queue-statistics TSV compared byte for byte), with 0 trims, 0 drops, 0 RTOs. Per-cell CCT and the comparison are in `data/trimrto/e5_summary.md` (section A1). Mean CCT, for reference (identical to E4 by construction): NSCC REPS 53.16 us, AR 53.17 us, Ofan 49.39 us; DCTCP REPS 61.99 us, AR 57.22 us, Ofan 49.39 us (E4 means over 10 seeds; the five seeds here match the corresponding E4 seeds exactly).

Why identical: `-disable_trim` has exactly two effects in the simulator, `FatTreeSwitch::_disable_trim` (a full queue drops instead of trimming; `compositequeue`) and `UecSrc::_trim_disbled` (which changes only the REPS freeze entry on RTO, `uec.cpp` `rtxTimerExpired`). Neither is reached when no queue overflows and no RTO fires. The v2 binary also reproduces the E4 numbers (E4 used the frozen binary), so v2 differs from it only in ways that do not affect these runs.

### A2. Stress variant: small buffer `-q 40 -ecn 5 10`, with and without trimming (NSCC, seeds 1-3)

Same flags otherwise (432 hosts, 4 MiB permutation). The default RTO here is about 13 us (6.25 us unloaded RTT + 4 queue drain times). Lower bound for NSCC: 48.81 us. Mean over 3 seeds (range in parentheses):

| LB | trimming | CCT us | CCT increase % | trims | drops | RTOs | RTS | freeze entries | max fabric queue |
|---|---|---|---|---|---|---|---|---|---|
| REPS | on | 56.76 (56.66-56.89) | 16.3 | 2,334 | 0 | 2 | 0 | 2 | 40 pkts (full) |
| REPS | off | 66.34 (65.98-66.83) | 35.9 | 0 | 13,725 | 13,799 | 66 | 344 | 40 (full) |
| AR | on | 55.97 (55.90-56.08) | 14.7 | 565 | 0 | 2 | 0 | 0 | 40 (full) |
| AR | off | 62.08 (62.05-62.15) | 27.2 | 0 | 600 | 708 | 0 | 0 | 40 (full) |
| Ofan | on | 49.38 | 1.17 | 0 | 0 | 0 | 0 | 0 | 8 |
| Ofan | off | 49.38 | 1.17 | 0 | 0 | 0 | 0 | 0 | 8 |

What trimming does when overflow happens: it turns losses into NACKs (RTOs drop from about 13,800 to 2 for REPS), and without it REPS loses much more than AR (about 13,700 drops vs 600) because it sprays over many more queues and, after the RTO, 344 flows enter freezing mode. Ofan is unaffected (its queues stay at 8 packets). So even in this regime Ofan keeps its +1.2% while the baselines get worse without trimming (+36% REPS, +27% AR); trimming is thus not what hurts the baselines relative to Ofan in the paper's Fig 12, and if the paper's baselines ran without trimming and with overflowing buffers, the gap would widen, not narrow. Caveat: one workload, 3 seeds.

## B. Fig 7a: REPS, freezing and the RTO

### B1. How the RTO is set (read-only code reading)

- `UecSrc::_rto` is initialised to `_min_rto` in the `UecSrc` constructor (`uec.cpp` ~1168) and **never updated afterwards** (no SRTT/RTTVAR estimation; `recalculateRTO()` only re-arms the timer from the oldest unacked send time). The RTO is one fixed value per run, per source: timer = send time + `_rto` (`startRTO`).
- `_min_rto` has three layers: static default `DEFAULT_UEC_RTO_MIN` = 100 us (`uec.h`); then `main_uec.cpp` ~1782 **overwrites it** with `network_max_unloaded_rtt + queuesize_bytes * 4 * 8 / linkspeed` (the comment says "2 priority queues; 3 hops for incast"); then `-min_rto <us>` (`main_uec.cpp` ~580, an integer, applied only if > 0) overrides that again.
- In this setup `network_max_unloaded_rtt` = 6.25 us. Default RTO: **38.3 us for `-q 193`** (800,950 B), **3,334 us for `-q 20000`** (83.2 MB), about 13 us for `-q 40`. So the infinite-buffer no-CCA runs of E2 (Fig 7) had an RTO longer than the whole transfer (16 MB: 177-190 us; 64 MB: 690-735 us), and could never time out. That is why E2 saw `rtos 0` and `freeze_entries 0`.
- The paper's own RTO is not stated in the passages we have; the infinite-buffer runs with a formula-derived RTO would behave like ours (no timeouts), which is what makes the paper's explanation ("queues long enough to cause a timeout") imply an RTO of the order of the queueing delay.
- REPS freezing on RTO (`rtxTimerExpired`, FREEZING): with trimming disabled the freeze is entered **only if** `_last_rto_max_rtt < 1.65 * _base_rtt` (base RTT 6.25 us here, i.e. only if the largest RTT in the recent window is below about 10.3 us); with trimming enabled it is entered on every RTO (when not already frozen and `explore_counter == 0`). Exit after `-exit_freeze` (default 10 ms in these runs: "can exit at ...10056442"). So under queue-induced delay (RTT above 10.3 us) the no-trim configuration deliberately does not freeze; freezing only occurs when the delay looks small, i.e. a failure-like timeout.

### B2. Runs

Config (as E2, `run_e2.sh` flag set): 432 hosts `fat_tree_432_1os_3t_800g.topo`, plain permutation (`gen_derangement.py ... perm`, seed 1), `-sender_cc_only -sender_cc_algo constant -cwnd 1000` (4.16 MB, never window-limited; note `run_e2.sh` uses 1000 packets, not 400), `-mtu 4160 -q 20000 -ecn 19 19 -disable_trim -disable_tor_ecn`; LB REPS = `-load_balancing_algo freezing -strat ecmp_host -paths 65535`, AR = `-load_balancing_algo ecmp -strat ecmp_ar`, Ofan = `-load_balancing_algo ecmp -strat ofan`; `-min_rto <v>` added except for the default row. 1 seed. Lower bounds (single flow 0->216, same flags): 176.605 us (16 MB), 687.786 us (64 MB). "Increase" = CCT / bound - 1. Counters (`rtos`, `freeze_entries`, `freeze_us`) are sums over the 432 flows from the flow-finish lines. Max fabric queue = max `max_q_bytes` over E>A, A>C, C>A, A>E links.

**16 MB** (full table with all columns in `data/trimrto/e5_summary.md`):

| min RTO us | REPS CCT / inc % | REPS RTOs / freeze entries | AR CCT / inc % | AR RTOs | Ofan CCT / inc % | Ofan RTOs |
|---|---|---|---|---|---|---|
| default (3,334) | 185.79 / +5.20 | 0 / 0 | 189.96 / +7.56 | 0 | 177.67 / +0.60 | 0 |
| 100 | 185.79 / +5.20 | 0 / 0 | 189.96 / +7.56 | 0 | 177.67 / +0.60 | 0 |
| 50 | 185.79 / +5.20 | 0 / 0 | 189.96 / +7.56 | 0 | 177.67 / +0.60 | 0 |
| 20 | 185.79 / +5.20 | 0 / 0 | 189.96 / +7.56 | 26 | 177.67 / +0.60 | 0 |
| 10 | **not finished** (killed, see below) | 2.9 M / 117 (of 156 finished flows) | 271.17 / +53.5 | 469,580 | 177.67 / +0.60 | 0 |
| 5 | **not finished** (killed) | 0.70 M / 29 (of 32 finished flows) | 503.45 / +185.1 | 2,607,209 | 350.33 / +98.4 | 1,607,826 |

Max fabric queue at 16 MB (no RTO storm): REPS 740 KB, AR 1,115 KB, Ofan 33 KB (peak queueing delay about 7, 11 and 0.3 us at 800G; peak REPS RTT about 9.9 us in the logs). Hence RTOs at 50 and 100 us never fire, 20 us fires only for AR (26 spurious RTOs, CCT unchanged), and 10 us is right at REPS' peak RTT.

**64 MB**:

| min RTO us | REPS CCT / inc % | REPS RTOs / freeze entries | AR CCT / inc % | AR RTOs | Ofan CCT / inc % | Ofan RTOs |
|---|---|---|---|---|---|---|
| default (3,334) | 715.00 / +3.96 | 0 / 0 | 734.94 / +6.86 | 0 | 690.81 / +0.44 | 0 |
| 50 | 715.00 / +3.96 | 0 / 0 | 737.17 / +7.18 | 769 | 690.81 / +0.44 | 0 |
| 30 | 724.79 / +5.38 | 1,049 / 0 | 788.00 / +14.6 | 83,638 | 690.81 / +0.44 | 0 |
| 25 | 742.96 / +8.02 | 11,616 / 0 | 827.20 / +20.3 | 237,693 | 690.81 / +0.44 | 0 |
| 20 | **1,078.02 / +56.7** | 111,785 / 1 | 881.48 / +28.2 | 605,032 | 690.81 / +0.44 | 0 |

Max fabric queue at 64 MB: REPS 1.6 MB (5.0 MB in the RTO-20 run), AR 3.8 MB, Ofan 33 KB. Ofan never queues, so no RTO can fire and it is immune at every setting except 5 us at 16 MB, where the RTO is below the unloaded RTT (6.25 us) and every packet times out.

The 16 MB RTO 10 and 5 REPS cells (and nothing else) did not finish: each had run for over 18 minutes of wall time and still simulated only about 2,400-3,100 us of the transfer (156 and 32 of 432 flows finished, 17x and 13x the lower bound at the last finish already, with several million RTOs and growing memory), so they were killed (rc 143 in the `.out`, no queue TSV). Their numbers above are lower bounds from the flows that had finished and the `started freezing` lines (393 and 429 flows had entered freezing mode in total). They are not comparable to the finished cells.

### B3. Reading

- **Does REPS' CCT increase grow with message size as in the paper's Fig 7a?** With the default RTO (what E2 measured) no: 5.2% at 16 MB and 4.0% at 64 MB, as in E2 (14% at 0.5 MB, falling). Only with an RTO below the peak queueing RTT does it rise, and then steeply: at 64 MB REPS is +8.0% / +56.7% for RTO 25 / 20 us versus +4.0% without timeouts, because queues grow with message size (REPS peak queue 0.74 MB at 16 MB vs 1.6 MB at 64 MB), so a fixed short RTO is crossed more often for bigger messages. At RTO 20 us the same value does nothing to REPS at 16 MB (+5.2%) but gives +56.7% at 64 MB: that is the paper's qualitative pattern (REPS fine at small messages, much worse at 64 MB) and magnitude (paper reading of Fig 7a, y axis log scale: REPS roughly +5-10% for 0.5-8 MB and roughly +50 to +100% at 64 MB; AR about +10% falling to about +2%; Ofan about +3% falling to well below 1%. These are approximate reads of the plotted markers, not tabulated values).
- **Is freezing the cause?** Not at 64 MB in our simulator: REPS had 0 freeze entries at RTO 30/25 and 1 at RTO 20 (551 us frozen) while suffering 111,785 RTOs. Since this build gates freezing on `RTT < 1.65 x base RTT` when trimming is off, an RTO caused by queueing delay does not freeze. The slowdown is the spurious-RTO / retransmission loop itself (each timeout retransmits a packet that is only delayed, adding load to the already long queues: REPS queue grows from 1.6 MB to 5.0 MB). AR suffers the same mechanism (+28.2%), so the loop is not REPS-specific here. Freezing does appear at 16 MB / RTO 10 (117+ flows) where the delay is near the freeze threshold, and there REPS collapses far worse than AR (AR +54% at the same RTO) and Ofan is untouched, so freezing (stale cached EVs reused while the RTO keeps firing) clearly aggravates the loss, but this is a different regime from the paper's long-queue one.
- **AR vs the paper:** paper AR about +2% at 64 MB. Ours: +6.9% without RTOs and +7 to +28% with short RTOs, so the paper's AR advantage over REPS at 64 MB (about 2% vs about 80%) is not reproduced; here AR is lower than REPS only at RTO 20 (28% vs 57%) and higher at the others.
- **Ofan:** +0.44% at 64 MB, paper below 1%, matches and is RTO-independent.

### Honest conclusion

- Trimming is not the reason Fig 12 does not match: with the paper's buffers (193 packets) it is never exercised (30/30 cells bit-identical). If the paper's runs had overflowing buffers, disabling trimming would inflate the REPS and AR baselines (A2: +16% to +36% for REPS, +15% to +27% for AR at `-q 40`), i.e. move toward the paper's larger baseline inflation, but that needs queues far above the 89 packets we observe, which is a buffer/queueing difference, not a trimming one.
- The Fig 7a "REPS gets worse at 64 MB" phenomenon is reproducible only by shortening the RTO to roughly the peak queueing delay (about 20-25 us at 64 MB, 1 seed): that gives +57% (paper: +50 to +100%). It is driven by spurious timeouts, not by the freezing mode in this build. We cannot claim this is the paper's mechanism: the paper's RTO is unknown to us, and the correct statement is that a REPS slowdown of the paper's size appears in our simulator under a short RTO, and that AR is also hurt (more than the paper's +2%).
- Limits: one seed per RTO cell (the 64 MB seed-1 REPS value at 20 us is a single run and the transition is sharp; 25 us gives +8%), two cells (16 MB REPS RTO 10 and 5) killed without completion, no-CCA `cwnd 1000`, mean-queue and per-flow RTO distributions not analysed.

## Reproduce

```bash
docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_trimrto.sh                 # all parts, ~1 h plus the 64 MB runs (PAR=2)
PART=r64 RTOS64="30 25" JTIMEOUT=2700 docker exec ...                                                          # extra RTO values
python3 experiments/exp33_ofan_paper_repro/scripts/summarize_trimrto.py                                        # reads runs.tar.gz and the E4 tarball
```

Note: the first launch of the 16 MB REPS RTO 10 and 5 cells ran until killed; to re-run them add a smaller `-end` (they do not finish within hours).

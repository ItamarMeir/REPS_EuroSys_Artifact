# E1 results: Ofan paper Fig 1 (utilisation, max queue, CCT vs load; no congestion control)

Reproduces Fig 1 of arXiv 2610.07230 (§1/§2.2). Figures (paper style, `scripts/paperstyle.py`): `plots/e1_fig1/fig1.png` (3 panels: (a) max utilisation = effective utilisation, (b) max queue, (c) CCT; REPS, AR with q=193, Ofan), single panels `plots/e1_fig1/fig1a_util.png`, `fig1b_maxq.png`, `fig1c_cct.png`, extras `plots/e1_fig1/extra_util_busiest.png`, `extra_cct_increase.png`. Mean ± SEM over 5 seeds (seed changes the random permutation, ECMP hashing and pointers). Tidy data `data/e1/e1_runs.csv` (130 runs), `data/e1/e1_summary.csv`; raw runs in `data/e1/runs.tar.gz` (extract to `data/e1/runs/` before re-running `aggregate_e1.py`).

## Setup
- Topology `topologies/fat_tree_432_1os_3t_800g.topo` (k=12, 432 hosts, 800G, 0.5 us/link). Workload: 1 MB (1048576 B) random permutation (`gen_derangement.py ... perm`, plain permutation: ~1/12 of flows intra-pod), 1 flow/host, all start at t=0.
- No CC: `-sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160` (window 16.6 MB >> flow). Load rho emulated by pacing: `-linkspeed 800000*rho` (topology links stay 800G); rho in 0.8, 0.85, 0.9, 0.95, 0.98, 1.0.
- `-disable_trim`, `-ecn 19 19` (kept on so REPS gets marks), `-disable_tor_ecn` for all main runs (project rule). Sensitivity `reps_dl` = REPS WITHOUT `-disable_tor_ecn` (rho 0.9, 1.0): results are byte-identical to REPS, because the host-downlink (E->H) queue never exceeds 59 KB < the 79 KB ECN threshold, so the flag has no effect here.
- Strategies: `ofan` = `-strat ofan -load_balancing_algo ecmp -q 20000`; `ar_q20000` = `-strat ecmp_ar -load_balancing_algo ecmp -q 20000` (default quantised comparator is relative to maxsize, so it degenerates toward random at this size); `ar_q193` = same with `-q 193` (800 KB, quantisation meaningful); `reps` = `-load_balancing_algo freezing -strat ecmp_host -paths 65535 -q 20000`. Exact commands: `data/e1/runs/*.cmd` (in the tarball). Driver `scripts/run_e1.sh` (idempotent, run in container `ofan-dev`), `scripts/aggregate_e1.py`, `scripts/plot_e1.py`.
- ar_q193: 0 drops, 0 trims, 0 RTOs in every run (max queue 174 KB < 800 KB), so it is loss-free and comparable. All other runs: 0 drops/trims/RTOs too.

## Metric definitions (stated honestly: the repo only logs per-queue totals, no time series)
- CCT = last flow finish. Lower bound (`single_us`) = one 1 MB flow alone at the same pacing (e.g. 16.86 us at rho=1); fixed path latency D = bound - size/(rho C) = 6.38 us. "CCT increase" = CCT/bound - 1.
- **Effective utilisation** = 100 (size/C)/(CCT - D): fraction of line rate actually sustained over the busy period; equals rho for an ideal run. This is the definition that best matches the paper's panel (a). 
- **Busiest-link utilisation** = 100 (max fabric-link data bytes / bytes of one flow) (size/C)/(CCT - D), max over E->A, A->C, C->A, A->E links. NOTE: this saturates near 97-98% for every strategy (a hot link is always busy), so it does NOT separate the strategies; I report it for completeness but do not consider it a match for the paper's metric.
- Max queue = max over all switch egress queues (5 layers) of max data-queue occupancy, KB = 1000 B.

## Results
Effective utilisation (%), ideal = load:

| strategy | 0.8 | 0.85 | 0.9 | 0.95 | 0.98 | 1.0 |
|---|---|---|---|---|---|---|
| Ofan | 78.5 ± 0.0 | 83.2 ± 0.0 | 87.8 ± 0.1 | 92.4 ± 0.0 | 94.9 ± 0.0 | 96.0 ± 0.1 |
| AR q=193 | 75.9 ± 0.2 | 79.3 ± 0.3 | 81.3 ± 0.3 | 83.3 ± 0.4 | 83.4 ± 0.7 | 83.1 ± 0.3 |
| AR q=20000 | 75.5 ± 0.3 | 78.5 ± 0.4 | 80.7 ± 0.4 | 82.0 ± 0.2 | 82.4 ± 0.2 | 81.4 ± 0.7 |
| REPS | 75.9 ± 0.2 | 78.9 ± 0.4 | 80.5 ± 0.3 | 81.0 ± 0.7 | 81.2 ± 0.5 | 81.1 ± 1.0 |
| REPS +ToR-dl ECN | - | - | 80.5 ± 0.3 | - | - | 81.1 ± 1.0 |

Busiest-link utilisation (%):

| strategy | 0.8 | 0.85 | 0.9 | 0.95 | 0.98 | 1.0 |
|---|---|---|---|---|---|---|
| Ofan | 79.2 ± 0.1 | 84.0 ± 0.1 | 88.6 ± 0.1 | 93.2 ± 0.1 | 95.8 ± 0.1 | 97.0 ± 0.1 |
| AR q=193 | 88.4 ± 0.7 | 94.2 ± 0.7 | 95.0 ± 0.6 | 96.5 ± 0.9 | 95.8 ± 0.7 | 96.2 ± 0.8 |
| AR q=20000 | 91.2 ± 2.0 | 92.2 ± 0.4 | 95.1 ± 0.6 | 97.7 ± 0.4 | 97.9 ± 0.8 | 98.1 ± 0.7 |
| REPS | 91.9 ± 0.5 | 95.2 ± 1.0 | 96.6 ± 0.5 | 98.0 ± 0.6 | 97.1 ± 0.7 | 97.9 ± 1.0 |
| REPS +ToR-dl ECN | - | - | 96.6 ± 0.5 | - | - | 97.9 ± 1.0 |

Max queue (KB):

| strategy | 0.8 | 0.85 | 0.9 | 0.95 | 0.98 | 1.0 |
|---|---|---|---|---|---|---|
| Ofan | 29 ± 0 | 31 ± 1 | 31 ± 1 | 32 ± 1 | 32 ± 2 | 33 ± 0 |
| AR q=193 | 84 ± 4 | 106 ± 12 | 116 ± 5 | 142 ± 6 | 161 ± 6 | 174 ± 6 |
| AR q=20000 | 87 ± 5 | 111 ± 10 | 137 ± 7 | 173 ± 11 | 201 ± 9 | 233 ± 16 |
| REPS | 93 ± 4 | 110 ± 8 | 128 ± 6 | 174 ± 21 | 200 ± 5 | 211 ± 6 |
| REPS +ToR-dl ECN | - | - | 128 ± 6 | - | - | 211 ± 6 |

CCT (us):

| strategy | 0.8 | 0.85 | 0.9 | 0.95 | 0.98 | 1.0 |
|---|---|---|---|---|---|---|
| Ofan | 19.77 ± 0.01 | 19.00 ± 0.01 | 18.33 ± 0.01 | 17.74 ± 0.01 | 17.43 ± 0.00 | 17.29 ± 0.01 |
| AR q=193 | 20.23 ± 0.03 | 19.62 ± 0.05 | 19.29 ± 0.05 | 18.96 ± 0.06 | 18.96 ± 0.10 | 18.99 ± 0.05 |
| AR q=20000 | 20.30 ± 0.05 | 19.76 ± 0.07 | 19.39 ± 0.07 | 19.17 ± 0.03 | 19.10 ± 0.03 | 19.25 ± 0.12 |
| REPS | 20.22 ± 0.04 | 19.69 ± 0.06 | 19.41 ± 0.04 | 19.33 ± 0.12 | 19.29 ± 0.08 | 19.32 ± 0.17 |
| REPS +ToR-dl ECN | - | - | 19.41 ± 0.04 | - | - | 19.32 ± 0.17 |

CCT increase over single-flow bound (%):

| strategy | 0.8 | 0.85 | 0.9 | 0.95 | 0.98 | 1.0 |
|---|---|---|---|---|---|---|
| Ofan | 1.3 ± 0.0 | 1.4 ± 0.0 | 1.6 ± 0.0 | 1.8 ± 0.0 | 2.0 ± 0.0 | 2.6 ± 0.1 |
| AR q=193 | 3.7 ± 0.1 | 4.8 ± 0.3 | 6.9 ± 0.3 | 8.9 ± 0.3 | 11.0 ± 0.6 | 12.6 ± 0.3 |
| AR q=20000 | 4.0 ± 0.2 | 5.5 ± 0.4 | 7.5 ± 0.4 | 10.1 ± 0.2 | 11.9 ± 0.2 | 14.2 ± 0.7 |
| REPS | 3.6 ± 0.2 | 5.1 ± 0.3 | 7.6 ± 0.2 | 10.9 ± 0.7 | 12.9 ± 0.5 | 14.6 ± 1.0 |
| REPS +ToR-dl ECN | - | - | 7.6 ± 0.2 | - | - | 14.6 ± 1.0 |

Where the max queue sits at rho=1 (KB, E->A / A->C / C->A / A->E / E->H): Ofan 26/30/33/30/32; REPS 211/138/148/160/57; AR q=20000 233/141/135/142/59; AR q=193 72/63/164/156/57 (see `e1_summary.csv`). Ofan is not at 1-2 packets (4 KB) because with plain (not inter-pod) permutation and shared up pointers the downstream layers still see a few packets of burst, but is flat in load at ~30 KB.

## Comparison with the paper's Fig 1 claims
| claim | ours | verdict |
|---|---|---|
| REPS and AR stop tracking the diagonal beyond load ~0.9 (utilisation plateau), ending below 95% at load 1 | effective util tracks load to ~0.85-0.9 then plateaus: REPS 81.1, AR 81-83 at load 1 (paper ~94-95) | qualitative MATCH (plateau, Ofan stays close to diagonal); magnitude MISMATCH (we are ~12 points lower than the paper's 94-95) |
| Ofan reaches ~99% at load 1 | 96.0 ± 0.1 (effective), 2.6% CCT above the single-flow bound | approximately matches (3 points lower; part of that is the ~0.4 us structural tail of a 1 MB message on 6-hop paths and my D estimate) |
| max queue grows with load for REPS/AR to ~200 KB at load 1, Ofan ~30 KB flat | REPS 211 ± 7, AR q=20000 233 ± 16, AR q=193 174 ± 6 (paper ~160 for AR); Ofan 33 ± 0, 29-33 across load | MATCH (REPS, AR, Ofan values all within ~15% of the paper) |
| CCT: REPS/AR improve little beyond 0.9, Ofan keeps improving | REPS 20.22 -> 19.32 us, AR 19.0-19.3 flat above 0.9; Ofan 19.77 -> 17.29 us | MATCH, absolute values near the paper's plot axes (paper REPS ~20.5->19.3, Ofan ~19->17) |

Caveats and honest mismatches:
1. Paper's utilisation metric is not defined in the text I read; with the busiest-link definition no strategy separates (all ~97-98%), so the match for the utilisation panel depends on adopting "effective utilisation". The paper's REPS/AR 94-95% vs our 81-83% is an unresolved gap: probably a different window/normalisation (e.g. utilisation measured over a sub-interval of the busy period, or averaged over sources only while sending) and not a behavioural difference, since CCT and queue panels agree well.
2. AR variants: ar_q20000 and reps are nearly indistinguishable in CCT; ar_q193 has smaller queues in the E->A/A->C layers (comparator effective) and slightly better CCT/util at high load, supporting that the quantisation matters, but its A->E/C->A queues are largest. Which AR the paper used is unknown.
3. 5 seeds, SEM small for Ofan (deterministic structure) and larger for REPS/AR max queue (a single worst link; e.g. +-16 KB for AR q=20000 at load 1).
4. `util_eff` at load 0.8 is below 80% for every strategy (78.5 Ofan) since D is estimated from a single path and head-of-flow packets on longer/different paths add latency; paper's curves start at the diagonal at 0.8.

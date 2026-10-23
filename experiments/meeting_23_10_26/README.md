# Meeting 2026-10-23: REPS buffer size, rate-controlled experiments

Source meeting: 2026-10-23 (Itamar Meir, Gabriel Skalosub, Chen Avin), topic "Load Balancing: Buffer Size Analysis in REPS". Zoom AI summary and full Hebrew transcript: the `.docx` in this directory. This README is an English translation of the summary (transcript excluded) plus the action items rewritten as experiments and missions. Previous meeting: [`../meeting_06_10_26/`](../meeting_06_10_26/README.md).

Vocabulary (B, k, valid EV, random draw, Freezing Mode) is as defined in the 2026-10-06 README.

## Key results
The discussion focused on whether the REPS buffer size B affects performance. The main conclusion: beyond roughly 4 to 8 entries, a larger buffer does not improve performance significantly. A problem surfaced in the link-degradation experiments: the congestion controller (NSCC) did not reduce the send rate as expected, which made the graphs incoherent. It was decided to run controlled experiments at three send rates (below, matching, and above network capacity) with no congestion control, to establish a clear baseline.

## Decisions
- **Buffer size:** 4 to 8 entries is enough; marginal benefit shrinks beyond that.
- **Gabriel:** this is a nice observation, not a dramatic result, and not by itself a basis for a paper. Itamar noted that the REPS paper in practice chose size 8 without saying so explicitly.
- **Future experiments:** three modes (low, matching, high rate relative to capacity), without congestion control.
- **Goal:** in the current experiments the send rate was neither known nor constant, so it was impossible to tell whether it matched capacity. With a known constant rate, each result can be attributed to a specific rate.
- **What changes in the implementation:** so far the rate was implemented as a window (rate converted to a fixed window size). A window is a sliding window that waits for ACKs, so the sender does not actually transmit at the configured rate: if the window corresponds to a rate above capacity, ACKs return at the capacity rate and the sender slows down. A constant-rate (rate-based) sender must be implemented, forced on the sender regardless of ACK arrival rate.
- **Alternative raised (Gabriel):** keep a fixed window in all experiments and vary network capacity instead. Itamar explained that this does not guarantee a controlled send rate, so the constant-rate sender was chosen.
- **The three experiment modes and expectations:**
  1. *Rate below capacity (under):* ACKs return faster than the send rate, so valid EVs may accumulate. This is where the buffer may actually matter.
  2. *Rate matching capacity:* expect low k (mostly 1 to 3); buffer size does not matter.
  3. *Rate above capacity (over, fully backlogged):* valid EVs do not accumulate, the sender draws random EVs, so size does not matter.
- At each of the three rates, run several buffer sizes and measure **k** (number of valid EVs in the buffer at send time) and the **percentage of packets sent with a valid EV vs a random EV**.
- At each rate, compare: healthy network; 50% degradation (all links leaving ToR 0 slowed by 50%); and the new non-uniform failure model.
- **Chen:** if in either the under or the over mode the size does not matter, that is a result one can stand behind; and if it does matter, we find a condition under which a large buffer helps.
- Removing congestion control is needed to isolate the buffer effect from NSCC's unpredictable behavior and to get a baseline with a known rate that does not change during the run.
- **Checking NSCC:** verify that the congestion controller really does not reduce the send rate under link degradation.
- **New failure model:** non-uniform failure across links (50% of the links degraded by 75%, 50% degraded by 25%).
  - Reason (Gabriel): total capacity still drops to 50%, but EVs are not necessarily distributed uniformly across the groups, especially with a small buffer, and there is no memory: EVs that were good get lost. This may be a failure model that REPS misses.
- **"Break" REPS (Gabriel):** examine different failure models designed to hurt REPS as much as possible, and let Claude think of such models too.
  - Idea: actively search for conditions where REPS performs badly, to find where there is room for improvement. Steady state on a healthy network will probably not yield much.
  - Gabriel: if a failure or degradation is found that REPS misses because of its reaction time (RTT), one can try to improve it, e.g. with a larger buffer or per-EV counters (a counting Bloom filter) to identify EVs that are good over time. Such an improvement could be the basis for a paper.

## Key technical findings
- **Why size does not matter at a matched rate:** at a matched send rate, the number of valid EVs in the buffer at any moment does not exceed 1 to 3, so enlarging the buffer adds no value.
- **Fully backlogged:** when the sender is faster than the ACK arrival rate, valid EVs do not accumulate. The buffer stays empty and the draw is random, so buffer size is irrelevant.
- **MPRDMA:** graphs with MPRDMA looked more reasonable. k stays low (mostly 1 to 3), consistent with the slower rate.
- **Role of the buffer:** to absorb variance in the ACK arrival rate. Low variance means a small buffer is enough. Gabriel: with congestion control the variance probably does not exceed about 8.
- **Rate reduction:** when the sender lowers its rate, some valid EVs are lost, but with an 8-entry buffer and one failed link, another EV is drawn and the rest compensate. To really hurt, an extreme scenario is needed in which all 8 stored EVs are the worst ones.
- **Analogy (Gabriel):** like Power of Two Choices / Power of K Choices, the marginal gain of increasing K is not significant.
- **Chen:** a rate reduction shows up as a narrower spray (fewer paths), not as a rate reduction on all paths. A larger buffer keeps spray quality higher. Gabriel agreed but said the benefit is negligible: zooming into the top-right graph shows only a slight rise in valid EVs.
- **Congestion control (Chen):** if a good congestion controller makes the buffer unnecessary, that is itself a significant finding, so it is important to understand the principle and not only see that size has no effect.
- **NSCC + 50% degradation graphs are not coherent with the no-failure graphs:** in the right-hand graph most draws are random (about 60%), as if the sender keeps transmitting at maximum rate. Proposed explanation: NSCC does not enter Freezing Mode (it is entered only on receiving a trimmed packet or on a timeout), and the target RTT configuration may have been too high.
- The findings do not depend on network topology (Chen asked, Gabriel confirmed).
- **Literature context (Gabriel):** in a survey of papers for the proposal, including REPS and about three others, the same idea appears: buffer management and packet spraying are not a classic caching problem and do not need much memory. In his view this is not a direction with a high chance of becoming a paper. A new paper by Keslasy was mentioned as a different topic; Jacob is expected to present it at the workshop day on 19 November. Also mentioned: the paper "Load Balancing for AI Training" (versions with and without OPS and Optimal; host-based vs switch-based), with an earlier version on arXiv.

## Open questions
1. Why does NSCC not react to the 50% capacity drop and keep a high send rate?
2. Will a non-uniform failure model reveal an advantage for a larger buffer?
3. Is there research value in improving REPS under specific failure/degradation conditions?
4. What is the difference between REPS with a small buffer and OPS (Oblivious Packet Spraying), which draws an EV with no memory? (Chen)

## Pending confirmation
- Check the send rate in the NSCC link-degradation experiments, to confirm the problem really is a too-high rate.
- Decide whether there is a basis for a paper around improving REPS under failure models.

## Next meeting
Next Monday at 15:00 (Zoom), subject to Chen's final confirmation. If that does not work, moved to Thursday. Itamar will send a reminder on Sunday.

---

# Action items as experiments and missions

Existing simulator hooks (checked against `htsim/sim/datacenter/main_uec.cpp`): `-reps_buffer_size`, `-sender_cc_algo constant`, `-cwnd`, `-host_cwnd_overrides`, `-fail_pipes_file`, `-timed_window` / `-timed_fail_tor_uplinks` / `-timed_fail_tor_downlinks`, `-failed N -down_ratio r` (uniform degradation), `-log_reps_events`, `-log_reps_window`. Prior NSCC degradation runs: `../exp28_link_degradation_sweep/`. **No rate-based (timer-paced) sender exists yet**; M2 builds it.

| ID | Type | Mission | Owner | Depends on |
|---|---|---|---|---|
| M1 | Diagnose | Confirm or refute "NSCC keeps a high rate under 50% degradation". | Itamar | none |
| M2 | Build | Constant-rate (rate-based) sender. | Itamar (with Claude) | none |
| M3 | Build | Non-uniform degradation failure model. | Itamar | none |
| M4 | Experiment (main) | Rate x failure x B sweep, no CC. | Itamar | M2, M3 |
| M5 | Experiment | REPS (small B) vs OPS on the same grid. | Itamar | M4 |
| M6 | Experiment | "Break REPS" failure-model search. | Itamar + Claude | M2 |
| M7 | Experiment (conditional) | Prototype a REPS improvement (bigger buffer / per-EV counters). | Itamar | M6 |
| M8 | Analysis | Explain the principle (why k is small; effect of CC). | Itamar | M1, M4 |
| M9 | Decision | Go/no-go on a paper basis. | Itamar, Chen, Gabriel | M4 to M6 |
| M10 | External | Share extra buffer-related papers. | Gabriel | none |
| M11 | Logistics | Remind about the next meeting. | Itamar | none |

Suggested order: M1, M2, M3 in parallel, then M4, then M5 and M6, then M7 and M8, then M9. Realistic target for the next meeting: M1 verdict, M2 working, first M4 slice (matched rate, healthy vs 50% degradation).

## M1. Diagnose NSCC under link degradation
Re-inspect the exp28 NSCC + 50% degradation runs: per-host send rate and cwnd over time, multiplicative-decrease events, Freezing Mode entries, trims and RTOs, and the share of random draws (`ev_random`, ~60% in the incoherent graph). Check the target queue delay / target RTT (`-target_q_delay`) against the queueing delay actually reached on degraded links, and whether Freezing Mode is ever entered. Output: a short verdict (rate really stays maximal? why?) that closes the "pending confirmation" item and open question 1.

## M2. Constant-rate sender
New sender mode (for example `-sender_cc_algo rate_const` with a rate in Gbps or as a fraction of line rate): packets released on a timer independent of ACKs, no window gating, no CC. Follow repo rules: `// ===== ADDED (rate-const-sender) =====` banners, a row in [`../MODIFICATIONS.md`](../MODIFICATIONS.md), an architecture doc, and byte-identical behavior when the flag is absent. Validation: measured send rate equals the configured rate at under, matched and over; sanity-check against `-sender_cc_algo constant`. Build and run inside Docker, `make clean` first.

## M3. Non-uniform degradation
50% of ToR 0's uplinks degraded by 75%, the other 50% by 25% (total capacity 50%). Reuse the exp28 degradation path and `-fail_pipes_file`; add per-link factors if missing. Validate that aggregate capacity is 50%.

## M4. Main sweep (proposed `exp34_buffer_rate_sweep`)
Grid: rate {under, matched, over capacity} x failure {healthy, uniform 50% on ToR 0, non-uniform from M3} x `-reps_buffer_size` {1, 2, 4, 8, 16, 32, 64} x at least 5 seeds; `-load_balancing_algo freezing`, no CC. One pass per run: `-log_reps_events` and `-log_reps_window` in the same run, plots built immediately, traces compressed afterwards. Metrics: k at send time, percent valid vs random draws, FCT p50/p99, goodput, spray width (distinct EVs/paths in use). Plots with 95% t-distribution CIs; compress runs to `runs.tar.gz`; README per `../RUNNING_EXPERIMENTS.md`. Answers: does B matter in under and over; where does a large buffer help.

## M5. REPS vs OPS
Same grid with an oblivious sprayer (no memory) against REPS with small B, to answer Chen's question 4. Reuse existing LB options (`path_random` and the other non-memory algorithms in the simulator).

## M6. "Break REPS" search
Ask Claude for adversarial failure models, for example asymmetric degradation, flapping or transient links, correlated multi-tier failures, failures timed to the RTT, partial-path loss where all stored EVs are bad. Implement via `-fail_pipes_file`, `-timed_*`, `-fail_src_paths`. Run against OPS and PATH_RR baselines and rank by REPS FCT gap.

## M7. REPS improvement (only if M6 finds a regime REPS misses due to RTT-scale reaction)
Prototype a larger buffer and per-EV counters (counting Bloom filter); relevant existing mechanisms: `-smart_filter_counter evhealth`, `repsMaxLifetimeEntropy`. Evaluate against M6's worst cases. Potential paper basis.

## M8. Principle
Explain why k stays at 1 to 3 (ACK-rate variance argument, power-of-K-choices analogy) and Chen's point that good CC makes the buffer unnecessary. Repeat the key M4 point with MPRDMA and with NSCC once M1 is resolved, so the CC-on case is covered.

## M9 to M11
M9: after M4 to M6, bring a go/no-go on a paper basis to the next meeting. M10: Gabriel shares papers; add them with the Keslasy paper, "Load Balancing for AI Training" and the 19 November workshop to the reading list. M11: Itamar reminds on Sunday about Monday 15:00 Zoom (fallback Thursday).

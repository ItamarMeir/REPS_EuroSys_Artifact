# Rate-const sender (`-rate_const_gbps`)

Purpose (meeting 2026-10-23, M2): inject at a known constant rate so REPS buffer behavior can be measured below, at, and above capacity without a congestion controller. The existing `-sender_cc_algo constant` fixes a *window*, which is ACK-clocked: above capacity the ACK rate throttles the sender, so the real rate is not the configured one.

## Semantics
- **Default (since `rate-const-nic`, 2026-10-24): R is the NIC egress rate in Gbps for ALL packet types** (data, retransmissions, ACK/NACK/control), by wire size. **`-rate_const_data_only`** restores the original behaviour described below: per-source pacer, full packet size (`_mtu`, header included) of new data and retransmissions only; RTS/control not counted.
- Requires `-sender_cc_algo constant` (no CC updates); `cwnd` is forced to 1e6 packets so the window never gates. Losses recover via NACK (trim on) or RTO as usual, spending the same rate budget.

## Mechanism (`htsim/sim/uec.{h,cpp}`)
- `rateGate()`: true if `now >= _rate_next_send`; otherwise arms the source's `UecRatePacer` for `_rate_next_send` and returns false. Called in `startFlow()` send loop, `sendIfPermitted()`, `timeToSend()` (refusal => `_nic.cantSend`, keeping the NIC contract), and the rtx path of `rtxTimerExpired()`. ACK handlers reach `sendIfPermitted()` and are therefore gated too (no ACK clocking).
- `rateCharge(pkt)`: after each emitted data packet, `_rate_next_send += pkt*8/R`; if idle longer than one gap the schedule restarts at `now` (no banked credit). The schedule is absolute, so NIC/control jitter does not drift the mean rate.
- The pacer is armed on demand only (no per-packet tick), fires `sendIfPermitted()`.

## Validation (2026-10-23, `fat_tree_1024_1os_2t_400g`, 16 MiB, seed 42, trim on, freezing B8, srv6 32 paths)
Single flow 0->512: FCT = 17.04 MB x 8 / R + 8.3 us fixed delay (4107 packets x 4150 B), R = 100/200/400 G gives 1371.2 / 689.8 / 349.1 us (linear fit on 1/R recovers 4150 B per packet).
Tornado (1024 flows), max FCT (us), RTOs:

| R (Gbps) | healthy | ToR0 uplinks all x0.5 (`-failed 32 -down_ratio 0.5`) |
|---|---|---|
| 100 | 1371.45, no ECN | 1371.45, no ECN (under) |
| 200 | 689.94, no ECN | 706.84, 64k ECN acks (matched) |
| 400 | 356.61, 9.7k ECN acks | 715.62, 136k ECN acks (over) |

No RTOs in any cell. Finish lines show `cwnd 4150000000` bytes (the override reached the sources).

Injection rate measured from the `-log_reps_events` trace (SEND+RTX rows of ToR0 host 0, degraded fabric, 100 us windows): R=200 -> 6.00 pkts/us (expected 6.02, 43 rtx); R=400 -> 11.9 to 12.05 pkts/us in steady state (expected 12.05; 3989 of 8096 packets are retransmits, so retransmits do spend the budget and the over-capacity sender is not ACK-throttled). Early windows run ~1.5% under R (shared NIC with ACK/control traffic).

Flag absent: every full flow-finish line (time and all counters) of the tornado NSCC x32 run is identical between the pre-change and post-change binary (`diff` empty, 1024 lines).

## NIC egress shaper (`rate-const-nic`, default mode)

Why: in all-to-all-ish workloads (tornado) every host is also a receiver and returns one 64 B ACK per 4150 B data packet through the same uplinks. A data-only pacer at R=200G therefore puts about 203G on a 200G degraded uplink (rho ~ 1.015): standing queue, ~50% of ACKs ECN-marked, ~49% random EVs, ~400 retransmits per run. On a healthy fabric the 400G NIC itself caps data+ACK so the same effect is hidden. A fixed sending rate must mean the rate of whatever the NIC puts on the wire.

Mechanism: `UecNIC::_egress_bps` (static, 0 = off) replaces `_linkspeed` in the port busy-time formula in `startSending()` and `sendControlPktNow()` via `egressSpeed()`, using the same integer expression as stock (`doNextEvent` matches ports by exact `send_end_time`). `main_uec.cpp` sets it from `-rate_const_gbps` unless `-rate_const_data_only`; requires `ports == 1`. `UecSrc::rateGate()/rateCharge()` become no-ops in shaper mode. Control-first arbitration (10:1) is unchanged. R is per host NIC, not per flow. Data goodput is about 1.5% lower than R (under: 1392 us instead of 1371 us for 16 MiB).

Validation (seed 42, tornado 16 MiB, matched/uniform50 B8 unless noted): flag absent and `-rate_const_data_only` finish lines byte-identical to the pre-change binary; shaper at R=400 byte-identical to `-sender_cc_algo constant -cwnd 1000000` without rate flag. Behaviour: matched/uniform50 0.53% random EV, 0 rtx, 286 ECN-marked ACKs, ToR0 FCT 702.4 us (data-only pacer: 49%, ~400 rtx, 63k ECN); over/healthy 0.65% random, FCT 356.6 us; under/healthy FCT 1392.4 us. Data-only R sweep (197/195/190 G) is in `meeting_23_10_26/M4/data/sweep_data_only_197_195_190.jsonl`.


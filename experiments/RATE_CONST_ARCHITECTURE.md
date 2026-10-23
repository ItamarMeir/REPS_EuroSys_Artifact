# Rate-const sender (`-rate_const_gbps`)

Purpose (meeting 2026-10-23, M2): inject at a known constant rate so REPS buffer behavior can be measured below, at, and above capacity without a congestion controller. The existing `-sender_cc_algo constant` fixes a *window*, which is ACK-clocked: above capacity the ACK rate throttles the sender, so the real rate is not the configured one.

## Semantics
- R is the per-source wire rate in Gbps, counting full packet size (`_mtu`, header included) of new data and retransmissions. RTS/control packets are not counted.
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

No RTOs in any cell. Flag absent: identical flow-finish lines to the pre-change binary (tornado NSCC x32, md5 equal).

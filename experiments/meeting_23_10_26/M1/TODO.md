# M1 TODO (deferred; resume after M2/M3 validation)

User request (2026-10-23): after the cwnd check on existing traces, compare NSCC at **native 50% fabric** (every link inherently 200G, not "degraded") against ToR0-degraded and healthy. Expectation: valid-EV draw probability in the 50% runs should look like healthy, because a good CC adapts the rate to the capacity; if the native-200G run looks healthy but ToR0-degraded does not, the gap is the CC failing to adapt on a partial-capacity path, not an inherent effect.

Status:
- Native-200G runs already executed (seed 42, NSCC, B8, tornado 16 MiB, topo `fat_tree_1024_1os_2t_200g_native.topo` = 400g topo with Downlink_speed_Gbps 200, `-linkspeed 200000`, srcs 0-31 event trace). Two variants, default target and `-target_q_delay 4.17`. Max FCT 706.568 us for both (target irrelevant when healthy-like). Raw outputs live in container `m23-dev:/tmp/n200_{t6,t417}.{csv,stdout}` — copy to `M1/data/` (gzip csv) before the container is removed.
- NOT yet analyzed: valid vs random EV share, ECN-marked ACK fraction, cwnd(t) for native-200G vs healthy-400G vs ToR0-degraded (existing `meeting_06_10_26/C1/NSCC/traces`).
- Then root-cause why NSCC does not adapt in ToR0-degraded (plan M1 steps 1-3).

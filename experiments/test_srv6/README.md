# test_srv6 — SRv6 source-routing verification suite

Not a measurement study: a set of smoke and correctness tests for the SRv6 substrate (`-use_srv6`, where the EV indexes a physical path and switches do no hashing). `scripts/run_tests.sh` runs 13 numbered tests (T0-T12) on a k=4 3-tier fabric (16 hosts, a single flow 0 to 8) and, for T10-T12, on K=16 (single flow 0 to 512). Raw output is in `runs/` (`*.out`, one CSV), workloads in `workloads/`.

| Test | What it checks |
|---|---|
| T0, T4 | SRv6 smoke; 4-path baseline FCT |
| T1, T7, T8 | PATH_RR / PATH_RANDOM / PATH_STATIC give the same FCT with and without SRv6 (e.g. 33.72 us for PATH_RR) |
| T2, T3a-c | Pinning EV to path 0 and failing exactly that link stalls the flow; failing a different link does not (33.72 us, baseline) |
| T4a, T4b, T4d | Failing one of four paths slows the flow to 170-241 us |
| T5, T6 | ECMP comparison. T5 (ECMP, path 0 failed) also stalls, so it is weaker evidence than the script's "PASS". T6 shows ECMP+SRv6 tornado finishing at 339.7 us vs 184.5 us for plain ECMP; the script does not flag this |
| T9 | Retransmissions obey SRv6: a 2-path failure still completes (533.8 us) |
| T10-T12 | K=16: all 64 paths reachable; failing path 0 stalls the pinned flow; failing an off-pod link does not |

The "wrong-fail" tests rely on choosing links off both the forward path and the ECMP return path of flow 0 to 8; the comment block at the top of `run_tests.sh` records which links were verified safe. Used to validate SRv6 before exp21 onward.

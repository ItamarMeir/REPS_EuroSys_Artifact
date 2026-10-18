# exp20 — PATH_RR path-count asymmetry on a k=8 fabric

**Question.** exp19 showed that restricting one host to 3 of 4 paths slows that host by about 0.20 slowdown units. Does the same relative restriction (15 of 16 paths) hurt as much on a larger fabric with more path diversity?

**Setup.** Same as [exp19](../exp19_path_rr_asymmetry_v19/) except: `fat_tree_128_1os_3t_400g_paper.topo` (k=8, 128 hosts, 16 paths per pair), tornado N=128, host 0 restricted with `-path_rr_npaths_override "0:15"`. Two conditions x 5 seeds (42-46) = 10 runs (`scripts/01_run_exp20.sh`; its header comment still says 10 seeds). Flags: PATH_RR `src_mod`, NSCC, `-cwnd 155 -q 60 -ecn 12 48 -disable_tor_ecn`, 256 MiB flows.

**Result** (FCT slowdown vs optimum):
- Mean slowdown over all flows is unchanged: 1.0355 (baseline) vs 1.0360 (constrained).
- Host 0 goes 1.036 to 1.063 (+0.027), and flows 1-3 rise by about 0.011. Only 4 of 128 flows change by more than 0.005.
- The effect is about 7x smaller than exp19 (+0.20): with 15 of 16 paths left, losing one costs far less than losing one of four.

**Files.** `scripts/01_run_exp20.sh`, `aggregate_exp20.py`, `plot_exp20_*.py`, `plots/{exp20_fct,exp20_queues,exp20_tor_queues}.png`, `data/`.

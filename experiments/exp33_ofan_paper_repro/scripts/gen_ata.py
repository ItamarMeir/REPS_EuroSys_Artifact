#!/usr/bin/env python3
"""One-shot all-to-all workload: every host sends one flow of <size> bytes to every other host, all starting at t=0.
Wraps htsim/sim/datacenter/connection_matrices/gen_serialn_alltoall.py with conns=groupsize=N, parallel=N-1
(=> single round, no triggers). Flows = N*(N-1).
Usage: gen_ata.py <out.cm> <nodes> <size_bytes> [seed=1]
Constant per-host volume (Fig 5 'const per-host'): size = total_per_host_bytes // (N-1)."""
import os, subprocess, sys
if len(sys.argv) not in (4, 5): sys.exit(__doc__)
out, n, size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
seed = sys.argv[4] if len(sys.argv) == 5 else "1"
gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "htsim", "sim", "datacenter",
                   "connection_matrices", "gen_serialn_alltoall.py")
subprocess.check_call([sys.executable, gen, out, str(n), str(n), str(n), str(n - 1), str(size), "0", seed])

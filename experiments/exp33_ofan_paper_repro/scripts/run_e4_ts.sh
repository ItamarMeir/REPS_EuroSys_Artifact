#!/usr/bin/env bash
# E4 time-series companion: ONE representative seed per (CCA, LB), 432 hosts, same flags as run_e4.sh plus
#   -log_core_queues (A->C queues, 1us), -log_tor_queues (E->A queues, 1us), -log_link (per-packet switch-forward log, used to
#   reconstruct per-port utilisation / queue depth offline), -end 150 (flows finish <~70us; samplers would otherwise run to 20 ms).
# Run inside container ofan-dev; strictly one simulator at a time. Raw logs go to $E4_TS_WORK (container /tmp), are reduced by ts_e4.py to data/e4/ts/<tag>_series.csv, raw deleted.
# usage: run_e4_ts.sh [seed=1]
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"; DC=$R/htsim/sim/datacenter
H=$R/experiments/exp33_ofan_paper_repro; T=$H/data/e4/ts; WK=${E4_TS_WORK:-/tmp/e4_ts_work}; W=$H/workloads; TOPO=$H/topologies/fat_tree_432_1os_3t_800g.topo
S=${1:-1}
lbargs() { case $1 in reps) echo "-load_balancing_algo freezing -paths 65535";; ar) echo "-strat ecmp_ar -load_balancing_algo ecmp";; ofan) echo "-strat ofan -load_balancing_algo ecmp";; esac; }
for cc in ${CCS:-dctcp nscc mswift}; do for lb in ${LBS:-reps ar ofan}; do
  tag=${cc}_${lb}_s$S; d=$WK/$tag; mkdir -p $T; [ -f $T/${tag}_series.csv ] && { echo "[skip] $tag"; continue; }
  rm -rf $d; mkdir -p $d/port $d/link_util   # raw logs on container-local disk (bind-mount file I/O is ~100x slower)
  ( cd $d; timeout 3000 $DC/htsim_uec -tm $W/perm432_4mb_s$S.cm -topo $TOPO -linkspeed 800000 -seed $S -end 150 -connections_mapping \
      -sender_cc_only -disable_tor_ecn -q 193 -ecn 19 19 -sender_cc_algo $cc $(lbargs $lb) \
      -log_core_queues $d/core.csv -log_tor_queues $d/tor.csv -log_link -save_data_folder $d > $d/out.txt 2>&1; echo "rc=$?" >> $d/out.txt )
  python3 $H/scripts/ts_e4.py $d $T/${tag}_series.csv && rm -rf $d
  echo "[done] $tag"
done; done

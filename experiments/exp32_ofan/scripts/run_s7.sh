#!/usr/bin/env bash
# S7: static Agg<->Core link failure smoke (54-host k=6, derangement 4 MiB, nscc, paper buffers). Run in container ofan-dev.
# Failure: -fail_link_time 0.01 1e9 (fail at 10 ns, i.e. before any packet reaches the pipe; recovery 1e9 us = never within -end).
# -fail_link_target <agg> <core> = indices into pipes_nup_nc[agg][core] (AGG/CORE=0 0 default; override via env).
# LinkFailureEvent fails BOTH directions (Agg->Core and Core->Agg pipes). Pipe silently frees packets (no counter): losses are
# derived from the failed link's queue stats (every packet enqueued toward a dead pipe is lost).
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"; DC=$R/htsim/sim/datacenter; E=$R/experiments/exp32_ofan
D=$E/data/${S7_DIR:-s7}; mkdir -p $D
AGG=${S7_AGG:-0}; CORE=${S7_CORE:-0}
TM=$E/workloads/derange54_4mb_s42.cm
TOPO=$DC/topologies/reps/fat_tree_54_1os_3t_400g.topo
COMMON="-tm $TM -topo $TOPO -linkspeed 400000 -seed 42 -end 20000 -connections_mapping -sender_cc_only -disable_tor_ecn -q 193 -ecn 19 19 -sender_cc_algo nscc"
FAIL="-fail_link_time 0.01 1000000000 -fail_link_target $AGG $CORE"
run() { local tag=$1; shift
  [ -f $D/$tag.out ] && { echo "[skip] $tag"; return; }
  local wd; wd=$(mktemp -d); ( cd $wd; timeout 3000 $DC/htsim_uec $COMMON "$@" -log_queue_stats $D/$tag.tsv > $D/$tag.out 2>&1; echo "rc=$?" >> $D/$tag.out )
  echo "[done] $tag"; }
run ofan_fail   -load_balancing_algo ecmp -strat ofan    $FAIL -log_ofan_counts $D/ofan_fail_counts.tsv
run ofan_ok     -load_balancing_algo ecmp -strat ofan    -log_ofan_counts $D/ofan_ok_counts.tsv
run ecmpar_fail -load_balancing_algo ecmp -strat ecmp_ar $FAIL
run reps_fail   -load_balancing_algo freezing -paths 65535 $FAIL
run ecmp_fail   -load_balancing_algo ecmp -strat ecmp_host $FAIL
python3 $E/scripts/s7_analyze.py $D $AGG $CORE | tee $D/summary.txt

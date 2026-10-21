#!/usr/bin/env bash
# V-C part 3: Ofan paper Figs 16/18 - average queue per layer vs time, 1024 hosts, 4 MB inter-pod derangement, no CCA, frozen binary.
# Uses the htsim queue samplers (-log_tor_queues E->A, -log_core_queues A->C, -log_core_downlink_queues C->A first 16 cores), which also
# work for source-routed path_rr (-log_link does not: it logs nothing for source-routed packets, and never logs A->E / E->H).
# -log_queue_stats gives the max queue of all 5 layers. Reduced by ts_vc3.py to data/vc/ts/<tag>_series.csv.
# Run in container ofan-dev. Env: SEEDS("1 2"), VARIANTS("ofan drb drb_hash"), BIN. Two sims in parallel max.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); E=$(dirname "$HERE"); X=$E/../exp33_ofan_paper_repro
BIN=${BIN:-/tmp/frozen/htsim_uec_frozen}; OUT=$E/data/vc; T=$OUT/ts; WK=/tmp/vc3_work; mkdir -p $T $WK
run_one() { st=$1; s=$2; tag=${st}_n1024_s$s; [ -f $T/${tag}_series.csv ] && return
  case $st in ofan) lb="-load_balancing_algo ecmp -strat ofan";; drb) lb="-load_balancing_algo path_rr";; drb_hash) lb="-load_balancing_algo path_rr -path_rr_start_mode srcdst_hash";; esac
  d=$WK/$tag; mkdir -p $d; cd $d
  timeout 3000 $BIN -topo $X/topologies/fat_tree_1024_1os_3t_800g.topo -linkspeed 800000 -end 150 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160 -disable_trim -disable_tor_ecn -ecn 19 19 -q 20000 \
    -tm $OUT/workloads/der1024_4mb_s$s.cm -seed $s $lb -log_tor_queues $d/tor.csv -log_core_queues $d/core.csv -log_core_downlink_queues $d/cdl.csv -log_queue_stats $T/${tag}_qs.tsv > $T/${tag}.out 2>&1
  python3 $E/scripts/ts_vc3.py $d/tor.csv $d/core.csv $d/cdl.csv $T/${tag}_series.csv; echo "done $tag finished=$(grep -c 'finished at' $T/${tag}.out)"; }
export -f run_one; export BIN X OUT T WK E
for s in ${SEEDS:-1 2}; do for st in ${VARIANTS:-ofan drb drb_hash}; do echo "$st $s"; done; done | xargs -P 2 -L1 bash -c 'run_one "$@"' _

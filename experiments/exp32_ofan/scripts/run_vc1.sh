#!/usr/bin/env bash
# V-C part 1: Ofan paper Fig 3 - worst-link overload per stage, 432 hosts, 1 MB inter-pod derangement, no CCA.
# Run INSIDE container ofan-dev with the FROZEN binary:  docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_vc1.sh
# Idempotent. Env: PAR (2), SEEDS ("1 2 3 4 5"), STRATS, BIN.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); E=$(dirname "$HERE"); X=$E/../exp33_ofan_paper_repro
BIN=${BIN:-/tmp/frozen/htsim_uec_frozen}
TOPO=$X/topologies/fat_tree_432_1os_3t_800g.topo
OUT=$E/data/vc; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p $RUNS $WL
SEEDS=${SEEDS:-"1 2 3 4 5"}; PAR=${PAR:-2}
STRATS=${STRATS:-"ofan rr_fixed jsq ar ar_q193 rsq rps reps drb"}
BASE="-topo $TOPO -linkspeed 800000 -end 200000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160 -disable_trim -disable_tor_ecn -ecn 19 19"
sflags() { case $1 in
 ofan)     echo "-q 20000 -load_balancing_algo ecmp -strat ofan";;
 rr_fixed) echo "-q 20000 -load_balancing_algo ecmp -strat ecmp_rr_fixed";;
 jsq)      echo "-q 20000 -load_balancing_algo ecmp -strat ecmp_ar -ar_method exact";;
 ar)       echo "-q 20000 -load_balancing_algo ecmp -strat ecmp_ar";;
 ar_q193)  echo "-q 193 -load_balancing_algo ecmp -strat ecmp_ar";;
 rsq)      echo "-q 20000 -load_balancing_algo ecmp -strat ecmp_random";;
 rps)      echo "-q 20000 -load_balancing_algo path_random";;
 reps)     echo "-q 20000 -load_balancing_algo freezing -paths 65535";;
 drb)      echo "-q 20000 -load_balancing_algo path_rr";;
 drb_hash) echo "-q 20000 -load_balancing_algo path_rr -path_rr_start_mode srcdst_hash";;
 drb_src)  echo "-q 20000 -load_balancing_algo path_rr -path_rr_start_mode src_mod";;
esac; }
J=$OUT/jobs1.txt; : > $J
for s in $SEEDS; do [ -f $WL/der_s$s.cm ] || python3 $E/scripts/gen_derangement.py $WL/der_s$s.cm 432 36 1048576 $s >/dev/null
  for st in $STRATS; do [ -f $RUNS/${st}_s$s.tsv ] || echo "${st}_s$s $st $s" >> $J; done; done
run_one() { tag=$1; st=$2; s=$3; d=$(mktemp -d); cd $d
  cmd="$BASE -tm $WL/der_s$s.cm -seed $s $(sflags $st)"; echo "$cmd" > $RUNS/$tag.cmd
  ( time timeout 3000 $BIN $cmd -log_queue_stats $RUNS/$tag.tmp > $RUNS/$tag.out 2>&1 ) 2> $RUNS/$tag.time
  mv $RUNS/$tag.tmp $RUNS/$tag.tsv 2>/dev/null; echo "done $tag"; cd /; rm -rf $d; }
export -f run_one sflags; export BASE BIN RUNS WL
xargs -P $PAR -L1 bash -c 'run_one "$@"' _ < $J

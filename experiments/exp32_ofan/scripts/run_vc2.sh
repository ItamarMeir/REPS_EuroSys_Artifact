#!/usr/bin/env bash
# V-C part 2: Ofan paper Fig 17 - ratio max queue DRB(path_rr) / Ofan vs hosts; 4 MB inter-pod derangement, no CCA, frozen binary.
# Run in container ofan-dev. Env: PAR(2) SEEDS("1 2 3 4 5") SIZES("128 250 432 686 1024") BIN
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); E=$(dirname "$HERE"); X=$E/../exp33_ofan_paper_repro
BIN=${BIN:-/tmp/frozen/htsim_uec_frozen}; OUT=$E/data/vc; RUNS=$OUT/runs2; WL=$OUT/workloads; mkdir -p $RUNS $WL
SEEDS=${SEEDS:-"1 2 3 4 5"}; SIZES=${SIZES:-"128 250 432 686 1024"}; PAR=${PAR:-2}
declare -A POD=([128]=16 [250]=25 [432]=36 [686]=49 [1024]=64)
J=$OUT/jobs2.txt; : > $J
for n in $SIZES; do for s in $SEEDS; do
  [ -f $WL/der${n}_4mb_s$s.cm ] || python3 $E/scripts/gen_derangement.py $WL/der${n}_4mb_s$s.cm $n ${POD[$n]} 4194304 $s >/dev/null
  for st in ${VARIANTS:-ofan drb}; do [ -f $RUNS/${st}_n${n}_s$s.tsv ] || echo "${st}_n${n}_s$s $st $n $s" >> $J; done; done; done
run_one() { tag=$1; st=$2; n=$3; s=$4; d=$(mktemp -d); cd $d
  case $st in ofan) lb="-load_balancing_algo ecmp -strat ofan";; drb) lb="-load_balancing_algo path_rr";; drb_hash) lb="-load_balancing_algo path_rr -path_rr_start_mode srcdst_hash";; drb_src) lb="-load_balancing_algo path_rr -path_rr_start_mode src_mod";; esac
  cmd="-topo $X/topologies/fat_tree_${n}_1os_3t_800g.topo -linkspeed 800000 -end 200000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160 -disable_trim -disable_tor_ecn -ecn 19 19 -q 20000 -tm $WL/der${n}_4mb_s$s.cm -seed $s $lb"
  echo "$cmd" > $RUNS/$tag.cmd
  ( time timeout 3000 $BIN $cmd -log_queue_stats $RUNS/$tag.tmp > $RUNS/$tag.out 2>&1 ) 2> $RUNS/$tag.time
  mv $RUNS/$tag.tmp $RUNS/$tag.tsv 2>/dev/null; echo "done $tag"; cd /; rm -rf $d; }
export -f run_one; export BIN RUNS WL X
xargs -P $PAR -L1 bash -c 'run_one "$@"' _ < $J

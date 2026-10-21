#!/usr/bin/env bash
# V-C DRB-faithfulness re-run (adds -path_rr_start_mode random / -path_rr_order agg_fast variants).
# Usage (inside container ofan-dev): run_vc_drb.sh <part: 1|2|3>   Env: OUT (/tmp/vcdrb; must contain workloads/), BIN (/tmp/drb/htsim_uec),
#   SEEDS, SIZES, VARIANTS (default: drb_rand drb_af drb_af_rand), PAR (2).  Output: $OUT/runs (part1), $OUT/runs2 (part2), $OUT/ts (part3).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); E=$(dirname "$HERE"); X=$E/../exp33_ofan_paper_repro
BIN=${BIN:-/tmp/drb/htsim_uec}; OUT=${OUT:-/tmp/vcdrb}; WL=$OUT/workloads; PAR=${PAR:-2}; PART=${1:-1}
VARIANTS=${VARIANTS:-"drb_rand drb_af drb_af_rand"}
declare -A POD=([128]=16 [250]=25 [432]=36 [686]=49 [1024]=64)
lb() { case $1 in
 ofan) echo "-load_balancing_algo ecmp -strat ofan";;
 drb) echo "-load_balancing_algo path_rr";;
 drb_hash) echo "-load_balancing_algo path_rr -path_rr_start_mode srcdst_hash";;
 drb_rand) echo "-load_balancing_algo path_rr -path_rr_start_mode random";;
 drb_af) echo "-load_balancing_algo path_rr -path_rr_order agg_fast";;
 drb_af_rand) echo "-load_balancing_algo path_rr -path_rr_order agg_fast -path_rr_start_mode random";;
 drb_af_hash) echo "-load_balancing_algo path_rr -path_rr_order agg_fast -path_rr_start_mode srcdst_hash";;
esac; }
COMMON="-linkspeed 800000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160 -disable_trim -disable_tor_ecn -ecn 19 19 -q 20000"
J=$OUT/jobs_part$PART.txt; : > $J
case $PART in
1) RUNS=$OUT/runs; mkdir -p $RUNS; for s in ${SEEDS:-1 2 3 4 5}; do for st in $VARIANTS; do [ -f $RUNS/${st}_s$s.tsv ] || echo "${st}_s$s $st 432 $s 1mb" >> $J; done; done;;
2) RUNS=$OUT/runs2; mkdir -p $RUNS; for n in ${SIZES:-128 250 432 686 1024}; do for s in ${SEEDS:-1 2 3}; do for st in $VARIANTS; do [ -f $RUNS/${st}_n${n}_s$s.tsv ] || echo "${st}_n${n}_s$s $st $n $s 4mb" >> $J; done; done; done;;
3) RUNS=$OUT/ts; mkdir -p $RUNS; for s in ${SEEDS:-1 2}; do for st in $VARIANTS; do [ -f $RUNS/${st}_n1024_s$s''_series.csv ] || echo "${st}_n1024_s$s $st 1024 $s 4mb" >> $J; done; done;;
esac
export -f lb; export BIN OUT WL RUNS E X COMMON PART
declare -p POD >/dev/null
run_one() { tag=$1; st=$2; n=$3; s=$4; sz=$5
  case $n in 128) pod=16;; 250) pod=25;; 432) pod=36;; 686) pod=49;; 1024) pod=64;; esac
  if [ $PART = 1 ]; then cm=$WL/der_s$s.cm; else cm=$WL/der${n}_4mb_s$s.cm; fi
  [ -f $cm ] || python3 $E/scripts/gen_derangement.py $cm $n $pod $([ $sz = 1mb ] && echo 1048576 || echo 4194304) $s >/dev/null
  d=$(mktemp -d); cd $d
  base="-topo $X/topologies/fat_tree_${n}_1os_3t_800g.topo $COMMON -tm $cm -seed $s $(lb $st)"
  if [ $PART = 3 ]; then
    timeout 3000 $BIN $base -end 150 -log_tor_queues $d/tor.csv -log_core_queues $d/core.csv -log_core_downlink_queues $d/cdl.csv -log_queue_stats $RUNS/${tag}_qs.tsv > $RUNS/$tag.out 2>&1
    python3 $E/scripts/ts_vc3.py $d/tor.csv $d/core.csv $d/cdl.csv $RUNS/${tag}_series.csv
  else
    echo "$base" > $RUNS/$tag.cmd
    timeout 3000 $BIN $base -end 200000 -log_queue_stats $RUNS/$tag.tmp > $RUNS/$tag.out 2>&1
    mv $RUNS/$tag.tmp $RUNS/$tag.tsv 2>/dev/null
  fi
  echo "done $tag finished=$(grep -c 'finished at' $RUNS/$tag.out)"; cd /; rm -rf $d; }
export -f run_one
xargs -P $PAR -L1 bash -c 'run_one "$@"' _ < $J

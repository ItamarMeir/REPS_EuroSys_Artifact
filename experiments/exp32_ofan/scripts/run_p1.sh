#!/usr/bin/env bash
# P1: routing-convergence gates G3/G4/G5 for Ofan vs ecmp_ar / ecmp_host / ecmp_rr / host REPS. Run INSIDE container ofan-dev
#   docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_p1.sh [minrtt|g3|g5|det|all]   (default all)
# Idempotent: a job is skipped when data/p1/<tag>.out exists. Failure = Agg0<->Core0 (both directions), never recovers.
# Tag: <strat>_G<G>_f<fail_us>  strat in ofan ecmp_ar ecmp_host ecmp_rr reps. Determinism repeat: <tag>_rep2.
# minRTT: single 4096 B inter-pod flow FCT (sender sees completion at ACK) -> data/p1/minrtt.txt; G5 uses k*minRTT.
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"; DC=$R/htsim/sim/datacenter; E=$R/experiments/exp32_ofan
D=$E/data/p1; mkdir -p $D
TM=$E/workloads/derange54_4mb_s42.cm
TOPO=$DC/topologies/reps/fat_tree_54_1os_3t_400g.topo
COMMON="-topo $TOPO -linkspeed 400000 -seed 42 -end 20000 -connections_mapping -sender_cc_only -disable_tor_ecn -q 193 -ecn 19 19 -sender_cc_algo nscc"
NEVER=1000000000
declare -A SARGS=( [ofan]="-strat ofan -load_balancing_algo ecmp" [ecmp_ar]="-strat ecmp_ar -load_balancing_algo ecmp" \
  [ecmp_host]="-strat ecmp_host -load_balancing_algo ecmp" [ecmp_rr]="-strat ecmp_rr -load_balancing_algo ecmp" \
  [reps]="-load_balancing_algo freezing -paths 65535" )
JOBS=$D/jobs.txt; : > $JOBS
job() { # strat G fail_us suffix [extra flags...]   -> line "tag|strat args|G|fail|extra"
  local s=$1 g=$2 f=$3 suf=$4; shift 4
  local tag=${s}_G${g}_f${f}${suf}
  [ -f $D/$tag.out ] && return
  echo "$tag|${SARGS[$s]}|$g|$f|$*" >> $JOBS
}
runjob() { IFS='|' read -r tag sargs g f extra <<< "$1"
  extra=${extra//@D@/$D}; local FARGS="-fail_link_time $f $NEVER -fail_link_target 0 0"; [ "$f" = none ] && FARGS=""
  local wd; wd=$(mktemp -d)
  ( cd $wd; timeout 3000 $DC/htsim_uec -tm $TM $COMMON $sargs $FARGS       -routing_convergence_us $g $extra -log_queue_stats $D/$tag.tsv > $D/$tag.out 2>&1; echo "rc=$?" >> $D/$tag.out ); rm -rf $wd
  echo "[done] $tag"; }
export -f runjob; export D DC COMMON TM NEVER
what=${1:-all}
if [ "$what" = minrtt ] || [ "$what" = all ]; then
  if [ ! -f $D/minrtt.txt ]; then
    printf 'Nodes 54\nConnections 1\n0->29 id 1 start 0 size 4096\n' > $D/single.cm
    wd=$(mktemp -d); ( cd $wd; $DC/htsim_uec -tm $D/single.cm $COMMON ${SARGS[ofan]} > $D/minrtt.out 2>&1 ); rm -rf $wd
    grep -oE "finished at [0-9.]+" $D/minrtt.out | awk '{print $3}' > $D/minrtt.txt
  fi
  echo "minRTT_us=$(cat $D/minrtt.txt)"
fi
[ "$what" = minrtt ] && exit 0
MINRTT=$(cat $D/minrtt.txt)
STR="ofan ecmp_ar ecmp_host ecmp_rr reps"
if [ "$what" = g3 ] || [ "$what" = all ]; then
  for s in $STR; do
    job $s 50 20 ""; job $s 0 0.01 ""; job $s $NEVER 0.01 ""; job $s 20 20 ""
  done
  job ofan 50 20 "_check" -routing_check   # same config + brute-force reference check (extra events only)
fi
if [ "$what" = g5 ] || [ "$what" = all ]; then
  for s in ofan ecmp_ar ecmp_host reps; do
    job $s 0 0.01 ""; job $s 0 20 ""   # G=0 mid-run (instant global knowledge; reference only, see OFAN_ARCHITECTURE)
    for k in 1 2 5 10; do job $s $(awk -v k=$k -v r=$MINRTT 'BEGIN{printf "%.3f", k*r}') 20 ""; done
    job $s $NEVER 20 ""
  done
fi
if [ "$what" = base ] || [ "$what" = all ]; then for s in $STR; do job $s 0 none ""; done; fi   # healthy reference (no failure; G irrelevant)
if [ "$what" = g4 ] || [ "$what" = all ]; then   # G4: ofan with per-(switch,key,type) counts, G=0 static failure (also G=50 mid-run for reference)
  job ofan 0 0.01 "_counts" -log_ofan_counts @D@/ofan_G0_f0.01_ofancounts.tsv
  job ofan 50 20 "_counts" -log_ofan_counts @D@/ofan_G50_f20_ofancounts.tsv
fi
if [ "$what" = det ] || [ "$what" = all ]; then
  job ofan 50 20 "_rep2"; job ofan 50 20 "_rep3"
fi
sort -u $JOBS -o $JOBS
echo "$(wc -l < $JOBS) jobs"
xargs -a $JOBS -d '\n' -P ${P1_PAR:-7} -I{} bash -c 'runjob "$1"' _ {}

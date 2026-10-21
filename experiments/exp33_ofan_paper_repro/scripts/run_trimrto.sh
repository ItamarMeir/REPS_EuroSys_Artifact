#!/usr/bin/env bash
# E5: (A) trimming-off checks for Fig 12 (E4 cells + -disable_trim; small-buffer stress with/without trim)
#     (B) REPS freezing/RTO hypothesis for Fig 7a: 16/64 MB permutation, infinite buffer, no CCA, -min_rto sweep.
# Run INSIDE container ofan-dev: docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_trimrto.sh
# Idempotent (skips tags whose .out ends with rc=). Env: PART (a|s|r16|r64|singles|all), PAR (default 2), SEEDS_A, RTOS16, RTOS64, SEEDS_R.
# Binary: private copy of /tmp/frozen/htsim_uec_v2.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); EXP=$(dirname "$HERE"); REPO=$(cd "$EXP/../.." && pwd)
BIN=${BIN:-/tmp/e5bin/htsim_uec_v2}; [ -x $BIN ] || { mkdir -p /tmp/e5bin; cp /tmp/frozen/htsim_uec_v2 $BIN; }
OUT=${OUT:-$EXP/data/trimrto}; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p $RUNS $WL
GEN=$REPO/experiments/exp32_ofan/scripts/gen_derangement.py
PART=${PART:-all}; PAR=${PAR:-2}
TOPO=$EXP/topologies/fat_tree_432_1os_3t_800g.topo
SEEDS_A=${SEEDS_A:-"1 2 3 4 5"}; SEEDS_S=${SEEDS_S:-"1 2 3"}; SEEDS_R=${SEEDS_R:-"1"}
RTOS16=${RTOS16:-"0 100 50 20 10 5"}; RTOS64=${RTOS64:-"0 50 10"}   # 0 = default (no -min_rto flag)
lb() { case $1 in reps) echo "-load_balancing_algo freezing -paths 65535";; ar) echo "-strat ecmp_ar -load_balancing_algo ecmp";; ofan) echo "-strat ofan -load_balancing_algo ecmp";; esac; }
lb_r() { case $1 in reps) echo "-load_balancing_algo freezing -strat ecmp_host -paths 65535";; ar) echo "-load_balancing_algo ecmp -strat ecmp_ar";; ofan) echo "-load_balancing_algo ecmp -strat ofan";; esac; }
J=$(mktemp)
# job line: tag | tm | flags...
for s in $SEEDS_A $SEEDS_S $SEEDS_R; do [ -f $EXP/workloads/perm432_4mb_s$s.cm ] || python3 $GEN $EXP/workloads/perm432_4mb_s$s.cm 432 36 4194304 $s perm >/dev/null; done
for mb in 16 64; do B=$((mb*1048576)); for s in $SEEDS_R; do [ -f $WL/perm_${B}_s$s.cm ] || python3 $GEN $WL/perm_${B}_s$s.cm 432 36 $B $s perm >/dev/null; done
  [ -f $WL/single_$B.cm ] || printf 'Nodes 432\nConnections 1\n0->216 id 1 start 0 size %d\n' $B > $WL/single_$B.cm; done
[ -f $EXP/workloads/single432_4mb.cm ] || printf 'Nodes 432\nConnections 1\n0->216 id 1 start 0 size 4194304\n' > $EXP/workloads/single432_4mb.cm
CA="-linkspeed 800000 -connections_mapping -sender_cc_only -disable_tor_ecn"
if [[ $PART == all || $PART == a ]]; then
  for cc in nscc dctcp; do for l in reps ar ofan; do for s in $SEEDS_A; do
    echo "a_${cc}_${l}_s$s $EXP/workloads/perm432_4mb_s$s.cm 20000 $s $CA -q 193 -ecn 19 19 -sender_cc_algo $cc $(lb $l) -disable_trim" | sed "s/ *$//" >> $J; done; done; done
fi
if [[ $PART == all || $PART == s ]]; then
  for l in reps ar ofan; do for s in $SEEDS_S; do for t in trim notrim; do x=""; [ $t = notrim ] && x="-disable_trim"
    echo "s_nscc_${l}_${t}_s$s $EXP/workloads/perm432_4mb_s$s.cm 20000 $s $CA -q 40 -ecn 5 10 -sender_cc_algo nscc $(lb $l) $x" | sed "s/ *$//" >> $J; done; done; done
fi
# (B): constant CCA, cwnd 1000 pkts (=4.16 MB, same as E2), infinite buffer q 20000, mtu 4160 (E2 flag set), -disable_trim
CR="$CA -sender_cc_algo constant -cwnd 1000 -mtu 4160 -ecn 19 19 -q 20000 -disable_trim"
rto_job() { mb=$1; r=$2; l=$3; s=$4; B=$((mb*1048576)); x=""; [ $r != 0 ] && x="-min_rto $r"
  echo "r_${l}_${mb}mb_rto${r}_s$s $WL/perm_${B}_s$s.cm 200000 $s $CR $(lb_r $l) $x" | sed "s/ *$//" >> $J; }
if [[ $PART == all || $PART == singles ]]; then
  for mb in 16 64; do B=$((mb*1048576)); echo "single_${mb}mb $WL/single_$B.cm 200000 1 $CR $(lb_r reps)" | sed "s/ *$//" >> $J; done
  echo "single_4mb_nscc $EXP/workloads/single432_4mb.cm 20000 1 $CA -q 193 -ecn 19 19 -sender_cc_algo nscc $(lb reps) -disable_trim" | sed "s/ *$//" >> $J
fi
if [[ $PART == all || $PART == r16 ]]; then for s in $SEEDS_R; do for r in $RTOS16; do for l in reps ofan ar; do rto_job 16 $r $l $s; done; done; done; fi
if [[ $PART == all || $PART == r64 ]]; then for s in $SEEDS_R; do for r in $RTOS64; do for l in reps ofan ar; do rto_job 64 $r $l $s; done; done; done; fi
export BIN RUNS TOPO JTIMEOUT
one() { tag=$1; tm=$2; end=$3; seed=$4; shift 4
  [ -f $RUNS/$tag.out ] && grep -q '^rc=' $RUNS/$tag.out && { echo "[skip] $tag"; return; }
  wd=$(mktemp -d); t0=$(date +%s)
  ( cd $wd; echo "$* -tm $tm -topo $TOPO -seed $seed -end $end" > $RUNS/$tag.cmd
    timeout ${JTIMEOUT:-5400} $BIN "$@" -tm $tm -topo $TOPO -seed $seed -end $end -log_queue_stats $RUNS/$tag.tsv > $RUNS/$tag.out 2>&1; echo "rc=$?" >> $RUNS/$tag.out ); rm -rf $wd
  echo "[done] $tag $(( $(date +%s)-t0 ))s"; }
export -f one
xargs -P $PAR -L1 bash -c 'one "$@"' _ < $J
rm -f $J

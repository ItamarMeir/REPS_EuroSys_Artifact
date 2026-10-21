#!/usr/bin/env bash
# E3: Ofan paper (arXiv 2610.07230) Fig 4 and Fig 5 repro. Run INSIDE container ofan-dev:
#   docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_e3.sh <PART> [extra env]
# PART: fig4 | fig5a | fig5b | fig5c | smoke
# Env: PAR (parallel sims, default 2; keep <=2 on the shared box), SEEDS (default "1 2 3 4 5"), NS (fig5 node counts),
#      ALGOS (fig4/fig5 algo list), SIZE_PF (fig5b per-flow bytes, default 262144), HOST_BYTES (fig5c per-host bytes, default 33554432)
# Idempotent: a run is skipped when <tag>.done exists. Raw runs in data/e3/runs/<tag>.{out,tsv,cmd,time,done}.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); H=$(dirname "$HERE"); E=$(dirname "$H")
BIN=$(cd "$E/../htsim/sim/datacenter" && pwd)/htsim_uec
GD=$E/exp32_ofan/scripts/gen_derangement.py
OUT=$H/data/e3; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p "$RUNS" "$WL"
PAR=${PAR:-2}; SEEDS=${SEEDS:-"1 2 3 4 5"}
declare -A POD=([16]=4 [54]=9 [128]=16 [250]=25 [432]=36 [1024]=64)

# NO-CCA: constant window of 400 packets (never window-limited at 800G, ~1.66 MB). Paper fn.6: practically infinite buffers
# (-q 20000, 83 MB/port, no trim). ECN 19 19 pkts (only REPS reacts). -disable_tor_ecn for all except reps_dl (sensitivity).
COMMON="-linkspeed 800000 -mtu 4160 -end 400000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 400 -disable_trim -ecn 19 19"
aflags() { case $1 in
 rr)      echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ecmp_rr_fixed";;
 jsq)     echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ecmp_ar -ar_method exact";;
 rsq)     echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ecmp_random";;
 rps)     echo "-disable_tor_ecn -q 20000 -load_balancing_algo path_random";;
 p2c)     echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ecmp_p2c";;
 reps)    echo "-disable_tor_ecn -q 20000 -load_balancing_algo freezing -paths 65535";;
 reps_dl) echo "-q 20000 -load_balancing_algo freezing -paths 65535";;
 ar20000) echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ecmp_ar";;
 ar193)   echo "-disable_tor_ecn -q 193 -load_balancing_algo ecmp -strat ecmp_ar";;
 drb)     echo "-disable_tor_ecn -q 20000 -load_balancing_algo path_rr";;
 drb_src) echo "-disable_tor_ecn -q 20000 -load_balancing_algo path_rr -path_rr_start_mode src_mod";;
 drb_hash) echo "-disable_tor_ecn -q 20000 -load_balancing_algo path_rr -path_rr_start_mode srcdst_hash";;
 ofan)    echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ofan";;
 single)  echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp";;
esac; }

# workload files: perm_N<n>_s<seed>_<bytes>.cm ; ata_N<n>_<bytes>.cm ; single_N<n>_<bytes>.cm
mk_perm()   { f=$WL/perm_N$1_s$2_$3.cm;   [ -f $f ] || python3 $GD $f $1 ${POD[$1]} $3 $2 perm >/dev/null; echo $f; }
mk_ata()    { f=$WL/ata_N$1_$2.cm;        [ -f $f ] || python3 $H/scripts/gen_ata.py $f $1 $2 >/dev/null; echo $f; }
mk_single() { f=$WL/single_N$1_$2.cm;     [ -f $f ] || printf 'Nodes %d\nConnections 1\n0->%d id 1 start 0 size %d\n' $1 $(($1/2)) $2 > $f; echo $f; }

one() { # tag algo N seed cmfile
  tag=$1; algo=$2; n=$3; seed=$4; cm=$5
  [ -f "$RUNS/$tag.done" ] && return 0
  topo=$H/topologies/fat_tree_${n}_1os_3t_800g.topo
  cmd="-tm $cm -topo $topo -seed $seed $COMMON $(aflags $algo)"
  echo "$cmd" > "$RUNS/$tag.cmd"
  d=$(mktemp -d); cd "$d"
  python3 $H/scripts/timed.py "$RUNS/$tag.out" "$BIN" $cmd -log_queue_stats "$RUNS/$tag.tsv" 2> "$RUNS/$tag.time"
  touch "$RUNS/$tag.done"; echo "done $tag $(cat $RUNS/$tag.time)"; cd /; rm -rf "$d"; return 0
}
export -f one aflags; export H BIN RUNS COMMON

jobs=$(mktemp); : > $jobs
add() { echo "$*" >> $jobs; }     # tag algo N seed cm
PART=${1:-fig4}
case $PART in
 smoke) ALGOS=${ALGOS:-"rr jsq rsq rps p2c reps ar20000 ar193 drb ofan single"}; N=${N:-54}; for a in $ALGOS; do
          add smoke__${a}__N${N}__s1 $a $N 1 $(mk_perm $N 1 1048576); done;;
 fig4)  ALGOS=${ALGOS:-"rr jsq rsq rps p2c reps reps_dl ar20000 ar193 drb ofan"}; N=432; for a in $ALGOS; do for s in $SEEDS; do
          add fig4__${a}__N${N}__s$s $a $N $s $(mk_perm $N $s 1048576); done; done
        add fig4__single__N${N}__s1 single $N 1 $(mk_single $N 1048576);;
 fig5a) ALGOS=${ALGOS:-"reps ar20000 ar193 ofan"}; NS=${NS:-"16 54 128 250 432 1024"}; for N in $NS; do for a in $ALGOS; do for s in ${SEEDS_BIG:-$SEEDS}; do
          add fig5a__${a}__N${N}__s$s $a $N $s $(mk_perm $N $s 1048576); done; done
          add fig5a__single__N${N}__s1 single $N 1 $(mk_single $N 1048576); done;;
 fig5b) ALGOS=${ALGOS:-"reps ar20000 ar193 ofan"}; NS=${NS:-"16 54 128"}; SEEDS_ATA=${SEEDS_ATA:-"1 2 3"}; SZ=${SIZE_PF:-262144}; for N in $NS; do for a in $ALGOS; do for s in $SEEDS_ATA; do
          add fig5b__${a}__N${N}__s$s $a $N $s $(mk_ata $N $SZ); done; done
          add fig5b__single__N${N}__s1 single $N 1 $(mk_single $N $((SZ*(N-1)))); done;;
 fig5c) ALGOS=${ALGOS:-"reps ar20000 ar193 ofan"}; NS=${NS:-"16 54 128"}; SEEDS_ATA=${SEEDS_ATA:-"1 2 3"}; HB=${HOST_BYTES:-33554432}; for N in $NS; do SZ=$((HB/(N-1))); for a in $ALGOS; do for s in $SEEDS_ATA; do
          add fig5c__${a}__N${N}__s$s $a $N $s $(mk_ata $N $SZ); done; done
          add fig5c__single__N${N}__s1 single $N 1 $(mk_single $N $((SZ*(N-1)))); done;;
esac
# note: ata workloads are seed-independent (one-shot all-to-all); the sim seed varies hashing/random choices only.
xargs -P "$PAR" -L1 bash -c 'one "$@"' _ < $jobs
rm -f $jobs

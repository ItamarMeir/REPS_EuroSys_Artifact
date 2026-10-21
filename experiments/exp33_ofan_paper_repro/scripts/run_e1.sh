#!/usr/bin/env bash
# E1: Ofan paper (arXiv 2610.07230) Fig 1 -- max utilisation / max queue / CCT vs offered load, NO congestion control.
# Run INSIDE container ofan-dev:  docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_e1.sh
# Idempotent (skips runs whose .tsv exists). Env: PAR (default 2), SEEDS (default "1 2 3 4 5"), RHOS, STRATS.
# Load rho is emulated by pacing each source at rho x line rate (-linkspeed 800000*rho; topology links stay 800G).
# NO-CCA: constant CC, huge window. ECN thresholds on (REPS needs marks); -disable_tor_ecn for ALL strategies (project
# rule for -sender_cc_only; harmless: E->H never queues because every host receives exactly one flow at <= line rate).
# reps_dl (optional, STRATS=reps_dl): REPS WITHOUT -disable_tor_ecn.
# ar_q20000: AR comparator relative to maxsize with -q 20000 (quantisation collapses to ~random);
# ar_q193 : AR with paper-like 193-pkt (~800 KB) maxsize so the quantised comparator is meaningful.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); EXP=$(dirname "$HERE"); ROOT=$(cd "$EXP/../.." && pwd)
BIN=$ROOT/htsim/sim/datacenter/htsim_uec
TOPO=$EXP/topologies/fat_tree_432_1os_3t_800g.topo
OUT=$EXP/data/e1; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p "$RUNS" "$WL"
NODES=432; POD=36; SIZE=1048576
SEEDS=${SEEDS:-"1 2 3 4 5"}; RHOS=${RHOS:-"0.8 0.85 0.9 0.95 0.98 1.0"}; PAR=${PAR:-2}
STRATS=${STRATS:-"ofan ar_q20000 ar_q193 reps"}
BASE="-topo $TOPO -end 200000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -mtu 4160 -disable_trim -ecn 19 19"
sflags() { case $1 in  # $1=strategy
 ofan)      echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ofan";;
 ar_q20000) echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ecmp_ar";;
 ar_q193)   echo "-disable_tor_ecn -q 193 -load_balancing_algo ecmp -strat ecmp_ar";;
 reps)      echo "-disable_tor_ecn -q 20000 -load_balancing_algo freezing -strat ecmp_host -paths 65535";;
 reps_dl)   echo "-q 20000 -load_balancing_algo freezing -strat ecmp_host -paths 65535";;  # sensitivity: ECN also on ToR downlinks (no -disable_tor_ecn)
 single)    echo "-disable_tor_ecn -q 20000 -load_balancing_algo ecmp -strat ofan";;
esac; }
jobs_list=$OUT/jobs.txt; : > "$jobs_list"
for s in $SEEDS; do
  [ -f "$WL/perm_s$s.cm" ] || python3 "$HERE/../../exp32_ofan/scripts/gen_derangement.py" "$WL/perm_s$s.cm" $NODES $POD $SIZE $s perm >/dev/null
done
printf 'Nodes %d\nConnections 1\n0->%d id 1 start 0 size %d\n' $NODES $((NODES/2)) $SIZE > "$WL/single.cm"
for r in $RHOS; do
  [ -f "$RUNS/single__rho$r.tsv" ] || echo "single__rho$r single $r 1 $WL/single.cm" >> "$jobs_list"
  for st in $STRATS; do for s in $SEEDS; do
    [ -f "$RUNS/${st}__rho${r}__s$s.tsv" ] || echo "${st}__rho${r}__s$s $st $r $s $WL/perm_s$s.cm" >> "$jobs_list"
  done; done
done
run_one() {
  tag=$1; st=$2; r=$3; seed=$4; wl=$5
  ls=$(python3 -c "print(800000*$r)")
  cmd="$BASE -tm $wl -linkspeed $ls -seed $seed $(sflags $st)"
  d=$(mktemp -d); cd "$d"; echo "$cmd" > "$RUNS/$tag.cmd"
  ( time timeout 3000 "$BIN" $cmd -log_queue_stats "$RUNS/$tag.tmp.tsv" > "$RUNS/$tag.out" 2>&1 ) 2> "$RUNS/$tag.time"
  mv "$RUNS/$tag.tmp.tsv" "$RUNS/$tag.tsv" 2>/dev/null; echo "done $tag"; cd /; rm -rf "$d"
}
export -f run_one sflags; export BASE BIN RUNS TOPO
xargs -P "$PAR" -L1 bash -c 'run_one "$@"' _ < "$jobs_list"
python3 "$HERE/aggregate_e1.py" "$OUT"

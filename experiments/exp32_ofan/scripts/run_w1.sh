#!/usr/bin/env bash
# W1: paced no-CCA discriminating test for the static-failure imbalance (Agg0<->Core0 dead, G=0, never recovers).
# Run INSIDE container ofan-dev:  docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_w1.sh
# Env: BIN (default frozen v2 binary), STRATS ("ofan"), RHOS, SIZES (bytes), PAR (default 2), OUT.
# rho emulated by pacing: -linkspeed 400000*rho; constant CC, huge window, -q 20000 -disable_trim (no CCA, no trimming).
# -sender_cc_only is used, so -disable_tor_ecn is mandatory (project rule).
# Idempotent: skips runs whose .tsv exists. Predictions: equal-per-port overloads at rho~2/3, weighted rho_max~8/9.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); E=$(dirname "$HERE"); ROOT=$(cd "$E/../.." && pwd)
BIN=${BIN:-/tmp/frozen/htsim_uec_v2}
TOPO=$ROOT/htsim/sim/datacenter/topologies/reps/fat_tree_54_1os_3t_400g.topo
OUT=${OUT:-$E/data/w1}; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p "$RUNS" "$WL"
STRATS=${STRATS:-"ofan"}; RHOS=${RHOS:-"0.5 0.6 0.65 0.7 0.8 0.85 0.9"}; SIZES=${SIZES:-"1048576 4194304"}; PAR=${PAR:-2}
BASE="-topo $TOPO -end 20000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 4000 -disable_trim -ecn 19 19 -disable_tor_ecn -q 20000 -seed 42 -load_balancing_algo ecmp"
for sz in $SIZES; do [ -f "$WL/d54_$sz.cm" ] || python3 "$E/scripts/gen_derangement.py" "$WL/d54_$sz.cm" 54 9 $sz 42 >/dev/null; done
jobs_list=$OUT/jobs.txt; : > "$jobs_list"
for st in $STRATS; do for sz in $SIZES; do for r in $RHOS; do for f in fail none; do
  tag="${st}__${f}__sz${sz}__rho${r}"; [ -f "$RUNS/$tag.tsv" ] || echo "$tag $st $f $sz $r" >> "$jobs_list"
done; done; done; done
run_one() {
  tag=$1; st=$2; f=$3; sz=$4; r=$5
  ls=$(python3 -c "print(400000*$r)")
  fa=""; [ "$f" = fail ] && fa="-fail_link_time 0.01 1000000000 -fail_link_target 0 0 -routing_convergence_us 0"
  [ "$f" = none ] && [ "$st" = ofan_weighted ] && fa="-routing_convergence_us 0"
  cmd="$BASE -tm $WL/d54_$sz.cm -linkspeed $ls -strat $st $fa"
  d=$(mktemp -d); cd "$d"; echo "$cmd" > "$RUNS/$tag.cmd"
  timeout 3000 "$BIN" $cmd -log_queue_stats "$RUNS/$tag.tmp.tsv" > "$RUNS/$tag.out" 2>&1
  mv "$RUNS/$tag.tmp.tsv" "$RUNS/$tag.tsv" 2>/dev/null; echo "done $tag"; cd /; rm -rf "$d"
}
export -f run_one; export BASE BIN RUNS WL
xargs -P "$PAR" -L1 bash -c 'run_one "$@"' _ < "$jobs_list"

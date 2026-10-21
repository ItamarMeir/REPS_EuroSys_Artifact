#!/usr/bin/env bash
# E6: Ofan paper Fig 9 -- CCT increase under random link failures, plain Ofan vs weighted Ofan vs REPS/AR/JSQ.
# Run INSIDE container ofan-dev:  docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_fig9.sh
# Env: BIN (default /tmp/frozen/htsim_uec_w2), PS (failure probabilities in %), SEEDS, STRATS, PAR (default 2).
# Instance = (p, seed): random cut cables (fig9_instance.py), inter-pod permutation 1 MB (432 hosts, 800G), every host paced
# at rho_max (fluid equal-share-per-valid-path); no CCA (constant cwnd 400), -q 20000 -disable_trim (E3 setup); failure
# known from t=0 (-routing_convergence_us 0) for ALL strategies. Lower bounds: single healthy flow at rho=1 (LB1) and at rho_max.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); EXP=$(dirname "$HERE")
BIN=${BIN:-/tmp/frozen/htsim_uec_w2}
TOPO=$EXP/topologies/fat_tree_432_1os_3t_800g.topo
OUT=${OUT:-$EXP/data/e6}; RUNS=$OUT/runs; INST=$OUT/inst; mkdir -p "$RUNS" "$INST"
PS=${PS:-"0 0.5 1 1.5 2"}; SEEDS=${SEEDS:-"1 2 3 4 5 6 7 8 9 10"}; PAR=${PAR:-2}
STRATS=${STRATS:-"ofan ofan_weighted jsq ar193 reps"}
COMMON="-topo $TOPO -mtu 4160 -end 400000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 400 -disable_trim -ecn 19 19 -disable_tor_ecn"
sflags() { case $1 in
 ofan)          echo "-q 20000 -load_balancing_algo ecmp -strat ofan";;
 ofan_weighted) echo "-q 20000 -load_balancing_algo ecmp -strat ofan_weighted";;
 jsq)           echo "-q 20000 -load_balancing_algo ecmp -strat ecmp_ar -ar_method exact";;
 ar193)         echo "-q 193 -load_balancing_algo ecmp -strat ecmp_ar";;
 reps)          echo "-q 20000 -load_balancing_algo freezing -paths 65535";;
 single)        echo "-q 20000 -load_balancing_algo ecmp";;
esac; }
jobs_list=$OUT/jobs.txt; : > "$jobs_list"
for p in $PS; do for s in $SEEDS; do
  d=$INST/p${p}_s$s
  [ -f "$d/inst.json" ] || python3 "$HERE/fig9_instance.py" "$d" $p $s > "$d.log" 2>&1
  for st in $STRATS; do
    [ "$st" = ofan_weighted ] && [ "$p" = 0 ] && continue   # identical to ofan on a healthy fabric (gate G3)
    [ -f "$RUNS/${st}__p${p}__s$s.tsv" ] || echo "${st}__p${p}__s$s $st $p $s" >> "$jobs_list"
  done
  [ -f "$RUNS/single__p${p}__s$s.tsv" ] || echo "single__p${p}__s$s single $p $s" >> "$jobs_list"
done; done
# LB1: single flow at rho=1
printf 'Nodes 432\nConnections 1\n0->216 id 1 start 0 size 1048576\n' > "$OUT/single.cm"
run_one() {
  tag=$1; st=$2; p=$3; s=$4; d=$INST/p${p}_s$s
  rho=$(python3 -c "import json;print(json.load(open('$d/inst.json'))['rho_max'])")
  ls=$(python3 -c "print(800000*$rho)")
  if [ "$st" = single ]; then extra="-tm $OUT/single.cm"; fa=""
  else extra="-tm $d/wl.cm"; fa="-fail_pipes_file $d/fail.txt"; fi
  cmd="$COMMON -linkspeed $ls -seed $s $(sflags $st) $extra $fa -routing_convergence_us 0"
  [ "$st" = single ] && cmd="$COMMON -linkspeed $ls -seed $s $(sflags $st) $extra"
  w=$(mktemp -d); cd "$w"; echo "$cmd" > "$RUNS/$tag.cmd"
  timeout 3000 "$BIN" $cmd -log_queue_stats "$RUNS/$tag.tmp.tsv" > "$RUNS/$tag.out" 2>&1
  mv "$RUNS/$tag.tmp.tsv" "$RUNS/$tag.tsv" 2>/dev/null; cd /; rm -rf "$w"; echo "done $tag"
}
[ -f "$RUNS/lb1.tsv" ] || { w=$(mktemp -d); cd "$w"; timeout 600 "$BIN" $COMMON -linkspeed 800000 -seed 1 $(sflags single) -tm "$OUT/single.cm" -log_queue_stats "$RUNS/lb1.tsv" > "$RUNS/lb1.out" 2>&1; cd /; rm -rf "$w"; }
export -f run_one sflags; export BIN INST RUNS OUT COMMON
xargs -P "$PAR" -L1 bash -c 'run_one "$@"' _ < "$jobs_list"

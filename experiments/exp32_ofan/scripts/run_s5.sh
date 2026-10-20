#!/usr/bin/env bash
# S5: NO-CCA queue/CCT trends, ofan vs switch-AR vs host-REPS (paper arXiv 2610.07230 Figs 1,3,4,7; App F bound).
# Run INSIDE container ofan-dev:  docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_s5.sh
# Idempotent: a run is skipped if its queue-stats TSV already exists. Env: PAR (parallel jobs, default 4),
# SIZES_MB (default "1 4 16 64"), TOPO_NAME (default fat_tree_432_1os_3t_400g), NODES/POD (default 432/36).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); EXP=$(dirname "$HERE")
BIN=$(cd "$EXP/../../htsim/sim/datacenter" && pwd)/htsim_uec
TOPO_NAME=${TOPO_NAME:-fat_tree_432_1os_3t_400g}; NODES=${NODES:-432}; POD=${POD:-36}
TOPO=$EXP/topologies/$TOPO_NAME.topo
[ -f "$TOPO" ] || TOPO=$(cd "$EXP/../../htsim/sim/datacenter/topologies/reps" && pwd)/$TOPO_NAME.topo
OUT=$EXP/data/s5; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p "$RUNS" "$WL"
SIZES_MB=${SIZES_MB:-"1 4 16 64"}; PAR=${PAR:-4}

# NO-CCA: constant CC, -cwnd in PACKETS (cwnd_b = cwnd * 4150 B). 400 pkts = 1.66 MB > BDP (~15us*400G = 0.75 MB)
# so sources are never window-limited. Buffers: 800 KB/port = -q 193 pkts (193*4150 = 800950 B).
# ECN thresholds (-ecn lo hi, packets): 19 19 = 78850 B ~ 80 KB step marking (matters for REPS only).
# Trimming disabled (-disable_trim): a trim would be a loss event; gate = 0 drops, 0 trims.
COMMON="-tm WL -topo $TOPO -linkspeed 400000 -seed 42 -end 200000 -connections_mapping -sender_cc_only
 -sender_cc_algo constant -cwnd 400 -disable_trim -q 193 -ecn 19 19"
# per-strategy flags. -disable_tor_ecn (project rule) for all; reps_dl = REPS with ECN also on ToR downlinks (sensitivity).
sflags() { case $1 in
 ofan)    echo "-disable_tor_ecn -load_balancing_algo ecmp -strat ofan -log_ofan_counts CNT";;
 ar)      echo "-disable_tor_ecn -load_balancing_algo ecmp -strat ecmp_ar";;
 reps)    echo "-disable_tor_ecn -load_balancing_algo freezing -strat ecmp_host -paths 65535";;
 reps_dl) echo "-load_balancing_algo freezing -strat ecmp_host -paths 65535";;
esac; }
STRATS=${STRATS:-"ofan ar reps reps_dl"}; WLS=${WLS:-"derange perm"}

mk_wl() { # name kind size_bytes
  [ -f "$WL/$1.cm" ] && return
  case $2 in
    derange) python3 "$HERE/gen_derangement.py" "$WL/$1.cm" $NODES $POD $3 42;;
    perm)    python3 "$HERE/gen_derangement.py" "$WL/$1.cm" $NODES $POD $3 42 perm;;
    single)  printf 'Nodes %d\nConnections 1\n0->%d id 1 start 0 size %d\n' $NODES $((NODES/2)) $3 > "$WL/$1.cm";;
  esac
}
jobs_list=$OUT/jobs.txt; : > "$jobs_list"
for m in $SIZES_MB; do
  B=$((m*1048576))
  for w in $WLS; do mk_wl ${w}_${m}mb $w $B; done
  mk_wl single_${m}mb single $B
  for s in $STRATS; do
    for w in $WLS single; do
      tag=${s}__${w}_${m}mb
      [ -f "$RUNS/$tag.tsv" ] || echo "$tag $s $w $m" >> "$jobs_list"
    done
  done
done
run_one() {
  tag=$1; s=$2; w=$3; m=$4
  cmd="$COMMON $(sflags $s)"; cmd=${cmd//WL/$WL/${w}_${m}mb.cm}; cmd=${cmd//CNT/$RUNS/$tag.counts.tsv}
  d=$(mktemp -d); cd "$d"
  echo "$cmd" > "$RUNS/$tag.cmd"
  ( time timeout 3000 "$BIN" $cmd -log_queue_stats "$RUNS/$tag.tmp.tsv" > "$RUNS/$tag.out" 2>&1 ) 2> "$RUNS/$tag.time"
  mv "$RUNS/$tag.tmp.tsv" "$RUNS/$tag.tsv" 2>/dev/null
  echo "done $tag"; cd /; rm -rf "$d"
}
export -f run_one sflags; export COMMON BIN RUNS WL TOPO
awk '{print $1" "$2" "$3" "$4}' "$jobs_list" | xargs -P "$PAR" -L1 bash -c 'run_one "$@"' _
python3 "$HERE/summarize_s5.py" "$OUT"

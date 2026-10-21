#!/usr/bin/env bash
# E2: Ofan paper (arXiv 2610.07230) Fig 7 (CCT increase vs message size) and Fig 8 (vs packet size), NO congestion control.
# Run INSIDE container ofan-dev:  docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_e2.sh
# Idempotent (a run is skipped if its .done marker exists). Relative paths only.
# Env: PART (fig7a|fig7b|fig8|trim|all; default all), PAR (parallel sims, default 2), SEEDS, SIZES_MB, MTUS, ATA_N, ATA_SIZES_KB, STRATS.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); EXP=$(dirname "$HERE"); REPO=$(cd "$EXP/../.." && pwd)
BIN=$REPO/htsim/sim/datacenter/htsim_uec; GEN=$REPO/experiments/exp32_ofan/scripts/gen_derangement.py
OUT=$EXP/data/e2; RUNS=$OUT/runs; WL=$OUT/workloads; mkdir -p "$RUNS" "$WL"
PART=${PART:-all}; PAR=${PAR:-2}
PERM_N=${PERM_N:-432}; PERM_POD=${PERM_POD:-36}; PERM_TOPO=$EXP/topologies/fat_tree_${PERM_N}_1os_3t_800g.topo
ATA_N=${ATA_N:-128}; ATA_TOPO=$EXP/topologies/fat_tree_${ATA_N}_1os_3t_800g.topo; ATA_POD=${ATA_POD:-16}
# Sizes in bytes: "0.5 MB" = 524288 etc.
SIZES_MB=${SIZES_MB:-"0.5 2 8 64"}; SEEDS=${SEEDS:-"1 2 3 4 5"}; SEEDS_BIG=${SEEDS_BIG:-"1 2"}
ATA_SIZES_KB=${ATA_SIZES_KB:-"128 256 512"}; ATA_SEEDS=${ATA_SEEDS:-"1 2 3"}
MTUS=${MTUS:-"1000 1500 2000 3000 4000 5000 6000 8000 10000"}; F8_SEEDS=${F8_SEEDS:-"1 2 3"}; F8_SIZES=${F8_SIZES:-"524288 4194304"}
STRATS7=${STRATS7:-"ofan ar_q193 ar_q20000 ar_exact reps"}; STRATS8=${STRATS8:-"ofan ar_q193 reps"}

# Byte-constant parameters (flags are in PACKETS of size MTU): infinite buffer 83.2 MB (=20000 pkt @4160), finite 800950 B (=193 @4150),
# ECN 78850 B (=19 pkt), cwnd 4.16 MB (>3x BDP at 800G, never window limited).
flags_for() { # strat mtu -> flags (without -tm/-topo/-seed/-end)
  s=$1; m=$2
  qinf=$(( (83200000 + m/2) / m )); q800=$(( (800950 + m/2) / m )); ecn=$(( (78850 + m/2) / m )); cw=$(( (4160000 + m/2) / m ))
  C="-linkspeed 800000 -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd $cw -mtu $m -disable_tor_ecn -ecn $ecn $ecn"
  case $s in
   ofan)             echo "$C -disable_trim -q $qinf -load_balancing_algo ecmp -strat ofan";;
   ar_q20000)        echo "$C -disable_trim -q $qinf -load_balancing_algo ecmp -strat ecmp_ar";;
   ar_q193)          echo "$C -disable_trim -q $q800 -load_balancing_algo ecmp -strat ecmp_ar";;
   ar_exact)         echo "$C -disable_trim -q $qinf -load_balancing_algo ecmp -strat ecmp_ar -ar_method exact";;
   reps)             echo "$C -disable_trim -q $qinf -load_balancing_algo freezing -strat ecmp_host -paths 65535";;
   reps_q193)        echo "$C -disable_trim -q $q800 -load_balancing_algo freezing -strat ecmp_host -paths 65535";;
   reps_trim_q20000) echo "$C -q $qinf -load_balancing_algo freezing -strat ecmp_host -paths 65535";;
   reps_trim_q193)   echo "$C -q $q800 -load_balancing_algo freezing -strat ecmp_host -paths 65535";;
   ofan_trim_q193)   echo "$C -q $q800 -load_balancing_algo ecmp -strat ofan";;
   ar_trim_q193)     echo "$C -q $q800 -load_balancing_algo ecmp -strat ecmp_ar";;
  esac; }
export -f flags_for

JOBS=$OUT/jobs.txt; : > "$JOBS"
add() { # tag strat kind(perm|ata|single) n topo pod size_bytes mtu seed end
  [ -f "$RUNS/$1.done" ] || echo "$*" >> "$JOBS"; }
fam() { case $1 in ofan*) echo ofan;; ar_*|ar*) echo ar_q20000;; reps*) echo reps;; esac; }
bytes_of_mb() { python3 -c "print(int(float('$1')*1048576))"; }

if [[ $PART == all || $PART == fig7a ]]; then
 for mb in $SIZES_MB; do
  B=$(bytes_of_mb $mb); [ "$mb" = 64 ] && sd=$SEEDS_BIG || sd=$SEEDS
  for f in ofan ar_q20000 reps; do add "single__${f}_perm_${B}_4160" $f single $PERM_N $PERM_TOPO $PERM_POD $B 4160 1 200000; done
  for s in $sd; do for st in $STRATS7; do add "f7a__${st}__perm_${B}_4160_s$s" $st perm $PERM_N $PERM_TOPO $PERM_POD $B 4160 $s 200000; done; done
 done
fi
if [[ $PART == all || $PART == trim ]]; then   # conjecture test: REPS with trimming / finite buffers at large messages
 for mb in ${TRIM_MB:-"16 64"}; do
  B=$(bytes_of_mb $mb)
  for f in ofan ar_q20000 reps; do add "single__${f}_perm_${B}_4160" $f single $PERM_N $PERM_TOPO $PERM_POD $B 4160 1 200000; done
  for s in ${TRIM_SEEDS:-1}; do for st in reps reps_q193 reps_trim_q20000 reps_trim_q193; do add "trim__${st}__perm_${B}_4160_s$s" $st perm $PERM_N $PERM_TOPO $PERM_POD $B 4160 $s 200000; done; done
 done
fi
if [[ $PART == all || $PART == fig7b ]]; then
 for kb in $ATA_SIZES_KB; do
  B=$((kb*1024)); TOT=$((B*(ATA_N-1)))
  for f in ofan ar_q20000 reps; do add "single__${f}_ata${ATA_N}_${TOT}_4160" $f single $ATA_N $ATA_TOPO $ATA_POD $TOT 4160 1 400000; done
  for s in $ATA_SEEDS; do for st in $STRATS7; do add "f7b__${st}__ata${ATA_N}_${B}_4160_s$s" $st ata $ATA_N $ATA_TOPO $ATA_POD $B 4160 $s 400000; done; done
 done
fi
if [[ $PART == all || $PART == fig8 ]]; then
 for B in $F8_SIZES; do for m in $MTUS; do
  for f in ofan ar_q20000 reps; do add "single__${f}_perm_${B}_$m" $f single $PERM_N $PERM_TOPO $PERM_POD $B $m 1 200000; done
  for s in $F8_SEEDS; do for st in $STRATS8; do add "f8__${st}__perm_${B}_${m}_s$s" $st perm $PERM_N $PERM_TOPO $PERM_POD $B $m $s 200000; done; done
 done; done
fi

run_one() { # tag strat kind n topo pod size mtu seed end
  tag=$1; st=$2; kind=$3; n=$4; topo=$5; pod=$6; size=$7; mtu=$8; seed=$9; end=${10}
  [ -f "$RUNS/$tag.done" ] && return
  case $kind in
   single) wl=$WL/single_${n}_${size}.cm; [ -f "$wl" ] || printf 'Nodes %d\nConnections 1\n0->%d id 1 start 0 size %d\n' $n $((n/2)) $size > "$wl"; st2=$(echo $st | sed 's/_.*//'); [ $st = ar_q20000 ] && st2=ar_q20000;;
   perm)   wl=$WL/perm_${n}_${size}_s$seed.cm; [ -f "$wl" ] || { python3 "$GEN" "$wl.$$" $n $pod $size $seed perm >/dev/null && mv "$wl.$$" "$wl"; };;
   ata)    wl=$WL/ata_${n}_${size}_s$seed.cm; [ -f "$wl" ] || { python3 "$HERE/gen_ata.py" "$wl.$$" $n $size $seed >/dev/null && mv "$wl.$$" "$wl"; };;
  esac
  d=$(mktemp -d); cd "$d"
  fl=$(flags_for $st $mtu)
  echo "$fl -tm $wl -topo $topo -seed $seed -end $end" > "$RUNS/$tag.cmd"
  python3 "$HERE/timed.py" "$RUNS/$tag.out" "$BIN" $fl -tm "$wl" -topo "$topo" -seed $seed -end $end -log_queue_stats "$RUNS/$tag.tsv" 2> "$RUNS/$tag.time"
  touch "$RUNS/$tag.done"; echo "done $tag $(cat $RUNS/$tag.time)"; cd /; rm -rf "$d"
}
export -f run_one; export BIN GEN HERE RUNS WL
# singles first (cheap), then the rest by job order
grep '^single' "$JOBS" > "$JOBS.s"; grep -v '^single' "$JOBS" > "$JOBS.r"
(cat "$JOBS.s"; cat "$JOBS.r") | awk '!seen[$1]++' | xargs -P "$PAR" -L1 bash -c 'run_one "$@"' _

#!/usr/bin/env bash
# E4: Ofan paper Fig 12 repro. 432 hosts, 800G, permutation, 4 MiB msgs, 3 CCAs x {reps, ar, ofan}, N seeds.
# Run inside container ofan-dev. Idempotent (skips tags whose .out ends with rc=). At most P=2 parallel sims.
# usage: run_e4.sh [nseeds=10]
# Buffers: -q 193 (193*4150 B = 800,950 B/port), -ecn 19 19 (~78.9 KB). No -mtu flag (4150 B wire pkt, as exp32).
# -disable_tor_ecn: project rule with -sender_cc_only (else ToR-downlink ECN re-enabled). Sensitivity "noDTE"
#   variant (nscc only) omits it, as exp26-31 did.
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"; DC=$R/htsim/sim/datacenter
H=$R/experiments/exp33_ofan_paper_repro; D=$H/data/e4/runs; W=$H/workloads; mkdir -p $D $W
NS=${1:-10}; P=${E4_PAR:-2}
TOPO=$H/topologies/fat_tree_432_1os_3t_800g.topo
G=$R/experiments/exp32_ofan/scripts/gen_derangement.py
for s in $(seq 1 $NS); do [ -f $W/perm432_4mb_s$s.cm ] || python3 $G $W/perm432_4mb_s$s.cm 432 36 4194304 $s perm; done
# single-flow lower bound workload (host 0 -> host 216, inter-pod)
[ -f $W/single432_4mb.cm ] || printf 'Nodes 432\nConnections 1\n0->216 id 1 start 0 size 4194304\n' > $W/single432_4mb.cm
JOBS=$(mktemp)
lbargs() { case $1 in reps) echo "-load_balancing_algo freezing -paths 65535";; ar) echo "-strat ecmp_ar -load_balancing_algo ecmp";; ofan) echo "-strat ofan -load_balancing_algo ecmp";; ofanhash) echo "-strat ofan -load_balancing_algo ecmp -ofan_ack_mode hash";; esac; }
for cc in dctcp nscc mswift; do
  echo "single_${cc} $cc single reps 1 dte" >> $JOBS
  for s in $(seq 1 $NS); do for lb in reps ar ofan; do echo "${cc}_${lb}_s$s $cc perm $lb $s dte" >> $JOBS; done; done
done
for s in $(seq 1 $NS); do echo "nscc_ofanhash_s$s nscc perm ofanhash $s dte" >> $JOBS; done   # ablation
echo "single_nscc_noDTE nscc single reps 1 nodte" >> $JOBS
for s in $(seq 1 $NS); do for lb in reps ar ofan; do echo "nscc_${lb}_noDTE_s$s nscc perm $lb $s nodte" >> $JOBS; done; done  # sensitivity
export DC H D W TOPO; export -f lbargs
one() { tag=$1; cc=$2; wl=$3; lb=$4; s=$5; dte=$6
  [ -f $D/$tag.out ] && grep -q '^rc=' $D/$tag.out && { echo "[skip] $tag"; return; }
  tm=$W/perm432_4mb_s$s.cm; [ $wl = single ] && tm=$W/single432_4mb.cm
  flag="-disable_tor_ecn"; [ $dte = nodte ] && flag=""
  wd=$(mktemp -d); ( cd $wd; timeout 3000 $DC/htsim_uec -tm $tm -topo $TOPO -linkspeed 800000 -seed $s -end 20000 -connections_mapping \
     -sender_cc_only $flag -q 193 -ecn 19 19 -sender_cc_algo $cc $(lbargs $lb) -log_queue_stats $D/$tag.tsv > $D/$tag.out 2>&1; echo "rc=$?" >> $D/$tag.out ); rm -rf $wd
  echo "[done] $tag"; }
export -f one
cat $JOBS | xargs -P $P -L1 bash -c 'one "$@"' _
rm -f $JOBS

#!/usr/bin/env bash
# S6: CCA sensitivity of Ofan vs ecmp_ar vs host REPS. Run inside container ofan-dev (paths are /workspace-relative via script location).
# Workload: 54-host k=6 3-tier, inter-pod derangement, 4 MiB flows (paper 4 MB messages), 400G.
# Buffers: paper 800 KB/port -> -q 193 pkts (193*4150 B = 801 KB); ECN low=high=80 KB -> -ecn 19 19 (19*4150 = 79 KB).
# -disable_tor_ecn: ALWAYS with -sender_cc_only (project rule; otherwise ToR-downlink ECN is re-enabled).
# Stress variant: S6_Q=40 S6_ECN="5 10" S6_DIR=s6_smallbuf ./run_s6.sh
# Idempotent: skips tags whose .out exists. usage: run_s6.sh [ofan|ecmp_ar|reps|ablation ...] (default all)
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"; DC=$R/htsim/sim/datacenter; E=$R/experiments/exp32_ofan
Q=${S6_Q:-193}; ECN=${S6_ECN:-"19 19"}; D=$E/data/${S6_DIR:-s6}; mkdir -p $D   # S6_Q/S6_ECN/S6_DIR override for the small-buffer stress variant
TM=$E/workloads/derange54_4mb_s42.cm
[ -f $TM ] || python3 $E/scripts/gen_derangement.py $TM 54 9 4194304 42
TOPO=$DC/topologies/reps/fat_tree_54_1os_3t_400g.topo
COMMON="-tm $TM -topo $TOPO -linkspeed 400000 -seed 42 -end 20000 -connections_mapping -sender_cc_only -disable_tor_ecn -q $Q -ecn $ECN"
run() { # tag ccalgo switch_strat lb extra...
  local tag=$1 cc=$2 strat=$3 lb=$4; shift 4
  [ -f $D/$tag.out ] && { echo "[skip] $tag"; return; }
  local wd; wd=$(mktemp -d); ( cd $wd; timeout 3000 $DC/htsim_uec $COMMON -sender_cc_algo $cc -load_balancing_algo $lb $strat "$@" \
     -log_queue_stats $D/$tag.tsv > $D/$tag.out 2>&1; echo "rc=$?" >> $D/$tag.out )
  echo "[done] $tag"
}
for cc in nscc mswift; do
  run ofan_$cc     $cc "-strat ofan"    ecmp
  run ecmpar_$cc   $cc "-strat ecmp_ar" ecmp
  run reps_$cc     $cc "" freezing -paths 65535
  run ofanhash_$cc $cc "-strat ofan"    ecmp -ofan_ack_mode hash
done
run ofanid_nscc  nscc "-strat ofan" ecmp -ofan_identity_order
run ofanid_mswift mswift "-strat ofan" ecmp -ofan_identity_order
# summary table (ideal packets/flow = 1027 observed for an uncongested 4 MiB flow)
{ printf "config\tfin\tstarted\tCCT_us\tmean_fct\tp99_fct\ttrims\tdrops\textra_pkts\tRTS\trtos\tfast_loss\tecn_acks\tabort\n"
  for t in ofan_nscc ecmpar_nscc reps_nscc ofanhash_nscc ofanid_nscc ofan_mswift ecmpar_mswift reps_mswift ofanhash_mswift ofanid_mswift; do
    [ -f $D/$t.out ] && python3 $E/scripts/summarize_run.py $t $D/$t.out $D/$t.tsv 1027; done; } | tee $D/summary.tsv

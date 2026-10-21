#!/usr/bin/env bash
# Verify new switch baselines on 54 hosts, 1MB inter-pod permutation, no-CCA flags (as exp32 S5), 800G topology.
# Run in container; results in data/verify_baselines/.
set -u; SEED=${SEED:-42}
E=/workspace/experiments; H=$E/exp33_ofan_paper_repro; BIN=/workspace/htsim/sim/datacenter/htsim_uec
O=$H/data/verify_baselines/seed$SEED; mkdir -p $O; cd $O

python3 $E/exp32_ofan/scripts/gen_derangement.py $O/perm54.cm 54 9 1048576 $SEED perm >/dev/null
COMMON="-tm $O/perm54.cm -topo $H/topologies/fat_tree_54_1os_3t_800g.topo -linkspeed 800000 -seed $SEED -end 200000 -connections_mapping
 -sender_cc_only -sender_cc_algo constant -cwnd 400 -disable_trim -q 20000 -disable_tor_ecn -load_balancing_algo ecmp"
run() { tag=$1; shift
  python3 $H/scripts/timed.py $O/$tag.out $BIN $COMMON "$@" -log_queue_stats $O/$tag.tsv
  echo "== $tag finished=$(grep -c 'Flow .* finished' $O/$tag.out) cct_us=$(grep 'Flow .* finished' $O/$tag.out | sed 's/.*finished at \([0-9.]*\).*/\1/' | sort -g | tail -1)"
  python3 $E/exp32_ofan/scripts/link_overload.py $O/$tag.tsv | tail -n +3
}
run rr_fixed   -strat ecmp_rr_fixed
run rr         -strat ecmp_rr
run random     -strat ecmp_random
run ar_quant   -strat ecmp_ar
run ar_exact   -strat ecmp_ar -ar_method exact
run p2c        -strat ecmp_p2c
run ofan       -strat ofan

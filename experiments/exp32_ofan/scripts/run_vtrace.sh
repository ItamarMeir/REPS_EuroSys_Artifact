#!/usr/bin/env bash
# Ofan reference-model verification. Run INSIDE container ofan-dev:
#   docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/run_vtrace.sh
# Runs htsim_uec -strat ofan with -log_ofan_trace on several topologies/modes (NSCC, no failures),
# then replays each trace through scripts/ofan_reference.py.
set -uo pipefail
R=/workspace; DC=$R/htsim/sim/datacenter; E=$R/experiments/exp32_ofan; V=$E/data/vtrace; T=$DC/topologies/reps
mkdir -p $V; cd $(mktemp -d)
FULL=${FULL:-4150}
# name topo workload  hosts_per_tor nodes hosts_per_pod pods extra-sim-flags extra-ref-flags
run() {
  name=$1; topo=$2; wl=$3; hpt=$4; nodes=$5; hpp=$6; pods=$7; sim_x=$8; ref_x=$9
  $DC/htsim_uec -tm $E/workloads/$wl -topo $topo -linkspeed 400000 -seed 42 -end 20000 \
    -connections_mapping -sender_cc_only -sender_cc_algo nscc -disable_tor_ecn \
    -load_balancing_algo ecmp -strat ofan $sim_x -log_ofan_trace $V/$name.tsv > $V/$name.out 2>&1
  echo "== $name: flows finished: $(grep -c 'finished at' $V/$name.out)"
  python3 $E/scripts/ofan_reference.py $V/$name.tsv --hosts-per-tor $hpt --nodes $nodes --hosts-per-pod $hpp \
     --pods $pods --full-size $FULL $ref_x
}
run t16   $T/fat_tree_16_1os_3t_400g.topo  derange16_1mb_s42.cm  2 16 4  4 "" "--selftest"
run t54   $T/fat_tree_54_1os_3t_400g.topo  derange54_4mb_s42.cm  3 54 9  6 "" "--selftest"
run t128  $T/fat_tree_128_1os_3t_400g.topo derange128_1mb_s42.cm 4 128 16 8 "" "--selftest"
run t32_2t $T/fat_tree_32_1os_2t_400g.topo perm32_1mb_s42.cm     4 32 32 1 "" "--selftest"
run t32_bundle $E/topologies/fat_tree_32_bundle2_3t_400g.topo derange32_1mb_s42.cm 4 32 16 2 "" "--selftest"
run t16_hash $T/fat_tree_16_1os_3t_400g.topo derange16_1mb_s42.cm 2 16 4 4 "-ofan_ack_mode hash" "--ack-mode hash"
run t16_ident $T/fat_tree_16_1os_3t_400g.topo derange16_1mb_s42.cm 2 16 4 4 "-ofan_identity_order" "--identity"

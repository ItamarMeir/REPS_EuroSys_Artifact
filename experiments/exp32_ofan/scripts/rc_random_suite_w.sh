#!/bin/bash
# Run -routing_check_random over the standard topology set. Run INSIDE ofan-dev. usage: rc_random_suite.sh [trials] [seed]
N=${1:-60}; SEED=${2:-5}
S=/workspace/experiments/exp32_ofan/scripts/rc_random_w.sh
DT=/workspace/htsim/sim/datacenter/topologies; ET=/workspace/experiments/exp32_ofan/topologies
for p in 0.1 0.4; do
 for cfg in "$DT/reps/fat_tree_16_1os_3t_400g.topo derange16_1mb_s42.cm" "$DT/reps/fat_tree_54_1os_3t_400g.topo derange54_4mb_s42.cm" \
   "$DT/reps/fat_tree_128_1os_3t_400g.topo derange128_1mb_s42.cm" "$DT/reps/fat_tree_32_1os_2t_400g.topo perm32_1mb_s42.cm" \
   "$DT/test.topo derange8_1mb_s42.cm" "$ET/fat_tree_32_bundle2_3t_400g.topo derange32_1mb_s42.cm"; do
  set -- $cfg
  echo "$(basename $1) $(bash $S $1 $2 $p $N $SEED | grep -E 'ROUTING_CHECK_RANDOM' | sed 's/ROUTING_CHECK_RANDOM //')"
 done
done

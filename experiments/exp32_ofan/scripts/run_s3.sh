#!/usr/bin/env bash
# S3: ofan on the 16-host permutation with per-physical-port counters. Run in container ofan-dev.
set -euo pipefail
R=/workspace; DC=$R/htsim/sim/datacenter; D=$R/experiments/exp32_ofan/data
mkdir -p $D; cd $(mktemp -d)
$DC/htsim_uec -tm $R/experiments/exp32_ofan/workloads/perm16_1mb_s42.cm \
  -topo $DC/topologies/reps/fat_tree_16_1os_3t_400g.topo -linkspeed 400000 -seed 42 -end 20000 \
  -connections_mapping -sender_cc_only -sender_cc_algo nscc -disable_tor_ecn \
  -load_balancing_algo ecmp -strat ofan "$@" -log_ofan_counts $D/s3_counts.tsv > $D/s3.out 2>&1
echo "flows finished: $(grep -c 'finished at' $D/s3.out)"

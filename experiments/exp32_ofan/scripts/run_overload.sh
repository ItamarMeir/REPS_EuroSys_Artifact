#!/usr/bin/env bash
# Per-layer link overload run (paper Fig 1/3/4 style). Run in container ofan-dev.
# usage: run_overload.sh <strat: ofan|ecmp_ar|ecmp_host|...> <workload.cm> <topo> [tag] [extra flags...]
set -euo pipefail
R=/workspace; DC=$R/htsim/sim/datacenter; D=$R/experiments/exp32_ofan/data
STRAT=$1; TM=$2; TOPO=$3; TAG=${4:-$STRAT}; shift 4 || shift $#
mkdir -p $D; cd $(mktemp -d)
$DC/htsim_uec -tm $TM -topo $TOPO -linkspeed 400000 -seed 42 -end 20000 \
  -connections_mapping -sender_cc_only -sender_cc_algo nscc -disable_tor_ecn \
  -load_balancing_algo ecmp -strat $STRAT "$@" -log_queue_stats $D/qs_$TAG.tsv > $D/qs_$TAG.out 2>&1
echo "$TAG flows finished: $(grep -c 'finished at' $D/qs_$TAG.out)"
python3 $R/experiments/exp32_ofan/scripts/link_overload.py $D/qs_$TAG.tsv

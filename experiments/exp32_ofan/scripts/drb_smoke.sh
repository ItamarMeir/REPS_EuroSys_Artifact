#!/usr/bin/env bash
# path_rr smoke: BIN=<binary> bash drb_smoke.sh <outfile> [extra flags]. Run in container ofan-dev.
BIN=${BIN:-/workspace/htsim/sim/datacenter/htsim_uec}; R=/workspace; out=$1; shift
d=$(mktemp -d); cd $d
$BIN -tm $R/experiments/exp32_ofan/workloads/perm16_1mb_s42.cm -topo $R/htsim/sim/datacenter/topologies/reps/fat_tree_16_1os_3t_400g.topo -linkspeed 400000 -seed 42 -end 20000 -connections_mapping -sender_cc_only -sender_cc_algo nscc -disable_tor_ecn -load_balancing_algo path_rr "$@" > $out 2>&1
cd /; rm -rf $d; sha256sum $out

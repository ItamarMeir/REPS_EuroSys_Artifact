#!/bin/bash
# Knowledge-only randomized mask test (-routing_check_random). Run INSIDE ofan-dev. usage: rc_random.sh topo workload p trials seed [extra htsim args]
DC=/workspace/htsim/sim/datacenter
T=$1; W=$2; P=$3; N=$4; S=$5
d=$(mktemp -d); cd $d
$DC/htsim_uec -tm /workspace/experiments/exp32_ofan/workloads/$W -topo $T -linkspeed 400000 -seed 42 -end 50 -connections_mapping -sender_cc_only -sender_cc_algo nscc -disable_tor_ecn -load_balancing_algo ecmp -strat ofan -routing_convergence_us 5 -routing_check -routing_check_random $N $S $P ${6:-} > out.txt 2>&1
echo "exit=$?"; grep -E "ROUTING_CHECK_RANDOM|ROUTING_CHECK_INFO|ROUTING_CHECK mismatches|rror" out.txt | head -8; grep MISMATCH out.txt | head -3
rm -rf $d

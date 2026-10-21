#!/usr/bin/env bash
# Smoke test: every generated topology loads and a 1MB inter-pod permutation completes under -strat ofan.
# Run in container: docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/smoke_topos.sh
set -u
E=/workspace/experiments; H=$E/exp33_ofan_paper_repro; BIN=/workspace/htsim/sim/datacenter/htsim_uec
T=/tmp/smoke_topos; mkdir -p $T; cd $T
for kk in "16 4" "54 9" "128 16" "250 25" "432 36" "1024 64"; do set -- $kk; n=$1; pod=$2
  python3 $E/exp32_ofan/scripts/gen_derangement.py $T/perm$n.cm $n $pod 1048576 42 perm >/dev/null
  python3 $H/scripts/timed.py $T/o$n.out $BIN -tm $T/perm$n.cm -topo $H/topologies/fat_tree_${n}_1os_3t_800g.topo -linkspeed 800000 -seed 42 -end 200000 \
   -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 400 -disable_trim -q 20000 -disable_tor_ecn \
   -load_balancing_algo ecmp -strat ofan 2> $T/o$n.time
  echo "hosts=$n finished_lines=$(grep -c 'Flow .* finished' $T/o$n.out) $(tail -1 $T/o$n.time)"
done

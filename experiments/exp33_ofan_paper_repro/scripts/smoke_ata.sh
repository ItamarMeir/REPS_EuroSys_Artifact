#!/usr/bin/env bash
# Smoke/scale test of one-shot all-to-all (gen_ata.py) under -strat ofan. Usage: smoke_ata.sh "N1 N2 ..." [size_bytes]
set -u
E=/workspace/experiments; H=$E/exp33_ofan_paper_repro; BIN=/workspace/htsim/sim/datacenter/htsim_uec
T=/tmp/smoke_ata; mkdir -p $T; cd $T; SZ=${2:-131072}
for n in $1; do
  python3 $H/scripts/gen_ata.py $T/ata$n.cm $n $SZ
  python3 $H/scripts/timed.py $T/a$n.out $BIN -tm $T/ata$n.cm -topo $H/topologies/fat_tree_${n}_1os_3t_800g.topo -linkspeed 800000 -seed 42 -end 400000 \
   -connections_mapping -sender_cc_only -sender_cc_algo constant -cwnd 400 -disable_trim -q 20000 -disable_tor_ecn \
   -load_balancing_algo ecmp -strat ofan
  echo "N=$n flows=$((n*(n-1))) finished=$(grep -c 'Flow .* finished' $T/a$n.out) last_finish_us=$(grep 'Flow .* finished' $T/a$n.out | sed 's/.*finished at \([0-9.]*\).*/\1/' | sort -g | tail -1)"
done

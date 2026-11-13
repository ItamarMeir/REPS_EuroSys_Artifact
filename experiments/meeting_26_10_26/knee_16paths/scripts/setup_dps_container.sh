#!/bin/bash
# Lay out the container filesystem the knee_16paths runners expect (/build/htsim_main/sim/datacenter, /work/knee16,
# /kneework16) from a bind-mounted repo at /workspace, WITHOUT writing into the repo. Run INSIDE the container; idempotent.
#   docker run -d --name dps-dev -v "$(pwd):/workspace" -w /workspace reps-artifact sleep infinity
#   docker exec dps-dev bash /workspace/experiments/meeting_26_10_26/knee_16paths/scripts/setup_dps_container.sh
set -e
W=/workspace
K=$W/experiments/meeting_26_10_26/knee_16paths
DC=/build/htsim_main/sim/datacenter
mkdir -p $DC/topologies/knee16 $DC/connection_matrices/knee16 /work/knee16 /kneework16 /dpsout
ln -sf $W/htsim/sim/datacenter/htsim_uec $DC/htsim_uec
for f in $K/data/topo/*; do cp -f "$f" $DC/topologies/knee16/; done
for f in $K/data/cm/*;   do cp -f "$f" $DC/connection_matrices/knee16/; done
for f in $K/data/degrade/*; do cp -f "$f" /work/knee16/; done
# runner chain: run_knee16 -> run_t3 -> run_m4, each next to the files it reads
cp -f $K/scripts/run_knee16.py /kneework16/
cp -f $W/experiments/meeting_26_10_26/T3/scripts/run_t3.py /kneework16/
cp -f $W/experiments/meeting_23_10_26/M4/scripts/run_m4.py /kneework16/
cp -f $W/experiments/meeting_26_10_26/T3/data/configs/configs.json /kneework16/configs.json
cp -f $K/data/configs_knee16.json $K/data/configs_knee16_q.json /kneework16/ 2>/dev/null || cp -f $K/data/configs_knee16.json /kneework16/
cp -f $K/scripts/*.py /kneework16/ 2>/dev/null || true
echo "container layout ready: $DC (binary -> $W/htsim/sim/datacenter/htsim_uec)"

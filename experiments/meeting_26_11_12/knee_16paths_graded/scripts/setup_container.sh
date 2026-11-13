#!/bin/bash
# Lay out the container filesystem for knee_16paths_graded (binary at /workspace/htsim/sim/datacenter/htsim_uec, repo bind-mounted at /workspace). Run INSIDE dps-dev; idempotent, writes nothing into the repo.
set -e
W=/workspace; E=$W/experiments; G=$E/meeting_26_11_12/knee_16paths_graded
DC=/build/htsim_main/sim/datacenter
mkdir -p $DC/topologies/knee16 $DC/connection_matrices/knee16 /work/knee16 /kneework16g
ln -sf $W/htsim/sim/datacenter/htsim_uec $DC/htsim_uec
cp -f $G/data/topo/* $DC/topologies/knee16/; cp -f $G/data/cm/* $DC/connection_matrices/knee16/; cp -f $G/data/degrade/* /work/knee16/
cp -f $E/meeting_26_10_26/T3/scripts/run_t3.py $E/meeting_26_10_23/M4/scripts/run_m4.py /kneework16g/
cp -f $E/meeting_26_10_26/T3/data/configs/configs.json /kneework16g/
cp -f $G/data/*.json /kneework16g/; cp -f $G/scripts/*.py /kneework16g/; cp -f $G/scripts/*.sh /kneework16g/
echo ready

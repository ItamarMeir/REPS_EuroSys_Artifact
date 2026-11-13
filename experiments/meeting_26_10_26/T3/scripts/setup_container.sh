#!/bin/bash
# Copy T3 inputs into the m23-dev container (no bind mounts). Run from anywhere; idempotent.
set -e
export MSYS_NO_PATHCONV=1
T3="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DC=/build/htsim_main/sim/datacenter
C=m23-dev
cp_in() { docker cp "$(cygpath -m "$1")" "$C:$2"; }       # docker.exe needs Windows host paths
docker exec $C mkdir -p /work/t3 /t3work /t3out $DC/topologies/t3 $DC/connection_matrices/t3
for f in "$T3"/data/configs/topo/*;    do cp_in "$f" $DC/topologies/t3/; done
for f in "$T3"/data/configs/tm/*;      do cp_in "$f" $DC/connection_matrices/t3/; done
for f in "$T3"/data/configs/degrade/*; do cp_in "$f" /work/t3/; done
cp_in "$T3/data/configs/configs.json" /t3work/configs.json
cp_in "$T3/scripts/run_t3.py" /t3work/run_t3.py
cp_in "$T3/../../meeting_23_10_26/M4/scripts/run_m4.py" /t3work/run_m4.py
docker exec $C bash -c "cmp /t3work/run_m4.py /t1work/run_m4.py && echo run_m4 same as T1"
docker exec $C bash -c "ls $DC/topologies/t3 $DC/connection_matrices/t3 /work/t3 | head -60"

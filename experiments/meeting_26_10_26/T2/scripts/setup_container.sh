#!/bin/bash
# Copy T2 inputs into the m23-dev container (no bind mounts). Idempotent; run from anywhere.
set -e
export MSYS_NO_PATHCONV=1
T2="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=m23-dev
cp_in() { docker cp "$(cygpath -m "$1")" "$C:$2"; }       # docker.exe needs Windows host paths
docker exec $C mkdir -p /work/t2 /t2work /t2out
for f in "$T2"/configs/degrade/*; do cp_in "$f" /work/t2/; done
cp_in "$T2/configs/configs.json" /t2work/configs.json
cp_in "$T2/scripts/run_t2.py" /t2work/run_t2.py
cp_in "$T2/../../meeting_23_10_26/M4/scripts/run_m4.py" /t2work/run_m4.py
docker exec $C bash -c "cmp /t2work/run_m4.py /t1work/run_m4.py && echo run_m4 same as T1"
docker exec $C bash -c "ls /work/t2 | head -20; ls /build/htsim_main/sim/datacenter/connection_matrices/tornado_128n_16mb.cm /build/htsim_main/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo"

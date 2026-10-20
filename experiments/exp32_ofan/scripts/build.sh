#!/usr/bin/env bash
# In-container full rebuild of htsim_uec. Run INSIDE container ofan-dev (repo at /workspace):
#   docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/build.sh [clean]
# Without "clean" does an incremental make; with "clean" does make clean first.
set -euo pipefail
cd /workspace/htsim/sim
if [ "${1:-}" = "clean" ]; then
  make clean; (cd datacenter && make clean)
fi
make -j"$(nproc)"
(cd datacenter && make -j"$(nproc)")
test -x /workspace/htsim/sim/datacenter/htsim_uec && echo BUILD OK || { echo BUILD FAILED; exit 1; }

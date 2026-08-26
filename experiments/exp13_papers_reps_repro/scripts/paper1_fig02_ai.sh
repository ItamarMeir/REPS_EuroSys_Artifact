#!/usr/bin/env bash
# Paper 1 Fig 2 (right): AI/ML collectives — Collective Runtime.
# 5 collectives in paper: AllToAll(n=4,8,16), Ring AllReduce, Butterfly AllReduce.
#
# DEFERRED: existing alltoall*.cm files are 32-node, all_red_*.cm files are 16-node.
# Running gen_files.py with --size_topo 128 overwrites these files (destructive).
# This script generates 128-node copies under exp13-specific names so we don't
# clobber the original 32/16-node files used elsewhere.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

GEN_DIR="$CM_DIR"
SEEDS="42 43 44"

# Regenerate 128-node AI workloads under exp13-specific names.
gen_ai_if_missing() {
    local out="$1"; shift
    if [[ -f "$out" ]]; then
        return 0
    fi
    echo "Generating AI: $(basename "$out")"
    python3 "$@"
}

# AllToAll variants: serialn flow with parallel_conn = 1/2/4/8/16. Paper plots 4/8/16.
for n_parallel in 4 8 16; do
    out="$CM_DIR/exp13_alltoall_n128_p${n_parallel}.cm"
    # gen_serialn_alltoall.py args: filename topo_size start end parallel_conn flow_size start_us seed
    # Flow size = 2 MB per the gen_files.py default (4 MB / 2).
    gen_ai_if_missing "$out" "$GEN_DIR/gen_serialn_alltoall.py" "$out" 128 128 128 $n_parallel 2000000 1 42
done

# Ring AllReduce, 128 nodes, 4 MB
out_ring="$CM_DIR/exp13_allreduce_ring_n128_4MB.cm"
gen_ai_if_missing "$out_ring" "$GEN_DIR/gen_allreduce.py" "$out_ring" 128 64 64 4000000 0 42

# Butterfly AllReduce, 128 nodes, 20 MB (from gen_files.py defaults)
out_fly="$CM_DIR/exp13_allreduce_butterfly_n128_20MB.cm"
gen_ai_if_missing "$out_fly" "$GEN_DIR/gen_allreduce_butterfly.py" "$out_fly" 128 1 128 20000000 1 42

# Now run REPS on each, 3 sim-seeds for path-choice variance.
LBS="freezing"
declare -A AI_WL
AI_WL[a2a4]="exp13_alltoall_n128_p4.cm"
AI_WL[a2a8]="exp13_alltoall_n128_p8.cm"
AI_WL[a2a16]="exp13_alltoall_n128_p16.cm"
AI_WL[ring]="exp13_allreduce_ring_n128_4MB.cm"
AI_WL[butterfly]="exp13_allreduce_butterfly_n128_20MB.cm"

for tag in a2a4 a2a8 a2a16 ring butterfly; do
    cm="$CM_DIR/${AI_WL[$tag]}"
    if [[ ! -f "$cm" ]]; then
        echo "WARN: missing $cm"
        continue
    fi
    for s in $SEEDS; do
        for lb in $LBS; do
            run_p1 fig02_ai "$lb" "$s" "$cm"
        done
    done
done

echo "[done] fig02_ai"

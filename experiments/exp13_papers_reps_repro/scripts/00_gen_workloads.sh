#!/usr/bin/env bash
# Generate missing connection-matrix workloads for exp13 paper reproductions.
# Idempotent: skips any .cm that already exists.
#
# Paper 1 (REPS, arXiv:2407.21625) needs perm/incast/tornado at {4,8,16} MB across 3 seeds.
# Paper 2 (CC4Spraying, arXiv:2509.07907v2) needs perm_250n_8MB_s{43,44}.cm (only s42 exists).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
GEN_DIR="$CM_DIR"

SIZE_4MB=4194304
SIZE_8MB=8388608
SIZE_16MB=16777216
SIZE_32MB=33554432

SEEDS=(42 43 44 45 46 47)

gen_if_missing() {
    local out="$1"; shift
    if [[ -f "$out" ]]; then
        return 0
    fi
    echo "Generating: $(basename "$out")"
    python3 "$@"
}

# Paper 1: Permutation 128n at {4,8,16} MB
for sz in $SIZE_4MB $SIZE_8MB $SIZE_16MB; do
    case $sz in
        $SIZE_4MB)  tag=4MB ;;
        $SIZE_8MB)  tag=8MB ;;
        $SIZE_16MB) tag=16MB ;;
    esac
    for s in "${SEEDS[@]}"; do
        out="$CM_DIR/perm_128n_128c_${tag}_s${s}.cm"
        gen_if_missing "$out" "$GEN_DIR/gen_permutation.py" "$out" 128 128 $sz 0 $s
    done
done

# Paper 1 Fig 7: Permutation 128n at 32 MB
for s in "${SEEDS[@]}"; do
    out="$CM_DIR/perm_128n_128c_32MB_s${s}.cm"
    gen_if_missing "$out" "$GEN_DIR/gen_permutation.py" "$out" 128 128 $SIZE_32MB 0 $s
done

# Paper 1: Incast 128n degree 8 at {4,8,16} MB
for sz in $SIZE_4MB $SIZE_8MB $SIZE_16MB; do
    case $sz in
        $SIZE_4MB)  tag=4MB ;;
        $SIZE_8MB)  tag=8MB ;;
        $SIZE_16MB) tag=16MB ;;
    esac
    for s in "${SEEDS[@]}"; do
        out="$CM_DIR/incast_n128_d8_${tag}_s${s}.cm"
        # gen_incast.py args: filename nodes conns flowsize extrastarttime randseed prefer_remote
        # conns = degree (8 senders to 1 receiver)
        gen_if_missing "$out" "$GEN_DIR/gen_incast.py" "$out" 128 8 $sz 0 $s 0
    done
done

# Paper 1: Tornado 128n at {4,8,16} MB.
# gen_tornado.py is deterministic (i -> i+N/2 fixed mapping), so per-seed files
# are byte-identical. We still emit s42/s43/s44 copies so the run scripts can
# index by seed uniformly. (Future: replace tornado.py with a stochastic variant.)
for sz in $SIZE_4MB $SIZE_8MB $SIZE_16MB; do
    case $sz in
        $SIZE_4MB)  tag=4MB ;;
        $SIZE_8MB)  tag=8MB ;;
        $SIZE_16MB) tag=16MB ;;
    esac
    for s in "${SEEDS[@]}"; do
        out="$CM_DIR/tornado_n128_${tag}_s${s}.cm"
        # gen_tornado.py args: filename nodes conns flowsize extrastarttime randseed
        gen_if_missing "$out" "$GEN_DIR/gen_tornado.py" "$out" 128 128 $sz 0 $s
    done
done
# Paper 1 Fig 1 micro: Tornado 16 MB (alias if needed)
for s in "${SEEDS[@]}"; do
    [[ -f "$CM_DIR/tornado_n128_16MB_s${s}.cm" ]] || true  # produced by loop above
done

# Paper 1 Fig 3 micro: Permutation 32 MB
for s in "${SEEDS[@]}"; do
    out="$CM_DIR/perm_128n_128c_32MB_s${s}.cm"
    [[ -f "$out" ]] || true  # produced by loop above
done

# Paper 2 Fig 8: missing 250n s43, s44
for s in 43 44; do
    out="$CM_DIR/perm_250n_250c_8MB_s${s}.cm"
    gen_if_missing "$out" "$GEN_DIR/gen_permutation.py" "$out" 250 250 $SIZE_8MB 0 $s
done

echo "=== Workload generation complete ==="
echo "Generated CMs in $CM_DIR matching pattern:"
ls -1 "$CM_DIR" | grep -E "^(perm_128n_128c_(4|8|16|32)MB|incast_n128_d8_(4|8|16)MB|tornado_n128_(4|8|16)MB)_s4[234]\.cm$" | wc -l
echo "Paper 2 250-perm 3 seeds:"
ls -1 "$CM_DIR"/perm_250n_250c_8MB_s4*.cm

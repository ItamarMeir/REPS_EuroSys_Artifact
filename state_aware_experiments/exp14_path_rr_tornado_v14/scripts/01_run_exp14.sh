#!/usr/bin/env bash
# exp14: PATH_RR vs REPS on tornado workload, 4-ary fat-tree (k=4, 16 hosts).
#
# Design matrix:
#   LB:   path_rr, freezing
#   CC:   constant (line-rate), nscc
#   Size: 4 MB, 8 MB, 16 MB
#   Seeds: 42 43 44  (simulator seeds; tornado pattern is deterministic)
#
# Output: data/exp14_<cond>_<wl_tag>_seed<s>.out per run (skipped if exists).
# Analyze: python3 aggregate_exp14.py && python3 plot_exp14.py

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXP_DIR="$SCRIPT_DIR/.."
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
TOPO_DIR="$REPO_ROOT/htsim/sim/datacenter/topologies/reps"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
DATA_DIR="$EXP_DIR/data"

mkdir -p "$DATA_DIR"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: binary not found: $BIN"
    echo "  cd $REPO_ROOT/htsim/sim && make -j8 && cd datacenter && make -j8"
    exit 1
fi

TOPO="$TOPO_DIR/fat_tree_16_1os_3t_400g.topo"
SEEDS="42 43 44"
SIZES_BYTES="4194304 8388608 16777216"

# Shared flags: paper-1-aligned for 16-host 3-tier, excluding MPRDMA-specific flags.
# -disable_tor_ecn is mandatory when -sender_cc_only is used (avoids spurious ECN on ToR downlinks).
BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000
  -end 10000"

for lb in path_rr freezing; do
    for cc in constant nscc; do
        cond="${lb}+${cc}"
        for size in $SIZES_BYTES; do
            wl_tag="tornado_n16_s${size}"
            tm="$CM_DIR/${wl_tag}.cm"
            if [[ ! -f "$tm" ]]; then
                echo "ERROR: workload file missing: $tm"
                exit 1
            fi
            for seed in $SEEDS; do
                outfile="$DATA_DIR/exp14_${cond}_${wl_tag}_seed${seed}.out"
                if [[ -f "$outfile" ]]; then
                    echo "[skip] $(basename "$outfile")"
                    continue
                fi
                echo "[run]  $cond size=${size} seed=${seed}"
                # Run from htsim/sim/datacenter so failure-generator relative paths resolve.
                # shellcheck disable=SC2086
                (cd "$REPO_ROOT/htsim/sim/datacenter" && \
                 "$BIN" $BASE \
                     -load_balancing_algo "$lb" \
                     -sender_cc_algo "$cc" \
                     -seed "$seed" \
                     -tm "$tm") \
                    > "$outfile" 2>&1
                echo "[done] $(basename "$outfile")"
            done
        done
    done
done

echo ""
echo "All runs complete. Run:"
echo "  python3 $EXP_DIR/aggregate_exp14.py"
echo "  python3 $EXP_DIR/plot_exp14.py"

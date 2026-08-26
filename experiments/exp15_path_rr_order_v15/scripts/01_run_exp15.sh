#!/usr/bin/env bash
# exp15: PATH_RR buffer-order study.
# Compares 4 starting-index strategies for the PATH_RR cycle under tornado,
# using line-rate CC (constant) only.
#
# Modes:
#   zero        - all flows start at index 0 (synchronized, current default)
#   src_mod     - start at src % num_paths  (desync by sender address)
#   dst_mod     - start at dst % num_paths  (desync by receiver address)
#   srcdst_hash - start at (src*7 + dst*3) % num_paths  (hash spread)
#
# Design: 4 modes × 3 sizes × 3 seeds = 36 runs
# Topology: fat_tree_16_1os_3t_400g.topo (k=4, 16 hosts, 3-tier)

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
MODES="zero src_mod dst_mod srcdst_hash"
SEEDS="42 43 44"
SIZES_BYTES="4194304 8388608 16777216"

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000
  -end 10000
  -load_balancing_algo path_rr
  -sender_cc_algo constant"

for mode in $MODES; do
    for size in $SIZES_BYTES; do
        wl_tag="tornado_n16_s${size}"
        tm="$CM_DIR/${wl_tag}.cm"
        if [[ ! -f "$tm" ]]; then
            echo "ERROR: workload file missing: $tm"
            exit 1
        fi
        for seed in $SEEDS; do
            outfile="$DATA_DIR/exp15_${mode}_${wl_tag}_seed${seed}.out"
            if [[ -f "$outfile" ]]; then
                echo "[skip] $(basename "$outfile")"
                continue
            fi
            echo "[run]  mode=${mode} size=${size} seed=${seed}"
            # shellcheck disable=SC2086
            (cd "$REPO_ROOT/htsim/sim/datacenter" && \
             "$BIN" $BASE \
                 -path_rr_start_mode "$mode" \
                 -seed "$seed" \
                 -tm "$tm") \
                > "$outfile" 2>&1
            echo "[done] $(basename "$outfile")"
        done
    done
done

echo ""
echo "All runs complete. Run:"
echo "  python3 $EXP_DIR/aggregate_exp15.py"
echo "  python3 $EXP_DIR/plot_exp15.py"

#!/usr/bin/env bash
# exp16: OPS (oblivious packet spraying) comparison — 16 MiB and 64 MiB.
# Adds ops_constant and ops_nscc to the exp16 data directory.

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
    echo "ERROR: binary not found: $BIN"; exit 1
fi

TOPO="$TOPO_DIR/fat_tree_16_1os_3t_400g.topo"
SEEDS="42 43 44"

declare -A END_TIME
END_TIME[16777216]=5000     # 16 MiB → -end 5 ms
END_TIME[67108864]=10000    # 64 MiB → -end 10 ms

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000"

for cc in constant nscc; do
    label="ops_${cc}"
    for size in "${!END_TIME[@]}"; do
        wl_tag="tornado_n16_s${size}"
        tm="$CM_DIR/${wl_tag}.cm"
        if [[ ! -f "$tm" ]]; then
            echo "ERROR: workload file missing: $tm"; exit 1
        fi
        endtime="${END_TIME[$size]}"
        for seed in $SEEDS; do
            outfile="$DATA_DIR/exp16_${label}_${wl_tag}_seed${seed}.out"
            if [[ -f "$outfile" ]]; then
                echo "[skip] $(basename "$outfile")"
                continue
            fi
            echo "[run]  label=${label} size=${size} seed=${seed}"
            (cd "$REPO_ROOT/htsim/sim/datacenter" && \
             "$BIN" $BASE \
                 -load_balancing_algo oblivious \
                 -sender_cc_algo "$cc" \
                 -end "$endtime" \
                 -seed "$seed" \
                 -tm "$tm") \
                > "$outfile" 2>&1
            echo "[done] $(basename "$outfile")"
        done
    done
done

echo ""
echo "OPS runs complete. Re-run:"
echo "  python3 $EXP_DIR/aggregate_exp16.py"
echo "  python3 $EXP_DIR/plot_exp16_ops.py"

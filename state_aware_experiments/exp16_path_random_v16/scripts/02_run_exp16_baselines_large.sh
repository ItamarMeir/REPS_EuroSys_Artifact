#!/usr/bin/env bash
# Run exp14 baseline conditions at elephant sizes (64 MiB, 256 MiB) for exp16 comparison.
# Output lands in exp16's data/ directory so plot_exp16.py sees all 6 conditions at all 3 sizes.

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
END_TIME[67108864]=10000     # 64 MiB  → -end 10 ms
END_TIME[268435456]=20000    # 256 MiB → -end 20 ms

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000"

for lb in path_rr freezing; do
    for cc in constant nscc; do
        label="${lb}_${cc}"   # underscore, matching exp16 naming
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
                echo "[run]  label=${label} size=${size} seed=${seed} end=${endtime}µs"
                (cd "$REPO_ROOT/htsim/sim/datacenter" && \
                 "$BIN" $BASE \
                     -load_balancing_algo "$lb" \
                     -sender_cc_algo "$cc" \
                     -end "$endtime" \
                     -seed "$seed" \
                     -tm "$tm") \
                    > "$outfile" 2>&1
                echo "[done] $(basename "$outfile")"
            done
        done
    done
done

echo ""
echo "Baseline large-flow runs complete. Re-run:"
echo "  python3 $EXP_DIR/aggregate_exp16.py"
echo "  python3 $EXP_DIR/plot_exp16.py"

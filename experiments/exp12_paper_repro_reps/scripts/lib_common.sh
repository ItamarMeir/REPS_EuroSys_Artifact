#!/usr/bin/env bash
# ============================================================
# lib_common.sh — Shared variables and run_sim() function.
# Source this file; do not execute it directly.
# ============================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
WL_DIR="$REPO_ROOT/experiments/workloads"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
TOPO_DIR="$REPO_ROOT/htsim/sim/datacenter/topologies/reps"
DATA_DIR="$REPO_ROOT/experiments/exp12_paper_repro_reps/data"

mkdir -p "$DATA_DIR"

# ──────────────────────────────────────────────────────────────
# Base flags common to all 128-node 800 Gbps experiments
# Uses paper-faithful topology (0.5 µs/hop) + ECMP elephant override (32 MB threshold)
# so that 64 MB elephant flows use static ECMP while short flows use REPS/FREEZING.
# ──────────────────────────────────────────────────────────────
BASE128="-sender_cc_only -disable_tor_ecn
  -load_balancing_algo freezing
  -topo $TOPO_DIR/fat_tree_128_1os_3t_800g_paper.topo
  -linkspeed 800000 -hop_latency 0.5 -q 200 -ecn 10 10 -cwnd 120
  -target_q_delay 1 -paths 65535 -sack_threshold 4000 -end 90000
  -ecmp_elephant_threshold 33554432"

# 250-node 400 Gbps topology (Fig 8).  Link speed matches topology rating.
BASE250="-sender_cc_only -disable_tor_ecn
  -load_balancing_algo freezing
  -topo $TOPO_DIR/fat_tree_250_1os_3t_400g_paper.topo
  -linkspeed 400000 -hop_latency 0.5 -q 200 -ecn 10 10 -cwnd 120
  -target_q_delay 1 -paths 65535 -sack_threshold 4000 -end 90000
  -ecmp_elephant_threshold 33554432"

CCAS="swift lswift mswift nscc mnscc"
SEEDS="42 43 44"

# ──────────────────────────────────────────────────────────────
# run_sim TAG CC SEED TM_FILE EXTRA_FLAGS
#   TAG  — short label used in output filename, e.g. "fig4"
#   EXTRA_FLAGS — optional extra simulator flags (e.g. -failed_link_ratio)
# ──────────────────────────────────────────────────────────────
run_sim() {
    local tag="$1" cc="$2" seed="$3" tm="$4"
    shift 4
    local extra="${*:-}"

    local outfile="$DATA_DIR/${tag}_${cc}_s${seed}.out"
    if [ -f "$outfile" ]; then
        echo "[skip] $outfile already exists"
        return 0
    fi

    local base_flags
    if echo "$tag" | grep -q "fig8"; then
        base_flags="$BASE250"
    else
        base_flags="$BASE128"
    fi

    echo "[run] $tag $cc seed=$seed  →  $(basename "$outfile")"
    # shellcheck disable=SC2086
    "$BIN" $base_flags -sender_cc_algo "$cc" -seed "$seed" -tm "$tm" $extra \
        > "$outfile" 2>&1
}

# Fig 12 variants — same runner but with different -swift_median_pct
run_sim_pct() {
    local tag="$1" cc="$2" seed="$3" tm="$4" pct="$5"
    local outfile="$DATA_DIR/${tag}_${cc}_p${pct}_s${seed}.out"
    if [ -f "$outfile" ]; then
        echo "[skip] $outfile already exists"
        return 0
    fi
    echo "[run] $tag $cc pct=$pct seed=$seed  →  $(basename "$outfile")"
    # shellcheck disable=SC2086
    "$BIN" $BASE128 -sender_cc_algo "$cc" -swift_median_pct "$pct" \
        -seed "$seed" -tm "$tm" > "$outfile" 2>&1
}

export -f run_sim run_sim_pct

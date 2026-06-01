#!/usr/bin/env bash
# ============================================================
# exp13 lib_common.sh — Shared variables and run_sim() helpers
# for REPS-only reproduction of REPS-new (Paper 1) and
# Congestion Control for Spraying (Paper 2).
# Source this file; do not execute directly.
# ============================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
WL_DIR="$REPO_ROOT/state_aware_experiments/workloads"   # Paper 2 workloads
TOPO_DIR="$REPO_ROOT/htsim/sim/datacenter/topologies/reps"
EXP_DIR="$REPO_ROOT/state_aware_experiments/exp13_papers_reps_repro"
DATA_DIR="$EXP_DIR/data"

mkdir -p "$DATA_DIR"

# ──────────────────────────────────────────────────────────────
# Paper 1 (REPS, arXiv:2407.21625) §4.1
#   - 2-tier or 3-tier fat-tree
#   - 400 Gbps, 0.5 µs/hop, MTU 4 KB
#   - Queue = 1 BDP. At BDP 60 pkts (≈ 8 hops × 500ns + transmission):
#     -q 60  -ecn 12 48  (Kmin = 20% of queue, Kmax = 80%)
#   - RTO 70 µs (via new -min_rto flag)
#   - REPS buffer = 8 (default in buffer_reps.cpp)
#   - CC: "DCTCP variant from MPRDMA" → mprdma
#   - EVS = 65 536 paths → -paths 65535
# ──────────────────────────────────────────────────────────────

# 128-node 2-tier (Paper 1 small)
BASE_P1_128_2T="-sender_cc_only -disable_tor_ecn -enable_qa_gate
  -sender_cc_algo mprdma
  -topo $TOPO_DIR/fat_tree_128_1os_2t_400g_paper.topo
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -min_rto 70 -other_location
  -paths 65535 -sack_threshold 4000 -end 90000"

# 128-node 3-tier (Paper 1 §D.2 sensitivity)
BASE_P1_128_3T="-sender_cc_only -disable_tor_ecn -enable_qa_gate
  -sender_cc_algo mprdma
  -topo $TOPO_DIR/fat_tree_128_1os_3t_400g_paper.topo
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -min_rto 70 -other_location
  -paths 65535 -sack_threshold 4000 -end 90000"

# 1024-node 2-tier (Paper 1 large; not used in 6h budget but kept for completeness)
BASE_P1_1024_2T="-sender_cc_only -disable_tor_ecn -enable_qa_gate
  -sender_cc_algo mprdma
  -topo $TOPO_DIR/fat_tree_1024_1os_2t_400g_paper.topo
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -min_rto 70 -other_location
  -paths 65535 -sack_threshold 4000 -end 90000"

# ──────────────────────────────────────────────────────────────
# Paper 2 (CC4Spraying, arXiv:2509.07907v2) §IV-A
#   - 3-tier fat-tree, 128 or 250 nodes
#   - 800 Gbps (400 G for Fig 8), 0.5 µs/hop, MTU 4 KB
#   - Buffer 800 KB → -q 200 (200·4KB)
#   - ECN 40 KB (low = high) → -ecn 10 10
#   - Target Q-delay 1 µs → -target_q_delay 1
#   - Init cwnd = BDP → -cwnd 120
#   - REPS only as LB → -load_balancing_algo freezing
#   - Mixed ECMP-elephant + REPS-sprayed via -ecmp_elephant_threshold 32 MB
# ──────────────────────────────────────────────────────────────

BASE_P2_128="-sender_cc_only -disable_tor_ecn
  -load_balancing_algo freezing
  -topo $TOPO_DIR/fat_tree_128_1os_3t_800g_paper.topo
  -linkspeed 800000 -hop_latency 0.5
  -q 200 -ecn 10 10 -cwnd 120
  -target_q_delay 1
  -paths 65535 -sack_threshold 4000 -end 90000
  -ecmp_elephant_threshold 33554432"

BASE_P2_250="-sender_cc_only -disable_tor_ecn
  -load_balancing_algo freezing
  -topo $TOPO_DIR/fat_tree_250_1os_3t_400g_paper.topo
  -linkspeed 400000 -hop_latency 0.5
  -q 200 -ecn 10 10 -cwnd 120
  -target_q_delay 1
  -paths 65535 -sack_threshold 4000 -end 90000
  -ecmp_elephant_threshold 33554432"

# 3 seeds per cell (paper default)
SEEDS="42 43 44"

# Paper 2 CCAs (Swift collapses in Fig 4; excluded after that)
CCAS_P2_FIG4="swift lswift mswift nscc mnscc"
CCAS_P2_OTHER="lswift mswift nscc mnscc"

# Paper 1 LBs (for ratio computation only)
LBS_P1="freezing ecmp oblivious"

# ──────────────────────────────────────────────────────────────
# run_p1 FIG LB SEED TM_FILE [EXTRA_FLAGS...]
#   Paper 1 wrapper (MPRDMA CC, 2-tier 128n by default).
#   Use run_p1_3t for 3-tier.
# ──────────────────────────────────────────────────────────────
run_p1() {
    local fig="$1" lb="$2" seed="$3" tm="$4"
    shift 4
    local extra="${*:-}"

    local tm_tag
    tm_tag=$(basename "$tm" .cm)
    local outfile="$DATA_DIR/p1_${fig}_${lb}_${tm_tag}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")"
        return 0
    fi

    echo "[run] $fig $lb $tm_tag s$seed"
    # shellcheck disable=SC2086
    # cd into htsim/sim/datacenter so the failuregenerator's relative paths
    # to ../failures_input/saved/ resolve correctly (avoids spurious "Error
    # opening file3!" at end-of-run; the sim itself works either way).
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $BASE_P1_128_2T -load_balancing_algo "$lb" -seed "$seed" -tm "$tm" $extra) \
        > "$outfile" 2>&1
}

# Same as run_p1 but uses the 3-tier topology.
run_p1_3t() {
    local fig="$1" lb="$2" seed="$3" tm="$4"
    shift 4
    local extra="${*:-}"

    local tm_tag
    tm_tag=$(basename "$tm" .cm)
    local outfile="$DATA_DIR/p1_${fig}_${lb}_${tm_tag}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")"
        return 0
    fi
    echo "[run-3t] $fig $lb $tm_tag s$seed"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $BASE_P1_128_3T -load_balancing_algo "$lb" -seed "$seed" -tm "$tm" $extra) \
        > "$outfile" 2>&1
}

# ──────────────────────────────────────────────────────────────
# run_p2 FIG CCA SEED TM_FILE [EXTRA_FLAGS...]
#   Wrapper for Paper 2 runs.
# ──────────────────────────────────────────────────────────────
run_p2() {
    local fig="$1" cca="$2" seed="$3" tm="$4"
    shift 4
    local extra="${*:-}"

    local outfile="$DATA_DIR/p2_${fig}_${cca}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")"
        return 0
    fi

    local base
    if echo "$fig" | grep -q "fig08"; then
        base="$BASE_P2_250"
    else
        base="$BASE_P2_128"
    fi

    echo "[run] $fig $cca s$seed"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $base -sender_cc_algo "$cca" -seed "$seed" -tm "$tm" $extra) \
        > "$outfile" 2>&1
}

# Paper 2 Fig 12: MSwift with -swift_median_pct sweep
run_p2_pct() {
    local fig="$1" pct="$2" seed="$3" tm="$4"
    shift 4
    local extra="${*:-}"

    local outfile="$DATA_DIR/p2_${fig}_mswift_p${pct}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")"
        return 0
    fi
    echo "[run] $fig mswift P${pct} s$seed"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $BASE_P2_128 -sender_cc_algo mswift -swift_median_pct "$pct" \
        -seed "$seed" -tm "$tm" $extra) > "$outfile" 2>&1
}

export -f run_p1 run_p2 run_p2_pct

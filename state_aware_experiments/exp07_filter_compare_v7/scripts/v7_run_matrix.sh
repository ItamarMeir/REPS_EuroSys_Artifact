#!/usr/bin/env bash
# v7_run_matrix.sh — exp07 driver
#
# Filter comparison: vanilla NSCC+REPS vs WTD (paper's §3.6.1 mechanism)
# vs smart-filter Modes A and B (two counter sources each).
#
# Design matrix: 6 modes × 4 workloads × 2 severities × 3 seeds = 144 cells
#
# Modes:
#   vanilla         — no extra flags (paper baseline)
#   wtd             — -wtd_in_nscc
#   sf_md_gain_ecn  — -smart_filter_mode md_gain -smart_filter_counter ecn
#   sf_md_gain_fresh— -smart_filter_mode md_gain -smart_filter_counter fresh
#   sf_blend_ecn    — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn
#   sf_blend_fresh  — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh
#
# Idempotent: skips runs whose run.out already exists.
# Always passes -disable_tor_ecn (mandatory with -sender_cc_only).
# Default B=8, EV domain = paths=65535 (full fat-tree entropy space).
#
# Usage: bash v7_run_matrix.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_400g.topo"
CM_DIR="${HTSIM_DIR}/connection_matrices"
WORKLOADS_DIR="${REPO_ROOT}/state_aware_experiments/workloads"
EXP_DIR="${SCRIPT_DIR}/.."
OUT_ROOT="${EXP_DIR}/runs"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[dry-run] Printing commands only — no runs will be executed"
fi

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [[ ! -x "${HTSIM}" ]]; then
    echo "ERROR: binary not found at ${HTSIM}" >&2
    echo "  Build with: cd htsim/sim && make -j8 && cd datacenter && make -j8" >&2
    exit 1
fi
if [[ ! -f "${TOPO}" ]]; then
    echo "ERROR: topology not found: ${TOPO}" >&2; exit 1
fi

# ── Design axes ────────────────────────────────────────────────────────────────
MODES=(vanilla wtd sf_md_gain_ecn sf_md_gain_fresh sf_blend_ecn sf_blend_fresh)
WORKLOADS=(pureperm_8mb composite perm_32mb perm_128mb)
SEVERITIES=(0 4)
SEEDS=(42 43 44)

# ── Common simulator flags ─────────────────────────────────────────────────────
# -paths 65535: use full fat-tree entropy domain (matches exp06 design)
# -reps_buffer_size 8: default B=8
read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 -paths 65535 \
-sender_cc_only -sender_cc_algo nscc \
-load_balancing_algo freezing -exit_freeze 200000000 \
-topo ${TOPO} -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 \
-disable_tor_ecn"

# ── Mode → extra flags mapping ─────────────────────────────────────────────────
mode_flags() {
    local mode="$1"
    case "${mode}" in
        vanilla)          echo "" ;;
        wtd)              echo "-wtd_in_nscc" ;;
        sf_md_gain_ecn)   echo "-smart_filter_mode md_gain -smart_filter_counter ecn" ;;
        sf_md_gain_fresh) echo "-smart_filter_mode md_gain -smart_filter_counter fresh" ;;
        sf_blend_ecn)     echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn" ;;
        sf_blend_fresh)   echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh" ;;
        *) echo "ERROR: unknown mode ${mode}" >&2; exit 1 ;;
    esac
}

# ── TM path helper ─────────────────────────────────────────────────────────────
tm_for_workload() {
    local wname="$1" seed="$2"
    case "${wname}" in
        pureperm_8mb) echo "${CM_DIR}/perm_n128_s8388608.cm" ;;
        composite)    echo "${WORKLOADS_DIR}/composite.cm" ;;
        perm_32mb)    echo "${CM_DIR}/perm_128n_128c_32MB_s${seed}.cm" ;;
        perm_128mb)   echo "${CM_DIR}/perm_128n_128c_128MB_s${seed}.cm" ;;
        *) echo "ERROR: unknown workload ${wname}" >&2; exit 1 ;;
    esac
}

# ── Progress tracking ──────────────────────────────────────────────────────────
total=$(( ${#MODES[@]} * ${#WORKLOADS[@]} * ${#SEVERITIES[@]} * ${#SEEDS[@]} ))
done_count=0
skip_count=0
fail_count=0
start_time=$(date +%s)

# ── Core run function ──────────────────────────────────────────────────────────
run_one() {
    local mode="$1" wname="$2" sev="$3" seed="$4"

    local tm; tm=$(tm_for_workload "${wname}" "${seed}")
    if [[ ! -f "${tm}" ]]; then
        echo "  ERROR: TM not found: ${tm}" >&2
        fail_count=$(( fail_count + 1 ))
        done_count=$(( done_count + 1 ))
        return 1
    fi

    local outdir="${OUT_ROOT}/${mode}/${wname}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"
    local logfile="${outdir}/reps_state.csv"

    # Build CLI
    local extra_flags; extra_flags=$(mode_flags "${mode}")
    read -ra extra_arr <<< "${extra_flags}"

    local cli=("${HTSIM}" "${COMMON_FLAGS[@]}"
        -tm "${tm}" -seed "${seed}"
        "${extra_arr[@]+"${extra_arr[@]}"}"
    )
    # Capture 3 source IDs for per-ACK diagnostics
    cli+=(-log_reps_state "${logfile}"
          -log_reps_state_src 0
          -log_reps_state_src 7
          -log_reps_state_src 63)
    if [[ "${sev}" -gt 0 ]]; then
        cli+=(-fail_link_time 50 200 -fail_link_target 0 0)
    fi

    done_count=$(( done_count + 1 ))

    if "${DRY_RUN}"; then
        echo "[${done_count}/${total}] DRY: ${cli[*]} > ${outfile}"
        return 0
    fi

    # Idempotency: skip if output already exists
    if [[ -f "${outfile}" ]]; then
        skip_count=$(( skip_count + 1 ))
        printf "[%d/%d] SKIP  %s/%s/sev%s/seed%s\n" \
            "${done_count}" "${total}" "${mode}" "${wname}" "${sev}" "${seed}"
        return 0
    fi

    mkdir -p "${outdir}"

    local cell_start; cell_start=$(date +%s)
    "${cli[@]}" > "${outfile}" 2>&1
    local rc=$?
    local cell_dur=$(( $(date +%s) - cell_start ))
    local elapsed=$(( $(date +%s) - start_time ))

    # Guard checks
    if ! grep -q "^Flow" "${outfile}" 2>/dev/null; then
        echo "  WARNING: no Flow lines in ${outfile}" >&2
        fail_count=$(( fail_count + 1 ))
    fi
    if grep -q "enable on tor downlink 1" "${outfile}" 2>/dev/null; then
        echo "  ERROR: 'enable on tor downlink 1' detected in ${outfile} — -disable_tor_ecn was ineffective!" >&2
        fail_count=$(( fail_count + 1 ))
    fi
    if [[ "${rc}" -ne 0 ]]; then
        fail_count=$(( fail_count + 1 ))
    fi

    printf "[%d/%d] %s  %s/%s/sev%s/seed%s  rc=%d  cell=%ds  elapsed=%ds\n" \
        "${done_count}" "${total}" \
        "$([ ${rc} -eq 0 ] && echo OK || echo FAIL)" \
        "${mode}" "${wname}" "${sev}" "${seed}" \
        "${rc}" "${cell_dur}" "${elapsed}"
}

# ── Main loop ─────────────────────────────────────────────────────────────────
echo "=== exp07 filter comparison (${total} cells) ==="
echo "  Modes:     ${MODES[*]}"
echo "  Workloads: ${WORKLOADS[*]}"
echo "  Severities: ${SEVERITIES[*]}"
echo "  Seeds:     ${SEEDS[*]}"
echo ""

for mode in "${MODES[@]}"; do
    for wname in "${WORKLOADS[@]}"; do
        for sev in "${SEVERITIES[@]}"; do
            for seed in "${SEEDS[@]}"; do
                run_one "${mode}" "${wname}" "${sev}" "${seed}"
            done
        done
    done
done

new_runs=$(( done_count - skip_count - fail_count ))
echo ""
echo "Done. Total: ${done_count}  Skipped: ${skip_count}  New: ${new_runs}  Failed: ${fail_count}"
echo "Outputs under: ${OUT_ROOT}"

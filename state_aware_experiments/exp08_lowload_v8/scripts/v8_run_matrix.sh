#!/usr/bin/env bash
# v8_run_matrix.sh — exp08 driver
#
# Low-load filter comparison: same 8 modes as exp07 (including the new
# evhealth counter) on sparse traffic matrices where outlier-EV spatial
# collisions actually occur.
#
# Design matrix: 8 modes × 3 workloads × 2 severities × 5 seeds = 240 cells
#
# Workloads:
#   perm_2c_8mb  — 2 concurrent 8 MB flows  (WTD targeted test, Part C)
#   perm_16c_8mb — 16 concurrent 8 MB flows (low load)
#   perm_32c_8mb — 32 concurrent 8 MB flows (moderate low load)
#
# Modes (same as exp07 + two new evhealth modes):
#   vanilla             — no extra flags (paper baseline)
#   wtd                 — -wtd_in_nscc
#   sf_md_gain_ecn      — -smart_filter_mode md_gain -smart_filter_counter ecn
#   sf_md_gain_fresh    — -smart_filter_mode md_gain -smart_filter_counter fresh
#   sf_blend_ecn        — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn
#   sf_blend_fresh      — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh
#   sf_md_gain_evhealth — -smart_filter_mode md_gain -smart_filter_counter evhealth
#   sf_blend_evhealth   — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter evhealth
#
# Idempotent: skips runs whose run.out already exists.
# Always passes -disable_tor_ecn (mandatory with -sender_cc_only).
# Default B=8, EV domain = paths=65535 (full fat-tree entropy space).
#
# Prerequisite: run gen_sparse_workloads.py first to create the TMs.
# Usage: bash v8_run_matrix.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_400g.topo"
CM_DIR="${HTSIM_DIR}/connection_matrices"
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
MODES=(vanilla wtd sf_md_gain_ecn sf_md_gain_fresh sf_blend_ecn sf_blend_fresh
       sf_md_gain_evhealth sf_blend_evhealth)
WORKLOADS=(perm_2c_8mb perm_16c_8mb perm_32c_8mb)
SEVERITIES=(0 4)
SEEDS=(42 43 44 45 46)

# ── Common simulator flags ─────────────────────────────────────────────────────
read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 -paths 65535 \
-sender_cc_only -sender_cc_algo nscc \
-load_balancing_algo freezing -exit_freeze 200000000 \
-topo ${TOPO} -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 \
-disable_tor_ecn"

# ── Mode → extra flags mapping ─────────────────────────────────────────────────
mode_flags() {
    local mode="$1"
    case "${mode}" in
        vanilla)              echo "" ;;
        wtd)                  echo "-wtd_in_nscc" ;;
        sf_md_gain_ecn)       echo "-smart_filter_mode md_gain -smart_filter_counter ecn" ;;
        sf_md_gain_fresh)     echo "-smart_filter_mode md_gain -smart_filter_counter fresh" ;;
        sf_blend_ecn)         echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn" ;;
        sf_blend_fresh)       echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh" ;;
        sf_md_gain_evhealth)  echo "-smart_filter_mode md_gain -smart_filter_counter evhealth" ;;
        sf_blend_evhealth)    echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter evhealth" ;;
        *) echo "ERROR: unknown mode ${mode}" >&2; exit 1 ;;
    esac
}

# ── TM path helper ─────────────────────────────────────────────────────────────
tm_for_workload() {
    local wname="$1" seed="$2"
    case "${wname}" in
        perm_2c_8mb)  echo "${CM_DIR}/perm_128n_2c_8MB_s${seed}.cm" ;;
        perm_16c_8mb) echo "${CM_DIR}/perm_128n_16c_8MB_s${seed}.cm" ;;
        perm_32c_8mb) echo "${CM_DIR}/perm_128n_32c_8MB_s${seed}.cm" ;;
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
        echo "  Run gen_sparse_workloads.py first." >&2
        fail_count=$(( fail_count + 1 ))
        done_count=$(( done_count + 1 ))
        return 1
    fi

    local outdir="${OUT_ROOT}/${mode}/${wname}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"
    local logfile="${outdir}/reps_state.csv"

    local extra_flags; extra_flags=$(mode_flags "${mode}")
    read -ra extra_arr <<< "${extra_flags}"

    local cli=("${HTSIM}" "${COMMON_FLAGS[@]}"
        -tm "${tm}" -seed "${seed}"
        "${extra_arr[@]+"${extra_arr[@]}"}"
    )
    # Log 3 source IDs for per-ACK diagnostics.
    # For 2-flow workload, only source 0 exists — extra -log_reps_state_src values
    # for sources 7 and 63 are silently ignored if those sources don't exist.
    cli+=(-log_reps_state "${logfile}"
          -log_reps_state_src 0
          -log_reps_state_src 1
          -log_reps_state_src 7)
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
        echo "  ERROR: 'enable on tor downlink 1' detected — -disable_tor_ecn was ineffective!" >&2
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
echo "=== exp08 low-load filter comparison (${total} cells) ==="
echo "  Modes:      ${MODES[*]}"
echo "  Workloads:  ${WORKLOADS[*]}"
echo "  Severities: ${SEVERITIES[*]}"
echo "  Seeds:      ${SEEDS[*]}"
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

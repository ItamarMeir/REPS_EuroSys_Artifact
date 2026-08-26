#!/usr/bin/env bash
# v9_run_matrix.sh — exp09 driver (Real-CDF workload filter comparison)
#
# Two-phase design:
#   --phase1 (default) — 24 cells: vanilla only × 2 CDFs × 3 loads × 2 sev × 2 seeds
#   --phase2            — 288 cells: all 8 modes × 2 CDFs × 3 loads × 2 sev × 3 seeds
#                         Idempotent — phase1 cells are reused (skip-if-exists).
#
# Modes (same as exp07/08):
#   vanilla             — paper baseline (no extra flags)
#   wtd                 — -wtd_in_nscc
#   sf_md_gain_ecn      — -smart_filter_mode md_gain -smart_filter_counter ecn
#   sf_md_gain_fresh    — -smart_filter_mode md_gain -smart_filter_counter fresh
#   sf_blend_ecn        — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn
#   sf_blend_fresh      — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh
#   sf_md_gain_evhealth — -smart_filter_mode md_gain -smart_filter_counter evhealth
#   sf_blend_evhealth   — -smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter evhealth
#
# Prerequisite: run gen_cdf_workloads.py first.
# Usage: bash v9_run_matrix.sh [--phase1|--phase2] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_400g.topo"
CM_DIR="${HTSIM_DIR}/connection_matrices"
EXP_DIR="${SCRIPT_DIR}/.."
OUT_ROOT="${EXP_DIR}/runs"

# ── Argument parsing ───────────────────────────────────────────────────────────
PHASE=1
DRY_RUN=false
for arg in "$@"; do
    case "${arg}" in
        --phase1)   PHASE=1 ;;
        --phase2)   PHASE=2 ;;
        --dry-run)  DRY_RUN=true ;;
        *) echo "Unknown argument: ${arg}" >&2; exit 1 ;;
    esac
done

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
# Phase-1: vanilla only, 2 seeds
P1_MODES=(vanilla)
P1_SEEDS=(42 43)

# Phase-2: all 8 modes, 3 seeds (phase1 cells are idempotently skipped)
P2_MODES=(vanilla wtd sf_md_gain_ecn sf_md_gain_fresh sf_blend_ecn sf_blend_fresh
          sf_md_gain_evhealth sf_blend_evhealth)
P2_SEEDS=(42 43 44)

WORKLOADS=(websearch hadoop)
LOADS=(30 60 90)
SEVERITIES=(0 4)

if [[ "${PHASE}" -eq 1 ]]; then
    MODES=("${P1_MODES[@]}")
    SEEDS=("${P1_SEEDS[@]}")
else
    MODES=("${P2_MODES[@]}")
    SEEDS=("${P2_SEEDS[@]}")
fi

# ── Common simulator flags ─────────────────────────────────────────────────────
read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 -paths 65535 \
-sender_cc_only -sender_cc_algo nscc \
-load_balancing_algo freezing -exit_freeze 200000000 \
-topo ${TOPO} -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 \
-disable_tor_ecn"

# ── Mode → extra flags ─────────────────────────────────────────────────────────
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
tm_path() {
    local wname="$1" load_pct="$2" seed="$3"
    printf '%s/cdf_%s_l%02d_s%d.cm' "${CM_DIR}" "${wname}" "${load_pct}" "${seed}"
}

# ── Progress ───────────────────────────────────────────────────────────────────
total=$(( ${#MODES[@]} * ${#WORKLOADS[@]} * ${#LOADS[@]} * ${#SEVERITIES[@]} * ${#SEEDS[@]} ))
done_count=0
skip_count=0
fail_count=0
start_time=$(date +%s)

# ── Core run function ──────────────────────────────────────────────────────────
run_one() {
    local mode="$1" wname="$2" load_pct="$3" sev="$4" seed="$5"

    local tm; tm=$(tm_path "${wname}" "${load_pct}" "${seed}")
    if [[ ! -f "${tm}" ]]; then
        echo "  ERROR: TM not found: ${tm}" >&2
        echo "  Run gen_cdf_workloads.py first." >&2
        (( fail_count++ )) || true
        (( done_count++ )) || true
        return 1
    fi

    local outdir="${OUT_ROOT}/${mode}/${wname}/l${load_pct}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"
    local logfile="${outdir}/reps_state.csv"

    local extra_flags; extra_flags=$(mode_flags "${mode}")
    read -ra extra_arr <<< "${extra_flags}"

    local cli=("${HTSIM}" "${COMMON_FLAGS[@]}"
        -tm "${tm}" -seed "${seed}"
        "${extra_arr[@]+"${extra_arr[@]}"}"
        -log_reps_state "${logfile}"
        -log_reps_state_src 0
        -log_reps_state_src 1
        -log_reps_state_src 7
    )
    if [[ "${sev}" -gt 0 ]]; then
        cli+=(-fail_link_time 50 200 -fail_link_target 0 0)
    fi

    (( done_count++ )) || true

    if "${DRY_RUN}"; then
        echo "[${done_count}/${total}] DRY: ${cli[*]} > ${outfile}"
        return 0
    fi

    if [[ -f "${outfile}" ]]; then
        (( skip_count++ )) || true
        printf "[%d/%d] SKIP  %s/%s/l%s/sev%s/seed%s\n" \
            "${done_count}" "${total}" "${mode}" "${wname}" "${load_pct}" "${sev}" "${seed}"
        return 0
    fi

    mkdir -p "${outdir}"

    local cell_start; cell_start=$(date +%s)
    "${cli[@]}" > "${outfile}" 2>&1
    local rc=$?
    local cell_dur=$(( $(date +%s) - cell_start ))
    local elapsed=$(( $(date +%s) - start_time ))

    if ! grep -q "^Flow" "${outfile}" 2>/dev/null; then
        echo "  WARNING: no Flow lines in ${outfile}" >&2
        (( fail_count++ )) || true
    fi
    if grep -q "enable on tor downlink 1" "${outfile}" 2>/dev/null; then
        echo "  ERROR: 'enable on tor downlink 1' detected — -disable_tor_ecn ineffective!" >&2
        (( fail_count++ )) || true
    fi
    if [[ "${rc}" -ne 0 ]]; then
        (( fail_count++ )) || true
    fi

    printf "[%d/%d] %s  %s/%s/l%s/sev%s/seed%s  rc=%d  cell=%ds  elapsed=%ds\n" \
        "${done_count}" "${total}" \
        "$([ ${rc} -eq 0 ] && echo OK || echo FAIL)" \
        "${mode}" "${wname}" "${load_pct}" "${sev}" "${seed}" \
        "${rc}" "${cell_dur}" "${elapsed}"
}

# ── Main loop ─────────────────────────────────────────────────────────────────
echo "=== exp09 CDF filter comparison — Phase ${PHASE} (${total} cells) ==="
echo "  Modes:      ${MODES[*]}"
echo "  Workloads:  ${WORKLOADS[*]}"
echo "  Loads:      ${LOADS[*]}"
echo "  Severities: ${SEVERITIES[*]}"
echo "  Seeds:      ${SEEDS[*]}"
echo ""

if "${DRY_RUN}"; then
    echo "[dry-run] Printing commands only — no runs will be executed"
fi

for mode in "${MODES[@]}"; do
    for wname in "${WORKLOADS[@]}"; do
        for load_pct in "${LOADS[@]}"; do
            for sev in "${SEVERITIES[@]}"; do
                for seed in "${SEEDS[@]}"; do
                    run_one "${mode}" "${wname}" "${load_pct}" "${sev}" "${seed}"
                done
            done
        done
    done
done

new_runs=$(( done_count - skip_count - fail_count ))
echo ""
echo "Done. Total: ${done_count}  Skipped: ${skip_count}  New: ${new_runs}  Failed: ${fail_count}"
echo "Outputs under: ${OUT_ROOT}"

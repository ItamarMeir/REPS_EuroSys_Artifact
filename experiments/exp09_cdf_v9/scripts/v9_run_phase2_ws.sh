#!/usr/bin/env bash
# v9_run_phase2_ws.sh — Phase 2 runner, WebSearch only
#
# Phase 1 established: WebSearch l=90 has ECN (high_counter_rate=0.02-0.16).
# Hadoop has zero ECN at all loads and is excluded from Phase 2.
#
# Design: 8 modes × 1 CDF (websearch) × 3 loads × 2 sev × 3 seeds = 144 cells
# Phase 1 cells (vanilla, seeds 42-43) are idempotently skipped.
# New cells: 7 modes × 3 loads × 2 sev × 3 seeds = 126 cells
#            + vanilla/seed44 × 3 loads × 2 sev = 6 cells
#
# Runs J jobs in parallel (default J=4).
# Usage: bash v9_run_phase2_ws.sh [--jobs N] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_400g.topo"
CM_DIR="${HTSIM_DIR}/connection_matrices"
EXP_DIR="${SCRIPT_DIR}/.."
OUT_ROOT="${EXP_DIR}/runs"

MAX_JOBS=4
DRY_RUN=false
for arg in "$@"; do
    case "${arg}" in
        --jobs=*)   MAX_JOBS="${arg#--jobs=}" ;;
        --jobs)     shift; MAX_JOBS="$1" ;;
        --dry-run)  DRY_RUN=true ;;
        *) echo "Unknown arg: ${arg}" >&2; exit 1 ;;
    esac
done

if [[ ! -x "${HTSIM}" ]]; then
    echo "ERROR: binary not found at ${HTSIM}" >&2; exit 1
fi

MODES=(vanilla wtd sf_md_gain_ecn sf_md_gain_fresh sf_blend_ecn sf_blend_fresh
       sf_md_gain_evhealth sf_blend_evhealth)
WORKLOADS=(websearch)
LOADS=(30 60 90)
SEVERITIES=(0 4)
SEEDS=(42 43 44)

read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 -paths 65535 \
-sender_cc_only -sender_cc_algo nscc \
-load_balancing_algo freezing -exit_freeze 200000000 \
-topo ${TOPO} -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 \
-disable_tor_ecn"

mode_flags() {
    case "$1" in
        vanilla)              echo "" ;;
        wtd)                  echo "-wtd_in_nscc" ;;
        sf_md_gain_ecn)       echo "-smart_filter_mode md_gain -smart_filter_counter ecn" ;;
        sf_md_gain_fresh)     echo "-smart_filter_mode md_gain -smart_filter_counter fresh" ;;
        sf_blend_ecn)         echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn" ;;
        sf_blend_fresh)       echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh" ;;
        sf_md_gain_evhealth)  echo "-smart_filter_mode md_gain -smart_filter_counter evhealth" ;;
        sf_blend_evhealth)    echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter evhealth" ;;
        *) echo "ERROR: unknown mode $1" >&2; exit 1 ;;
    esac
}

tm_path() {
    printf '%s/cdf_%s_l%02d_s%d.cm' "${CM_DIR}" "$1" "$2" "$3"
}

# ── Build cell list ────────────────────────────────────────────────────────────
CELLS=()
for mode in "${MODES[@]}"; do
    for wname in "${WORKLOADS[@]}"; do
        for load_pct in "${LOADS[@]}"; do
            for sev in "${SEVERITIES[@]}"; do
                for seed in "${SEEDS[@]}"; do
                    CELLS+=("${mode}|${wname}|${load_pct}|${sev}|${seed}")
                done
            done
        done
    done
done

total=${#CELLS[@]}
done_count=0
skip_count=0
fail_count=0
start_time=$(date +%s)
active_jobs=0
declare -A job_pids

report_job() {
    local pid="$1"
    local label="${job_pids[$pid]}"
    local outfile="${job_pids_out[$pid]}"
    wait "${pid}"
    local rc=$?
    local elapsed=$(( $(date +%s) - start_time ))
    (( done_count++ )) || true
    local status="OK"
    if [[ "${rc}" -ne 0 ]]; then
        (( fail_count++ )) || true
        status="FAIL"
    elif ! grep -q "^Flow.*finished" "${outfile}" 2>/dev/null; then
        (( fail_count++ )) || true
        status="WARN(no flows)"
    fi
    printf "[%d/%d] %s  %s  elapsed=%ds\n" \
        "${done_count}" "${total}" "${status}" "${label}" "${elapsed}"
    unset "job_pids[$pid]"
    unset "job_pids_out[$pid]"
    (( active_jobs-- )) || true
}

declare -A job_pids_out

run_cell_bg() {
    local mode="$1" wname="$2" load_pct="$3" sev="$4" seed="$5"
    local label="${mode}/${wname}/l${load_pct}/sev${sev}/seed${seed}"

    local tm; tm=$(tm_path "${wname}" "${load_pct}" "${seed}")
    local outdir="${OUT_ROOT}/${mode}/${wname}/l${load_pct}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"
    local logfile="${outdir}/reps_state.csv"

    if [[ ! -f "${tm}" ]]; then
        echo "  WARN: TM missing: ${tm}" >&2
        (( fail_count++ )) || true
        return
    fi

    if [[ -f "${outfile}" ]]; then
        (( skip_count++ )) || true
        (( done_count++ )) || true
        printf "[%d/%d] SKIP  %s\n" "${done_count}" "${total}" "${label}"
        return
    fi

    if "${DRY_RUN}"; then
        echo "DRY: ${label}"
        (( done_count++ )) || true
        return
    fi

    mkdir -p "${outdir}"
    local extra_flags; extra_flags=$(mode_flags "${mode}")
    read -ra extra_arr <<< "${extra_flags}"

    (
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
        "${cli[@]}" > "${outfile}" 2>&1
    ) &
    local bg_pid=$!
    job_pids[$bg_pid]="${label}"
    job_pids_out[$bg_pid]="${outdir}/run.out"
    (( active_jobs++ )) || true
}

echo "=== exp09 Phase 2 — WebSearch only (${total} cells, J=${MAX_JOBS}) ==="
echo "  Modes:     ${MODES[*]}"
echo "  Workloads: ${WORKLOADS[*]}"
echo "  Loads:     ${LOADS[*]}"
echo "  Severities: ${SEVERITIES[*]}"
echo "  Seeds:      ${SEEDS[*]}"
echo ""
if "${DRY_RUN}"; then echo "[dry-run]"; fi

for cell in "${CELLS[@]}"; do
    IFS='|' read -r mode wname load_pct sev seed <<< "${cell}"

    # Throttle
    while [[ "${active_jobs}" -ge "${MAX_JOBS}" ]]; do
        reaped=false
        for pid in "${!job_pids[@]}"; do
            if ! kill -0 "${pid}" 2>/dev/null; then
                report_job "${pid}"
                reaped=true
                break
            fi
        done
        "${reaped}" || sleep 1
    done

    run_cell_bg "${mode}" "${wname}" "${load_pct}" "${sev}" "${seed}"
done

# Drain
while [[ "${active_jobs}" -gt 0 ]]; do
    for pid in "${!job_pids[@]}"; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            report_job "${pid}"
            break
        fi
    done
    sleep 1
done

new_runs=$(( done_count - skip_count - fail_count ))
echo ""
echo "Done. Total: ${done_count}  Skipped: ${skip_count}  New: ${new_runs}  Failed: ${fail_count}"
echo "Outputs under: ${OUT_ROOT}"

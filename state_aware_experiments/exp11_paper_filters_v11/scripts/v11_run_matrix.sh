#!/usr/bin/env bash
# v11_run_matrix.sh — exp11 paper-workload filter comparison.
#
# 8 modes × 4 paper workloads × 2 sev × 3 seeds = 192 cells.
# Topology: 800 Gbps 3-tier 128-host fat-tree.
# Queue/ECN/cwnd settings are paper-faithful (-q 200 -ecn 10 50 -cwnd 100).
#
# Usage:
#   bash v11_run_matrix.sh [--jobs N] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_800g.topo"
PAPER_WL_DIR="${REPO_ROOT}/state_aware_experiments/workloads"
PERM_TM="${HTSIM_DIR}/connection_matrices/perm_n128_s8388608.cm"
EXP_DIR="${SCRIPT_DIR}/.."
OUT_ROOT="${EXP_DIR}/runs"

MAX_JOBS=4
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --jobs=*)   MAX_JOBS="${1#--jobs=}" ;;
        --jobs)     shift; MAX_JOBS="$1" ;;
        --dry-run)  DRY_RUN=true ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ ! -x "${HTSIM}" ]]; then
    echo "ERROR: binary not found: ${HTSIM}" >&2; exit 1
fi

# ── Design axes ─────────────────────────────────────────────────────────────────
MODES=(vanilla wtd
       sf_md_gain_ecn sf_md_gain_fresh sf_md_gain_evhealth
       sf_blend_ecn sf_blend_fresh sf_blend_evhealth)
WORKLOADS=(baseline perm hsdp incast32)
SEVERITIES=(0 4)
SEEDS=(42 43 44)

# ── Common simulator flags (paper-faithful 800 G) ──────────────────────────────
read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 -paths 65535 \
-sender_cc_only -sender_cc_algo nscc \
-load_balancing_algo freezing -exit_freeze 200000000 \
-topo ${TOPO} -linkspeed 800000 \
-q 200 -ecn 10 50 -cwnd 100 \
-disable_tor_ecn"

mode_flags() {
    case "$1" in
        vanilla)              echo "" ;;
        wtd)                  echo "-wtd_in_nscc" ;;
        sf_md_gain_ecn)       echo "-smart_filter_mode md_gain -smart_filter_counter ecn" ;;
        sf_md_gain_fresh)     echo "-smart_filter_mode md_gain -smart_filter_counter fresh" ;;
        sf_md_gain_evhealth)  echo "-smart_filter_mode md_gain -smart_filter_counter evhealth" ;;
        sf_blend_ecn)         echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter ecn" ;;
        sf_blend_fresh)       echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter fresh" ;;
        sf_blend_evhealth)    echo "-smart_filter_mode rtt_blend_ecn_thresh -smart_filter_counter evhealth" ;;
        *) echo "ERROR: unknown mode $1" >&2; exit 1 ;;
    esac
}

tm_path() {
    local workload="$1" seed="$2"
    case "${workload}" in
        baseline) printf '%s/paper_baseline_s%d.cm' "${PAPER_WL_DIR}" "${seed}" ;;
        hsdp)     printf '%s/paper_hsdp_s%d.cm'     "${PAPER_WL_DIR}" "${seed}" ;;
        incast32) printf '%s/paper_incast32_s%d.cm' "${PAPER_WL_DIR}" "${seed}" ;;
        perm)     printf '%s' "${PERM_TM}" ;;
        *) echo "ERROR: unknown workload ${workload}" >&2; exit 1 ;;
    esac
}

# ── Cell list ───────────────────────────────────────────────────────────────────
CELLS=()
for mode in "${MODES[@]}"; do
    for wname in "${WORKLOADS[@]}"; do
        for sev in "${SEVERITIES[@]}"; do
            for seed in "${SEEDS[@]}"; do
                CELLS+=("${mode}|${wname}|${sev}|${seed}")
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
declare -A job_pids_out

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
        status="FAIL(rc=${rc})"
    elif ! grep -q "finished at" "${outfile}" 2>/dev/null; then
        (( fail_count++ )) || true
        status="WARN(no flows)"
    fi
    printf "[%d/%d] %s  %s  elapsed=%ds\n" \
        "${done_count}" "${total}" "${status}" "${label}" "${elapsed}"
    unset "job_pids[$pid]"
    unset "job_pids_out[$pid]"
    (( active_jobs-- )) || true
}

run_cell_bg() {
    local mode="$1" wname="$2" sev="$3" seed="$4"
    local label="${mode}/${wname}/sev${sev}/seed${seed}"

    local tm; tm=$(tm_path "${wname}" "${seed}")
    local outdir="${OUT_ROOT}/${mode}/${wname}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"
    local logfile="${outdir}/reps_state.csv"

    if [[ ! -f "${tm}" ]]; then
        echo "  WARN: TM missing: ${tm}" >&2
        (( fail_count++ )) || true
        (( done_count++ )) || true
        return
    fi

    if [[ -f "${outfile}" ]]; then
        (( skip_count++ )) || true
        (( done_count++ )) || true
        printf "[%d/%d] SKIP  %s\n" "${done_count}" "${total}" "${label}"
        return
    fi

    if "${DRY_RUN}"; then
        printf "DRY: %s  tm=%s\n" "${label}" "${tm}"
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
    job_pids_out[$bg_pid]="${outfile}"
    (( active_jobs++ )) || true
}

echo "=== exp11 paper-workload filter comparison (${total} cells, J=${MAX_JOBS}) ==="
echo "  modes:     ${MODES[*]}"
echo "  workloads: ${WORKLOADS[*]}"
echo "  sev:       ${SEVERITIES[*]}"
echo "  seeds:     ${SEEDS[*]}"
echo "  topology:  ${TOPO##*/}"
echo "  paper-faithful: -q 200 -ecn 10 50 -cwnd 100 at 800 Gbps"
echo ""
"${DRY_RUN}" && echo "[dry-run mode]"

for cell in "${CELLS[@]}"; do
    IFS='|' read -r mode wname sev seed <<< "${cell}"

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

    run_cell_bg "${mode}" "${wname}" "${sev}" "${seed}"
done

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

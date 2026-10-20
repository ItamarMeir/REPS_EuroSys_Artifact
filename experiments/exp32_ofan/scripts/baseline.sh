#!/usr/bin/env bash
# Regression baseline for the fat_tree_switch / main_uec change. Run INSIDE container ofan-dev:
#   docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/baseline.sh [outdir]
# Default outdir = experiments/exp32_ofan/baseline (writes <cfg>.out + SHA256SUMS).
# Pass another outdir (e.g. .../after) to produce a comparable set, then diff SHA256SUMS.
# Each config is run twice; the run fails if the two outputs differ (determinism check).
# Workload: 16-host random permutation, 1 MiB flows, seed 42, fat_tree_16_1os_3t_400g (3-tier, 4 pods).
set -euo pipefail
R=/workspace
DC=$R/htsim/sim/datacenter
OUT=${1:-$R/experiments/exp32_ofan/baseline}
mkdir -p "$OUT"
COMMON=(-tm $R/experiments/exp32_ofan/workloads/perm16_1mb_s42.cm
        -topo $DC/topologies/reps/fat_tree_16_1os_3t_400g.topo
        -linkspeed 400000 -seed 42 -end 20000 -connections_mapping
        -sender_cc_only -sender_cc_algo nscc -disable_tor_ecn
        -load_balancing_algo freezing)
declare -A CFG=( [default]="" [ecmp_host]="-strat ecmp_host" [ecmp_ar]="-strat ecmp_ar" [ecmp_rr]="-strat ecmp_rr" [ofan]="-strat ofan -load_balancing_algo ecmp" )
ORDER=(default ecmp_host ecmp_ar ecmp_rr ofan)
run() { # $1=cfg $2=outfile ; run in private scratch cwd so logout.dat is not shared/tracked
  local d; d=$(mktemp -d)
  ( cd "$d" && $DC/htsim_uec "${COMMON[@]}" ${CFG[$1]} > "$2" 2>&1 )
  rm -rf "$d"
}
rm -f "$OUT/SHA256SUMS"
for c in "${ORDER[@]}"; do
  run "$c" "$OUT/$c.out"
  run "$c" "$OUT/$c.out.rerun"
  if ! cmp -s "$OUT/$c.out" "$OUT/$c.out.rerun"; then echo "NONDETERMINISTIC: $c"; exit 1; fi
  rm -f "$OUT/$c.out.rerun"
  echo "$c: deterministic ($(grep -c 'finished at' "$OUT/$c.out") flows finished)"
done
( cd "$OUT" && sha256sum default.out ecmp_host.out ecmp_ar.out ecmp_rr.out ofan.out | tee SHA256SUMS )

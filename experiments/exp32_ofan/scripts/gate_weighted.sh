#!/usr/bin/env bash
# Regression/identity gates for -strat ofan_weighted. Run INSIDE container ofan-dev:
#   docker exec ofan-dev bash /workspace/experiments/exp32_ofan/scripts/gate_weighted.sh
# PRE binary = copy of the pre-change htsim_uec (default /tmp/frozen/htsim_uec_pre_weighted).
set -uo pipefail
DC=/workspace/htsim/sim/datacenter; E=/workspace/experiments/exp32_ofan; PRE=${PRE:-/tmp/frozen/htsim_uec_pre_weighted}
bash $E/scripts/baseline.sh /tmp/bl_after >/dev/null 2>&1
diff /tmp/bl_after/SHA256SUMS $E/baseline/SHA256SUMS >/dev/null && echo "G1 BASELINE_IDENTICAL" || echo "G1 BASELINE_DIFFERS"
COMMON="-topo $DC/topologies/reps/fat_tree_54_1os_3t_400g.topo -tm $E/workloads/derange54_4mb_s42.cm -linkspeed 400000 -seed 42 -end 20000 -connections_mapping -sender_cc_only -disable_tor_ecn -q 193 -ecn 19 19 -sender_cc_algo nscc -load_balancing_algo ecmp"
F="-fail_link_time 0.01 1000000000 -fail_link_target 0 0 -routing_convergence_us 0"
W=$(mktemp -d); cd $W
$PRE $COMMON -strat ofan $F > pre.out 2>&1; $DC/htsim_uec $COMMON -strat ofan $F > post.out 2>&1
cmp -s pre.out post.out && echo "G2 OFAN_FAIL_IDENTICAL" || echo "G2 OFAN_FAIL_DIFFERS"
$DC/htsim_uec $COMMON -strat ofan -routing_convergence_us 0 > h1.out 2>&1; $DC/htsim_uec $COMMON -strat ofan_weighted -routing_convergence_us 0 > h2.out 2>&1
cmp -s h1.out h2.out && echo "G3 HEALTHY_WEIGHTED_IDENTICAL" || echo "G3 HEALTHY_WEIGHTED_DIFFERS"
$DC/htsim_uec $COMMON -strat ofan_weighted -fail_link_time 0.01 1000000000 -fail_link_target 0 0 > e.out 2>&1; echo "G3b ofan_weighted without -routing_convergence_us rc=$? (expect 1)"
# G4: filtered-vector path (ecmp_ar with a known failure) must be unchanged by the rc_lookup/RcEntry edits
$PRE $COMMON -strat ecmp_ar $F > pre_ar.out 2>&1; $DC/htsim_uec $COMMON -strat ecmp_ar $F > post_ar.out 2>&1
cmp -s pre_ar.out post_ar.out && echo "G4 ECMP_AR_FAIL_IDENTICAL" || echo "G4 ECMP_AR_FAIL_DIFFERS"
# G5: -routing_check pass (plain ofan, random known-down sets) must be unchanged by the check-pass edits
CK="-strat ofan -routing_convergence_us 5 -routing_check -routing_check_random 20 5 0.2"
$PRE $COMMON $CK > pre_ck.out 2>&1; $DC/htsim_uec $COMMON $CK > post_ck.out 2>&1
cmp -s pre_ck.out post_ck.out && echo "G5 ROUTING_CHECK_OFAN_IDENTICAL" || echo "G5 ROUTING_CHECK_OFAN_DIFFERS"
cd /; rm -rf $W

#!/bin/bash
# Extraction and identity checks of the DPS arm (graded fabric, cfg h512_p16g_msgNhDcap_*, 3 seeds, B = 8, 4 latencies), run in the container (/kneework16g). Nothing here runs a simulation.
# usage: bash extract_dps.sh <dps out dir> <result dir>
set -e
cd /kneework16g
D=${1:-/k16g_dps}; O=${2:-/k16g_out}
mkdir -p $O
cp $D/results.jsonl $O/dps_results.jsonl
python3 e_permessage.py 512 16 $O/dps_permessage.csv $D/results.jsonl $D/traces
for L in 250 1000 4000 16000; do
  nice python3 n_uplink_mech.py $D/traces $O/dps_um_$L.csv h512_p16g_msgNhDcap lat$L
done
python3 n_uplink_check.py $D/traces h512_p16g_msgNhDcap lat250_B8_s42 lat1000_B8_s43 lat4000_B8_s44 lat16000_B8_s42 > $O/dps_identity_checks.log
cat $O/dps_identity_checks.log
echo EXTRACT_DPS_DONE

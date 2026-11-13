#!/bin/bash
# Extraction and identity checks of the DPS arm (95% / 5%, cfg h512_p16_msgNhDcap_*), run in the container next to the other scripts (/kneework16).
# usage: bash extract_dps.sh <dps out dir> <result dir>      Nothing here runs a simulation.
set -e
cd /kneework16
D=${1:-/k16_dps}; O=${2:-/dpsout/res}
mkdir -p $O
cp $D/results.jsonl $O/dps_results.jsonl
python3 e_permessage.py 512 16 $O/dps_permessage.csv $D/results.jsonl $D/traces
for L in 250 500 1000 2000 4000 8000 16000; do
  nice python3 n_uplink_mech.py $D/traces $O/dps_um_$L.csv h512_p16_msgNhDcap lat$L
done
python3 n_uplink_check.py $D/traces h512_p16_msgNhDcap lat250_B8_s42 lat500_B8_s43 lat1000_B8_s44 lat2000_B8_s42 lat4000_B8_s43 lat8000_B8_s44 lat16000_B8_s42 > $O/dps_identity_checks.log
cat $O/dps_identity_checks.log
echo EXTRACT_DPS_DONE

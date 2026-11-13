#!/bin/bash
# DPS arm (95% / 5% only, -dps_dist capacity), 3 seeds, 7 latencies = 21 cells. Resumable. Run in the container (/kneework16).
cd /kneework16
mkdir -p /k16_dps
for L in 250 500 1000 2000 4000 8000 16000; do
  W=4; [ $L -gt 4000 ] && W=3
  nice python3 run_knee16.py --out /k16_dps --cfgs h512_p16_msgNhDcap_lat$L --seeds 42 43 44 --bsmap bsmap_knee16_dps.json --workers $W
done
echo DPS16_DONE

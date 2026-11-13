#!/bin/bash
# Worst-case pilot cell of the 16-path sweep (plan advisor item 1): lat 16000, B = 1536 (widest trace rows, 64 traced flows), both arms, one seed, run together.
# Samples the resident set of htsim_uec and of the in-cell analysis (python) every 5 s. Run in the container (m23-dev).
cd /kneework16
rm -rf /k16_worst_reps /k16_worst_god
echo '{"h512_p16_msgNh_lat16000":[1536],"h512_p16_msgNhG_lat16000":[1536]}' > /tmp/worst_bsmap.json
( nice python3 run_knee16.py --out /k16_worst_reps --cfgs h512_p16_msgNh_lat16000 --seeds 42 --bsmap /tmp/worst_bsmap.json --workers 1 > /k16_worst_reps.log 2>&1 ) &
( nice python3 run_knee16.py --out /k16_worst_god --cfgs h512_p16_msgNhG_lat16000 --seeds 42 --bsmap /tmp/worst_bsmap.json --workers 1 > /k16_worst_god.log 2>&1 ) &
: > /k16_worst_rss.log
while pgrep -f run_knee16.py > /dev/null; do
  echo "$(date +%s) $(ps -eo rss,comm | awk '$2=="htsim_uec"{s+=$1} $2=="python3"{p+=$1} END{print "htsim_kB",s+0,"python_kB",p+0}')" >> /k16_worst_rss.log
  sleep 5
done
echo WORST_DONE >> /k16_worst_rss.log

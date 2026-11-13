#!/bin/bash
# Full ladder of the 16-path study. Run in the container (m23-dev) as: docker exec -d m23-dev sh -c 'bash /kneework16/run_ladder16.sh > /k16_ladder.log 2>&1'
# Resumable (run_knee16.py skips cells already in results.jsonl). Order: seeds 42-45 for every latency and arm first, then seeds 46-49, so a usable half exists early.
# Worst cell (lat 16000, B 1536) measured 260-280 s and < 1 GB (htsim 0.6 GB + analysis 0.8 GB), so 4 workers for lat <= 4000 and 3 workers above (container 7.8 GB).
cd /kneework16
mkdir -p /k16_reps /k16_god /k16_sol
nice python3 run_knee16.py --out /k16_sol --cfgs $(for L in 250 500 1000 2000 4000 8000 16000; do echo h512_p16_sol_lat$L h512_p16_sol1p_lat$L; done) --seeds 42 43 44 45 46 47 48 49 --bsmap bsmap_knee16.json --workers 4
for SEEDS in "42 43 44 45" "46 47 48 49"; do
  for L in 250 500 1000 2000 4000 8000 16000; do
    W=4; [ $L -gt 4000 ] && W=3
    nice python3 run_knee16.py --out /k16_reps --cfgs h512_p16_msgNh_lat$L --seeds $SEEDS --bsmap bsmap_knee16.json --workers $W
    nice python3 run_knee16.py --out /k16_god --cfgs h512_p16_msgNhG_lat$L --seeds $SEEDS --bsmap bsmap_knee16.json --workers $W
  done
done
echo LADDER16_DONE

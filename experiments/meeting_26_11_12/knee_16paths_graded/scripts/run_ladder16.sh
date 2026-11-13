#!/bin/bash
# Stage 1 of knee_16paths_graded: 4 latencies x 4 seeds (42-45) x 52 B values per arm (REPS, god), DPS 3 seeds, speed-of-light smoke (2 cells).
# Run inside the container: docker exec -d dps-dev sh -c 'bash /kneework16g/run_ladder16.sh > /k16g_ladder.log 2>&1'. Resumable (run_knee16.py skips cells in results.jsonl).
# Smallest latencies first so the page and predictions can be checked early. 4 workers up to 4 us, 3 at 16 us (worst cell < 1 GB, container 7.8 GB).
cd /kneework16g
mkdir -p /k16g_reps /k16g_god /k16g_sol /k16g_dps
nice python3 run_knee16.py --out /k16g_sol --cfgs h512_p16g_sol_lat250 h512_p16g_sol_lat16000 --seeds 42 --bsmap bsmap_knee16.json --workers 2
for L in 250 1000 4000 16000; do
  W=4; [ $L -gt 4000 ] && W=3
  nice python3 run_knee16.py --out /k16g_reps --cfgs h512_p16g_msgNh_lat$L --seeds 42 43 44 45 --bsmap bsmap_knee16.json --workers $W
  nice python3 run_knee16.py --out /k16g_god --cfgs h512_p16g_msgNhG_lat$L --seeds 42 43 44 45 --bsmap bsmap_knee16.json --workers $W
  nice python3 run_knee16.py --out /k16g_dps --cfgs h512_p16g_msgNhDcap_lat$L --seeds 42 43 44 --bsmap bsmap_knee16_dps.json --workers $W
done
echo LADDER16G_DONE

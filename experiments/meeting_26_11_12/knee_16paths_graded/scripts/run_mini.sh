#!/bin/bash
# Mini-sweep gate: 2 latencies x 3 B x 2 seeds, both arms, DPS (1 cell per latency and seed), speed-of-light cells. Run in dps-dev: docker exec -d dps-dev sh -c 'bash /kneework16g/run_mini.sh > /k16g_mini.log 2>&1'. Outputs /k16g_mini_*.
cd /kneework16g
for arm in msgNh msgNhG; do
  nice python3 run_knee16.py --out /k16g_mini_$arm --cfgs h512_p16g_${arm}_lat250 h512_p16g_${arm}_lat16000 --seeds 42 43 --bsmap bsmap_mini.json --workers 4
done
nice python3 run_knee16.py --out /k16g_mini_dps --cfgs h512_p16g_msgNhDcap_lat250 h512_p16g_msgNhDcap_lat16000 --seeds 42 43 --bsmap bsmap_mini.json --workers 2
nice python3 run_knee16.py --out /k16g_mini_sol --cfgs h512_p16g_sol_lat250 h512_p16g_sol1p_lat250 h512_p16g_sol_lat16000 h512_p16g_sol1p_lat16000 --seeds 42 43 --bsmap bsmap_mini.json --workers 4
echo MINI_DONE

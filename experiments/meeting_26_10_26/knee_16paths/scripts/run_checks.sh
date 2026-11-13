#!/bin/bash
# Identity checks (n_uplink_check.py) on a sample of final-sweep cells, both arms. Run in the container (m23-dev).
cd /kneework16
CELLS="lat250_B2_s42 lat250_B128_s49 lat1000_B32_s43 lat2000_B128_s44 lat4000_B160_s45 lat8000_B320_s46 lat8000_B1024_s47 lat16000_B2_s48 lat16000_B256_s49 lat16000_B1536_s42"
echo REPS; python3 n_uplink_check.py /k16_reps/traces h512_p16_msgNh $CELLS
echo GOD;  python3 n_uplink_check.py /k16_god/traces h512_p16_msgNhG $CELLS
echo CHECKS_DONE

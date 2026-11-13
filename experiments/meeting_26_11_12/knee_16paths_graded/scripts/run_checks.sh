#!/bin/bash
# Identity checks (n_uplink_check.py) on a sample of final-sweep cells, both arms. Run in the container (m23-dev).
cd /kneework16g
CELLS="lat250_B2_s42 lat250_B128_s45 lat1000_B32_s43 lat1000_B256_s44 lat4000_B160_s45 lat4000_B512_s42 lat16000_B2_s43 lat16000_B256_s44 lat16000_B1536_s45"
echo REPS; python3 n_uplink_check.py /k16g_reps/traces h512_p16g_msgNh $CELLS
echo GOD;  python3 n_uplink_check.py /k16g_god/traces h512_p16g_msgNhG $CELLS
echo CHECKS_DONE

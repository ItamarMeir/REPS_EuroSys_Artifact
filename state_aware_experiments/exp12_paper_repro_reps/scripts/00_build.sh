#!/usr/bin/env bash
# ============================================================
# 00_build.sh — Build htsim_uec with Swift/LSwift/MSwift/MNSCC
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SIM_DIR="$REPO_ROOT/htsim/sim"

echo "[build] Cleaning and rebuilding htsim simulator..."
cd "$SIM_DIR"
make clean -j8 2>&1 | tail -5
make -j8 2>&1 | tail -10

cd "$SIM_DIR/datacenter"
make clean -j8 2>&1 | tail -5
make -j8 2>&1 | tail -10

BIN="$SIM_DIR/datacenter/htsim_uec"
if [ -x "$BIN" ]; then
    echo "[build] SUCCESS: $BIN ($(ls -lh "$BIN" | awk '{print $5}'))"
else
    echo "[build] FAILED: binary not found"
    exit 1
fi

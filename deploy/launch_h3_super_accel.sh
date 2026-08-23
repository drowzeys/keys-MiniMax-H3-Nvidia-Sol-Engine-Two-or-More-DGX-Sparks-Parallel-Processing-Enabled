#!/usr/bin/env bash
# Two-Spark Super Accel pair: STAGE1 on HEAD, STAGE2 on WORKER.
# Occupancy matches NVIDIA v2: one request = 1 Stage-1 GPU + 1 Stage-2 GPU.
# Pause DSV4F first (farm mode). GB200 latency numbers do not apply to GB10.
#
#   HEAD=10.100.10.2 WORKER=10.100.10.3 bash deploy/launch_h3_super_accel.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HEAD="${HEAD:-10.100.10.2}"
WORKER="${WORKER:-10.100.10.3}"
H3_DIR="${H3_DIR:-$HOME/h3-cotenancy}"
PORT="${H3_PORT:-8188}"

echo "Super Accel pair  STAGE1=$HEAD:$PORT  STAGE2=$WORKER:$PORT"
echo "farm the whole UMA on both boxes — do not co-tenant DSV4F"

launch_remote() {
  local ip="$1" role="$2"
  scp -q "$HERE/launch_h3_parallel.sh" "keyspark@$ip:/tmp/launch_h3_parallel.sh"
  ssh "keyspark@$ip" "H3_DIR='$H3_DIR' H3_PORT='$PORT' bash /tmp/launch_h3_parallel.sh '$role'"
}

launch_remote "$HEAD" STAGE1
launch_remote "$WORKER" STAGE2

echo
echo "orchestrator (from any box with HTTP to the pair):"
echo "  python3 comfy/super-accel-driver.py \\"
echo "      --plan comfy/example_super_accel_plan.json \\"
echo "      --stage1-node ${HEAD}:${PORT} --stage2-node ${WORKER}:${PORT} \\"
echo "      --phase all"
echo
echo "Do not claim NVIDIA GB200 6.85s / 22× on this GB10 pair until you log a bench."

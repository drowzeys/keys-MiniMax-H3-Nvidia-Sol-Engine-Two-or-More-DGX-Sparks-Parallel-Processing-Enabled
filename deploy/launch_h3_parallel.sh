#!/usr/bin/env bash
# H3-only ComfyUI launcher for a parallel-fleet Spark. Roles:
#   CHAIN   — Sol-FREE process: continuation chains only (the suite owns the H3 hooks)
#   CREATE  — Sol-ENABLED process: keyframes, re-rolls, ESRGAN upscale workers
#   STAGE1  — CREATE-family: H3 + LightX2V 4-step Super Accel draft (never Continue graphs)
#   STAGE2  — CREATE-family: LTX-2.5 Super Accel refiner (no H3 continuation suite)
# NEVER run SolAttnPatch graphs in a CHAIN process (poisons the hooks until restart).
# STAGE1/STAGE2 are farm-mode jobs: pause any DSV4F co-tenant first.
set -euo pipefail
ROLE="${1:?usage: launch_h3_parallel.sh CHAIN|CREATE|STAGE1|STAGE2}"
H3_DIR="${H3_DIR:-$HOME/h3-cotenancy}"
PORT="${H3_PORT:-8188}"
cd "$H3_DIR/ComfyUI"
# whole node belongs to H3 (no LLM co-tenant): tiny reserve, generous headroom
if [ -f "$H3_DIR/logs/comfyui.pid" ]; then kill "$(cat $H3_DIR/logs/comfyui.pid)" 2>/dev/null || true; fi
fuser -k ${PORT}/tcp 2>/dev/null || true; sleep 1

park() { [ -d "$1" ] && mv "$1" "$1.disabled" || true; }
unpark() { [ -d "$1.disabled" ] && mv "$1.disabled" "$1" || true; }

# always restore the continuation suite before role-specific parking
unpark custom_nodes/Herrgotts-H3-Infinite-Continuation-Suite
unpark custom_nodes/ComfyUI-H3-Motion-Context
unpark custom_nodes/ComfyUI-H3-Motion-Context-MultiRef

case "$ROLE" in
  CHAIN)
    # park competing hook owners; suite stays enabled
    park custom_nodes/ComfyUI-H3-Motion-Context
    park custom_nodes/ComfyUI-H3-Motion-Context-MultiRef ;;
  CREATE) : ;;  # Sol/Sage stay available for keyframe + upscale speed
  STAGE1|STAGE2)
    # Super Accel: park continuation / motion-context so they cannot own H3 hooks
    park custom_nodes/Herrgotts-H3-Infinite-Continuation-Suite
    park custom_nodes/ComfyUI-H3-Motion-Context
    park custom_nodes/ComfyUI-H3-Motion-Context-MultiRef ;;
  *) echo "unknown role $ROLE"; exit 1 ;;
esac
mkdir -p "$H3_DIR/logs"
nohup choom -n 800 -- .venv/bin/python main.py \
  --listen 0.0.0.0 --port "$PORT" \
  --disable-pinned-memory --reserve-vram 8 --vram-headroom 10 \
  > "$H3_DIR/logs/comfyui.log" 2>&1 &
echo $! > "$H3_DIR/logs/comfyui.pid"
echo "H3 $ROLE node up on :$PORT (pid $(cat $H3_DIR/logs/comfyui.pid))"
case "$ROLE" in
  STAGE1|STAGE2)
    echo "Super Accel $ROLE — farm the whole node; do not co-tenant DSV4F. See docs/H3_SUPER_ACCELERATION.md"
    ;;
esac
# --- GB10 vLLM spin-wait fix (see GB10_SPIN_WAIT_PATCH.md) --------------------
# If this script runs a stock vLLM image, the served container will busy-spin CPU
# cores at max clock while waiting on shm_broadcast (busy_loop_s=1s default),
# heating the shared GB10 SoC. Prefer an image built with the patch baked in.
# https://nacyot.github.io/artifacts/vllm-spin-wait-gb10/

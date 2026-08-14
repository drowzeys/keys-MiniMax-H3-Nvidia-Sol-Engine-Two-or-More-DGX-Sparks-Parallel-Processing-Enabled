#!/usr/bin/env bash
# H3-only ComfyUI launcher for a parallel-fleet Spark. Two roles:
#   CHAIN  — Sol-FREE process: continuation chains only (the suite owns the H3 hooks)
#   CREATE — Sol-ENABLED process: keyframes, re-rolls, ESRGAN upscale workers
# NEVER run SolAttnPatch graphs in a CHAIN process (poisons the hooks until restart).
set -euo pipefail
ROLE="${1:?usage: launch_h3_parallel.sh CHAIN|CREATE}"
H3_DIR="${H3_DIR:-$HOME/h3-cotenancy}"
PORT="${H3_PORT:-8188}"
cd "$H3_DIR/ComfyUI"
# whole node belongs to H3 (no LLM co-tenant): tiny reserve, generous headroom
if [ -f "$H3_DIR/logs/comfyui.pid" ]; then kill "$(cat $H3_DIR/logs/comfyui.pid)" 2>/dev/null || true; fi
fuser -k ${PORT}/tcp 2>/dev/null || true; sleep 1
case "$ROLE" in
  CHAIN)
    # park hook-owning packs for this process's lifetime
    for d in custom_nodes/ComfyUI-H3-Motion-Context custom_nodes/ComfyUI-H3-Motion-Context-MultiRef; do
      [ -d "$d" ] && mv "$d" "$d.disabled" || true
    done ;;
  CREATE) : ;;  # Sol/Sage stay available for keyframe + upscale speed
  *) echo "unknown role $ROLE"; exit 1 ;;
esac
mkdir -p "$H3_DIR/logs"
nohup choom -n 800 -- .venv/bin/python main.py \
  --listen 0.0.0.0 --port "$PORT" \
  --disable-pinned-memory --reserve-vram 8 --vram-headroom 10 \
  > "$H3_DIR/logs/comfyui.log" 2>&1 &
echo $! > "$H3_DIR/logs/comfyui.pid"
echo "H3 $ROLE node up on :$PORT (pid $(cat $H3_DIR/logs/comfyui.pid))"

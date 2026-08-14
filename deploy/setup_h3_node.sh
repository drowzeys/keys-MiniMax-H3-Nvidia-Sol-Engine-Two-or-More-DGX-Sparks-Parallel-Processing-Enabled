#!/usr/bin/env bash
# Fresh-Spark setup: weights (bf16 finals + stock TE + VAEs + ESRGAN) + the
# continuation suite. Assumes ComfyUI 0.31.x at ~/h3-cotenancy/ComfyUI.
set -euo pipefail
M="$HOME/h3-cotenancy/ComfyUI/models"
mkdir -p "$M"/{diffusion_models,text_encoders,vae,upscale_models}
REPO=Comfy-Org/MiniMax-H3
get() { [ -f "$M/$2" ] || hf download "$REPO" "$1" --local-dir /tmp/h3dl && mkdir -p "$(dirname "$M/$2")" && mv -n "/tmp/h3dl/$1" "$M/$2" || true; }
get diffusion_models/minimax_h3_fl2va_pruned_bf16.safetensors diffusion_models/minimax_h3_fl2va_pruned_bf16.safetensors
get text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors
get vae/minimax_h3_video_vae_fp16.safetensors vae/minimax_h3_video_vae_fp16.safetensors
get vae/minimax_h3_audio_vae_fp32.safetensors vae/minimax_h3_audio_vae_fp32.safetensors
[ -f "$M/upscale_models/RealESRGAN_x2plus.pth" ] || curl -fL --retry 3 -o "$M/upscale_models/RealESRGAN_x2plus.pth" \
  "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"
cd "$HOME/h3-cotenancy/ComfyUI/custom_nodes"
[ -d Herrgotts-H3-Infinite-Continuation-Suite ] || git clone https://github.com/HerrgottMargott/Herrgotts-H3-Infinite-Continuation-Suite
sudo apt-get install -y earlyoom 2>/dev/null && sudo systemctl enable --now earlyoom || echo "install earlyoom manually (recommended)"
echo "node ready — launch with deploy/launch_h3_parallel.sh CHAIN|CREATE"

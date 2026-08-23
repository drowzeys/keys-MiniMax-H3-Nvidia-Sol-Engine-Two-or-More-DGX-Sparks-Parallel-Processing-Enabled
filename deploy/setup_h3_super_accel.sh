#!/usr/bin/env bash
# Super Acceleration extras on top of setup_h3_node.sh.
# Stage 1: LightX2V 4-step Comfy LoRA + TAEH3.
# Stage 2: gated LTX-2.5 distilled int8-convrot + Gemma-4 TE + original VAEs + x2 upsampler.
#
# LTX-2.5 is gated. Accept https://huggingface.co/Lightricks/LTX-2.5 first.
#   huggingface-cli login
#   SKIP_LTX=1  — Stage-1 only
#   STAGE=1|2|all  (default all)
set -euo pipefail

H3_DIR="${H3_DIR:-$HOME/h3-cotenancy}"
COMFY="${COMFY_ROOT:-$H3_DIR/ComfyUI}"
M="$COMFY/models"
STAGE="${STAGE:-all}"
SKIP_LTX="${SKIP_LTX:-0}"
CN="$COMFY/custom_nodes"

mkdir -p "$M"/{diffusion_models,text_encoders,vae,vae_approx,loras,latent_upscale_models,upscale_models} "$CN"

need_hf() {
  if command -v hf >/dev/null; then
    HF=(hf)
  elif command -v huggingface-cli >/dev/null; then
    HF=(huggingface-cli)
  else
    echo "need huggingface_hub CLI (hf or huggingface-cli)" >&2
    exit 1
  fi
}

dl() {
  local repo="$1" src="$2" dest="$3"
  if [ -s "$dest" ]; then
    echo "have $dest"
    return 0
  fi
  echo "==> $repo :: $src"
  mkdir -p "$(dirname "$dest")"
  local tmp
  tmp="$(mktemp -d /tmp/h3sa.XXXXXX)"
  "${HF[@]}" download "$repo" "$src" --local-dir "$tmp"
  mkdir -p "$(dirname "$dest")"
  mv -n "$tmp/$src" "$dest"
  rm -rf "$tmp"
}

need_hf

if [ "$STAGE" = "all" ] || [ "$STAGE" = "1" ]; then
  echo "=== Stage 1 extras (LightX2V + TAEH3) ==="
  dl lightx2v/Minimax-h3-Turbo \
    minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors \
    "$M/loras/minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors"
  dl Kijai/MiniMax-H3-TAE \
    vae_approx/taeh3.safetensors \
    "$M/vae_approx/taeh3.safetensors"
  # also expose as a regular VAE name so VAELoader can see it
  ln -sfn "$M/vae_approx/taeh3.safetensors" "$M/vae/taeh3.safetensors"
fi

if [ "$STAGE" = "all" ] || [ "$STAGE" = "2" ]; then
  if [ "$SKIP_LTX" = "1" ]; then
    echo "SKIP_LTX=1 — not fetching LTX-2.5 (gated). Stage 2 graphs will fail until you fetch it."
  else
    echo "=== Stage 2 extras (LTX-2.5, gated) ==="
    echo "If this 403s: accept the license at https://huggingface.co/Lightricks/LTX-2.5 and huggingface-cli login"
    LTX=Lightricks/LTX-2.5
    dl "$LTX" diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors \
      "$M/diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"
    dl "$LTX" text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors \
      "$M/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
    dl "$LTX" vae/ltx-2.5-video-vae-bf16.safetensors \
      "$M/vae/ltx-2.5-video-vae-bf16.safetensors"
    dl "$LTX" vae/ltx-2.5-audio-vae-bf16.safetensors \
      "$M/vae/ltx-2.5-audio-vae-bf16.safetensors"
    dl "$LTX" latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors \
      "$M/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
  fi
fi

if [ -d "$CN" ]; then
  if [ ! -d "$CN/ComfyUI-KJNodes/.git" ]; then
    git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git "$CN/ComfyUI-KJNodes" || true
  fi
fi

echo
echo "Super Accel extras in $M"
echo "Launch STAGE1 / STAGE2 with deploy/launch_h3_parallel.sh"
echo "Docs: docs/H3_SUPER_ACCELERATION.md"
echo "Do not mix Super Accel graphs into a CHAIN process."

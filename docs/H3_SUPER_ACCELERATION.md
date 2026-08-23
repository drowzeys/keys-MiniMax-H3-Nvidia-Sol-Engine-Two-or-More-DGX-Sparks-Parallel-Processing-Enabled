# MiniMax-H3 Super Acceleration on DGX Sparks

NVIDIA SANA, 2026-08-17: [H3 Super Acceleration](https://nvlabs.github.io/Sana/Sol-Engine/H3-Super-Acceleration/)  
Source contract: [NVlabs/Sana `sol-engine` / `models/minimax_h3/super_acceleration`](https://github.com/NVlabs/Sana/tree/sol-engine/models/minimax_h3/super_acceleration)

This is a **draft + refine CREATE path**. It does **not** replace the sealed 20-step continuation quality stack in this repo.

## What NVIDIA actually ships

H3 Super Acceleration is a **composite two-stage profile**, not a YAML Sol-Engine recipe and not a drop-in for 20-step H3+Sol+FBC:

```text
Stage 1  MiniMax-H3 FL2VA + LightX2V 4-step LoRA   896×512  124f / 24 fps
         cache reuse OFF · TAEH3 decode
         → BF16 video [1, 3, 121, 384, 672] + FP32 stereo 32 kHz PCM
Stage 2  LTX-2.5 original Video VAE encode · x2 latent upsampler
         3 joint updates at sigmas 0.909375, 0.725, 0.421875, 0.0
         Sol-Attn on LTX layers 1–47 (layer 0 dense) · taus 1.0, 1.25, 1.5
         TAEHV decode · mux original H3 PCM (discard LTX audio)
```

NVIDIA measured this on **GB200**. Public page: serial stages on one GB200, **6.852 s** for a 5 s 1344×768 clip (**22.2×** vs published SGLang). Formal v2 job `6304303`: two independent 1+1 GPU pairs, median E2E **6.761 s**.

**This is not lossless.** NVIDIA says the sampling path changes; detail, texture, motion, or audio can differ from the SGLang / 20-step baseline.

## Claim limits on DGX Spark (GB10, sm_121)

| Claim | Status |
|---|---|
| GB200 6.85 s / 22× vs SGLang | NVIDIA-published **GB200** evidence only |
| Same latency on a GB10 | **Do not claim.** Unmeasured. GB10 is a different GPU, UMA, and kernel stack |
| cute_sm100 Sol-Attn kernel-call contract (3 dense / 141 Sol / 141 cute_sm100) | **GB200-only.** Will not run on sm_121 |
| NVIDIA SGLang Stage-1 container (`lmsysorg/sglang@sha256:71145ca9…`) | GB200 SM100 compile caches. Not the Spark Comfy path |
| Spark Comfy Super Accel wall time | **Unmeasured until a GB10 bench is logged** |

Two-Spark pair topology **does** match NVIDIA’s v2 occupancy rule: one request occupies one Stage-1 GPU and one Stage-2 GPU. It is **not** tensor, context, or model parallelism.

## How it maps onto this fleet

| Fleet | Topology | Notes |
|---|---|---|
| **2 Sparks (recommended)** | Spark A = STAGE1, Spark B = STAGE2 | Matches NVIDIA 1+1 pair. Farm-mode (no DSV4F co-tenant) |
| **4 Sparks** | Two independent pairs | Matches NVIDIA’s validated four-GPU launch |
| **1 Spark (heretic / solo)** | Serial STAGE1 → kill Comfy → STAGE2 | H3 bf16 + LTX-2.5 22B will not both stay resident in 121 GB UMA |

Roles stay under the existing hook-owner rule:

| Role | Process | Super Accel? |
|---|---|---|
| **CHAIN** | Sol-**free** | **No.** Continuation suite owns H3 hooks. 20-step quality path. |
| **CREATE** | Sol-enabled | Keyframes / ESRGAN / 20-step spans |
| **STAGE1** | CREATE-family | H3 + LightX2V 4-step. Never run Continue graphs here. |
| **STAGE2** | CREATE-family | LTX-2.5 refiner. No H3 continuation suite. |

**Never** mix Super Accel graphs into a CHAIN process.

## Spark Comfy path vs NVIDIA native path

This repo operationalizes a **Comfy-native Super Accel** that follows the algorithmic contract on GB10. It is an integration candidate, not a bit-for-bit replay of job `6304303`.

| Boundary | NVIDIA v2 (GB200) | Spark Comfy (this repo) |
|---|---|---|
| Stage 1 runtime | SGLang H3 + overlays, compile `max-autotune-no-cudagraphs` | ComfyUI MiniMax-H3 nodes |
| Stage 1 LoRA | `lightx2v/Minimax-h3-Turbo` `minimax_h3_fl2v_turbo_4step_v0.1.safetensors` | Comfy conversion `minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors` |
| Stage 1 decode | TAEH3 (`taeh3.pth`) | TAEH3 (`Kijai/MiniMax-H3-TAE`) if it loads; else official H3 VAE (slower) |
| Handoff | Authenticated loopback TCP, direct BF16+PCM, dest-CUDA ACK | MP4 + 32 kHz PCM over HTTP/SCP (NVIDIA’s documented diagnostic fallback). Shape still 121 frames @ 24 fps |
| Stage 2 transformer | `ltx-2.5-22b-dev-transformer-bf16` (~42 GB) | **Default:** `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot` (~21.5 GB) so it fits a GB10. Optional bf16 on request |
| Stage 2 schedule | Manual sigmas `0.909375, 0.725, 0.421875, 0.0` | Same `ManualSigmas` string (this is the tail of the official LTX-2.5 distilled schedule) |
| Stage 2 attention | Strict Sol-Attn layers 1–47, cute_sm100 | **Off by default.** SM121 `SolAttnPatch` is the H3 port, not LTX cute_sm100 |
| Stage 2 decode | Wide LTX TAEHV | Official LTX Video VAE by default; TAEHV if the checkpoint is present |
| Audio | Mux original H3 PCM; discard LTX audio | Same (ffmpeg mux after Stage 2) |

A clone of NVlabs `sol-engine` plus the SGLang container is the only way to run the **native** GB200 profile. That is out of scope for GB10 until NVIDIA publishes an sm_121 Stage-2 backend.

## Weights (not git-vendored)

LTX-2.5 is **gated** ([Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5)). Accept the LTX-2 Community License, then `huggingface-cli login`, then run setup.

| File | Role |
|---|---|
| `loras/minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors` | Stage 1 LightX2V 4-step (Comfy) |
| `vae_approx/taeh3.safetensors` | Stage 1 TAEH3 |
| `diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | Stage 2 LTX (Spark default) |
| `text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | Stage 2 TE |
| `vae/ltx-2.5-video-vae-bf16.safetensors` | Original LTX Video VAE (encoder stays original — NVIDIA invariant) |
| `vae/ltx-2.5-audio-vae-bf16.safetensors` | LTX Audio VAE (encoded, then discarded) |
| `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | Learned x2 latent upsampler |

H3 bf16 DiT + stock TE + H3 VAEs still come from `deploy/setup_h3_node.sh`.

## Quick start (2 Sparks, farm mode)

```bash
# on both Sparks, after the usual H3 node setup:
bash deploy/setup_h3_super_accel.sh          # LightX2V + TAEH3 + LTX-2.5 (gated)

# farm-mode: pause any DSV4F co-tenant. Super Accel needs the whole UMA.
# Spark A:
bash deploy/launch_h3_parallel.sh STAGE1     # :8188
# Spark B:
H3_PORT=8188 bash deploy/launch_h3_parallel.sh STAGE2

# orchestrator:
python3 comfy/super-accel-driver.py \
    --plan comfy/example_super_accel_plan.json \
    --stage1-node 10.100.10.2:8188 \
    --stage2-node 10.100.10.3:8188 \
    --phase all
```

Single-Spark serial (heretic pack):

```bash
bash deploy/launch_h3_parallel.sh STAGE1
python3 comfy/super-accel-driver.py --plan ... --stage1-node 127.0.0.1:8188 --phase stage1
bash deploy/launch_h3_parallel.sh STAGE2
python3 comfy/super-accel-driver.py --plan ... --stage2-node 127.0.0.1:8188 --phase stage2
python3 comfy/super-accel-driver.py --plan ... --phase mux
```

## What Super Accel is for (and not for)

**Use it for:** short talking-head / I2V clips, preview drafts, high-throughput CREATE jobs, 768p/1080p 5–10 s shots where NVIDIA’s speed–quality tradeoff is acceptable.

**Do not use it for:** *Hesitation v6*-class continuous-take music videos, world-morph Continue chains, or any deliverable that currently requires the sealed 20-step CHAIN path. Super Accel does not carry Herrgott latents across joins.

Sibling packs:

- Dual-boot + 20-step farm: [keys-DGX-Sparkticus-Ultimate-Power-Pack-Unleashed](https://github.com/drowzeys/keys-DGX-Sparkticus-Ultimate-Power-Pack-Unleashed-Dual-DGX-Sparks-Needed)
- Single-Spark Sol+FBC+Heretic: [keys-heretic-MiniMax-H3-sol-engine-more-speed-upgrades-upscaler-finish-Single-DGX-Spark](https://github.com/drowzeys/keys-heretic-MiniMax-H3-sol-engine-more-speed-upgrades-upscaler-finish-Single-DGX-Spark)

## Credits

- NVIDIA SANA: Yitong Li\*, Junsong Chen\*, Haozhe Liu, Haopeng Li, Yuze Ma, Yongchang Liu, Song Han, Enze Xie (equal contribution marked \*)
- LightX2V Turbo LoRA: [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo)
- TAEH3 / TAEHV: [madebyollin/taehv](https://github.com/madebyollin/taehv), Comfy pack [Kijai/MiniMax-H3-TAE](https://huggingface.co/Kijai/MiniMax-H3-TAE)
- LTX-2.5: Lightricks (LTX-2 Community License — review before commercial use)
- Dual-serve factory this fleet sits on: Tony / [tonyd2wild/ds4-h3-video-gen-factory](https://github.com/tonyd2wild/ds4-h3-video-gen-factory)

Provenance pointers: [`vendor/nvlabs-super-accel/`](../vendor/nvlabs-super-accel/PIN.md).

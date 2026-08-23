# NVIDIA Super Acceleration pin

This directory records the **exact upstream identity** this pack integrates against.
It does **not** vendor NVIDIA’s SGLang overlays, cute_sm100 kernels, weights, LoRAs,
datasets, or compile caches.

## Upstream

| Field | Value |
|---|---|
| Page | https://nvlabs.github.io/Sana/Sol-Engine/H3-Super-Acceleration/ |
| Repo | https://github.com/NVlabs/Sana |
| Branch | `sol-engine` |
| Path | `models/minimax_h3/super_acceleration/` |
| Page date | 2026-08-17 |
| Team | NVIDIA SANA (Yitong Li\*, Junsong Chen\*, Haozhe Liu, Haopeng Li, Yuze Ma, Yongchang Liu, Song Han, Enze Xie) |

## Contract files to re-read on bump

- `README.md` — two-GPU occupancy, TAEH3 / TAEHV, LightX2V LoRA
- `STAGE2_CONTRACT.md` — tensor shapes, sigmas, Sol-Attn layers 1–47, mux H3 PCM
- `THIRD_PARTY_NOTICES.md` — licenses and SHA pins
- `run_gb200.sh` — 2 independent 1+1 pairs, not TP/CP/FSDP
- `BENCHMARK_REFERENCE.json` — GB200 latency only

## Fixed v2 numbers (NVIDIA, GB200 — do not paste as Spark results)

Formal Slurm job `6304303` (20 hot requests, two pairs):

| Boundary | Median |
|---|---:|
| Complete H3 Stage 1 → final Stage 2 MP4 | 6.760544632 s |
| Stage 1 wall | 4.2919342775 s |
| Stage 2 resident service | 2.446938 s |

Public page combined Stage 1+2 on one GB200: **6.852 s** (5 s · 1344×768), **14.931 s** (10 s).

## Spark adaptations this pack is allowed to make

1. ComfyUI instead of SGLang Stage 1.
2. LightX2V **ComfyUI-converted** 4-step LoRA (`v1.1_768p_comfyui_bf16`) instead of the v0.1 SGLang file.
3. MP4+PCM handoff instead of authenticated loopback BF16 TCP.
4. LTX-2.5 **distilled int8-convrot** transformer as GB10 default (bf16 22B is the NVIDIA GB200 file).
5. SM121 H3 `SolAttnPatch` stays on Stage 1 CREATE graphs only; Stage 2 cute_sm100 is **not** emulated.

Anything else (sigmas, 896×512 / 124f, 121 consumed frames, original LTX VAE encoder, x2 latent upsampler, mux original H3 PCM, cache reuse off) is a contract break — bump this pin and re-bench.

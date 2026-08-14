# Measured time efficiency — MiniMax-H3 on N DGX Sparks (GB10, 864×480/24fps)

All numbers measured on the reference fleet 2026-08-13/14 (bf16 finals config).

## Atomic costs (one GB10, whole node for H3)

| Task | Time |
|---|---|
| Keyframe still, 22 f bf16 (Sol-enabled process) | 35–65 s |
| FLF span, 158 f (Sol-Engine + FBC, CFG 1) | **232 s** (392 s without Sol/FBC) |
| Continuation clip, 10 s film (suite, Sol-free process) | ~14.5 min (770–980 s observed) |
| Suite chain-stitch (freeze-aware, per act) | 2–6 min |
| ESRGAN ×2, per second of film | ~9 s |
| Reference: Mac Studio M3 Ultra native h3.c | ~4× a GB10 per clip at matched quality |

## Scaling law

* **FLF spans scale ~linearly** with node count (independent jobs): 27 spans = 58 min on 2 Sparks.
* **Chains scale by the LONGEST CHAIN**, not clip total — write more, shorter chains to
  use more nodes. Clips are serial inside a chain (each continues the previous latent).
* **Upscaling adds ~zero wall time** when overlapped: the CREATE node upscales each act
  the moment its chain stitches, while other chains still render.

## Case study — *Hesitation v6* (2:46 film, 23 clips, 4 chains, 27 keyframes)

| Fleet | Wall time (chains + stitch) | Notes |
|---|---|---|
| 1 Spark (everything serial) | ~5.6 h + 25 min upscale | baseline |
| 2 Sparks (chains split 2/2) | ~3.5 h, upscale overlapped | CREATE node doubles as 2nd chain node between phases |
| **3 Sparks (production run)** | **~3.0 h all-in** | Act I (8 clips) / Act III (7) / both solo chains (4+4); keyframe board on the CREATE node beforehand ≈ 25 min + QC |

Longest chain (8 clips ≈ 1.9 h) set the wall clock — with 4 Sparks and the same film
re-cut as 6 shorter chains, the same content lands in ~1.4 h.

## Why H3-only buys headroom

bf16 DiT (40 GB) + int8 TE (27 GB) resident ≈ 70 GB, leaving **~50 GB working headroom**
per node — enough for same-node ESRGAN batches, keyframe re-rolls between chain clips,
and long-chain context growth without OOM (with earlyoom + choom victim priority, an
over-budget spike costs one retryable render, never the node).

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

## NVIDIA Super Acceleration (GB200 published — not a GB10 bench)

NVIDIA SANA measured H3 Super Acceleration on **GB200**, not on this fleet’s GB10 Sparks.

| Setting | Hardware | E2E | vs published SGLang |
|---|---|---:|---:|
| 1344×768 · 5 s | 1× GB200 | **6.852 s** | 22.2× |
| 1344×768 · 10 s | 1× GB200 | **14.931 s** | 27.7× |
| Same clip on 1–2× GB10 | DGX Spark | **unmeasured** | do not invent a multiplier |

The Spark Comfy path in this repo follows the same 4+3 step contract (see [H3_SUPER_ACCELERATION.md](./H3_SUPER_ACCELERATION.md)). Log a GB10 wall time before quoting throughput.

## Why H3-only buys headroom

bf16 DiT (40 GB) + int8 TE (27 GB) resident ≈ 70 GB, leaving **~50 GB working headroom**
per node — enough for same-node ESRGAN batches, keyframe re-rolls between chain clips,
and long-chain context growth without OOM (with earlyoom + choom victim priority, an
over-budget spike costs one retryable render, never the node).


---

# MEASURED BENCHMARK RUN (2026-08-14) — blank page → 2× master in 3h32m

Full production benchmark on the reference fleet: a NEW 2:46 film ("Hesitation" solo cut —
same structural shape as v6: 27 keyframes, 4 chains, 23 clips) produced start-to-finish
with this repo's workflow on 3 GB10 Sparks. Every timestamp from the live log:

| Milestone | Clock | Phase time |
|---|---|---|
| T0 — blank page (creative plan authoring begins) | 07:33:55 | — |
| Keyframe board start (CREATE node) | 07:35:36 | plan: 2 min |
| Board 27/27 + QC + 3 re-rolls sealed | 07:57:23 | board+QC: 22 min |
| Chains start on ALL 3 nodes | 07:59:34 | — |
| First chain done (4 clips) | 08:52:23 | 52.8 min |
| First act 2× upscaled — **overlapped, chains still rendering** | 09:17:08 | — |
| Last chain done (23/23 clips) | 10:44:36 | chains: 2h45m |
| Last overlapped 2× done | 11:04:34 | +20 min tail |
| **1728×960 master assembled** | **11:05:44** | **TOTAL 3h32m** |

**vs the v6 baseline** (same shape, produced without this workflow): board with ~40%
re-roll rate ≈ 1.2 h; chains ≈ 2.8 h; stitches fetched serially; upscale as a separate
+35 min pass after everything; total ≈ **4.5–5 h clean-path** (the real v6 run took
longer still due to failures this repo's findings now prevent). **Net: ~25–30% wall
saved, and the 2× master exists 1 minute after the last upscale instead of 35+.**

## Scheduling findings from the run (encoded in the driver)

1. **Solo-cast discipline pays immediately**: first-roll keyframe QC pass rate was
   **24/27 (89%)** vs ~60% on v6's couple film — doubling/summoning artifacts were the
   dominant re-roll cause and are structural, not random.
2. **Co-located upscaling taxes the co-resident chain ~2×** (13 min clips stretched to
   25–35 min while ESRGAN shared the GPU), and contention slows the upscale itself
   ~3–4× (592 s uncontended vs 2284–2401 s contended). It is STILL net-positive —
   3 of 4 upscales finished inside the chain window — but place the upscale worker on
   the node whose chain lane is SHORTEST, and expect the final act's upscale to trail
   ~10–20 min after the last chain.
3. **Chain clip pace (uncontended): 13.2 min per 10 s clip** at 864×480 bf16 on a GB10.

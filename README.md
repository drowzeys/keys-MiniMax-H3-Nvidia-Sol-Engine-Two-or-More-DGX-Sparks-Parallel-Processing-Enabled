# keys-MiniMax-H3 + Nvidia-Sol-Engine on Two (or More) DGX-Sparks — Parallel Processing Enabled

**Pure MiniMax-H3 film factory for multi-Spark fleets.** No LLM co-tenant, no memory
juggling: every GB10's full **121 GB UMA** belongs to H3, and the workflow distributes
**creation, continuation-chain rendering, and upscaling across all your Sparks in
parallel** — no waiting for one segment's job to finish before the next begins.

This is the exact configuration that produced *Hesitation v6* (a 2:46 continuous-take
music video: latent-carried clip chains, world-morph shots, split-view storylines),
adapted for **2, 3, or N DGX Sparks**.

> *Based on Tony's [ds4-h3-video-gen-factory](https://github.com/tonyd2wild/ds4-h3-video-gen-factory).*
> Sibling repo (H3 + DSV4F co-tenancy, the full Power Pack):
> [keys-DGX-Sparkticus-Ultimate-Power-Pack-Unleashed](https://github.com/drowzeys/keys-DGX-Sparkticus-Ultimate-Power-Pack-Unleashed-Dual-DGX-Sparks-Needed)

---

## The sealed H3 configuration (measured, not vibes)

| Piece | Value | Why |
|---|---|---|
| DiT (finals) | `minimax_h3_fl2va_pruned_bf16` (~40 GB, from [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)) | int8-convrot is DRAFT tier only (posterized banding); bf16 matches native-h3.c quality |
| Text encoder | STOCK `qwen3vl_32b_minimax_h3_int8_convrot` (27 GB) | Heretic TE retired (its own author advises against heretic models for H3) |
| Speed stack | **NVIDIA Sol-Engine / SolAttn + FBC** on span/keyframe graphs | 392 s → **232 s** per 158-frame span at 864×480 on one GB10 |
| Guidance | **CFG 1** (instrumental) · **CFG 5 + zeroed negative** for generated speech | guidance-free H3 speech babbles in ComfyUI |
| Sampler | res_multistep · simple · 20 steps · SigmaShift 12/3 | quality path; no Turbo LoRA for deliverables |
| Continuation | [Herrgott's H3 Infinite Continuation Suite](https://github.com/HerrgottMargott/Herrgotts-H3-Infinite-Continuation-Suite), 10 s clips | full-latent carry: motion + native audio continue across joins |
| Memory | `--disable-pinned-memory --reserve-vram 8 --vram-headroom 10` + earlyoom + `choom -n 800` | whole node for H3; renders die before the box does |

**⚠️ One hook owner per ComfyUI process:** the Continuation Suite and `SolAttnPatch`
(and Motion-Context packs) fight over H3's runtime hooks. This repo's role split makes
that a non-issue: **chain nodes run Sol-free processes; keyframe/upscale nodes run
Sol-enabled processes.** Never mix in one process. Details: [docs/FINDINGS.md](docs/FINDINGS.md).

## The parallel architecture

```
 ORCHESTRATOR (any box, zero GPU cost — talks HTTP to every node)
 comfy/parallel-film-driver.py
        │
        ├─ phase 1: KEYFRAME BOARD  → Sol-enabled node(s), ~35–65 s/still, QC gate
        │
        ├─ phase 2: CHAINS (the film) — one chain per node, ALL NODES AT ONCE
        │     Spark 1: Act I chain   (clips are serial *within* a chain,
        │     Spark 2: Act III chain  chains are parallel *across* nodes)
        │     Spark 3: solo chains for split-view acts
        │
        ├─ phase 3 (OVERLAPPED): PARALLEL UPSCALE WORKERS
        │     as each chain finishes stitching, an ESRGAN ×2 worker on the
        │     keyframe/upscale node picks the act up IMMEDIATELY — upscaling
        │     runs while other chains are still rendering, so the 2× master
        │     is ready minutes after the last chain, not hours
        │
        └─ phase 4: ASSEMBLE — split-view composition, act concat, song mux
```

With no LLM co-tenant there is **~75 GB of true headroom** on every node after the
bf16 DiT + TE are resident — that headroom is what makes same-node keyframe re-rolls
and pipelined ESRGAN upscaling free.

## Measured time efficiency (GB10, 864×480/24 fps)

| Task | 1 Spark | 2 Sparks | 3 Sparks |
|---|---|---|---|
| Keyframe still (22 f, bf16) | 35–65 s | parallel ÷2 | parallel ÷3 |
| FLF span, 158 f (Sol+FBC, CFG 1) | 232 s | ÷2 | ÷3 |
| Continuation clip (10 s film) | ~14.5 min | chains in parallel | chains in parallel |
| **Hesitation v6 case study** (23 clips, 4 chains, 27 keyframes) | ~5.6 h chains alone | ~3.5 h | **~3.0 h wall, all-in** |
| ESRGAN ×2 of the full 2:46 film | +25 min serial | **overlapped → ~0 added wall** | overlapped |
| Reference: Mac Studio M3 Ultra (native h3.c) | ~4× slower per clip than one GB10 | — | — |

Chains bound the wall clock by the **longest chain**, not the clip total — write your
film as more, shorter chains to scale with node count. A 27-span FLF music video
(the v2 pipeline, also included in the driver's lineage) scales nearly linearly:
2 Sparks rendered 27 spans in 58 min.

## Quick start

```bash
# on every render Spark (weights + suite + nodes):
bash deploy/setup_h3_node.sh          # fetch weights (bf16+TE+VAEs+ESRGAN), install suite
bash deploy/launch_h3_parallel.sh CHAIN     # Sol-free process  (chain nodes)
bash deploy/launch_h3_parallel.sh CREATE    # Sol-enabled process (keyframe/upscale node)

# on the orchestrator (any machine):
python3 comfy/parallel-film-driver.py --plan comfy/example_film_plan.json \
    --chain-nodes 10.0.0.1:8188,10.0.0.2:8188 --create-node 10.0.0.3:8188 \
    --phase kf          # board + QC gate
python3 comfy/parallel-film-driver.py ... --phase film   # chains ∥ + upscale ∥ + assemble
```

Two-Spark minimum: one CHAIN node + one CREATE node (keyframes, re-rolls, upscale) —
the CREATE node doubles as a second chain node between phases. Three or more: one
CREATE node + the rest CHAIN nodes, one chain each.

## What's in the box

| Path | What |
|---|---|
| [comfy/parallel-film-driver.py](comfy/parallel-film-driver.py) | N-node orchestrator: keyframe board, chain scheduler, overlapped upscale workers, assembly |
| [comfy/example_film_plan.json](comfy/example_film_plan.json) | Genericized Hesitation-v6 plan (3 acts, split-view, world-morphs) |
| [deploy/setup_h3_node.sh](deploy/setup_h3_node.sh) | Weights + suite + custom-node setup for a fresh Spark |
| [deploy/launch_h3_parallel.sh](deploy/launch_h3_parallel.sh) | H3-only launcher, CHAIN/CREATE roles, OOM victim priority |
| [docs/FINDINGS.md](docs/FINDINGS.md) | The five field findings: hook-owner rule, solo-cast rule, anchored re-rolls, world-morph prompting, operational quirks |
| [docs/TIME_EFFICIENCY.md](docs/TIME_EFFICIENCY.md) | Full measured tables + scaling math |

## OOM protection (still install it)

No co-tenant ≠ no OOM: a 40 GB DiT + long chains + an ESRGAN batch can still spike.
`launch_h3_parallel.sh` starts ComfyUI under `choom -n 800`; install earlyoom once per
node (`sudo apt-get install -y earlyoom && sudo systemctl enable --now earlyoom`) and an
over-budget spike kills one retryable render instead of freezing the Spark.

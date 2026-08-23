# Credits

**Big thanks.** Multi-Spark MiniMax-H3 is possible because of the projects below.
Star and cite them. This repo is the parallel film factory + optional Super Accel CREATE path.

## Dual-serve spine

- **[Tony / tonyd2wild](https://github.com/tonyd2wild/ds4-h3-video-gen-factory)** —
  DS4 + H3 on two Sparks, start order, util discipline. Required shout-out on any demo.

## Model and Comfy

- **[MiniMax](https://www.minimax.io/)** — MiniMax-H3  
- **[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)** — bf16 FL2VA, stock TE, VAEs  
- **[comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI)**  

## Quality speed stack (20-step CREATE graphs)

- **NVIDIA SANA Sol-Engine / SolAttn** — [H3 on-device](https://nvlabs.github.io/Sana/Sol-Engine/H3-OnDevice/)  
- **[kijai](https://github.com/kijai)** — SolAttn Triton, KJNodes  
- **H3 FirstBlockCache** (Blackwell Sol-Attn ports)  
- **[xmarre/ComfyUI-Spectrum-MiniMax-H3](https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3)** v0.2.1 audio fix  
- SageAttention via KJ node (`sageattention==1.0.6`) — never global `--use-sage-attention`  
- **[HerrgottMargott / Infinite Continuation Suite](https://github.com/HerrgottMargott/Herrgotts-H3-Infinite-Continuation-Suite)** — CHAIN path  
- **[NikoDemon80 / Motion Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)**  
- Real-ESRGAN x2 (xinntao)

## Super Acceleration (optional CREATE path — not quality)

- **NVIDIA SANA** — [H3 Super Acceleration](https://nvlabs.github.io/Sana/Sol-Engine/H3-Super-Acceleration/)  
  Yitong Li\*, Junsong Chen\*, Haozhe Liu, Haopeng Li, Yuze Ma, Yongchang Liu, Song Han, Enze Xie  
- **[LightX2V / MiniMax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo)**  
- **[madebyollin/taehv](https://github.com/madebyollin/taehv)** · **[Kijai/MiniMax-H3-TAE](https://huggingface.co/Kijai/MiniMax-H3-TAE)**  
- **[Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5)** (LTX-2 Community License)

Quality deliverables stay **bf16 + stock TE + 20 steps, no LoRA, no heretic**.

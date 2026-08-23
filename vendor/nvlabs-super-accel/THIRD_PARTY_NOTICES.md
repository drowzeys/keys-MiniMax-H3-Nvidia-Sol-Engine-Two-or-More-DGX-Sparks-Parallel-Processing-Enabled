# Third-party notices (Spark Super Acceleration integration)

Adapted from NVIDIA SANA `models/minimax_h3/super_acceleration/THIRD_PARTY_NOTICES.md`.
This is not legal advice and does not replace upstream licenses.

This pack does **not** redistribute model weights, LoRAs, datasets, first-frame
media, generated videos, container images, Python environments, or compiled
kernels/caches.

## NVIDIA Sol Engine / H3 Super Acceleration

Source: [NVlabs/Sana](https://github.com/NVlabs/Sana) branch `sol-engine`.
Follow that repository’s root license for the integration sources. The Super
Acceleration directory is a composite of two independently resident runtimes
and is **not** covered by the lightweight YAML `sol_engine` API.

## LightX2V MiniMax-H3 Turbo LoRA

[lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo).
NVIDIA’s formal file: `minimax_h3_fl2v_turbo_4step_v0.1.safetensors`
(revision `050494d5fe05bd1b1140b8565ea51dc33a5085a5`).
This pack’s Comfy default is the community ComfyUI conversion
`minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors`.
Consult the model card before download or redistribution.

## TAEH3 / TAEHV

[madebyollin/taehv](https://github.com/madebyollin/taehv), MIT.
Comfy safetensors pack: [Kijai/MiniMax-H3-TAE](https://huggingface.co/Kijai/MiniMax-H3-TAE), Apache-2.0.
NVIDIA’s formal `taeh3.pth` SHA-256:
`af92965c2d7986a89a757e7cccd26f9eeeff0c3f0d5495eb168aeb2d6d9be9ba`.
Wide `taeltx2_3_wide.pth` SHA-256:
`007788e6b9cb7f77e8589ae30ba7456b119d38b0d017e1d349c1c1d11e3d6339`.
Those `.pth` files are not bundled here.

## LTX-2.5

[Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) and
[Lightricks/LTX-2](https://github.com/Lightricks/LTX-2).
Governed by the **LTX-2 Community License Agreement**, not Apache-2.0.
The repo is gated. Review commercial-use and use-based restrictions before
downloading. NVIDIA Stage 2 keeps the **original** LTX Video VAE encoder
because the Refiner was trained on that latent distribution.

## MiniMax-H3

[MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) /
[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3).
Consult the model card. This pack’s quality path still uses the Comfy-Org
bf16 FL2VA DiT + stock int8-convrot TE.

## SGLang (NVIDIA Stage 1 only — not used on Spark)

[sgl-project/sglang](https://github.com/sgl-project/sglang) commit
`12eadf86f12aec2e6f81a6e38b61b964a4c6b529`.
Pinned image digest `sha256:71145ca99ebc458265e93cebd00b52bb9f419f052e7d0de09a54fa0f72fed888`.
Not launched by the Spark Comfy driver.

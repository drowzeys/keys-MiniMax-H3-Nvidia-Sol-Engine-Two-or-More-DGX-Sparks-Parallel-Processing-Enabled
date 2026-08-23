#!/usr/bin/env python3
"""MiniMax-H3 Super Acceleration driver — Stage 1 (H3+LightX2V) → Stage 2 (LTX-2.5).

CREATE-path only. Do not point this at a CHAIN (Sol-free continuation) process.

Two-Spark pair (matches NVIDIA 1+1 occupancy):
  python3 comfy/super-accel-driver.py --plan comfy/example_super_accel_plan.json \\
      --stage1-node A:8188 --stage2-node B:8188 --phase all

Single-Spark serial: run --phase stage1, relaunch Comfy as STAGE2, then --phase stage2 mux.

GB200 6.85 s / 22× figures are NVIDIA-published GB200 numbers. Do not print them as
GB10 results. See docs/H3_SUPER_ACCELERATION.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

for base in (Path(__file__).resolve().parent, Path.home() / "comfy"):
    if (base / "h3-weld.py").is_file():
        _s = importlib.util.spec_from_file_location("h3weld", str(base / "h3-weld.py"))
        W = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(W)
        break
else:
    sys.exit("h3-weld.py not found (needs submit/wait helpers)")

ap = argparse.ArgumentParser()
ap.add_argument("--plan", required=True)
ap.add_argument("--stage1-node", default="", help="CREATE-family STAGE1 Comfy host:port")
ap.add_argument("--stage2-node", default="", help="CREATE-family STAGE2 Comfy host:port")
ap.add_argument("--phase", required=True, choices=["stage1", "stage2", "mux", "all"])
ap.add_argument("--outdir", default=str(Path.home() / "Videos" / "super_accel"))
ap.add_argument("--shot", default="", help="run only this shot id")
a = ap.parse_args()

PLAN = json.loads(Path(a.plan).read_text())
OUT = Path(a.outdir)
OUT.mkdir(parents=True, exist_ok=True)
SEED = int(PLAN.get("seed", 20260817))
W1, H1 = int(PLAN.get("width", 896)), int(PLAN.get("height", 512))
FRAMES1 = int(PLAN.get("stage1_frames", 124))
FRAMES2 = int(PLAN.get("stage2_frames", 121))
FPS = int(PLAN.get("fps", 24))
W2, H2 = int(PLAN.get("stage2_width", 1344)), int(PLAN.get("stage2_height", 768))
DW, DH = int(PLAN.get("draft_width", 672)), int(PLAN.get("draft_height", 384))
SIGMAS = PLAN.get("stage2_sigmas", "0.909375, 0.725, 0.421875, 0.0")
STEPS1 = int(PLAN.get("stage1_steps", 4))
NEG = PLAN.get("negative", "")
USE_TAEH3 = bool(PLAN.get("use_taeh3", True))


def shots():
    xs = PLAN.get("shots") or []
    if a.shot:
        xs = [s for s in xs if s.get("id") == a.shot]
        if not xs:
            sys.exit(f"shot {a.shot!r} not in plan")
    return xs


def stage1_graph(shot, seed):
    prompt = shot["prompt"]
    first = shot.get("first_frame")
    vae = PLAN["taeh3_vae"] if USE_TAEH3 else PLAN["video_vae"]
    cond_cls = "MiniMaxH3ImageToVideoAudio" if first else "MiniMaxH3TextToVideoAudio"
    g = {
        "u": {"class_type": "UNETLoader",
              "inputs": {"unet_name": PLAN["unet"], "weight_dtype": "default"}},
        "lora": {"class_type": "LoraLoaderModelOnly",
                 "inputs": {"model": ["u", 0],
                            "lora_name": PLAN["stage1_lora"],
                            "strength_model": float(PLAN.get("stage1_lora_strength", 1.0))}},
        "c": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": PLAN["te_file"], "type": "minimax", "device": "default"}},
        "vv": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "va": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["audio_vae"]}},
        "cond": {"class_type": cond_cls,
                 "inputs": {"prompt": prompt, "width": W1, "height": H1, "length": FRAMES1,
                            "clip": ["c", 0], "vae": ["vv", 0]}},
        "shift": {"class_type": "MiniMaxH3SigmaShift",
                  "inputs": {"shift_video": 12, "shift_audio": 3, "model": ["lora", 0]}},
        "guide": {"class_type": "BasicGuider",
                  "inputs": {"model": ["shift", 0], "conditioning": ["cond", 0]}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "sched": {"class_type": "BasicScheduler",
                  "inputs": {"scheduler": "simple", "steps": STEPS1, "denoise": 1.0,
                             "model": ["shift", 0]}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["noise", 0], "guider": ["guide", 0],
                           "sampler": ["samp", 0], "sigmas": ["sched", 0],
                           "latent_image": ["cond", 1]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["run", 0], "vae": ["vv", 0]}},
        "deca": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["run", 0], "vae": ["va", 0]}},
        "vid": {"class_type": "CreateVideo",
                "inputs": {"fps": FPS, "images": ["dec", 0], "audio": ["deca", 0]}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["vid", 0], "filename_prefix": f"sa_s1_{shot['id']}",
                            "format": "mp4", "codec": "h264"}},
    }
    if first:
        g["img"] = {"class_type": "LoadImage", "inputs": {"image": first}}
        g["cond"]["inputs"]["image"] = ["img", 0]
    return g


def stage2_graph(shot, seed, video_file):
    """LTX-2.5 3-step refine of the Stage-1 draft. Mux of H3 PCM happens after fetch."""
    prompt = shot["prompt"]
    g = {
        "vidin": {"class_type": "LoadVideo", "inputs": {"file": video_file}},
        "comp": {"class_type": "GetVideoComponents", "inputs": {"video": ["vidin", 0]}},
        "scale": {"class_type": "ImageScale",
                  "inputs": {"image": ["comp", 0], "upscale_method": "bilinear",
                             "width": DW, "height": DH, "crop": "center"}},
        "u": {"class_type": "UNETLoader",
              "inputs": {"unet_name": PLAN["ltx_unet"], "weight_dtype": "default"}},
        "c": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": PLAN["ltx_te"], "type": "ltxv", "device": "default"}},
        "vv": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["ltx_video_vae"]}},
        "va": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["ltx_audio_vae"]}},
        "upm": {"class_type": "LatentUpscaleModelLoader",
                "inputs": {"model_name": PLAN["ltx_upsampler"]}},
        "pos": {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["c", 0], "text": prompt}},
        "neg": {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["c", 0], "text": NEG}},
        "ltxc": {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                            "frame_rate": float(FPS)}},
        "enc": {"class_type": "VAEEncode",
                "inputs": {"pixels": ["scale", 0], "vae": ["vv", 0]}},
        "up": {"class_type": "LTXVLatentUpsampler",
               "inputs": {"samples": ["enc", 0], "upscale_model": ["upm", 0], "vae": ["vv", 0]}},
        "ff0": {"class_type": "ImageFromBatch",
                "inputs": {"image": ["comp", 0], "batch_index": 0, "length": 1}},
        "ff": {"class_type": "ImageScale",
               "inputs": {"image": ["ff0", 0], "upscale_method": "lanczos",
                          "width": W2, "height": H2, "crop": "center"}},
        "guide_ff": {"class_type": "LTXVImgToVideoInplace",
                     "inputs": {"vae": ["vv", 0], "image": ["ff", 0], "latent": ["up", 0],
                                "strength": 1.0, "bypass": False}},
        "enca": {"class_type": "VAEEncodeAudio",
                 "inputs": {"audio": ["comp", 1], "vae": ["va", 0]}},
        "av": {"class_type": "LTXVConcatAVLatent",
               "inputs": {"video_latent": ["guide_ff", 0], "audio_latent": ["enca", 0]}},
        "msamp": {"class_type": "ModelSamplingLTXV",
                  "inputs": {"model": ["u", 0], "max_shift": 2.05, "base_shift": 0.95,
                             "latent": ["av", 0]}},
        "guider": {"class_type": "CFGGuider",
                   "inputs": {"model": ["msamp", 0], "positive": ["ltxc", 0],
                              "negative": ["ltxc", 1], "cfg": 1.0}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
        "sig": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["noise", 0], "guider": ["guider", 0],
                           "sampler": ["samp", 0], "sigmas": ["sig", 0],
                           "latent_image": ["av", 0]}},
        "split": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["run", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["split", 0], "vae": ["vv", 0]}},
        "vid": {"class_type": "CreateVideo", "inputs": {"fps": FPS, "images": ["dec", 0]}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["vid", 0], "filename_prefix": f"sa_s2_{shot['id']}",
                            "format": "mp4", "codec": "h264"}},
    }
    return g


def _run(cmd):
    subprocess.run(cmd, check=True)


def trim_to_frames(src: Path, dest: Path, n: int):
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
          "-frames:v", str(n), "-c:v", "libx264", "-crf", "12", "-c:a", "copy", str(dest)])


def extract_pcm(src: Path, dest: Path):
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
          "-vn", "-ac", "2", "-ar", "32000", "-c:a", "pcm_s16le", str(dest)])


def mux_pcm(video: Path, pcm: Path, dest: Path):
    _run(["ffmpeg", "-y", "-loglevel", "error",
          "-i", str(video), "-i", str(pcm),
          "-map", "0:v:0", "-map", "1:a:0",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-shortest", str(dest)])


def phase_stage1():
    node = a.stage1_node.strip()
    if not node:
        sys.exit("--stage1-node required")
    for i, shot in enumerate(shots()):
        sid = shot["id"]
        if shot.get("first_frame"):
            W.upload_image(node, shot["first_frame"], Path(shot["first_frame"]).name)
            shot = dict(shot)
            shot["first_frame"] = Path(shot["first_frame"]).name
        g = stage1_graph(shot, SEED + i)
        t0 = time.time()
        pid = W.submit(node, g)
        clip = OUT / f"{sid}_stage1.mp4"
        W.wait_and_fetch(node, pid, clip, timeout=3600, tag=f"s1:{sid}")
        dt = time.time() - t0
        trim = OUT / f"{sid}_stage1_{FRAMES2}f.mp4"
        trim_to_frames(clip, trim, FRAMES2)
        extract_pcm(clip, OUT / f"{sid}_h3.wav")
        print(f"[stage1] {sid} {dt:.1f}s GB10-wall (not a GB200 claim) → {trim}", flush=True)


def phase_stage2():
    node = a.stage2_node.strip()
    if not node:
        sys.exit("--stage2-node required")
    for i, shot in enumerate(shots()):
        sid = shot["id"]
        src = OUT / f"{sid}_stage1_{FRAMES2}f.mp4"
        if not src.is_file():
            src = OUT / f"{sid}_stage1.mp4"
        if not src.is_file():
            sys.exit(f"missing Stage-1 media for {sid}: {src}")
        remote_name = f"sa_s1_{sid}.mp4"
        W.upload_image(node, src, remote_name)
        g = stage2_graph(shot, SEED + 1000 + i, remote_name)
        t0 = time.time()
        pid = W.submit(node, g)
        clip = OUT / f"{sid}_stage2.mp4"
        W.wait_and_fetch(node, pid, clip, timeout=3600, tag=f"s2:{sid}")
        dt = time.time() - t0
        print(f"[stage2] {sid} {dt:.1f}s GB10-wall (not a GB200 claim) → {clip}", flush=True)


def phase_mux():
    for shot in shots():
        sid = shot["id"]
        video = OUT / f"{sid}_stage2.mp4"
        pcm = OUT / f"{sid}_h3.wav"
        dest = OUT / f"{sid}_super_accel.mp4"
        if not video.is_file():
            sys.exit(f"missing Stage-2 video {video}")
        if not pcm.is_file():
            print(f"[mux] {sid} no H3 PCM — copying Stage-2 as-is", flush=True)
            dest.write_bytes(video.read_bytes())
            continue
        mux_pcm(video, pcm, dest)
        print(f"[mux] {sid} H3 PCM muxed → {dest}", flush=True)


if a.phase in ("stage1", "all"):
    phase_stage1()
if a.phase in ("stage2", "all"):
    phase_stage2()
if a.phase in ("mux", "all"):
    phase_mux()

#!/usr/bin/env python3
"""Parallel film driver — MiniMax-H3 continuous-take productions on N DGX Sparks.

Distributes the three workloads of a chain-based film across a fleet:
  * keyframe board       -> CREATE node (Sol-enabled process), sequential + QC gate
  * continuation chains  -> CHAIN nodes (Sol-free processes), one chain per node,
                            all nodes rendering AT ONCE (clips serial within a chain)
  * ESRGAN x2 upscaling  -> CREATE node workers that pick up each act THE MOMENT its
                            chain stitches — overlapped with the remaining chains, so
                            the 2x master lands minutes after the last chain
  * assembly             -> split-view composition, act concat, song mux

Usage:
  parallel-film-driver.py --plan film.json --chain-nodes A:8188,B:8188 \
      --create-node C:8188 --phase kf|film|assemble [--no-upscale]

Plan schema: see example_film_plan.json. Chains render 10 s clips with Herrgott's
H3 Infinite Continuation Suite; each act stores latents in its own directory and is
stitched with the suite's freeze-aware chain stitcher.

Requires h3-weld.py (submit/poll helpers) alongside this script or in ~/comfy.
"""
import argparse, json, subprocess, sys, threading, time, queue
from pathlib import Path

import importlib.util
for base in (Path(__file__).resolve().parent, Path.home() / "comfy"):
    if (base / "h3-weld.py").is_file():
        _s = importlib.util.spec_from_file_location("h3weld", str(base / "h3-weld.py"))
        W = importlib.util.module_from_spec(_s); _s.loader.exec_module(W)
        break
else:
    sys.exit("h3-weld.py not found (needs submit/wait helpers)")

ap = argparse.ArgumentParser()
ap.add_argument("--plan", required=True)
ap.add_argument("--chain-nodes", required=True, help="comma list, Sol-FREE processes")
ap.add_argument("--create-node", required=True, help="Sol-ENABLED process (kf + upscale)")
ap.add_argument("--phase", required=True, choices=["kf", "film", "assemble"])
ap.add_argument("--outdir", default=str(Path.home() / "Videos" / "parallel_film"))
ap.add_argument("--no-upscale", action="store_true")
ap.add_argument("--upscale-model", default="RealESRGAN_x2plus.pth")
a = ap.parse_args()

PLAN = json.loads(Path(a.plan).read_text())
OUT = Path(a.outdir); OUT.mkdir(parents=True, exist_ok=True)
CHAIN_NODES = [n.strip() for n in a.chain_nodes.split(",")]
CREATE = a.create_node.strip()
ALL_NODES = CHAIN_NODES + [CREATE]
W_, H_ = PLAN.get("width", 864), PLAN.get("height", 480)
SEED = PLAN.get("seed", 1000)
STYLE = PLAN["style"]


# ----------------------------------------------------------------- keyframes
def kf_graph(prompt, seed, prefix, first=None):
    g = {
        "u": {"class_type": "UNETLoader",
              "inputs": {"unet_name": PLAN["unet"], "weight_dtype": "default"}},
        "c": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": PLAN["te_file"], "type": "minimax", "device": "default"}},
        "vv": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["video_vae"]}},
        "va": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["audio_vae"]}},
        "cond": {"class_type": "MiniMaxH3TextToVideoAudio" if not first else "MiniMaxH3ImageToVideoAudio",
                 "inputs": {"prompt": prompt, "width": W_, "height": H_,
                            "length": PLAN.get("kf_frames", 22),
                            "clip": ["c", 0], "vae": ["vv", 0],
                            **({"image": ["img", 0]} if first else {})}},
        "shift": {"class_type": "MiniMaxH3SigmaShift",
                  "inputs": {"shift_video": 12, "shift_audio": 3, "model": ["u", 0]}},
        "guide": {"class_type": "BasicGuider",
                  "inputs": {"model": ["shift", 0], "conditioning": ["cond", 0]}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "sched": {"class_type": "BasicScheduler",
                  "inputs": {"scheduler": "simple", "steps": 20, "denoise": 1.0,
                             "model": ["shift", 0]}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["noise", 0], "guider": ["guide", 0],
                           "sampler": ["samp", 0], "sigmas": ["sched", 0],
                           "latent_image": ["cond", 1]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["run", 0], "vae": ["vv", 0]}},
        "vid": {"class_type": "CreateVideo", "inputs": {"fps": 24, "images": ["dec", 0]}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["vid", 0], "filename_prefix": prefix,
                            "format": "mp4", "codec": "h264"}},
    }
    if first:
        g["img"] = {"class_type": "LoadImage", "inputs": {"image": first}}
    return g


def phase_kf():
    kfs = PLAN["keyframes"]
    for i, (kf_id, text) in enumerate(kfs.items()):
        prompt = f"{STYLE}\n{text}"
        g = kf_graph(prompt, SEED + i, f"film_kf_{kf_id}")
        pid = W.submit(CREATE, g)
        clip = OUT / f"kf_{kf_id}.mp4"
        W.wait_and_fetch(CREATE, pid, clip, timeout=2400, tag=f"kf:{kf_id}")
        png = OUT / f"kf_{kf_id}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.12",
                        "-i", str(clip), "-frames:v", "1", str(png)], check=True)
        for n in ALL_NODES:
            W.upload_image(n, png, f"film_{kf_id}.png")
        print(f"[{i+1}/{len(kfs)}] kf {kf_id}", flush=True)
    print("KF BOARD DONE — QC the stills before running --phase film", flush=True)


# ------------------------------------------------------------------- chains
def start_graph(clip, act):
    return {
        "u": {"class_type": "UNETLoader",
              "inputs": {"unet_name": PLAN["unet"], "weight_dtype": "default"}},
        "c": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": PLAN["te_file"], "type": "minimax", "device": "default"}},
        "vv": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["video_vae"]}},
        "va": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["audio_vae"]}},
        "f": {"class_type": "LoadImage", "inputs": {"image": f"film_{clip['kf_first']}.png"}},
        "l": {"class_type": "LoadImage", "inputs": {"image": f"film_{clip['kf_last']}.png"}},
        "start": {"class_type": "H3ContinuousStartV11",
                  "inputs": {"prompt": act_cast(act) + STYLE + " " + clip["motion"],
                             "width": W_, "height": H_,
                             "duration": PLAN.get("clip_duration", 10.0),
                             "ref_image_size": "match", "clip": ["c", 0], "vae": ["vv", 0],
                             "first_frame": ["f", 0], "last_frame": ["l", 0],
                             "reference_image": ["f", 0]}},
        **_sampler_tail("start"),
    }


def continue_graph(clip, act, idx):
    g = {
        "u": {"class_type": "UNETLoader",
              "inputs": {"unet_name": PLAN["unet"], "weight_dtype": "default"}},
        "c": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": PLAN["te_file"], "type": "minimax", "device": "default"}},
        "vv": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["video_vae"]}},
        "va": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["audio_vae"]}},
        "prev": {"class_type": "H3ContinuousLoadLatent",
                 "inputs": {"latent_path": f"h3_continuous_{act}", "clip_index": idx}},
        "l": {"class_type": "LoadImage", "inputs": {"image": f"film_{clip['kf_last']}.png"}},
        "start": {"class_type": "H3ContinuousContinueV11",
                  "inputs": {"prompt": act_cast(act) + STYLE + " " + clip["motion"],
                             "width": W_, "height": H_,
                             "duration": PLAN.get("clip_duration", 10.0),
                             "context_frames": "22", "handover_mode": "auto",
                             "alignment_mode": "phase_aligned_extended",
                             "manual_landing_tail_frames": 34, "ref_image_size": "match",
                             "clip": ["c", 0], "vae": ["vv", 0],
                             "previous_latent": ["prev", 0], "handover": ["prev", 3],
                             "last_frame": ["l", 0], "reference_image": ["l", 0]}},
    }
    g.update(_sampler_tail("start"))
    return g


def _sampler_tail(cond_node):
    return {
        "shift": {"class_type": "MiniMaxH3SigmaShift",
                  "inputs": {"shift_video": 12, "shift_audio": 3, "model": ["u", 0]}},
        "guide": {"class_type": "BasicGuider",
                  "inputs": {"model": ["shift", 0], "conditioning": [cond_node, 0]}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "sched": {"class_type": "BasicScheduler",
                  "inputs": {"scheduler": "simple", "steps": 20, "denoise": 1.0,
                             "model": ["shift", 0]}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["noise", 0], "guider": ["guide", 0],
                           "sampler": ["samp", 0], "sigmas": ["sched", 0],
                           "latent_image": [cond_node, 1]}},
        "analyze": {"class_type": "H3ContinuousAnalyzeHandoverV11",
                    "inputs": {"preset": "Balanced", "analysis_window": 72, "freeze_hold": 8,
                               "safety_margin": 3, "context_frames": "22", "analysis_size": 192,
                               "final_mean_diff_threshold": 0.012,
                               "final_active_pixel_threshold": 0.025,
                               "max_final_active_area_percent": 3.0,
                               "transition_mean_diff_threshold": 0.002,
                               "transition_active_pixel_threshold": 0.01,
                               "max_transition_active_area_percent": 1.0,
                               "min_static_transition_percent": 70.0,
                               "max_consecutive_motion_outliers": 2,
                               "final_reference_frames": 15, "min_final_match_percent": 75.0,
                               "max_consecutive_final_outliers": 3, "safety_mode": "fixed",
                               "images": ["dec", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["run", 0], "vae": ["vv", 0]}},
        "deca": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["run", 0], "vae": ["va", 0]}},
        "savelat": {"class_type": "H3ContinuousSaveLatent",
                    "inputs": {"filename_prefix": "SET_AT_SUBMIT", "clip_index": 0,
                               "latent": ["run", 0], "handover": ["analyze", 0]}},
        "stitchout": {"class_type": "H3ContinuousStitchOutputV11",
                      "inputs": {"output_mode": "Full", "images": ["dec", 0],
                                 "handover": ["analyze", 0], "audio": ["deca", 0]}},
        "vid": {"class_type": "CreateVideo",
                "inputs": {"fps": 24, "images": ["stitchout", 0], "audio": ["stitchout", 1]}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["vid", 0], "filename_prefix": "SET_AT_SUBMIT",
                            "format": "mp4", "codec": "h264"}},
    }


def act_cast(act):
    solo = PLAN["acts"][act].get("solo_cast")
    if solo:
        return solo + " "
    return PLAN.get("cast", "") + " "


def run_chain(act, node):
    clips = PLAN["acts"][act]["clips"]
    for i, clip in enumerate(clips):
        g = start_graph(clip, act) if i == 0 else continue_graph(clip, act, i)
        g["savelat"]["inputs"]["filename_prefix"] = f"h3_continuous_{act}/clip"
        g["savelat"]["inputs"]["clip_index"] = i + 1
        g["save"]["inputs"]["filename_prefix"] = f"video/film_{act}_clip{i}"
        g["noise"]["inputs"]["noise_seed"] = SEED + 1000 * (list(PLAN["acts"]).index(act) + 1) + i
        for attempt in (1, 2):
            try:
                pid = W.submit(node, g)
                W.wait_and_fetch(node, pid, OUT / f"{act}_clip{i}.mp4", timeout=3600,
                                 tag=f"{act}:clip{i}")
                break
            except Exception as e:
                print(f"  {act} clip{i} attempt {attempt} failed: {e}", flush=True)
                if attempt == 2:
                    raise
                time.sleep(30)
        print(f"[{act}] clip {i+1}/{len(clips)} on {node}", flush=True)
    # stitch on the same node, then hand to the upscale queue
    stitch(act, node)
    UPSCALE_Q.put(act)


def stitch(act, node):
    g = {
        "vv": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["video_vae"]}},
        "va": {"class_type": "VAELoader", "inputs": {"vae_name": PLAN["audio_vae"]}},
        "st": {"class_type": "H3ContinuousStitchSavedChainV11",
               "inputs": {"latent_prefix": f"h3_continuous_{act}/clip", "first_clip": 1,
                          "last_clip": len(PLAN["acts"][act]["clips"]),
                          "filename_prefix": f"video/film_{act}_stitched",
                          "video_crossfade_frames": 4, "audio_crossfade_ms": 15.0,
                          "luminance_match": False, "luminance_fade_frames": 16,
                          "max_luminance_correction_percent": 10.0, "crf": 18,
                          "max_safe_tail_bridge_frames": 2,
                          "video_vae": ["vv", 0], "audio_vae": ["va", 0]}},
    }
    try:
        pid = W.submit(node, g)
        W.wait_and_fetch(node, pid, OUT / f"{act}_stitched.mp4", timeout=3600, tag=f"stitch:{act}")
    except Exception:
        pass  # the stitcher writes to the node's output dir without registering an API output
    _fetch_stitch(act, node)
    print(f"[{act}] stitched", flush=True)


def _fetch_stitch(act, node):
    """The suite's stitcher encodes to output/video/ on the node; poll + fetch."""
    host = node.split(":")[0]
    remote = f"~/h3-cotenancy/ComfyUI/output/video/film_{act}_stitched_00001_.mp4"
    for _ in range(90):
        r = subprocess.run(["ssh", host, f"stat -c %s {remote} 2>/dev/null"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            s1 = r.stdout.strip(); time.sleep(10)
            s2 = subprocess.run(["ssh", host, f"stat -c %s {remote}"],
                                capture_output=True, text=True).stdout.strip()
            if s1 == s2:
                subprocess.run(["scp", "-q", f"{host}:{remote}",
                                str(OUT / f"{act}_stitched.mp4")], check=True)
                return
        time.sleep(20)
    raise RuntimeError(f"stitch fetch timed out for {act}")


# ----------------------------------------------------- overlapped upscaling
UPSCALE_Q: "queue.Queue[str]" = queue.Queue()


def upscale_worker():
    while True:
        act = UPSCALE_Q.get()
        if act is None:
            return
        src = OUT / f"{act}_stitched.mp4"
        name = f"film_up_{act}.mp4"
        W.upload_image(CREATE, src, name)
        g = {
            "1": {"class_type": "LoadVideo", "inputs": {"file": name}},
            "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
            "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": a.upscale_model}},
            "4": {"class_type": "ImageUpscaleWithModel",
                  "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
            "5": {"class_type": "CreateVideo",
                  "inputs": {"images": ["4", 0], "fps": ["2", 2], "audio": ["2", 1]}},
            "6": {"class_type": "SaveVideo",
                  "inputs": {"video": ["5", 0], "filename_prefix": f"video/film_{act}_2x",
                             "format": "mp4", "codec": "h264"}},
        }
        pid = W.submit(CREATE, g)
        W.wait_and_fetch(CREATE, pid, OUT / f"{act}_2x.mp4", timeout=3600, tag=f"up:{act}")
        print(f"[{act}] 2x upscaled (overlapped)", flush=True)


def phase_film():
    acts = list(PLAN["acts"])
    workers = []
    if not a.no_upscale:
        for _ in range(max(1, len(CHAIN_NODES) // 2)):
            t = threading.Thread(target=upscale_worker, daemon=True)
            t.start(); workers.append(t)
    # longest chains first, one per node; nodes pick up the next chain when free
    order = sorted(acts, key=lambda x: -len(PLAN["acts"][x]["clips"]))
    q = queue.Queue()
    for act in order:
        q.put(act)

    def node_loop(node):
        while True:
            try:
                act = q.get_nowait()
            except queue.Empty:
                return
            run_chain(act, node)

    threads = [threading.Thread(target=node_loop, args=(n,)) for n in CHAIN_NODES]
    [t.start() for t in threads]; [t.join() for t in threads]
    for _ in workers:
        UPSCALE_Q.put(None)
    [t.join() for t in workers]
    print("ALL CHAINS RENDERED, STITCHED" + ("" if a.no_upscale else ", UPSCALED"), flush=True)


# ---------------------------------------------------------------- assembly
def phase_assemble():
    suffix = "" if a.no_upscale else "_2x"
    scale = 1 if a.no_upscale else 2
    half, hh = 432 * scale, 480 * scale
    layout = PLAN["assembly"]
    parts = []
    for seg in layout:
        if isinstance(seg, list):  # split view [left_act, right_act]
            l, r = seg
            out = OUT / f"split_{l}_{r}{suffix}.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                            "-i", str(OUT / f"{l}_stitched{suffix}.mp4".replace("_stitched_2x", "_2x")),
                            "-i", str(OUT / f"{r}_stitched{suffix}.mp4".replace("_stitched_2x", "_2x")),
                            "-filter_complex",
                            f"[0:v]crop={half}:{hh}:{half//2}:0[l];"
                            f"[1:v]crop={half}:{hh}:{half//2}:0[r];[l][r]hstack=inputs=2[v]",
                            "-map", "[v]", "-r", "24", str(out)], check=True)
            parts.append(out)
        else:
            f = OUT / (f"{seg}_2x.mp4" if not a.no_upscale else f"{seg}_stitched.mp4")
            parts.append(f)
    concat = OUT / "film_concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-an", "-c:v", "libx264", "-crf", "18",
                    str(OUT / "film_video.mp4")], check=True)
    dur = float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(OUT / "film_video.mp4")],
                               capture_output=True, text=True, check=True).stdout.strip())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(OUT / "film_video.mp4"), "-i", PLAN["song"],
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-af", f"afade=t=out:st={max(0, dur-3):.2f}:d=3", "-c:a", "aac",
                    "-t", f"{dur:.3f}", str(OUT / "film_final.mp4")], check=True)
    print("ASSEMBLED:", OUT / "film_final.mp4", flush=True)


if a.phase == "kf":
    phase_kf()
elif a.phase == "film":
    phase_film()
else:
    phase_assemble()

"""Turn a video plan into an mp4 with Higgsfield: image per shot -> animated clip -> one video.

Higgsfield bills per generation (video by the second), so a plan is only rendered after it is
approved. Model IDs are on the model pages at cloud.higgsfield.ai and can be swapped with the
HIGGSFIELD_IMAGE_MODEL / HIGGSFIELD_VIDEO_MODEL variables.
"""

import logging
import os
import subprocess
from pathlib import Path

import requests

IMAGE_MODEL = os.environ.get("HIGGSFIELD_IMAGE_MODEL") or "bytedance/seedream/v4/text-to-image"
VIDEO_MODEL = os.environ.get("HIGGSFIELD_VIDEO_MODEL") or "kling-video/v3.0-turbo/image-to-video"
WIDTH, HEIGHT = 1080, 1920


class RenderError(RuntimeError):
    pass


def render(item, seconds, hf=None):
    """Generate an image and then a clip for every shot. Returns the clip URLs for the queue."""
    hf = hf or _higgsfield()
    clips = []
    for i, shot in enumerate(item["shots"], 1):
        logging.info("Shot %d/%d: image", i, len(item["shots"]))
        image = _run(hf, IMAGE_MODEL, {"prompt": shot["image_prompt"], "resolution": "2K", "aspect_ratio": "9:16"})
        image_url = image["images"][0]["url"]
        logging.info("Shot %d/%d: video", i, len(item["shots"]))
        video = _run(hf, VIDEO_MODEL, {"image_url": image_url, "prompt": shot["motion_prompt"], "duration": seconds})
        clips.append({"image_url": image_url, "video_url": video["video"]["url"]})
    return clips


def assemble(clips, out_dir, download=None, ffmpeg=None):
    """Download the clips and join them into one 1080x1920 H.264 mp4 without audio.

    Audio is left out on purpose: add a TikTok sound or voiceover in the app.
    """
    download, ffmpeg = download or _download, ffmpeg or _ffmpeg
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, clip in enumerate(clips, 1):
        path = out_dir / f"shot_{i}.mp4"
        download(clip["video_url"], path)
        paths.append(path)
    listing = out_dir / "clips.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in paths))
    video = out_dir / "video.mp4"
    ffmpeg([
        "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart", str(video),
    ])  # fmt: skip
    return video


def _run(hf, model, arguments):
    controller = hf.submit(model, arguments=arguments)
    status = None
    for status in controller.poll_request_status():
        pass
    if not isinstance(status, hf.Completed):  # Failed, NSFW or Cancelled
        raise RenderError(f"{model} ended as {type(status).__name__} for {arguments.get('prompt', '')[:80]!r}")
    return controller.get()


def _higgsfield():
    if not (os.environ.get("HF_KEY") or (os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET"))):
        raise SystemExit("Set HF_KEY=key:secret (or HF_API_KEY and HF_API_SECRET) from cloud.higgsfield.ai.")
    import higgsfield_client

    return higgsfield_client


def _download(url, path):
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)


def _ffmpeg(args):
    result = subprocess.run(["ffmpeg", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode:
        raise RenderError(f"ffmpeg failed: {result.stderr[-500:]}")

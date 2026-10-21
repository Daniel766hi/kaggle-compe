"""Turn a video plan into an mp4 with Higgsfield: image per shot -> animated clip -> one video.

Higgsfield bills per generation (video by the second), so a plan is only rendered after it is
approved. Model IDs are on the model pages at cloud.higgsfield.ai and can be swapped with the
HIGGSFIELD_IMAGE_MODEL / HIGGSFIELD_VIDEO_MODEL variables.
"""

import json
import logging
import os
import subprocess
import textwrap
from pathlib import Path

import requests

IMAGE_MODEL = os.environ.get("HIGGSFIELD_IMAGE_MODEL") or "bytedance/seedream/v4/text-to-image"
VIDEO_MODEL = os.environ.get("HIGGSFIELD_VIDEO_MODEL") or "kling-video/v3.0-turbo/image-to-video"
WIDTH, HEIGHT = 1080, 1920
FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux and GitHub Actions
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
)
MUSIC_TYPES = {".mp3", ".m4a", ".aac", ".wav"}


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


def assemble(clips, out_dir, texts=(), seconds=None, audio=False, music=None, download=None, ffmpeg=None):
    """Download the clips and join them into one 1080x1920 H.264 mp4.

    texts: on-screen text burned in, one per clip, each shown for `seconds`.
    audio: add an AAC track, `music` (looped and cut to length) or silence. Without it the
    video has no audio, for platforms where a sound is added in the app.
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

    args = ["-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    if audio and music:
        args += ["-stream_loop", "-1", "-i", str(music)]
    elif audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    filters = [
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease",
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
        "fps=30",
        *_captions(texts, seconds, out_dir),
    ]
    args += ["-vf", ",".join(filters), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest"]
    else:
        args += ["-an"]
    video = out_dir / "video.mp4"
    ffmpeg([*args, "-movflags", "+faststart", str(video)])
    return video


def pick_music(path, item_id):
    """A music file, or one file from a folder (rotating by item id); None when there is none."""
    path = Path(path) if path else None
    if path is None or not path.exists():
        return None
    if path.is_file():
        return path
    tracks = sorted(p for p in path.iterdir() if p.suffix.lower() in MUSIC_TYPES)
    return tracks[item_id % len(tracks)] if tracks else None


def probe(path):
    """Duration in seconds, size in bytes and stream codecs, from ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,sample_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )  # fmt: skip
    if out.returncode:
        raise RenderError(f"ffprobe failed: {out.stderr[-300:]}")
    info = json.loads(out.stdout)
    return {
        "duration": float(info["format"]["duration"]),
        "size": int(info["format"]["size"]),
        "streams": {s["codec_type"]: s for s in info["streams"]},
    }


def _captions(texts, seconds, out_dir):
    """drawtext filters: each text centred a little above the middle, clear of the app's buttons."""
    if not texts:
        return []
    font = os.environ.get("VIDEO_FONT") or next((f for f in FONTS if os.path.exists(f)), None)
    if not font:
        raise RenderError("No font for on-screen text; install fonts-dejavu-core or set VIDEO_FONT to a .ttf file.")
    filters = []
    for i, text in enumerate(texts):
        if not text.strip():
            continue
        text_file = out_dir / f"text_{i + 1}.txt"
        text_file.write_text(textwrap.fill(text.strip(), 20))  # read from a file: no escaping trouble
        filters.append(
            f"drawtext=fontfile='{font}':textfile='{text_file}':fontsize=62:fontcolor=white:line_spacing=16"
            f":box=1:boxcolor=black@0.55:boxborderw=30:x=(w-text_w)/2:y=h*0.32-text_h/2"
            f":enable='between(t,{i * seconds},{(i + 1) * seconds})'"
        )
    return filters


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

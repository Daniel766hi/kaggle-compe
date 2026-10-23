"""Turn a video plan into an mp4: one clip per shot, joined, with on-screen text and audio.

Clips come from Pexels stock videos (free: a PEXELS_API_KEY from pexels.com/api, clips free to
use, creators credited in the caption) or from Higgsfield (paid: image per shot, then an animated
clip; model IDs can be swapped with HIGGSFIELD_IMAGE_MODEL / HIGGSFIELD_VIDEO_MODEL). A plan is only
rendered after it is approved.
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
    "C:/Windows/Fonts/arialbd.ttf",  # Windows
)
MUSIC_TYPES = {".mp3", ".m4a", ".aac", ".wav"}
PEXELS_SEARCH = "https://api.pexels.com/videos/search"


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


def render_stock(item, seconds, session=None):
    """Find a free Pexels clip for every shot. Returns the clip records, with credits, for the queue."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise SystemExit("Set PEXELS_API_KEY (free: pexels.com/api, 'Your API key').")
    session = session or requests.Session()
    used, clips = set(), []
    for i, shot in enumerate(item["shots"], 1):
        query = shot["search_query"]
        logging.info("Shot %d/%d: finding a clip for %r", i, len(item["shots"]), query)
        video = None
        for params in ({"orientation": "portrait"}, {}):  # vertical clips first, then any (cropped to fit)
            found = _pexels(session, key, {"query": query, "per_page": 15, **params})
            video = next((v for v in found if v["id"] not in used and v.get("duration", 0) >= seconds), None)
            if video:
                break
        if video is None:
            raise RenderError(f"No stock clip found for {query!r}. Revise the plan with a simpler search.")
        used.add(video["id"])
        clips.append({
            "video_url": _best_file(video["video_files"])["link"],
            "source": video["url"],
            "credit": video["user"]["name"],
            "query": query,
        })  # fmt: skip
    return clips


def credits(clips):
    """The caption line that credits stock clip creators ('' for AI clips)."""
    names = list(dict.fromkeys(c["credit"] for c in clips if c.get("credit")))
    return f"Clips from Pexels: {', '.join(names)}" if names else ""


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
    trim = f"outpoint {seconds}\n" if seconds else ""  # stock clips are longer than a shot
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n{trim}" for p in paths))

    args = ["-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    if audio and music:
        args += ["-stream_loop", "-1", "-i", str(music)]
    elif audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    filters = [
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase",
        f"crop={WIDTH}:{HEIGHT}",  # fill the vertical frame; landscape clips lose their sides
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
            f"drawtext=fontfile='{_ff_path(font)}':textfile='{_ff_path(text_file)}':fontsize=62:fontcolor=white:line_spacing=16"
            f":box=1:boxcolor=black@0.55:boxborderw=30:x=(w-text_w)/2:y=h*0.32-text_h/2"
            f":enable='between(t,{i * seconds},{(i + 1) * seconds})'"
        )
    return filters


def _ff_path(path):
    """A path inside an ffmpeg filter: forward slashes, and the colon of C: escaped (Windows)."""
    return Path(path).as_posix().replace(":", "\\:")


def _pexels(session, key, params):
    resp = session.get(PEXELS_SEARCH, params=params, headers={"Authorization": key}, timeout=60)
    if resp.status_code >= 400:
        raise RenderError(f"Pexels search failed: HTTP {resp.status_code} {resp.text[:200]}")
    return resp.json().get("videos", [])


def _best_file(files):
    """The smallest mp4 that is still at least 1280 px tall, or the largest one there is."""
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
    if not mp4:
        raise RenderError("Pexels returned no mp4 file for that clip")
    tall = sorted((f for f in mp4 if (f.get("height") or 0) >= 1280), key=lambda f: f["height"])
    return tall[0] if tall else max(mp4, key=lambda f: f.get("height") or 0)


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

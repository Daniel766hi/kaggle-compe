"""Turn a video plan into an mp4: one clip per shot, joined, with on-screen text and audio.

Clips come from free stock videos, creators credited in the caption: Pixabay (PIXABAY_API_KEY from
pixabay.com/api/docs) or Pexels (PEXELS_API_KEY; Pexels has paused new keys). Or from Higgsfield (paid: image per shot, then an animated
clip; model IDs can be swapped with HIGGSFIELD_IMAGE_MODEL / HIGGSFIELD_VIDEO_MODEL). A plan is only
rendered after it is approved.
"""

import json
import logging
import os
import random
import subprocess
import textwrap
from pathlib import Path

import requests

from .music import make_track

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
PIXABAY_SEARCH = "https://pixabay.com/api/videos/"
FADE = 0.4  # seconds of crossfade between shots
LEAD_IN = 0.8  # start this far into a stock clip: many open on a still frame
PICK_FROM = 12  # random pick among this many good matches, so popular clips don't repeat
STOCK_SITES = {"pixabay": ("PIXABAY_API_KEY", "Pixabay"), "pexels": ("PEXELS_API_KEY", "Pexels")}
# Pixabay sits behind Cloudflare, which challenges Python's default user agent.
USER_AGENT = "Mozilla/5.0 (compatible; AI-Office/1.0; +https://github.com/Daniel766hi/kaggle-compe)"


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


def stock_site():
    """Which free stock site to search: STOCK_SITE, or whichever key is set (Pixabay first)."""
    chosen = (os.environ.get("STOCK_SITE") or "").strip().lower()
    if chosen in STOCK_SITES:
        return chosen
    for site, (env, _) in STOCK_SITES.items():
        if os.environ.get(env):
            return site
    raise SystemExit("Set PIXABAY_API_KEY (free: log in at pixabay.com, then open pixabay.com/api/docs).")


def render_stock(item, seconds, session=None, exclude=(), rng=None):
    """Find a free stock clip for every shot. Returns the clip records, with credits, for the queue.

    exclude: clips already used (their page URLs), so no two videos show the same footage.
    Each shot takes a random pick among the best unused matches, not always the top result.
    """
    site = stock_site()
    env, name = STOCK_SITES[site]
    key = os.environ.get(env)
    if not key:
        raise SystemExit(f"Set {env} to use {name} clips.")
    session, rng = session or requests.Session(), rng or random.Random()
    search = _search_pixabay if site == "pixabay" else _search_pexels
    used, clips = set(exclude), []
    for i, shot in enumerate(item["shots"], 1):
        query = shot["search_query"]
        logging.info("Shot %d/%d: finding a %s clip for %r", i, len(item["shots"]), name, query)
        candidates = []
        for clip in search(session, key, query):
            if clip["page"] not in used and clip["duration"] >= seconds:
                candidates.append(clip)
                if len(candidates) == PICK_FROM:
                    break
        if not candidates:
            raise RenderError(f"No unused stock clip found for {query!r}. Revise the plan with a different search.")
        clip = rng.choice(candidates)
        used.add(clip["page"])
        clips.append({"video_url": clip["url"], "source": clip["page"], "credit": clip["credit"], "site": name, "query": query})
    return clips


def used_clips(items, except_id=None):
    """Page URLs of every stock clip already in a video, so new videos don't repeat them."""
    return {c["source"] for it in items if it["id"] != except_id for c in it.get("clips", []) if c.get("source")}


def credits(clips):
    """The caption line that credits stock clip creators ('' for AI clips)."""
    names = list(dict.fromkeys(c["credit"] for c in clips if c.get("credit")))
    if not names:
        return ""
    site = next((c.get("site") for c in clips if c.get("site")), "Pexels")
    return f"Clips from {site}: {', '.join(names)}"


def assemble(clips, out_dir, texts=(), seconds=None, audio=False, music=None, download=None, ffmpeg=None, seed=0):
    """Download the clips and join them into one smooth 1080x1920 H.264 mp4.

    Each clip starts a moment in (stock footage often opens on a still frame), fills the vertical
    frame, and crossfades into the next. texts: on-screen text, one per clip, fading in and out.
    audio: add an AAC track: `music` (a file, looped and cut to length) or, without one, an original
    tune made for this video (shorts/music.py). Without audio the video is silent, for platforms
    where a sound is added in the app.
    """
    download, ffmpeg = download or _download, ffmpeg or _ffmpeg
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, clip in enumerate(clips, 1):
        path = out_dir / f"shot_{i}.mp4"
        download(clip["video_url"], path)
        paths.append(path)
    seconds = seconds or min(_duration(p) for p in paths)
    fade = round(min(FADE, seconds / 4), 2) if len(paths) > 1 else 0
    total = len(paths) * seconds - (len(paths) - 1) * fade

    args, chains = ["-y"], []
    for i, path in enumerate(paths):
        length = _duration(path)
        start = round(min(LEAD_IN, max(0.0, length - seconds - fade)), 2)  # skip a still opening frame
        args += ["-ss", str(start), "-t", str(seconds + fade), "-i", str(path)]
        chains.append(
            f"[{i}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1,"
            f"fps=30,format=yuv420p,eq=saturation=1.06:contrast=1.03,"
            f"tpad=stop_mode=clone:stop_duration={seconds + fade},trim=duration={seconds + fade},setpts=PTS-STARTPTS[v{i}]"
        )
    last = "v0"
    for i in range(1, len(paths)):
        offset = round(i * (seconds - fade), 3)
        chains.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={offset}[x{i}]")
        last = f"x{i}"
    captions = _captions(texts, seconds, out_dir, fade)
    chains.append(f"[{last}]trim=duration={total}{',' if captions else ''}{','.join(captions)}[video]")

    if audio:
        if music == "none":
            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        else:
            if not music:
                music = out_dir / "music.wav"
                make_track(music, total, seed)
            args += ["-stream_loop", "-1", "-i", str(music)]
        fade_out = min(1.5, total / 4)
        chains.append(
            f"[{len(paths)}:a]atrim=duration={total},asetpts=PTS-STARTPTS,lowpass=f=9000,"
            f"afade=t=in:d=0.3,afade=t=out:st={round(total - fade_out, 3)}:d={round(fade_out, 3)},volume=0.9[audio]"
        )
    args += ["-filter_complex", ";".join(chains), "-map", "[video]"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30"]
    if audio:
        args += ["-map", "[audio]", "-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
    else:
        args += ["-an"]
    video = out_dir / "video.mp4"
    ffmpeg([*args, "-t", str(total), "-movflags", "+faststart", str(video)])
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


def _captions(texts, seconds, out_dir, fade=0):
    """drawtext filters: bold white text with a dark outline, centred a little above the middle
    (clear of the app's buttons), each line centred, fading in and out over its own shot."""
    if not texts:
        return []
    font = os.environ.get("VIDEO_FONT") or next((f for f in FONTS if os.path.exists(f)), None)
    if not font:
        raise RenderError("No font for on-screen text; install fonts-dejavu-core or set VIDEO_FONT to a .ttf file.")
    size, gap = 68, 86  # font size and line height in pixels
    filters = []
    for i, text in enumerate(texts):
        if not text.strip():
            continue
        begin = round(i * (seconds - fade) + (0.15 if i == 0 else fade / 2), 3)
        end = round((i + 1) * (seconds - fade) + fade / 2 - 0.1, 3)
        alpha = f"if(lt(t,{begin}+0.25),(t-{begin})/0.25,if(gt(t,{end}-0.25),({end}-t)/0.25,1))"
        lines = balanced_lines(text.strip())
        for n, line in enumerate(lines):
            text_file = out_dir / f"text_{i + 1}_{n + 1}.txt"
            text_file.write_text(line, encoding="utf-8")  # read from a file: no escaping trouble
            y = f"h*0.30-{len(lines) * gap // 2}+{n * gap}"
            filters.append(
                f"drawtext=fontfile='{_ff_path(font)}':textfile='{_ff_path(text_file)}':fontsize={size}:fontcolor=white"
                f":borderw=7:bordercolor=black@0.85:shadowx=0:shadowy=4:shadowcolor=black@0.4"
                f":x=(w-text_w)/2:y={y}:alpha='{alpha}':enable='between(t,{begin},{end})'"
            )
    return filters


def balanced_lines(text, width=18):
    """Wrap text into as few lines as fit `width`, with the lines about equally long."""
    count = len(textwrap.wrap(text, width)) or 1
    for w in range(max(1, -(-len(text) // count)), width + 1):  # narrowest width that keeps the count
        lines = textwrap.wrap(text, w)
        if len(lines) <= count:
            return lines
    return textwrap.wrap(text, width)


def _duration(path):
    return probe(path)["duration"]


def _ff_path(path):
    """A path inside an ffmpeg filter: forward slashes, and the colon of C: escaped (Windows)."""
    return Path(path).as_posix().replace(":", "\\:")


def _search_pexels(session, key, query):
    """Candidate clips from Pexels: vertical ones first, then any orientation (cropped to fit)."""
    for extra in ({"orientation": "portrait"}, {}):
        resp = session.get(PEXELS_SEARCH, params={"query": query, "per_page": 40, **extra},
                           headers={"Authorization": key}, timeout=60)  # fmt: skip
        if resp.status_code >= 400:
            raise RenderError(f"Pexels search failed: HTTP {resp.status_code} {resp.text[:200]}")
        for video in resp.json().get("videos", []):
            yield {
                "id": video["id"], "duration": video.get("duration", 0), "url": _best_pexels_file(video["video_files"])["link"],
                "page": video["url"], "credit": video["user"]["name"],
            }  # fmt: skip


def _best_pexels_file(files):
    """The smallest mp4 that is still at least 1280 px tall, or the largest one there is."""
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
    if not mp4:
        raise RenderError("Pexels returned no mp4 file for that clip")
    tall = sorted((f for f in mp4 if (f.get("height") or 0) >= 1280), key=lambda f: f["height"])
    return tall[0] if tall else max(mp4, key=lambda f: f.get("height") or 0)


def _search_pixabay(session, key, query):
    """Candidate clips from Pixabay (landscape mostly; cropped to fill the vertical frame)."""
    params = {"key": key, "q": query, "per_page": 50, "safesearch": "true"}
    resp = session.get(PIXABAY_SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
    if resp.status_code >= 400:
        raise RenderError(f"Pixabay search failed: HTTP {resp.status_code} {resp.text[:200]}")
    for hit in resp.json().get("hits", []):
        size = _best_pixabay_size(hit.get("videos") or {})
        if size:
            yield {"id": hit["id"], "duration": hit.get("duration", 0), "url": size["url"],
                   "page": hit.get("pageURL", ""), "credit": hit.get("user", "")}  # fmt: skip


def _best_pixabay_size(videos):
    """1080p ('medium' usually) is enough for a vertical crop; 4K is a slow download."""
    for name in ("medium", "large", "small"):
        size = videos.get(name) or {}
        if size.get("url"):
            return size
    return None


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
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": USER_AGENT}) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)


def _ffmpeg(args):
    result = subprocess.run(["ffmpeg", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode:
        raise RenderError(f"ffmpeg failed: {result.stderr[-500:]}")

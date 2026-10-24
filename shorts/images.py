"""AI pictures for the videos, and the camera moves that bring them to life.

Pictures come from FLUX on Cloudflare Workers AI: free for about 60 pictures a day with a free
Cloudflare account (10,000 "neurons" a day, reset at 00:00 UTC = 07:00 WIB). Set
CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (a token with the "Workers AI" permission).
Every shot after the first is drawn with the first picture as a reference, so the animal looks
the same all through the video.

Optional real motion: with DASHSCOPE_API_KEY set, Alibaba's Wan model (from the Qwen team's
Model Studio) animates each picture into a video clip. New accounts get a small free quota; after
that it is paid, and the office falls back to smooth camera moves over the pictures.
"""

import base64
import logging
import os
import tempfile
import time
from pathlib import Path

import requests

from .render import FADE, HEIGHT, WIDTH, RenderError, _download, _ffmpeg

CLOUDFLARE_RUN = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
IMAGE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
IMAGE_SIZE = (768, 1344)  # vertical, multiples of 16; cropped to 9:16 when animated
REFERENCE_SIDE = 512  # the model takes reference pictures up to 512 x 512
WAN_URL = "https://dashscope-intl.aliyuncs.com"
WAN_MODEL = "wan2.6-i2v-flash"
CAMERA = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up")
ZOOM = 0.14  # how far the camera moves: 14% of the frame


def configured():
    return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"))


class CloudflareImages:
    def __init__(self, account_id=None, token=None, session=None, model=None):
        self.account = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.token = token or os.environ.get("CLOUDFLARE_API_TOKEN")
        if not (self.account and self.token):
            raise RenderError(
                "AI pictures need a free Cloudflare account: set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN "
                "(run the setup script, or see the README)."
            )
        self.session = session or requests.Session()
        self.model = model or os.environ.get("CLOUDFLARE_IMAGE_MODEL") or IMAGE_MODEL

    def generate(self, prompt, reference=None):
        """One vertical picture (PNG/JPEG bytes). reference: bytes of a small picture to stay close to."""
        url = CLOUDFLARE_RUN.format(account=self.account, model=self.model)
        headers = {"Authorization": f"Bearer {self.token}"}
        if "flux-1-schnell" in self.model:  # the older model: JSON, square pictures only
            resp = self.session.post(url, headers=headers, json={"prompt": prompt[:2048], "steps": 8}, timeout=120)
        else:
            width, height = IMAGE_SIZE
            fields = {"prompt": (None, prompt[:2048]), "width": (None, str(width)), "height": (None, str(height))}
            if reference:
                fields["input_image_0"] = ("reference.png", reference, "image/png")
            resp = self.session.post(url, headers=headers, files=fields, timeout=120)
        if resp.status_code in (401, 403):
            raise RenderError("Cloudflare didn't accept the API token. Make one with the 'Workers AI' permission.")
        if resp.status_code == 429 or "4006" in resp.text:
            raise RenderError("Today's free AI pictures are used up. They come back at 07:00 WIB (00:00 UTC).")
        if resp.status_code >= 400:
            raise RenderError(f"Cloudflare Workers AI error {resp.status_code}: {resp.text[:300]}")
        try:
            return base64.b64decode(resp.json()["result"]["image"])
        except (ValueError, KeyError, TypeError) as e:
            raise RenderError(f"Cloudflare sent no picture: {resp.text[:300]}") from e


class Wan:
    """Animates a picture into a 5-second clip with Alibaba's Wan model (DASHSCOPE_API_KEY)."""

    def __init__(self, key=None, session=None, sleep=time.sleep):
        self.key = key or os.environ.get("DASHSCOPE_API_KEY")
        self.base = (os.environ.get("DASHSCOPE_BASE_URL") or WAN_URL).rstrip("/")
        self.model = os.environ.get("WAN_MODEL") or WAN_MODEL
        self.session, self.sleep = session or requests.Session(), sleep

    def animate(self, picture, prompt, seconds=5, timeout_s=900):
        """Returns the URL of the finished clip."""
        headers = {"Authorization": f"Bearer {self.key}", "X-DashScope-Async": "enable"}
        body = {
            "model": self.model,
            "input": {"prompt": prompt, "img_url": "data:image/png;base64," + base64.b64encode(picture).decode()},
            "parameters": {"resolution": "720P", "duration": seconds, "prompt_extend": True},
        }
        resp = self.session.post(f"{self.base}/api/v1/services/aigc/video-generation/video-synthesis",
                                 headers=headers, json=body, timeout=60)  # fmt: skip
        if resp.status_code >= 400:
            raise RenderError(f"Wan error {resp.status_code}: {resp.text[:300]}")
        task = resp.json()["output"]["task_id"]
        waited = 0
        while waited < timeout_s:
            self.sleep(10)
            waited += 10
            out = self.session.get(f"{self.base}/api/v1/tasks/{task}", headers={"Authorization": headers["Authorization"]},
                                   timeout=60).json().get("output", {})  # fmt: skip
            if out.get("task_status") == "SUCCEEDED":
                return out["video_url"]
            if out.get("task_status") in ("FAILED", "CANCELED", "UNKNOWN"):
                raise RenderError(f"Wan couldn't animate the picture: {out.get('message') or out.get('code')}")
        raise RenderError("Wan took too long")


def render_pictures(item, seconds, out_dir, images=None, wan=None, ffmpeg=None):
    """Draw each shot, then turn it into a moving clip. Returns the clips for render.assemble."""
    images = images or CloudflareImages()
    if wan is None and os.environ.get("DASHSCOPE_API_KEY"):
        wan = Wan()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips, reference = [], None
    for n, shot in enumerate(item["shots"], 1):
        picture = images.generate(shot["image_prompt"], reference)
        path = out_dir / f"picture_{n}.png"
        path.write_bytes(picture)
        if reference is None and "flux-1-schnell" not in images.model:
            reference = _small(path, ffmpeg)  # later shots keep the same animal
        clip = out_dir / f"moving_{n}.mp4"
        source = f"ai-picture:{path.name}"
        if wan is not None:
            try:
                _download(wan.animate(picture, shot.get("action") or shot["image_prompt"], seconds), clip)
                source = f"wan:{path.name}"
            except (RenderError, requests.RequestException, KeyError, ValueError) as e:
                logging.warning("Wan animation failed for shot %d (%s); using a camera move instead", n, e)
                wan = None  # don't try again for the next shots: the quota is probably gone
        if not source.startswith("wan"):
            camera_move(path, clip, seconds + FADE, shot.get("camera") or CAMERA[(n - 1) % len(CAMERA)], ffmpeg)
        clips.append({"video_url": str(clip.resolve()), "source": source, "picture": str(path)})
    return clips


def camera_move(picture, out, seconds, move="zoom_in", ffmpeg=None):
    """A slow, eased camera move over a still picture, as a 1080x1920 30 fps clip."""
    frames = int(round(seconds * 30))
    p = f"(1-cos(PI*on/{frames}))/2"  # eased progress, 0 -> 1
    big_w, big_h = WIDTH * 3, HEIGHT * 3  # move over a 3x picture, in full colour, so the motion is smooth
    center_x, center_y = "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    zoom, x, y = {
        "zoom_in": (f"1+{ZOOM}*{p}", center_x, center_y),
        "zoom_out": (f"{1 + ZOOM}-{ZOOM}*{p}", center_x, center_y),
        "pan_left": (f"{1 + ZOOM}", f"(iw-iw/zoom)*(1-{p})", center_y),
        "pan_right": (f"{1 + ZOOM}", f"(iw-iw/zoom)*{p}", center_y),
        "pan_up": (f"{1 + ZOOM}", center_x, f"(ih-ih/zoom)*(1-{p})"),
    }.get(move, (f"1+{ZOOM}*{p}", center_x, center_y))
    vf = (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h},setsar=1,format=yuv444p,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps=30,format=yuv420p"
    )
    (ffmpeg or _ffmpeg)(["-y", "-loop", "1", "-i", str(picture), "-vf", vf, "-frames:v", str(frames),
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])  # fmt: skip
    return out


def _small(path, ffmpeg=None):
    """The picture scaled to fit 512 x 512, as PNG bytes (the size the model takes as a reference)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "reference.png"
        side = REFERENCE_SIDE
        (ffmpeg or _ffmpeg)(["-y", "-i", str(path), "-vf", f"scale={side}:{side}:force_original_aspect_ratio=decrease",
                             "-frames:v", "1", str(out)])  # fmt: skip
        return out.read_bytes()


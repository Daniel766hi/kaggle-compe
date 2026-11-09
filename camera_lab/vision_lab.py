"""Vision Lab live: real-time camera tools with OpenCV.

    pip install opencv-python numpy            # required
    pip install ultralytics                    # optional: YOLO object detection (mode 1)

    python camera_lab/vision_lab.py            # webcam 0
    python camera_lab/vision_lab.py --source 1 # another camera
    python camera_lab/vision_lab.py --source video.mp4 --mode counter --headless out.mp4

Modes (press the number key while the window is open):
  1  detect    YOLO object detection if ultralytics is installed, otherwise face detection
  2  counter   count moving objects that cross the line (like a conveyor or a doorway counter)
  3  motion    background subtraction: what moves, how much of the frame, and a heat map
  4  colour    click the image to pick a colour; the largest blob of it is tracked with a trail
  5  edges     Canny edge detection
  6  cartoon   smoothed colours with inked edges
Keys: s = save a snapshot, r = reset the counter, [ and ] = move the counting line, q or Esc = quit.
"""

import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

MODES = ["detect", "counter", "motion", "colour", "edges", "cartoon"]
ACCENT = (106, 122, 11)      # BGR of the page accent
MARK = (46, 83, 226)         # BGR of the warning colour


def put_label(img, text, org, scale=0.55, color=(255, 255, 255), bg=(20, 23, 15)):
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = org
    cv2.rectangle(img, (x - 4, y - h - 6), (x + w + 4, y + base + 2), bg, -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


class Detector:
    """YOLO if available, else OpenCV's bundled frontal-face cascade."""

    def __init__(self):
        self.kind, self.model = "faces", None
        try:
            from ultralytics import YOLO  # noqa: PLC0415 - optional dependency
            self.model = YOLO("yolov8n.pt")  # downloads ~6 MB on first use
            self.kind = "yolo"
        except Exception:  # noqa: BLE001 - fall back to faces
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self.model = cv2.CascadeClassifier(path)

    def __call__(self, frame):
        """List of (label, confidence, (x, y, w, h))."""
        if self.kind == "yolo":
            out = []
            for r in self.model(frame, verbose=False):
                for box, cls, conf in zip(r.boxes.xywh.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist()):
                    cx, cy, w, h = box
                    out.append((r.names[int(cls)], conf, (int(cx - w / 2), int(cy - h / 2), int(w), int(h))))
            return out
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.model.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        return [("face", 1.0, tuple(map(int, f))) for f in faces]


class LineCounter:
    """Counts moving blobs whose centre crosses a horizontal line, with a simple nearest-centroid tracker.

    Each frame: background subtraction finds moving blobs; each blob is matched to the nearest track from
    the previous frame (within max_jump pixels). A track that moves from one side of the line to the other
    is counted once, by direction.
    """

    def __init__(self, line_frac=0.5, min_area=600, max_jump=80):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=40, detectShadows=False)
        self.line_frac, self.min_area, self.max_jump = line_frac, min_area, max_jump
        self.tracks, self.next_id = {}, 0
        self.down = self.up = 0

    def reset(self):
        self.tracks, self.down, self.up = {}, 0, 0

    def blobs(self, frame):
        mask = self.bg.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= self.min_area]

    def update(self, frame):
        h = frame.shape[0]
        line_y = int(h * self.line_frac)
        boxes = self.blobs(frame)
        centres = [(x + w / 2, y + h_ / 2) for x, y, w, h_ in boxes]
        new_tracks = {}
        free = dict(self.tracks)
        for (cx, cy), box in zip(centres, boxes):
            best, best_d = None, self.max_jump
            for tid, t in free.items():
                d = np.hypot(cx - t["c"][0], cy - t["c"][1])
                if d < best_d:
                    best, best_d = tid, d
            if best is None:
                best, self.next_id = self.next_id, self.next_id + 1
                track = {"c": (cx, cy), "counted": False}
            else:
                track = free.pop(best)
                prev_y = track["c"][1]
                if not track["counted"] and (prev_y < line_y) != (cy < line_y):
                    track["counted"] = True
                    if cy >= line_y:
                        self.down += 1
                    else:
                        self.up += 1
                track["c"] = (cx, cy)
            track["box"] = box
            new_tracks[best] = track
        self.tracks = new_tracks
        return line_y

    def draw(self, frame, line_y):
        cv2.line(frame, (0, line_y), (frame.shape[1], line_y), MARK, 2)
        for tid, t in self.tracks.items():
            x, y, w, h = t["box"]
            cv2.rectangle(frame, (x, y), (x + w, y + h), ACCENT if not t["counted"] else MARK, 2)
            cv2.circle(frame, tuple(int(v) for v in t["c"]), 4, (255, 255, 255), -1)
        put_label(frame, f"down {self.down}   up {self.up}   total {self.down + self.up}", (10, 30), 0.7)


class Lab:
    def __init__(self, mode="detect"):
        self.mode = mode
        self.detector = None
        self.counter = LineCounter()
        self.motion_bg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=32, detectShadows=False)
        self.heat = None
        self.pick_hsv, self.trail = None, deque(maxlen=60)
        self.last_frame = None

    def on_click(self, event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and self.last_frame is not None:
            patch = self.last_frame[max(0, y - 3):y + 4, max(0, x - 3):x + 4]
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).mean(axis=0)
            self.pick_hsv, self.mode = hsv, "colour"
            self.trail.clear()

    def process(self, frame):
        self.last_frame = frame.copy()
        out = frame.copy()
        if self.mode == "detect":
            self.detector = self.detector or Detector()
            for label, conf, (x, y, w, h) in self.detector(frame):
                cv2.rectangle(out, (x, y), (x + w, y + h), MARK, 2)
                put_label(out, f"{label} {conf:.0%}" if self.detector.kind == "yolo" else label, (x + 4, max(18, y - 6)))
            put_label(out, f"detector: {self.detector.kind}", (10, out.shape[0] - 12), 0.5)
        elif self.mode == "counter":
            line_y = self.counter.update(frame)
            self.counter.draw(out, line_y)
        elif self.mode == "motion":
            mask = self.motion_bg.apply(frame)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            self.heat = mask.astype(np.float32) / 255 if self.heat is None else 0.97 * self.heat + 0.03 * (mask / 255)
            heat = cv2.applyColorMap(np.uint8(255 * np.clip(self.heat * 4, 0, 1)), cv2.COLORMAP_INFERNO)
            out = cv2.addWeighted(frame, 0.6, heat, 0.4, 0)
            out[mask > 0] = (0.5 * out[mask > 0] + 0.5 * np.array(MARK)).astype(np.uint8)
            put_label(out, f"moving: {100 * (mask > 0).mean():.1f}% of the frame", (10, 30), 0.7)
        elif self.mode == "colour":
            if self.pick_hsv is None:
                put_label(out, "click the image to pick a colour", (10, 30), 0.7)
            else:
                h, s, v = self.pick_hsv
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                lo = np.array([max(0, h - 10), max(40, s - 70), max(40, v - 80)])
                hi = np.array([min(179, h + 10), 255, 255])
                mask = cv2.inRange(hsv, lo, hi)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    c = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(c) > 300:
                        (x, y), r = cv2.minEnclosingCircle(c)
                        cv2.circle(out, (int(x), int(y)), int(r), MARK, 2)
                        self.trail.appendleft((int(x), int(y)))
                for i in range(1, len(self.trail)):
                    cv2.line(out, self.trail[i - 1], self.trail[i], ACCENT, max(1, 6 - i // 10))
                put_label(out, f"colour share: {100 * (mask > 0).mean():.1f}%", (10, 30), 0.7)
        elif self.mode == "edges":
            edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0), 60, 140)
            out = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
            out[edges > 0] = (220, 255, 120)
        elif self.mode == "cartoon":
            smooth = cv2.bilateralFilter(cv2.pyrDown(frame), 9, 75, 75)
            smooth = cv2.pyrUp(smooth)[: frame.shape[0], : frame.shape[1]]
            gray = cv2.medianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 7)
            ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 4)
            out = cv2.bitwise_and(smooth, smooth, mask=ink)
        put_label(out, f"[{MODES.index(self.mode) + 1}] {self.mode}   keys 1-6, s snapshot, q quit", (10, out.shape[0] - 40), 0.45)
        return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default="0", help="camera index (0, 1, ...) or a video file")
    p.add_argument("--mode", default="detect", choices=MODES)
    p.add_argument("--headless", metavar="OUT.mp4", help="no window: process the whole source and write a video")
    args = p.parse_args()
    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Could not open {args.source!r}. Is the camera connected and not used by another app?")
    lab = Lab(args.mode)
    writer = None
    if not args.headless:
        cv2.namedWindow("Vision Lab")
        cv2.setMouseCallback("Vision Lab", lab.on_click)
    shots = Path("snapshots")
    t0, frames = time.time(), 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        out = lab.process(frame)
        frames += 1
        if args.headless:
            if writer is None:
                fps = cap.get(cv2.CAP_PROP_FPS) or 25
                writer = cv2.VideoWriter(args.headless, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out.shape[1], out.shape[0]))
            writer.write(out)
            continue
        cv2.imshow("Vision Lab", out)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if ord("1") <= key <= ord("6"):
            lab.mode = MODES[key - ord("1")]
        elif key == ord("s"):
            shots.mkdir(exist_ok=True)
            path = shots / f"vision-lab-{lab.mode}-{int(time.time())}.png"
            cv2.imwrite(str(path), out)
            print("saved", path)
        elif key == ord("r"):
            lab.counter.reset()
        elif key == ord("["):
            lab.counter.line_frac = max(0.1, lab.counter.line_frac - 0.05)
        elif key == ord("]"):
            lab.counter.line_frac = min(0.9, lab.counter.line_frac + 0.05)
    cap.release()
    if writer is not None:
        writer.release()
    if not args.headless:
        cv2.destroyAllWindows()
    print(f"{frames} frames, {frames / max(time.time() - t0, 1e-9):.1f} fps; counter: down {lab.counter.down}, up {lab.counter.up}")


if __name__ == "__main__":
    main()

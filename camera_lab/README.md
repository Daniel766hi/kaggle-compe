# Vision Lab: camera, detection and image processing

Two small tools for playing with computer vision.

## 1. Vision Lab live (Python + OpenCV, your webcam)

```
pip install opencv-python numpy
pip install ultralytics          # optional: YOLO object detection (80 kinds of objects)
python camera_lab/vision_lab.py
```

| Key | Mode | What it does |
|---|---|---|
| 1 | detect | YOLOv8 object detection with ultralytics installed, otherwise face detection |
| 2 | counter | counts moving objects crossing a line, by direction (a conveyor or doorway counter) |
| 3 | motion | background subtraction: moving share of the frame and a heat map of where motion happens |
| 4 | colour | click to pick a colour; the largest blob of that colour is tracked with a trail |
| 5 | edges | Canny edge detection |
| 6 | cartoon | bilateral-filtered colours with inked edges |

Other keys: `s` saves a snapshot to `snapshots/`, `r` resets the counter, `[` and `]` move the counting
line, `q` quits. Use `--source 1` for another camera, or `--source video.mp4 --headless out.mp4` to
process a video file without a window.

**How the counter works**: background subtraction (MOG2) finds moving blobs; each blob is matched to the
nearest blob of the previous frame; a track whose centre moves from one side of the line to the other is
counted once, as "down" or "up". It needs no AI model, so it runs fast on any laptop. It assumes objects
are separated as they cross; touching objects merge into one blob.

Tests (synthetic video, no camera needed): `pytest tests/test_camera_lab.py`.

## 2. Vision Lab web page (your phone camera)

A page that runs in the browser: take a photo or pick a sample, then
- **detect objects** with COCO-SSD (MobileNet SSD, TensorFlow.js) running on the device,
- **edges** (Sobel), **colour measurement** (tap a colour, see its share of the image),
  **cartoon** (posterize + edges) and an exposure **histogram**,
- ask Claude about the photo.

It is published as a Claude artifact; its source is `vision_lab_web.html` (the model weights are served
next to it and not stored in this repository).

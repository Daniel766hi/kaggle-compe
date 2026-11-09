"""Download the COCO-SSD lite MobileNet v2 weights (TensorFlow.js, Apache 2.0) into models/coco/.

They are about 18 MB and not stored in this repository; run this once before publishing the site.
"""
import json
import urllib.request
from pathlib import Path

BASE = "https://storage.googleapis.com/tfjs-models/savedmodel/ssdlite_mobilenet_v2/"
out = Path(__file__).parent / "models" / "coco"
out.mkdir(parents=True, exist_ok=True)
manifest = urllib.request.urlopen(BASE + "model.json").read()
(out / "model.json").write_bytes(manifest)
for group in json.loads(manifest)["weightsManifest"]:
    for name in group["paths"]:
        (out / name).write_bytes(urllib.request.urlopen(BASE + name).read())
        print("got", name)

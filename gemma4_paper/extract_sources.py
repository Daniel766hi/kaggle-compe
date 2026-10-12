"""Cache the .py sources of each task snapshot as sources/<instance_id>.json.gz.

The full snapshots are ~21 GB (they carry git history); the study only needs Python
sources. Reads snapshots straight out of the competition zip so they never hit disk:

    python gemma4_paper/extract_sources.py --zip gemma-4-developer-agent.zip --data <dir>
"""

import argparse
import gzip
import json
import zipfile
from pathlib import Path

from run_study import snapshot_sources

ap = argparse.ArgumentParser()
ap.add_argument("--zip", type=Path, required=True)
ap.add_argument("--data", type=Path, required=True)
a = ap.parse_args()
out = a.data / "sources"
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(a.zip) as z:
    names = [n for n in z.namelist() if n.startswith("snapshots/") and n.endswith(".tgz")]
    for n in names:
        iid = Path(n).name[: -len(".tgz")]
        dst = out / f"{iid}.json.gz"
        if dst.exists():
            continue
        with z.open(n) as f:
            src = snapshot_sources(f)
        dst.write_bytes(gzip.compress(json.dumps(src).encode()))
        print(iid, len(src), flush=True)

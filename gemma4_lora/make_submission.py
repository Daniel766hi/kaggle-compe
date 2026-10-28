"""Build and validate submission.zip from an agent directory, and print its files_sha256.

    python gemma4_lora/make_submission.py gemma4_paper/agent/locate --out <dir>/submission.zip

files_sha256 = sha256 of json.dumps({path: text}, sort_keys=True), the key used in Dariush Afshar's
census of public draws, so draws of identical files can be pooled. Validation uses the official
adk_submission package (install the wheelhouse wheels first).
"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("agent_dir", type=Path)
ap.add_argument("--out", type=Path, required=True)
a = ap.parse_args()
assert a.out.name == "submission.zip", "the competition only accepts a file named submission.zip"

from adk_submission import discover_declared_models, validate_directory  # noqa: E402

validate_directory(a.agent_dir)
models = sorted(discover_declared_models(a.agent_dir))
assert models == ["gemma-4-31b-it-qat-w4a16-ct"], models
files = {p.relative_to(a.agent_dir).as_posix(): p for p in sorted(a.agent_dir.rglob("*"))
         if p.is_file() and p.name not in ("SOURCE.md",) and "__pycache__" not in p.parts}
texts = {k: p.read_text() for k, p in files.items() if p.suffix != ".safetensors"}
with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
    for k, p in sorted(files.items()):
        z.write(p, k)
print("valid", models, "files", sorted(files))
print("files_sha256", hashlib.sha256(json.dumps(texts, sort_keys=True).encode()).hexdigest()[:8])
